"""
Extracteurs pour analyser les descriptions DiameX et en extraire des informations structurées
(Nom d'ouvrage, mois, montants, etc.)
"""

import re
import unicodedata
from datetime import datetime
from django.db.models import Q, Value
from django.db.models.functions import Lower, Replace
from apps.organization.models import Ouvrage, OuvrageAlias, normaliser_alias_ouvrage
from apps.billing.models import PointEau


def _normaliser_nom_ouvrage_sans_espaces(value):
    """Normalise un nom uniquement pour la comparaison, sans modifier l'affichage."""
    return normaliser_alias_ouvrage(value)


def _trouver_ouvrage_par_nom(ouvrage_nom):
    """Trouve un ouvrage même si les espaces diffèrent entre les deux noms."""
    ouvrage_nom = str(ouvrage_nom or '').strip()
    if not ouvrage_nom:
        return None

    ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
    if ouvrage:
        return ouvrage

    nom_sans_espaces = _normaliser_nom_ouvrage_sans_espaces(ouvrage_nom)
    if nom_sans_espaces:
        alias = OuvrageAlias.objects.select_related('ouvrage').filter(
            alias_normalise=nom_sans_espaces
        ).first()
        if alias:
            return alias.ouvrage

        # Mode « résolution en mémoire » (traitements de masse) : l'index connaît déjà
        # les noms d'ouvrages sans espaces, inutile de rescanner la table par écriture.
        from .resolution_memoire import ouvrage_par_nom_sans_espaces

        actif, ouvrage = ouvrage_par_nom_sans_espaces(nom_sans_espaces)
        if actif:
            if ouvrage:
                return ouvrage
        else:
            nom_base_sans_espaces = Lower(
                Replace(
                    Replace(
                        Replace('nom_ouvrage', Value(' '), Value('')),
                        Value('\t'),
                        Value(''),
                    ),
                    Value('\u00a0'),
                    Value(''),
                )
            )
            ouvrage = Ouvrage.objects.annotate(
                _nom_sans_espaces=nom_base_sans_espaces
            ).filter(_nom_sans_espaces=nom_sans_espaces).first()
            if ouvrage:
                return ouvrage

    return Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()


def _rattacher_ouvrage_reconnu(result):
    """Ajoute l'objet reconnu et restaure son nom original avec ses espaces."""
    ouvrage = result.get('ouvrage_obj')
    if ouvrage:
        result['ouvrage_nom'] = ouvrage.nom_ouvrage
        return result

    ouvrage = _trouver_ouvrage_par_nom(result.get('ouvrage_nom'))
    result['ouvrage_obj'] = ouvrage
    if ouvrage:
        result['ouvrage_nom'] = ouvrage.nom_ouvrage
    return result


def nettoyer_suffixe_paiement_volume(description):
    """Retire les suffixes de pointage ajoutes a la fin d'un libelle."""
    description_clean = str(description or '').strip()
    description_clean = re.sub(r'\s*\[.*?\]\s*$', '', description_clean).strip()
    description_clean = re.sub(r'\s*\([^()]*\)\s*$', '', description_clean).strip()
    return description_clean


def est_paiement_volume_multi(description):
    """
    Detecte les vrais paiements multi-segments.

    Dans ``Paiement ... 01/04/2026 (40;90)``, le point-virgule separe
    des numeros de releves/IDXLS et non plusieurs paiements.
    """
    return ';' in nettoyer_suffixe_paiement_volume(description)


def _trouver_point_eau_indemnite(ouvrage, idxls):
    """
    Helper pour chercher un point d'eau pour les indemnités
    Filtre par type: BF, PMH, PMHI uniquement
    Si idxls est None ou si aucun point d'eau n'est trouvé avec cet idxls,
    retourne le premier point d'eau de l'ouvrage (du bon type)

    Args:
        ouvrage: Objet Ouvrage
        idxls: Numéro IDXLS du point d'eau (peut être None)

    Returns:
        PointEau ou None
    """
    if not ouvrage:
        return None

    try:
        # Si idxls est fourni, chercher d'abord avec cet idxls
        if idxls is not None:
            point_eau = PointEau.objects.filter(
                ouvrage=ouvrage,
                idxls=idxls,
                type_point_eau__nom_type__in=['BF', 'PMH', 'PMHI']
            ).first()
            if point_eau:
                return point_eau

        # Sinon (pas d'idxls ou pas trouvé), prendre le premier point d'eau de l'ouvrage
        point_eau = PointEau.objects.filter(
            ouvrage=ouvrage,
            type_point_eau__nom_type__in=['BF', 'PMH', 'PMHI']
        ).first()
        return point_eau
    except:
        return None


def extraire_ouvrage_et_mois_paiement_volume(description):
    """
    Extrait le nom de l'ouvrage et le mois depuis une description de paiement volumétrique

    Formats supportés:
    1. Simple: "Paiement au volume [NOM_OUVRAGE] [DATE]"
    2. Multi-paiement avec ouvrage répété: "Paiement au volume Anjahambe 03/2025 9200; Anjahambe 04/2025 246500; ..."
    3. Multi-paiement avec ouvrage hérité: "Paiement au volume Anjahambe 12/2025 41400; 01/2025 24200; 02/2025 21900; ..."

    Date peut être DD/MM/YYYY, MM/YYYY ou YYYY MM

    Returns:
        - Si description simple: dict unique
        - Si multi-paiement: list de dict

        dict: {
            'ouvrage_nom': str ou None,
            'ouvrage_obj': Ouvrage ou None,
            'mois': int ou None,
            'annee': int ou None,
            'date_str': str ou None,
            'montant': float ou None (pour multi-paiement)
        }
    """
    result_template = {
        'ouvrage_nom': None,
        'ouvrage_obj': None,
        'mois': None,
        'annee': None,
        'date_str': None,
        'montant': None
    }

    if not description:
        return result_template.copy()

    # Vérifier si c'est un multi-paiement (contient des points-virgules)
    if est_paiement_volume_multi(description):
        return _extraire_multi_paiements(description)

    # Sinon, traitement simple (ancien comportement)
    return _extraire_paiement_simple(description)


def _extraire_multi_paiements(description):
    """
    Traite les descriptions avec plusieurs paiements séparés par des points-virgules

    Format 1 (ouvrage répété): "Paiement au volume Anjahambe 03/2025 9200; Anjahambe 04/2025 246500; ..."
    Format 2 (ouvrage hérité): "Paiement au volume Anjahambe 12/2025 41400; 01/2025 24200; ..."
    """
    results = []

    # Enlever le préfixe "Paiement au volume" si présent
    desc_clean = re.sub(r'^Paiement au volume\s+', '', description, flags=re.IGNORECASE).strip()

    # Séparer par point-virgule
    segments = [seg.strip() for seg in desc_clean.split(';') if seg.strip()]

    ouvrage_courant = None
    ouvrage_obj_courant = None

    for i, segment in enumerate(segments):
        result = {
            'ouvrage_nom': None,
            'ouvrage_obj': None,
            'mois': None,
            'annee': None,
            'date_str': None,
            'montant': None
        }

        # Pattern pour capturer: [Ouvrage optionnel] MM/YYYY | DD/MM/YYYY | DD/MM/YY | MM/YY + montant optionnel
        pattern_segment = r'^(?:(.+?)\s+)?(\d{2}/\d{4}|\d{2}/\d{2}/\d{2,4}|\d{2}/\d{2})(?:\s+(\d+(?:[,\s]\d+)*))?'
        match = re.match(pattern_segment, segment)

        if match:
            ouvrage_seg = match.group(1)
            date_str = match.group(2)
            montant_str = match.group(3)

            # Déterminer l'ouvrage
            if ouvrage_seg:
                # Ce segment a un nom d'ouvrage explicite
                ouvrage_courant = ouvrage_seg.strip()
                # Chercher l'ouvrage dans la base
                try:
                    ouvrage_obj_courant = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_courant).first()
                    if not ouvrage_obj_courant:
                        ouvrage_obj_courant = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_courant).first()
                except:
                    ouvrage_obj_courant = None
            # Sinon, hériter de l'ouvrage du segment précédent

            result['ouvrage_nom'] = ouvrage_courant
            result['ouvrage_obj'] = ouvrage_obj_courant

            # Parser la date
            try:
                if '/' in date_str:
                    parts = date_str.split('/')
                    if len(parts) == 2:  # MM/YYYY ou MM/YY
                        mois = int(parts[0])
                        annee = int(parts[1])
                        if annee < 100:  # convertir années à deux chiffres
                            annee = 2000 + annee if annee < 50 else 1900 + annee
                        result['mois'] = mois
                        result['annee'] = annee
                        result['date_str'] = date_str
                    elif len(parts) == 3:  # DD/MM/YYYY ou DD/MM/YY
                        fmt = '%d/%m/%Y' if len(parts[2]) == 4 else '%d/%m/%y'
                        date_obj = datetime.strptime(date_str, fmt)
                        result['mois'] = date_obj.month
                        result['annee'] = date_obj.year
                        result['date_str'] = date_str
            except ValueError:
                pass

            # Parser le montant si présent
            if montant_str:
                try:
                    montant_clean = montant_str.replace(' ', '').replace(',', '')
                    result['montant'] = float(montant_clean)
                except ValueError:
                    pass

            results.append(result)
        else:
            # Si le pattern ne matche pas, essayer de parser juste comme un nom d'ouvrage
            # (cas où le dernier segment est juste "Anjahambe" sans date ni montant)
            if segment and not any(char.isdigit() for char in segment):
                # C'est probablement juste un nom d'ouvrage en fin de description
                # On l'ignore car il ne constitue pas un paiement complet
                pass

    # Retourner la liste de résultats (ou un dict vide si aucun paiement trouvé)
    return results if results else [{'ouvrage_nom': None, 'ouvrage_obj': None, 'mois': None, 'annee': None, 'date_str': None, 'montant': None}]


def _extraire_paiement_simple(description):
    """
    Traite une description de paiement simple (ancien comportement)
    """
    result = {
        'ouvrage_nom': None,
        'ouvrage_obj': None,
        'point_eau_obj': None,
        'point_eau_idxls': None,
        'mois': None,
        'annee': None,
        'date_str': None,
        'montant': None
    }

    # Pattern 1: DD/MM/YYYY ou DD/MM/YY (avec année sur 2 ou 4 chiffres)
    pattern1 = r'Paiement au volume\s+(.+?)\s+(\d{2}/\d{2}/\d{2,4})'
    match1 = re.search(pattern1, description, re.IGNORECASE)

    if match1:
        ouvrage_nom = match1.group(1).strip()
        date_str = match1.group(2)

        # Parser la date DD/MM/YYYY ou DD/MM/YY
        try:
            if len(date_str) == 10:  # DD/MM/YYYY
                date_obj = datetime.strptime(date_str, '%d/%m/%Y')
            elif len(date_str) == 8:  # DD/MM/YY
                date_obj = datetime.strptime(date_str, '%d/%m/%y')
            else:
                raise ValueError("Format de date non reconnu")

            result['mois'] = date_obj.month
            result['annee'] = date_obj.year
            result['date_str'] = date_str
        except ValueError:
            pass

        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage dans la base
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                # Essayer une recherche partielle
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage
        except:
            pass

        return result

    # Pattern 2: YYYY MM
    pattern2 = r'Paiement au volume\s+(.+?)\s+(\d{4})\s+(\d{1,2})'
    match2 = re.search(pattern2, description, re.IGNORECASE)

    if match2:
        ouvrage_nom = match2.group(1).strip()
        annee = int(match2.group(2))
        mois = int(match2.group(3))

        result['ouvrage_nom'] = ouvrage_nom
        result['mois'] = mois
        result['annee'] = annee
        result['date_str'] = f"{annee} {mois:02d}"

        # Chercher l'ouvrage dans la base
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                # Essayer une recherche partielle
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage
        except:
            pass

        return result

    # Pattern 3: Tentative générique - prendre le texte entre "volume" et une date quelconque
    pattern3 = r'Paiement au volume\s+(.+)'
    match3 = re.search(pattern3, description, re.IGNORECASE)

    if match3:
        reste = match3.group(1).strip()

        # Chercher une date à la fin
        date_pattern = r'(\d{2}/\d{2}/\d{4})|(\d{4}\s+\d{1,2})$'
        date_match = re.search(date_pattern, reste)

        if date_match:
            # Tout ce qui est avant la date = nom de l'ouvrage
            ouvrage_nom = reste[:date_match.start()].strip()
            result['ouvrage_nom'] = ouvrage_nom

            # Chercher l'ouvrage
            try:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
                if not ouvrage:
                    ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
                result['ouvrage_obj'] = ouvrage
            except:
                pass

    if result['point_eau_idxls']:
        try:
            idxls_int = int(result['point_eau_idxls'])
            if not result['point_eau_obj']:
                point_eau = None
                if result['ouvrage_obj']:
                    point_eau = PointEau.objects.filter(
                        ouvrage=result['ouvrage_obj'],
                        idxls=idxls_int
                    ).first()
                if not point_eau:
                    point_eau = PointEau.objects.filter(idxls=idxls_int).first()
                result['point_eau_obj'] = point_eau

            if result['point_eau_obj'] and not result['ouvrage_obj'] and result['point_eau_obj'].ouvrage:
                result['ouvrage_obj'] = result['point_eau_obj'].ouvrage
                result['ouvrage_nom'] = result['ouvrage_nom'] or result['point_eau_obj'].ouvrage.nom_ouvrage
        except (ValueError, TypeError):
            pass

    return result


def extraire_ouvrage_paiement_forfaitaire(description):
    """
    Extrait le nom de l'ouvrage depuis une description de paiement forfaitaire

    Formats acceptés:
    1. "Paiement forfaitaire_U_[Quantité]_[Prix unitaire]_[NOM_OUVRAGE]"
    2. "Paiement forfaitaire_U__[Prix unitaire]_[NOM_OUVRAGE]" (double underscore)
    3. "Paiement forfaitaire_Fft_[Quantité]_[Prix]_[NOM_OUVRAGE]" (préfixe Fft)
    3b. "Paiement forfaitaire_Fft_[Prix]_[NOM_OUVRAGE]" (Fft sans quantité, 2 underscores)
    4. "Paiement forfaitaire_fft_[Prix]_[NOM_OUVRAGE]" (fft minuscule sans quantité)
    5. "Paiement forfaitaire BF[num] [NOM_OUVRAGE]" (avec code BF)
    6. "Paiement forfaitaire_[NOM_OUVRAGE]" (sans _U_)

    Exemples:
    - "Paiement forfaitaire_U_1_75000_Ambanja BP"
    - "Paiement forfaitaire_U__75000_Ambodihasina I"
    - "Paiement forfaitaire_Fft_1_200000_Manankasina"
    - "Paiement forfaitaire_Fft_50000_Ambatofanahazana Ouest PPMH"
    - "Paiement forfaitaire_fft_1250000_Ankodondona"
    - "Paiement forfaitaire_U_2_300 000_ Antanetibe" (avec espaces dans prix)
    - "__Paiement forfaitaire BF1 Anjahamarina Lovasoa___"

    Returns:
        dict: {
            'ouvrage_nom': str ou None,
            'ouvrage_obj': Ouvrage ou None,
            'quantite': int ou None,
            'prix_unitaire': float ou None,
            'mois': None (pas dans le format),
            'annee': None (pas dans le format),
            'date_str': None
        }
    """
    result = {
        'ouvrage_nom': None,
        'ouvrage_obj': None,
        'mois': None,
        'annee': None,
        'date_str': None,
        'quantite': None,
        'prix_unitaire': None,
        'info_supplementaire': {}
    }

    if not description:
        return result

    description_norm = unicodedata.normalize('NFKD', description).encode('ascii', 'ignore').decode('ascii')

    # Nettoyer les underscores en début et fin
    description_clean = description.strip('_')

    # Supprimer le texte entre crochets (ex: "[100000 split 2/2]")
    description_clean = re.sub(r'\[.*?\]', '', description_clean).strip()
    suffix_match = re.search(r'\(([^()]*)\)\s*$', description_clean)
    if suffix_match:
        raw_suffix = suffix_match.group(1).strip()
        idxls_parts = [part.strip() for part in raw_suffix.split(';') if part.strip()]
        if idxls_parts and all(part.isdigit() for part in idxls_parts):
            result['info_supplementaire']['idxls_list'] = idxls_parts

    # Supprimer le suffixe optionnel entre parenthèses
    # ex: (1;2;3)
    description_clean = re.sub(r'\s*\([^()]*\)\s*$', '', description_clean).strip()

    def clean_price(price_str):
        """Nettoie une chaîne de prix (enlève espaces, underscores)"""
        if not price_str:
            return None
        # Enlever espaces, underscores, virgules
        cleaned = price_str.replace(' ', '').replace('_', '').replace(',', '')
        try:
            return float(cleaned)
        except ValueError:
            return None

    def clean_ouvrage_name(ouvrage_str):
        """Nettoie le nom de l'ouvrage (enlève codes BF multiples)"""
        if not ouvrage_str:
            return None
        # Enlever les codes BF multiples au début (ex: "BF1,BF2,BF4_" ou "BF5_")
        # Pattern mis à jour pour gérer "BF" répété : BF1,BF2,BF4_
        cleaned = re.sub(r'^BF[\d,BF]+_', '', ouvrage_str)
        return cleaned.strip().strip('_')

    # Pattern 1: Format complet "Paiement forfaitaire_U_[Quantité]_[Prix]_[Ouvrage]"
    # Accepte espaces dans le prix: "300 000" ou "300000"
    pattern1 = r'Paiement forfaitaire_U_(\d+(?:\.\d+)?)_([\d\s]+(?:\.\d+)?)_(.+)'
    match1 = re.search(pattern1, description_clean, re.IGNORECASE)

    if match1:
        quantite_str = match1.group(1)
        prix_unitaire_str = match1.group(2)
        ouvrage_nom_raw = match1.group(3).strip().strip('_')
        ouvrage_nom = clean_ouvrage_name(ouvrage_nom_raw)

        # Parser quantité et prix (nettoyer le prix)
        try:
            result['quantite'] = int(float(quantite_str))
        except ValueError:
            pass

        prix_cleaned = clean_price(prix_unitaire_str)
        if prix_cleaned:
            result['prix_unitaire'] = prix_cleaned

        result['ouvrage_nom'] = ouvrage_nom

        return _rattacher_ouvrage_reconnu(result)

    # Pattern 2: Format avec double underscore "Paiement forfaitaire_U__[Prix]_[Ouvrage]"
    # Accepte espaces dans le prix
    pattern2 = r'Paiement forfaitaire_U__([\d\s]+(?:\.\d+)?)_(.+)'
    match2 = re.search(pattern2, description_clean, re.IGNORECASE)

    if match2:
        prix_unitaire_str = match2.group(1)
        ouvrage_nom_raw = match2.group(2).strip().strip('_')
        ouvrage_nom = clean_ouvrage_name(ouvrage_nom_raw)

        prix_cleaned = clean_price(prix_unitaire_str)
        if prix_cleaned:
            result['prix_unitaire'] = prix_cleaned

        result['ouvrage_nom'] = ouvrage_nom

        return _rattacher_ouvrage_reconnu(result)

    # Pattern 3: Format avec Fft complet "Paiement forfaitaire_Fft_[Quantité]_[Prix]_[Ouvrage]"
    pattern3 = r'Paiement forfaitaire_Fft_(\d+(?:\.\d+)?)_([\d\s]+(?:\.\d+)?)_(.+)'
    match3 = re.search(pattern3, description_clean, re.IGNORECASE)

    if match3:
        quantite_str = match3.group(1)
        prix_unitaire_str = match3.group(2)
        ouvrage_nom_raw = match3.group(3).strip().strip('_')
        ouvrage_nom = clean_ouvrage_name(ouvrage_nom_raw)

        # Parser quantité et prix
        try:
            result['quantite'] = int(float(quantite_str))
        except ValueError:
            pass

        prix_cleaned = clean_price(prix_unitaire_str)
        if prix_cleaned:
            result['prix_unitaire'] = prix_cleaned

        result['ouvrage_nom'] = ouvrage_nom

        return _rattacher_ouvrage_reconnu(result)

    # Pattern 3b: Format Fft sans quantité avec 2 underscores "Paiement forfaitaire_Fft_[Prix]_[Ouvrage]"
    # Ex: "Paiement forfaitaire_Fft_50000_Ambatofanahazana Ouest PPMH"
    # Ce pattern doit être testé AVANT le pattern 4 car plus spécifique
    pattern3b = r'Paiement forfaitaire_Fft_([\d\s]+(?:\.\d+)?)_(.+)'
    match3b = re.search(pattern3b, description_clean, re.IGNORECASE)

    if match3b:
        prix_unitaire_str = match3b.group(1)
        ouvrage_nom_raw = match3b.group(2).strip().strip('_')
        ouvrage_nom = clean_ouvrage_name(ouvrage_nom_raw)

        prix_cleaned = clean_price(prix_unitaire_str)
        if prix_cleaned:
            result['prix_unitaire'] = prix_cleaned

        result['ouvrage_nom'] = ouvrage_nom

        return _rattacher_ouvrage_reconnu(result)

    # Pattern 4: Format fft sans quantité "Paiement forfaitaire_fft_[Prix]_[Ouvrage]"
    pattern4 = r'Paiement forfaitaire_fft_([\d\s]+(?:\.\d+)?)_(.+)'
    match4 = re.search(pattern4, description_clean, re.IGNORECASE)

    if match4:
        prix_unitaire_str = match4.group(1)
        ouvrage_nom_raw = match4.group(2).strip().strip('_')
        ouvrage_nom = clean_ouvrage_name(ouvrage_nom_raw)

        prix_cleaned = clean_price(prix_unitaire_str)
        if prix_cleaned:
            result['prix_unitaire'] = prix_cleaned

        result['ouvrage_nom'] = ouvrage_nom

        return _rattacher_ouvrage_reconnu(result)

    # Pattern 5a: Format avec codes BF multiples underscore "Paiement forfaitaire BF[codes]_[Ouvrage]"
    # Ex: "Paiement forfaitaire BF1,BF2,BF4_Antanetipatara" ou "Paiement forfaitaire BF5_Antanetipatara"
    pattern5a = r'Paiement forfaitaire\s+BF[\d,]+_(.+)'
    match5a = re.search(pattern5a, description_clean, re.IGNORECASE)

    if match5a:
        ouvrage_nom_raw = match5a.group(1).strip().strip('_')
        ouvrage_nom = clean_ouvrage_name(ouvrage_nom_raw)
        result['ouvrage_nom'] = ouvrage_nom

        return _rattacher_ouvrage_reconnu(result)

    # Pattern 5b: Format avec code BF espace "Paiement forfaitaire BF[num] [Ouvrage]"
    pattern5b = r'Paiement forfaitaire\s+BF\d+\s+(.+)'
    match5b = re.search(pattern5b, description_clean, re.IGNORECASE)

    if match5b:
        ouvrage_nom_raw = match5b.group(1).strip().strip('_')
        ouvrage_nom = clean_ouvrage_name(ouvrage_nom_raw)
        result['ouvrage_nom'] = ouvrage_nom

        return _rattacher_ouvrage_reconnu(result)

    # Pattern 6: Format simple "Paiement forfaitaire_[Ouvrage]" ou "Paiement forfaitaire [Ouvrage]"
    pattern6 = r'Paiement forfaitaire[_\s]+(.+)'
    match6 = re.search(pattern6, description_clean, re.IGNORECASE)

    if match6:
        ouvrage_nom_raw = match6.group(1).strip().strip('_')
        ouvrage_nom = clean_ouvrage_name(ouvrage_nom_raw)
        result['ouvrage_nom'] = ouvrage_nom

        return _rattacher_ouvrage_reconnu(result)

    return result


def extraire_ouvrage_cartes_sociales(description):
    """
    Extrait le nom de l'ouvrage et la date depuis une description de cartes sociales

    Formats acceptés:
    - "Cartes sociales [OUVRAGE] [DD/MM/YYYY]" (format standard)
    - "Cartes sociales [OUVRAGE] conso [DD/MM/YYYY]" (ancien format avec "conso")

    Exemples:
    - "Cartes sociales Ambato 01/11/2025"
    - "Cartes sociales Ambanja BP conso 15/03/2025"

    Returns:
        dict: {
            'ouvrage_nom': str ou None,
            'ouvrage_obj': Ouvrage ou None,
            'mois': int ou None,
            'annee': int ou None,
            'date_str': str ou None
        }
    """
    result = {
        'ouvrage_nom': None,
        'ouvrage_obj': None,
        'mois': None,
        'annee': None,
        'date_str': None
    }

    if not description:
        return result

    # Essayer d'abord le format standard: "Cartes sociales [Ouvrage] [DD/MM/YYYY]"
    pattern_standard = r'Cartes sociales\s+(.+?)\s+(\d{2}/\d{2}/\d{4})'
    match = re.search(pattern_standard, description, re.IGNORECASE)

    # Si ça ne fonctionne pas, essayer l'ancien format avec "conso"
    if not match:
        pattern_conso = r'Cartes sociales\s+(.+?)\s+consos?\s+(\d{2}/\d{2}/\d{4})'
        match = re.search(pattern_conso, description, re.IGNORECASE)

    if match:
        ouvrage_nom = match.group(1).strip()
        date_str = match.group(2)

        # Parser la date DD/MM/YYYY
        try:
            date_obj = datetime.strptime(date_str, '%d/%m/%Y')
            result['mois'] = date_obj.month
            result['annee'] = date_obj.year
            result['date_str'] = date_str
        except ValueError:
            pass

        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage dans la base
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                # Essayer une recherche partielle
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage
        except:
            pass

    return result


def extraire_installation_bp_bf(description):
    """
    Extrait l'ouvrage et l'IDxls depuis une description d'installation BP/BF

    Formats acceptés:
    - "[Type paiement]_[IDxls]_[Ouvrage]" (sans nom de personne)
    - "_[Nom personne]_[Type paiement]_[IDxls]_[Ouvrage]" (avec nom de personne)
    - Accepte BP et BF
    - Ignore le texte entre crochets [...]

    Exemples:
    - "Paiement demande devis installation BP_78_Vohipeno"
    - "_RAVAOJANAHARY Hanta_Paiement pour installation BP_01_Antsahafilo"
    - "_NABABANY_Paiement pour installation BF_5_Maroaomby"
    - "Paiement pour installation BP_81_Vohipeno [facilité de paiement]"

    Returns:
        dict: {
            'ouvrage_nom': str ou None,
            'ouvrage_obj': Ouvrage ou None,
            'point_eau_idxls': str ou None,
            'point_eau_obj': PointEau ou None,
            'mois': None,
            'annee': None,
            'date_str': None
        }
    """
    from apps.billing.models import PointEau

    result = {
        'ouvrage_nom': None,
        'ouvrage_obj': None,
        'point_eau_idxls': None,
        'point_eau_obj': None,
        'mois': None,
        'annee': None,
        'date_str': None
    }

    if not description:
        return result

    # Nettoyer le texte entre crochets (ex: [facilité de paiement])
    # Pattern: tout ce qui est entre [ et ] (inclus)
    description_clean = re.sub(r'\s*\[.*?\]\s*', ' ', description).strip()

    # Format avec nom sans underscore initial :
    # [Nom abonne]_Paiement pour devis installation BP_[IDXls]_[Ouvrage]
    # L'ouvrage et l'IDXls sont lus depuis les deux derniers segments.
    pattern_pour_devis = (
        r'^[^_]+_Paiement\s+pour\s+devis\s+installation\s+B[PF]'
        r'_(\d+)_([^_]+)$'
    )
    match_pour_devis = re.match(pattern_pour_devis, description_clean, re.IGNORECASE)
    if match_pour_devis:
        idxls = match_pour_devis.group(1).strip()
        ouvrage_nom = match_pour_devis.group(2).strip()
        result['point_eau_idxls'] = idxls
        result['ouvrage_nom'] = ouvrage_nom

        try:
            ouvrage_obj = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage_obj:
                ouvrage_obj = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage_obj

            if ouvrage_obj:
                result['point_eau_obj'] = PointEau.objects.filter(
                    ouvrage=ouvrage_obj,
                    idxls=int(idxls),
                ).first()
            else:
                result['point_eau_obj'] = PointEau.objects.filter(idxls=int(idxls)).first()
        except Exception:
            pass

        return result

    parts = description_clean.split('_')

    # Détection du format selon si commence par underscore
    if description.startswith('_'):
        # Format avec nom: _[Nom]_[Type]_[IDxls]_[Ouvrage]
        if len(parts) >= 4:
            # parts[1] = Nom personne
            # parts[2] = Type paiement
            # parts[3] = IDxls ou Ouvrage
            # parts[4] = Ouvrage (si existe)

            idxls = ''
            ouvrage_nom = ''

            if len(parts) >= 5:
                # Format complet avec IDxls et Ouvrage
                idxls = parts[3].strip()
                ouvrage_nom = parts[4].strip()
            else:
                # Seulement 4 parties: parts[3] peut être IDxls ou Ouvrage
                identifiant = parts[3].strip()
                if identifiant.isdigit():
                    idxls = identifiant
                    ouvrage_nom = ''
                else:
                    idxls = ''
                    ouvrage_nom = identifiant

            # ÉTAPE 1: Chercher l'ouvrage d'abord
            ouvrage_obj = None
            if ouvrage_nom:
                result['ouvrage_nom'] = ouvrage_nom
                try:
                    ouvrage_obj = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
                    if not ouvrage_obj:
                        ouvrage_obj = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
                    result['ouvrage_obj'] = ouvrage_obj
                except:
                    pass

            # ÉTAPE 2: Chercher le point d'eau DANS cet ouvrage (si trouvé)
            if idxls:
                result['point_eau_idxls'] = idxls
                try:
                    # Si on a trouvé l'ouvrage, filtrer par ouvrage ET idxls
                    if ouvrage_obj:
                        pe = PointEau.objects.filter(
                            ouvrage=ouvrage_obj,
                            idxls=int(idxls)
                        ).first()
                    else:
                        # Sinon, chercher juste par IDxls
                        pe = PointEau.objects.filter(idxls=int(idxls)).first()
                        # Et récupérer l'ouvrage depuis le PE
                        if pe and not ouvrage_nom:
                            ouvrage_nom = pe.ouvrage.nom_ouvrage if pe.ouvrage else ''
                            result['ouvrage_nom'] = ouvrage_nom
                            result['ouvrage_obj'] = pe.ouvrage

                    result['point_eau_obj'] = pe
                except:
                    pass

    else:
        # Format sans underscore initial. Deux variantes possibles:
        # - [Type]_[IDxls]_[Ouvrage] (sans nom de personne)
        # - [Nom personne]_[Type]_[IDxls]_[Ouvrage] (avec nom de personne)
        # Règle: le nom de l'ouvrage est toujours après le dernier underscore.
        # Le segment "Type paiement" est repéré par le mot-clé "Paiement"/"Paiment"
        # pour distinguer un éventuel nom de personne placé avant.
        idxls = ''
        ouvrage_nom = ''

        if len(parts) < 2:
            return result

        # Chercher l'index du segment "Type paiement" (contient "paiement"/"paiment")
        type_index = None
        for i, part in enumerate(parts[:-1]):
            if re.search(r'paiem?ent', part, re.IGNORECASE):
                type_index = i
                break

        if type_index is not None:
            reste = parts[type_index + 1:]
            if len(reste) >= 2:
                idxls = reste[0].strip()
                ouvrage_nom = reste[-1].strip()
            elif len(reste) == 1:
                identifiant = reste[0].strip()
                if identifiant.isdigit():
                    idxls = identifiant
                else:
                    ouvrage_nom = identifiant
        elif len(parts) >= 3:
            idxls = parts[1].strip()
            ouvrage_nom = parts[2].strip()
        else:
            # Seulement 2 parties: parts[1] peut être IDxls ou Ouvrage
            identifiant = parts[1].strip()
            if identifiant.isdigit():
                idxls = identifiant
                ouvrage_nom = ''
            else:
                idxls = ''
                ouvrage_nom = identifiant

        # ÉTAPE 1: Chercher l'ouvrage d'abord
        ouvrage_obj = None
        if ouvrage_nom:
            result['ouvrage_nom'] = ouvrage_nom
            try:
                ouvrage_obj = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
                if not ouvrage_obj:
                    ouvrage_obj = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
                result['ouvrage_obj'] = ouvrage_obj
            except:
                pass

        # ÉTAPE 2: Chercher le point d'eau DANS cet ouvrage (si trouvé)
        if idxls:
            result['point_eau_idxls'] = idxls
            try:
                # Si on a trouvé l'ouvrage, filtrer par ouvrage ET idxls
                if ouvrage_obj:
                    pe = PointEau.objects.filter(
                        ouvrage=ouvrage_obj,
                        idxls=int(idxls)
                    ).first()
                else:
                    # Sinon, chercher juste par IDxls
                    pe = PointEau.objects.filter(idxls=int(idxls)).first()
                    # Et récupérer l'ouvrage depuis le PE
                    if pe and not ouvrage_nom:
                        ouvrage_nom = pe.ouvrage.nom_ouvrage if pe.ouvrage else ''
                        result['ouvrage_nom'] = ouvrage_nom
                        result['ouvrage_obj'] = pe.ouvrage

                result['point_eau_obj'] = pe
            except:
                pass

    return result


def extraire_indemnite_rbf_ppmh(description):
    """
    Extrait le point d'eau et l'ouvrage depuis une description d'indemnité RBF/PPMH/BF

    Formats attendus:
    - "..._Indemnité RBF[IDxls] [année]_..._[montant]_[NOM_OUVRAGE]" (nouveau format)
    - "..._Indemnité RBF[IDxls]_..._Ar [NOM_OUVRAGE]"
    - "..._Nettoyage BF[IDxls]_..._[montant]_[NOM_OUVRAGE]"
    - "..._Indemnité PPMH_..._Ar [NOM_OUVRAGE]"

    Exemples:
    - "MANARIASA Daniel_Indemnité RBF2 2025_Fft_20000_Ambodiampaly / Analambahy" (nouveau)
    - "_RAVELONIRINA Herisoa_Indemnité RBF1_Trimestre_Fft_5000_Ar Andranobe"
    - "RAMIADANA Francelette_Nettoyage BF3_Fft_20000_Vohipenohely"
    - "_RAZAFINDRAVAO Marie Pierrette_Indemnité PPMH_Trimestre_5000_Ar Ambohijatovo PPMH"

    Returns:
        dict: {
            'ouvrage_nom': str ou None,
            'ouvrage_obj': Ouvrage ou None,
            'point_eau_idxls': str ou None (ex: "1", "2", "3" pour RBF1, BF3, etc.),
            'point_eau_obj': PointEau ou None,
            'type_indemnite': str ou None ('RBF', 'BF' ou 'PPMH'),
            'mois': None,
            'annee': None,
            'date_str': None
        }
    """
    from apps.billing.models import PointEau

    result = {
        'ouvrage_nom': None,
        'ouvrage_obj': None,
        'point_eau_idxls': None,
        'point_eau_obj': None,
        'type_indemnite': None,
        'mois': None,
        'annee': None,
        'date_str': None
    }

    if not description:
        return result

    # Pattern 0a (NOUVEAU): Indemnité RBF[numéro] [année]_..._pour gestion [OUVRAGE]
    # Ex: "LIEN SONINA_Indemnité RBF3 2025_Fft_20000_pour gestion Ampasimbola Ampasina Maningory"
    # Le nom de l'ouvrage vient après "pour gestion"
    # Les annotations entre crochets sont informatives et ne participent pas
    # a l'identification du point d'eau (ex. "[RBF3]").
    description = re.sub(r'\s*\[[^\]]*\]', '', str(description)).strip()

    # Format court : Indemnite RBF[numero]_[OUVRAGE]
    # Ex: "_TSIMANAMBOHO Franclin_Indemnite RBF2_Ambalabe [RBF3]"
    pattern_rbf_court = r'Indemnit(?:é|e)\s+RBF(\d+)_([^_]+)$'
    match_rbf_court = re.search(pattern_rbf_court, description, re.IGNORECASE)

    if match_rbf_court:
        idxls = match_rbf_court.group(1)
        ouvrage_nom = match_rbf_court.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            if ouvrage:
                result['point_eau_obj'] = _trouver_point_eau_indemnite(ouvrage, idxls)
        except Exception:
            pass

        return result

    pattern_rbf_pour_gestion = r'Indemnité\s+RBF(\d+)\s+\d{4}.*pour\s+gestion\s+(.+)$'
    match_rbf_pour_gestion = re.search(pattern_rbf_pour_gestion, description, re.IGNORECASE)

    if match_rbf_pour_gestion:
        idxls = match_rbf_pour_gestion.group(1)  # Le numéro après RBF
        ouvrage_nom = match_rbf_pour_gestion.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 0a1: Indemnité RBF[numéro]_[info année]_[OUVRAGE]
    # Ex: "_RAZAFINDRAFINDRA Zafrine_Indemnité RBF7_2025 et 2024_Vohitrantsotry"
    # L'ouvrage vient après le dernier underscore (après l'information d'année)
    # DOIT être testé AVANT Pattern 0b (plus spécifique - avec info année complexe)
    pattern_rbf_annee_info = r'Indemnité\s+RBF(\d+)_([^_]+)_(.+)$'
    match_rbf_annee_info = re.search(pattern_rbf_annee_info, description, re.IGNORECASE)

    if match_rbf_annee_info:
        idxls = match_rbf_annee_info.group(1)  # Le numéro après RBF
        annee_info = match_rbf_annee_info.group(2).strip()  # L'info d'année (ex: "2025 et 2024")
        ouvrage_nom = match_rbf_annee_info.group(3).strip()  # Le nom après le dernier underscore

        # Vérifier que l'info d'année contient bien des chiffres (année)
        # et que le nom d'ouvrage ne commence pas par des chiffres seuls (montant)
        if re.search(r'\d{4}', annee_info) and not re.match(r'^\d+$', ouvrage_nom):
            result['point_eau_idxls'] = idxls
            result['type_indemnite'] = 'RBF'
            result['ouvrage_nom'] = ouvrage_nom

            # Chercher l'ouvrage
            try:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
                if not ouvrage:
                    ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
                result['ouvrage_obj'] = ouvrage

                # Chercher le point d'eau par IDxls ET ouvrage
                if ouvrage:
                    point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                    result['point_eau_obj'] = point_eau
            except:
                pass

            return result

    # Pattern 0b (NOUVEAU): Indemnité RBF[numéro] [année]_..._[montant]_[OUVRAGE]
    # Ex: "MANARIASA Daniel_Indemnité RBF2 2025_Fft_20000_Ambodiampaly / Analambahy"
    # Le nom de l'ouvrage vient après le dernier underscore
    pattern_rbf_nouveau = r'Indemnité\s+RBF(\d+)\s+\d{4}.*_(\d+)_(.+)$'
    match_rbf_nouveau = re.search(pattern_rbf_nouveau, description, re.IGNORECASE)

    if match_rbf_nouveau:
        idxls = match_rbf_nouveau.group(1)  # Le numéro après RBF
        ouvrage_nom = match_rbf_nouveau.group(3).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1: Indemnité RBF[numéro]_..._Ar [OUVRAGE]
    # Ex: "_RAVELONIRINA Herisoa_Indemnité RBF1_Trimestre_Fft_5000_Ar Andranobe"
    pattern_rbf = r'Indemnité\s+RBF(\d+).*?_Ar\s+(.+?)(?:\s+(?:PPMH|RBF).*)?$'
    match_rbf = re.search(pattern_rbf, description, re.IGNORECASE)

    if match_rbf:
        idxls = match_rbf.group(1)  # Le numéro après RBF
        ouvrage_nom = match_rbf.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a0: Indemnité RBF[numéro]_..._[montant]_[année] [OUVRAGE]
    # Ex: "FILAVANA Laurence_Indemnité RBF5_Fft_20000_2025 Lohariana"
    # L'année vient après le montant, l'ouvrage après l'année (avec espace)
    # DOIT être testé AVANT Pattern 1a (plus spécifique)
    pattern_rbf_annee_apres = r'Indemnité\s+RBF(\d+).*?_\d+_\d{4}\s+(.+)$'
    match_rbf_annee_apres = re.search(pattern_rbf_annee_apres, description, re.IGNORECASE)

    if match_rbf_annee_apres:
        idxls = match_rbf_annee_apres.group(1)
        ouvrage_nom = match_rbf_annee_apres.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a-mixte: Indemnité RBF[numéro]_U_[num]_[montant]_[OUVRAGE]
    # Ex: "_RAHARIMASITIARAY Mahefasoa Bako_Indemnité RBF2_U_1_5000_Antsahafilo"
    # Format mixte RBF[n]_U_[n], l'ouvrage vient après le dernier underscore
    # DOIT être testé AVANT Pattern 1a (plus spécifique)
    pattern_rbf_mixte = r'Indemnité\s+RBF(\d+)_U_\d+_\d+_(.+)$'
    match_rbf_mixte = re.search(pattern_rbf_mixte, description, re.IGNORECASE)

    if match_rbf_mixte:
        idxls = match_rbf_mixte.group(1)  # Premier numéro après RBF
        ouvrage_nom = match_rbf_mixte.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a: Indemnité RBF[numéro]_..._[montant]_[OUVRAGE] (sans Ar)
    # Ex: "_RIMILIARISOA Soloherinarindra_Indemnité RBF5_Fft_5000_Rangaina"
    pattern_rbf_sans_ar = r'Indemnité\s+RBF(\d+).*?_(\d+)_(.+)$'
    match_rbf_sans_ar = re.search(pattern_rbf_sans_ar, description, re.IGNORECASE)

    if match_rbf_sans_ar:
        idxls = match_rbf_sans_ar.group(1)
        ouvrage_nom = match_rbf_sans_ar.group(3).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a2b: Indemnité RBF_U_[montant]_x [num] pour RBF[num] [année] [OUVRAGE]
    # Ex: "_VAVY Pelagie_Indemnite RBF_U_20000_x 1 pour RBF1 2024 Behalo"
    # L'ouvrage vient après le dernier chiffre (année)
    # DOIT être testé AVANT Pattern 1a2 (plus spécifique)
    pattern_rbf_u_x_pour = r'Indemni[té]e?\s+RBF_U_(\d+)_x\s+\d+\s+pour\s+RBF\d+\s+(\d{4})\s+(.+)$'
    match_rbf_u_x_pour = re.search(pattern_rbf_u_x_pour, description, re.IGNORECASE)

    if match_rbf_u_x_pour:
        annee = match_rbf_u_x_pour.group(2)
        ouvrage_nom = match_rbf_u_x_pour.group(3).strip()

        # Pas d'idxls explicite dans ce format
        result['point_eau_idxls'] = None
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Prendre le premier point d'eau de l'ouvrage (pas d'idxls)
            if ouvrage:
                from apps.billing.models import PointEau
                point_eau = PointEau.objects.filter(
                    ouvrage=ouvrage,
                    type_point_eau__nom_type__in=['BF', 'PMH', 'PMHI']
                ).first()
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a2: Indemnité RBF_U_[numéro]_[montant]_[OUVRAGE]
    # Ex: "Indemnité RBF_U_1_20000_Ambatoharanana Mandiamanga"
    # Ex: "Indemnite RBF_U_5_20000_Ambolofotsy" (sans accent)
    pattern_rbf_u = r'Indemnit[ée]\s+RBF_U_(\d+)_(\d+)_(.+)$'
    match_rbf_u = re.search(pattern_rbf_u, description, re.IGNORECASE)

    if match_rbf_u:
        idxls = match_rbf_u.group(1)
        ouvrage_nom = match_rbf_u.group(3).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a2b: Indemnité savon_U_[idxls]_[montant]_[OUVRAGE]
    # Ex: "_JOHNNY Arson_Indemnité savon_U_3_1500_Ambatoharanana Miarinarivo"
    # Format avec montant entre idxls et ouvrage
    pattern_savon_u_montant = r'Indemnit[ée]\s+savon_U_(\d+)_\d+_(.+)$'
    match_savon_u_montant = re.search(pattern_savon_u_montant, description, re.IGNORECASE)

    if match_savon_u_montant:
        idxls = match_savon_u_montant.group(1)
        ouvrage_nom = match_savon_u_montant.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'  # Considéré comme RBF car format _U_
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a2c: Indemnité savon_U_[idxls]_[OUVRAGE]
    # Ex: "_BETANY Narcisse_Indemnité savon_U_2_Vohibaribe"
    # Format simplifié sans montant ni RBF
    pattern_savon_u = r'Indemnit[ée]\s+savon_U_(\d+)_(.+)$'
    match_savon_u = re.search(pattern_savon_u, description, re.IGNORECASE)

    if match_savon_u:
        idxls = match_savon_u.group(1)
        ouvrage_nom = match_savon_u.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'  # Considéré comme RBF car format _U_
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a2d: Savon_U_[idxls]_[montant]_[OUVRAGE] (sans "Indemnité")
    # Ex: "Savon_U_3_1500_Ambatoharanana I"
    # Format court sans le mot "Indemnité" au début
    pattern_savon_u_court = r'^[^_]*_?Savon_U_(\d+)_\d+_(.+)$'
    match_savon_u_court = re.search(pattern_savon_u_court, description, re.IGNORECASE)

    if match_savon_u_court:
        idxls = match_savon_u_court.group(1)
        ouvrage_nom = match_savon_u_court.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'  # Considéré comme RBF car format _U_
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a3: Indemnité RB[numéro]_U_[numéro]_[montant]_[OUVRAGE] (sans F dans RB)
    # Ex: "_RAZAFINDRATSIMBA Bodo Harimanitra_Indemnité RB1_U_1_5000_Manankasina"
    pattern_rb_u = r'Indemnité\s+RB(\d+)_U_\d+_(\d+)_(.+)$'
    match_rb_u = re.search(pattern_rb_u, description, re.IGNORECASE)

    if match_rb_u:
        idxls = match_rb_u.group(1)
        ouvrage_nom = match_rb_u.group(3).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'  # On traite RB comme RBF
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a4: Indemnité RBF[num]_[OUVRAGE] (format simple)
    # Ex: "_Albert_Indemnité RBF1_Ambalahady"
    # Ex: "DADA Robert_Indemnité RBF3_Fft_Ampasimbola/Andilamena"
    # Format simple avec code optionnel (Fft, etc.)
    pattern_rbf_simple = r'Indemnit[ée]\s+RBF(\d+)_(?:[A-Za-z]{2,4}_)?(.+)$'
    match_rbf_simple = re.search(pattern_rbf_simple, description, re.IGNORECASE)

    if match_rbf_simple:
        idxls = match_rbf_simple.group(1)
        ouvrage_nom = match_rbf_simple.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a3: Indemnité RBF_[année]_[OUVRAGE]
    # Ex: "_AH et RBF_Indemnité RBF_2025_Andraidraika"
    # Format avec année SANS mois avant le nom de l'ouvrage
    # IMPORTANT: Ce pattern doit être testé AVANT Pattern 1a4 (année + mois)
    pattern_rbf_annee = r'Indemnit[ée]\s+RBF_(\d{4})_(.+)$'
    match_rbf_annee = re.search(pattern_rbf_annee, description, re.IGNORECASE)

    # Vérifier que ce n'est PAS un format avec mois (éviter d'attraper "2025 03_Imongy")
    if match_rbf_annee:
        annee_str = match_rbf_annee.group(1)
        reste = match_rbf_annee.group(2).strip()

        # S'assurer qu'il n'y a PAS de mois (nombre à 2 chiffres suivi de underscore)
        # Ex: "2025 03_Imongy" → a un mois, donc skip
        if not re.match(r'^\d{2}_', reste):
            annee = int(annee_str)
            ouvrage_nom = reste

            result['point_eau_idxls'] = None  # Pas de numéro
            result['type_indemnite'] = 'RBF'
            result['ouvrage_nom'] = ouvrage_nom
            result['annee'] = annee

            # Chercher l'ouvrage
            try:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
                if not ouvrage:
                    ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
                result['ouvrage_obj'] = ouvrage

                # Pas d'IDXLS, prendre le premier point d'eau de l'ouvrage
                if ouvrage:
                    point_eau = _trouver_point_eau_indemnite(ouvrage, None)
                    result['point_eau_obj'] = point_eau
            except:
                pass

            return result

    # Pattern 1a4: Indemnité RBF_[année] [mois]_[OUVRAGE]
    # Ex: "_AH et RBF_Indemnité RBF_2025 03_Imongy"
    # Format avec année et mois avant le nom de l'ouvrage
    pattern_rbf_annee_mois = r'Indemnit[ée]\s+RBF_(\d{4})\s+(\d{2})_(.+)$'
    match_rbf_annee_mois = re.search(pattern_rbf_annee_mois, description, re.IGNORECASE)

    if match_rbf_annee_mois:
        annee = int(match_rbf_annee_mois.group(1))
        mois = int(match_rbf_annee_mois.group(2))
        ouvrage_nom = match_rbf_annee_mois.group(3).strip()

        result['point_eau_idxls'] = None  # Pas de numéro
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom
        result['annee'] = annee
        result['mois'] = mois

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pas d'IDXLS, prendre le premier point d'eau de l'ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, None)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1a5: Indemnité RBF_[OUVRAGE] (sans numéro)
    # Ex: "_RAZAFY Emilienne_Indemnité RBF_Antsahalava"
    # Format très simple sans numéro RBF
    pattern_rbf_sans_num = r'Indemnit[ée]\s+RBF_(.+)$'
    match_rbf_sans_num = re.search(pattern_rbf_sans_num, description, re.IGNORECASE)

    if match_rbf_sans_num:
        ouvrage_nom = match_rbf_sans_num.group(1).strip()

        result['point_eau_idxls'] = None  # Pas de numéro
        result['type_indemnite'] = 'RBF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pas d'IDXLS, prendre le premier point d'eau de l'ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, None)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1b0aa: Indemnité RBF___indemnité de savon BF[num] [année]..._[OUVRAGE]
    # Ex: "_RAMIARINARIVO Dorisse_Indemnité RBF___indemnité de savon BF1 2025_Ampasimbola/Andilamena"
    # Ex: "_IARILINE_Indemnité RBF___indemnité de savon BF1 2025 et collecte RBF1 2024_Vohitrantsotry"
    # Format complexe avec triple underscore, année et texte optionnel
    # DOIT être testé AVANT Pattern 1b0a (plus spécifique)
    pattern_rbf_savon_bf = r'Indemnit[ée]\s+RBF___indemnit[ée]\s+de\s+savon\s+BF(\d+)\s+\d{4}.*?_([^_]+)$'
    match_rbf_savon_bf = re.search(pattern_rbf_savon_bf, description, re.IGNORECASE)

    if match_rbf_savon_bf:
        idxls = match_rbf_savon_bf.group(1)
        ouvrage_nom = match_rbf_savon_bf.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'BF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1b0a: Indemnité de savon BF[numéro]_..._[montant]_[OUVRAGE]
    # Ex: "_NICOLAS_Indemnité de savon BF2_Fft_20000_Ambinanindranomena"
    # Sans "pour gestion", l'ouvrage vient après le dernier underscore
    # DOIT être testé AVANT Pattern 1b0 (plus spécifique - sans "pour gestion")
    pattern_bf_savon_simple = r'Indemnit[eé]\s+de\s+[Ss]avon\s+BF(\d+).*?_(\d+)_(.+)$'
    match_bf_savon_simple = re.search(pattern_bf_savon_simple, description, re.IGNORECASE)

    if match_bf_savon_simple:
        idxls = match_bf_savon_simple.group(1)
        ouvrage_nom = match_bf_savon_simple.group(3).strip()

        # Vérifier que l'ouvrage ne contient PAS "pour gestion"
        # Si c'est le cas, ce n'est pas le bon pattern
        if 'pour gestion' not in ouvrage_nom.lower():
            result['point_eau_idxls'] = idxls
            result['type_indemnite'] = 'BF'
            result['ouvrage_nom'] = ouvrage_nom

            # Chercher l'ouvrage
            try:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
                if not ouvrage:
                    ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
                result['ouvrage_obj'] = ouvrage

                # Chercher le point d'eau par IDxls ET ouvrage
                if ouvrage:
                    point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                    result['point_eau_obj'] = point_eau
            except:
                pass

            return result

    # Pattern 1b0: Indemnité de Savon BF[numéro]_..._pour gestion [OUVRAGE]
    # Ex: "_RANDRIANTSARA Serges_Indemnité de Savon BF2_Fft_20000_pour gestion Vohipenohely"
    # Ex: "_SAHANTA Sella_Indemnité de SavonBF5_Fft_20000_pour gestion Vohipenohely"
    # Ex: "_VELONDIZY Florine_Indemnité de Savon BF1_Fft_20000_pour gestion Ambalatenina Nord"
    # Support avec ou sans espace après "Savon"
    # DOIT être testé AVANT Pattern 1b (plus spécifique)
    pattern_bf_savon_pour_gestion = r'Indemnit[eé]\s+de\s+Savon\s*BF(\d+).*?_\d+_pour\s+gestion\s+(.+)$'
    match_bf_savon_pour_gestion = re.search(pattern_bf_savon_pour_gestion, description, re.IGNORECASE)

    if match_bf_savon_pour_gestion:
        idxls = match_bf_savon_pour_gestion.group(1)
        ouvrage_nom = match_bf_savon_pour_gestion.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'BF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1b0b: Nettoyage BF[numéro]_..._Ar[_| ]x [num] pour gestion [OUVRAGE]
    # Ex: "_RASOARIMANANA Herivololona_Nettoyage BF2_Trimestre_5000_Ar x 3 pour gestion Tsarasaotra"
    # Ex: "_RASOARIMALALA Nirina_Nettoyage BF3_Trimestre_5000_Ar_x 2 pour gestion Ambohimanatrika"
    # Avec multiplicateur "x [num]" (avec ou sans underscore avant x) et sans "la" avant gestion
    # DOIT être testé AVANT Pattern 1b (plus spécifique)
    pattern_bf_ar_x_pour_gestion = r'Nettoyage\s+BF(\d+).*?_\d+_Ar[_\s]+x\s+\d+\s+pour\s+gestion\s+(.+)$'
    match_bf_ar_x_pour_gestion = re.search(pattern_bf_ar_x_pour_gestion, description, re.IGNORECASE)

    if match_bf_ar_x_pour_gestion:
        idxls = match_bf_ar_x_pour_gestion.group(1)
        ouvrage_nom = match_bf_ar_x_pour_gestion.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'BF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1b: Nettoyage BF[numéro]_..._Ar pour la gestion [OUVRAGE]
    # Ex: "_RATOANDROARILALA Nirina Rova_Nettoyage BF6_Fft_5000_Ar pour la gestion Rangaina"
    pattern_bf_pour_gestion = r'Nettoyage\s+BF(\d+).*?_Ar\s+pour\s+la\s+gestion\s+(.+)$'
    match_bf_pour_gestion = re.search(pattern_bf_pour_gestion, description, re.IGNORECASE)

    if match_bf_pour_gestion:
        idxls = match_bf_pour_gestion.group(1)
        ouvrage_nom = match_bf_pour_gestion.group(2).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'BF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1b1a: Nettoyage BF[numéro]_..._[montant]_[année]_[OUVRAGE]
    # Ex: "_INDRIANDAHY_Nettoyage BF2_Fft_20000_2025_Ambatolongo"
    # L'ouvrage vient après le dernier underscore (après l'année à 4 chiffres)
    # DOIT être testé AVANT Pattern 1b2 (plus spécifique - avec année)
    pattern_bf_annee = r'Nettoyage\s+BF(\d+).*?_(\d+)_(\d{4})_(.+)$'
    match_bf_annee = re.search(pattern_bf_annee, description, re.IGNORECASE)

    if match_bf_annee:
        idxls = match_bf_annee.group(1)  # Le numéro après BF
        annee = match_bf_annee.group(3)  # L'année (2025)
        ouvrage_nom = match_bf_annee.group(4).strip()  # Le nom après l'année

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'BF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1b2: Nettoyage BF[numéro]_..._[montant]_[OUVRAGE]
    # Ex: "RAMIADANA Francelette_Nettoyage BF3_Fft_20000_Vohipenohely"
    # Ex: "_RAKOTORATSIMAMANGA Alfred_Nettoyage BF3_Trimestre_5000_Ar_Mahitsitady"
    # Le nom de l'ouvrage vient après le dernier underscore (en ignorant "Ar_" si présent)
    pattern_bf = r'Nettoyage\s+BF(\d+).*?_(\d+)_(?:Ar_)?(.+)$'
    match_bf = re.search(pattern_bf, description, re.IGNORECASE)

    if match_bf:
        idxls = match_bf.group(1)  # Le numéro après BF
        ouvrage_nom = match_bf.group(3).strip()  # group(3) car (?:Ar_)? est non-capturant

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'BF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1b2a: Nettoyage BF[numéro]_[OUVRAGE] (sans montant)
    # Ex: "_RAMIADANA Francelette_Nettoyage BF3_Vohipenohely"
    # Ex: "_RAVOLOLONIRINA Harimalala Lydia_Nettoyage BF2_Anjohy"
    # Format simplifié : Nettoyage BF suivi d'un numéro, puis underscore et nom ouvrage
    # DOIT être testé AVANT Pattern 1b3 (plus spécifique - avec numéro)
    pattern_bf_simple = r'Nettoyage\s+BF(\d+)_([^_]+)$'
    match_bf_simple = re.search(pattern_bf_simple, description, re.IGNORECASE)

    if match_bf_simple:
        idxls = match_bf_simple.group(1)  # Le numéro après BF
        ouvrage_nom = match_bf_simple.group(2).strip()  # Le nom après l'underscore

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'BF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par IDxls ET ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, idxls)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1b3: Nettoyage BF_[OUVRAGE] (sans numéro)
    # Ex: "_TOMILAHY_Nettoyage BF_Ambalafary Mahambo"
    # Format simple sans numéro BF, donc pas d'IDXLS
    pattern_bf_sans_num = r'Nettoyage\s+BF_(.+)$'
    match_bf_sans_num = re.search(pattern_bf_sans_num, description, re.IGNORECASE)

    if match_bf_sans_num:
        ouvrage_nom = match_bf_sans_num.group(1).strip()

        result['point_eau_idxls'] = None  # Pas de numéro
        result['type_indemnite'] = 'BF'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pas d'IDXLS, donc prendre le premier point d'eau de l'ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, None)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1b4: Indemnité savon_[OUVRAGE] (format très simple)
    # Ex: "_GAIRA Augistin_Indemnité savon_Ambinanisakoana"
    # Sans "de", sans BF, sans numéro - format générique
    # DOIT être testé APRÈS tous les autres patterns savon (fallback)
    pattern_savon_generique = r'Indemnit[ée]\s+savon_(.+)$'
    match_savon_generique = re.search(pattern_savon_generique, description, re.IGNORECASE)

    if match_savon_generique:
        ouvrage_nom = match_savon_generique.group(1).strip()

        result['point_eau_idxls'] = None  # Pas de numéro
        result['type_indemnite'] = 'PE'  # Type générique
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pas d'IDXLS, prendre le premier point d'eau de l'ouvrage
            if ouvrage:
                point_eau = _trouver_point_eau_indemnite(ouvrage, None)
                result['point_eau_obj'] = point_eau
        except:
            pass

        return result

    # Pattern 1c0: Nettoyage PMH/PPMH_..._Ar_pour gestion [OUVRAGE]
    # Ex: "_RAZAFINDRAVAO Marie Pierrette_Nettoyage PMH_Trimestre_5000_Ar_pour gestion Ambohijatovo PPMH"
    # Support PMH ou PPMH (PMH sera traité comme PPMH)
    # DOIT être testé AVANT Pattern 1c (plus spécifique)
    pattern_nettoyage_pmh_pour_gestion = r'Nettoyage\s+P{1,2}MH.*?_\d+_(?:Ar_)?pour\s+gestion\s+(.+)$'
    match_nettoyage_pmh_pour_gestion = re.search(pattern_nettoyage_pmh_pour_gestion, description, re.IGNORECASE)

    if match_nettoyage_pmh_pour_gestion:
        ouvrage_nom = match_nettoyage_pmh_pour_gestion.group(1).strip()

        result['type_indemnite'] = 'PPMH'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pour PPMH, récupérer automatiquement le point d'eau s'il n'y en a qu'un seul
            if ouvrage:
                points_eau = PointEau.objects.filter(ouvrage=ouvrage)
                if points_eau.count() == 1:
                    result['point_eau_obj'] = points_eau.first()
        except:
            pass

        return result

    # Pattern 1c_U: Indemnité PPMH_U_[num1]_[num2]_[OUVRAGE]
    # Ex: "_RAVONIARIMANANA Lucie_Indemnité PPMH_U_1_5000_Ampetsapetsa PPMH2"
    # Format avec _U_ suivi de numéros, le nom de l'ouvrage est après le dernier underscore
    # DOIT être testé AVANT Pattern 1c (plus spécifique - avec _U_)
    pattern_ppmh_u = r'Indemnité\s+PPMH_U_\d+_\d+_(.+)$'
    match_ppmh_u = re.search(pattern_ppmh_u, description, re.IGNORECASE)

    if match_ppmh_u:
        ouvrage_nom = match_ppmh_u.group(1).strip()

        result['type_indemnite'] = 'PPMH'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pour PPMH, récupérer automatiquement le point d'eau s'il n'y en a qu'un seul
            if ouvrage:
                points_eau = PointEau.objects.filter(ouvrage=ouvrage)
                if points_eau.count() == 1:
                    result['point_eau_obj'] = points_eau.first()
        except:
            pass

        return result

    # Pattern 1c: Indemnité PPMH_..._[année] pour gestion [OUVRAGE]
    # Ex: "_VE Dolin_Indemnité PPMH_Fft_20000_2025 pour gestion Amboditononona 2"
    pattern_ppmh_pour_gestion = r'Indemnité\s+PPMH.*?_\d{4}\s+pour\s+gestion\s+(.+)$'
    match_ppmh_pour_gestion = re.search(pattern_ppmh_pour_gestion, description, re.IGNORECASE)

    if match_ppmh_pour_gestion:
        ouvrage_nom = match_ppmh_pour_gestion.group(1).strip()

        result['type_indemnite'] = 'PPMH'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pour PPMH, récupérer automatiquement le point d'eau s'il n'y en a qu'un seul
            if ouvrage:
                points_eau = PointEau.objects.filter(ouvrage=ouvrage)
                if points_eau.count() == 1:
                    result['point_eau_obj'] = points_eau.first()
        except:
            pass

        return result

    # Pattern 1d: Indemnité FPMH/PPMH_[année]_[OUVRAGE]
    # Ex: "_MARTHE Linda_Indemnité FPMH_2025_Andraoka FPMH1"
    # L'ouvrage vient après le dernier underscore (après l'année)
    pattern_ppmh_annee = r'Indemnité\s+(?:F?P{1,2}MH)_(\d{4})_(.+)$'
    match_ppmh_annee = re.search(pattern_ppmh_annee, description, re.IGNORECASE)

    if match_ppmh_annee:
        annee = match_ppmh_annee.group(1)  # L'année (2025)
        ouvrage_nom = match_ppmh_annee.group(2).strip()

        result['type_indemnite'] = 'PPMH'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pour PPMH, récupérer automatiquement le point d'eau s'il n'y en a qu'un seul
            if ouvrage:
                points_eau = PointEau.objects.filter(ouvrage=ouvrage)
                if points_eau.count() == 1:
                    result['point_eau_obj'] = points_eau.first()
        except:
            pass

        return result

    # Pattern 1e: Indemnité PPMH_[OUVRAGE] (format simple direct)
    # Ex: "_RAZAFINDRAVAO Pierette_Indemnité PPMH_Ambohijatovo PPMH"
    # L'ouvrage vient directement après PPMH_ sans année ni montant
    # DOIT être testé AVANT Pattern 2 (plus spécifique - sans montant)
    pattern_ppmh_simple = r'Indemnité\s+(?:F?P{1,2}MH)_([A-Za-zÀ-ÿ0-9\s\-_\']+?)(?:\s+(?:F?P{1,2}MH).*)?$'
    match_ppmh_simple = re.search(pattern_ppmh_simple, description, re.IGNORECASE)

    if match_ppmh_simple:
        ouvrage_nom_raw = match_ppmh_simple.group(1).strip()

        # Vérifier que ce n'est pas un format avec montant (ex: "Trimestre_5000")
        # Si contient underscore + chiffres, ce n'est probablement pas le bon pattern
        if not re.search(r'_\d{3,}', ouvrage_nom_raw):
            ouvrage_nom = ouvrage_nom_raw

            result['type_indemnite'] = 'PPMH'
            result['ouvrage_nom'] = ouvrage_nom

            # Chercher l'ouvrage
            try:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
                if not ouvrage:
                    ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
                result['ouvrage_obj'] = ouvrage

                # Pour PPMH, récupérer automatiquement le point d'eau s'il n'y en a qu'un seul
                if ouvrage:
                    points_eau = PointEau.objects.filter(ouvrage=ouvrage)
                    if points_eau.count() == 1:
                        result['point_eau_obj'] = points_eau.first()
            except:
                pass

            return result

    # Pattern 2: Indemnité PPMH_..._[montant]_Ar [OUVRAGE]
    # Ex: "_RAZAFINDRAVAO Marie Pierrette_Indemnité PPMH_Trimestre_5000_Ar Ambohijatovo PPMH"
    pattern_ppmh_ar = r'Indemnité\s+PPMH.*?_\d+_Ar\s+(.+?)(?:\s+PPMH.*)?$'
    match_ppmh_ar = re.search(pattern_ppmh_ar, description, re.IGNORECASE)

    if match_ppmh_ar:
        ouvrage_nom = match_ppmh_ar.group(1).strip()

        result['type_indemnite'] = 'PPMH'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pour PPMH, récupérer automatiquement le point d'eau s'il n'y en a qu'un seul
            if ouvrage:
                points_eau = PointEau.objects.filter(ouvrage=ouvrage)
                if points_eau.count() == 1:
                    result['point_eau_obj'] = points_eau.first()
        except:
            pass

        return result

    # Pattern 3: Indemnité PPMH_..._[montant]_[OUVRAGE] (sans Ar)
    # Ex: "_RAMASIARIMANANA Blandine_Indemnité PPMH_Fft_5000_Ambatofanahazana PPMH"
    pattern_ppmh = r'Indemnité\s+PPMH.*?_(\d+)_(.+?)(?:\s+PPMH.*)?$'
    match_ppmh = re.search(pattern_ppmh, description, re.IGNORECASE)

    if match_ppmh:
        ouvrage_nom = match_ppmh.group(2).strip()

        result['type_indemnite'] = 'PPMH'
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pour PPMH, récupérer automatiquement le point d'eau s'il n'y en a qu'un seul
            if ouvrage:
                points_eau = PointEau.objects.filter(ouvrage=ouvrage)
                if points_eau.count() == 1:
                    result['point_eau_obj'] = points_eau.first()
        except:
            pass

        return result

    # Pattern GÉNÉRIQUE avec "pour gestion": [Texte]_..._pour gestion [OUVRAGE]
    # Pour les lignes génériques sans type explicite mais avec "pour gestion"
    # Ex: "_BRIDO_Savon_Fft_20000_pour gestion Vohipenohely"
    # DOIT être testé AVANT le pattern générique standard
    pattern_generique_pour_gestion = r'^[^_]*_([^_]+)_.*?_\d+_pour\s+gestion\s+(.+)$'
    match_generique_pour_gestion = re.search(pattern_generique_pour_gestion, description, re.IGNORECASE)

    if match_generique_pour_gestion:
        type_designation = match_generique_pour_gestion.group(1).strip()  # Ex: "Savon", "Nettoyage"
        ouvrage_nom = match_generique_pour_gestion.group(2).strip()

        result['type_indemnite'] = 'PE'  # Type générique Point d'Eau
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Pas d'idxls disponible dans ce format, donc pas de recherche point_eau
        except:
            pass

        return result

    # Pattern GÉNÉRIQUE (fallback): [Texte]_U_[numéro]_[montant]_[OUVRAGE]
    # Pour les lignes sans type explicite (RBF, PPMH, BF)
    # Ex: "Savon_U_4_1500_Ambinanimbakoanina"
    # Le nom de l'ouvrage est après le dernier underscore
    pattern_generique_u = r'_U_(\d+)_(\d+)_(.+)$'
    match_generique_u = re.search(pattern_generique_u, description, re.IGNORECASE)

    if match_generique_u:
        idxls = match_generique_u.group(1)
        ouvrage_nom = match_generique_u.group(3).strip()

        result['point_eau_idxls'] = idxls
        result['type_indemnite'] = 'PE'  # Type générique Point d'Eau
        result['ouvrage_nom'] = ouvrage_nom

        # Chercher l'ouvrage
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()
            result['ouvrage_obj'] = ouvrage

            # Chercher le point d'eau par idxls
            if ouvrage:
                try:
                    point_eau = _trouver_point_eau_indemnite(ouvrage, int(idxls))
                    result['point_eau_obj'] = point_eau
                except:
                    pass
        except:
            pass

        return result

    return result


def extraire_indemnite_hors_zone(description):
    """
    Extrait l'identité, le calcul et le reste d'une description d'indemnité hors zone
    Exemple: "_ADMIN TOTO Olivianne Wenda_Indemnité hors zone_4 x 30000 Ar_du 16 au 19/12/25 pour formation Tanà"
    """
    result = {
        'ouvrage_nom': None,
        'ouvrage_obj': None,
        'mois': None,
        'annee': None,
        'date_str': None,
        'info_supplementaire': {}
    }

    if not description:
        return result

    # Pattern flexible pour capturer l'identité, le type, le calcul et le reste
    pattern = r'^_?(.*?)_?(Indemnit[ée]\s+(?:hors\s+zone|terrain))_+(.*?)_+(.*)$'
    match = re.search(pattern, description, re.IGNORECASE)

    if match:
        result['info_supplementaire']['identité'] = match.group(1).strip()
        result['info_supplementaire']['type_indemnité'] = match.group(2).strip()
        result['info_supplementaire']['calcul'] = match.group(3).strip()
        result['info_supplementaire']['reste'] = match.group(4).strip()
        
        # Essayer d'extraire une date du reste (format du 16 au 19/12/25)
        date_pattern = r'(\d{2}/\d{2}/\d{2,4})'
        date_match = re.search(date_pattern, result['info_supplementaire']['reste'])
        if date_match:
            result['date_str'] = date_match.group(1)
            try:
                # Si date au format DD/MM/YY (8 chars)
                if len(result['date_str']) == 8:
                    d = datetime.strptime(result['date_str'], '%d/%m/%y')
                    result['mois'] = d.month
                    result['annee'] = d.year
                elif len(result['date_str']) == 10: # DD/MM/YYYY
                    d = datetime.strptime(result['date_str'], '%d/%m/%Y')
                    result['mois'] = d.month
                    result['annee'] = d.year
            except:
                pass
    else:
        # Pattern simple
        pattern_simple = r'^_?(.*?)_?(Indemnit[ée]\s+(?:hors\s+zone|terrain))_+(.*)$'
        match_simple = re.search(pattern_simple, description, re.IGNORECASE)
        if match_simple:
            result['info_supplementaire']['identité'] = match_simple.group(1).strip()
            result['info_supplementaire']['type_indemnité'] = match_simple.group(2).strip()
            result['info_supplementaire']['calcul'] = match_simple.group(3).strip()

    return result


def extraire_remise_eau_descente_bp(description):
    """
    Extrait l'ouvrage et l'IDxls depuis une description de paiement remise en eau ou descente BP
    
    Formats acceptés (compte 761000):
    1. _[Nom (facultatif)]_Paiement remise en eau_[IDxls (facultatif)]_[Nom ouvrage]
    2. _[Nom]_Paiement descente BP_[IDxls]_[Nom ouvrage]
    
    Exemples:
    - "_Dupont_Paiement remise en eau_123_Antsahatanteraka"
    - "_Paiement remise en eau_456_Ambohimanga"
    - "_Martin_Paiement descente BP_789_Anjahambe"
    
    Returns:
        dict: {
            'ouvrage_nom': str ou None,
            'ouvrage_obj': Ouvrage ou None,
            'point_eau_idxls': str ou None,
            'point_eau_obj': PointEau ou None,
            'type_paiement': str ou None ('remise_eau' ou 'descente_bp'),
            'nom_personne': str ou None,
            'mois': None,
            'annee': None,
            'date_str': None
        }
    """
    result = {
        'ouvrage_nom': None,
        'ouvrage_obj': None,
        'point_eau_idxls': None,
        'point_eau_obj': None,
        'type_paiement': None,
        'nom_personne': None,
        'mois': None,
        'annee': None,
        'date_str': None,
        'info_supplementaire': {}
    }
    
    if not description:
        return result

    description_clean = re.sub(r'\s*\[.*?\]\s*', ' ', description).strip()
    description_norm = unicodedata.normalize('NFKD', description_clean).encode('ascii', 'ignore').decode('ascii')

    def _parse_from_underscore_tail(raw_description):
        """
        Fallback robuste:
        - l'ouvrage est le segment apres le dernier underscore
        - l'IDxls est le segment numerique juste avant
        """
        cleaned = (raw_description or '').strip().strip('_')
        if not cleaned or '_' not in cleaned:
            return None

        parts = [part.strip() for part in cleaned.split('_') if part.strip()]
        if len(parts) < 2:
            return None

        ouvrage_nom = parts[-1]
        idxls = parts[-2] if parts[-2].isdigit() else None
        prefix_parts = parts[:-2] if idxls else parts[:-1]
        if not prefix_parts:
            return None

        nom_personne = None
        type_parts = prefix_parts
        if 'paiement' not in prefix_parts[0].lower():
            nom_personne = prefix_parts[0]
            type_parts = prefix_parts[1:]

        type_label = ' '.join(type_parts).strip()
        if not type_label:
            return None

        type_label_norm = unicodedata.normalize('NFKD', type_label).encode('ascii', 'ignore').decode('ascii').lower()

        type_paiement = None
        type_display = None
        if 'paiement remise en eau' in type_label_norm:
            type_paiement = 'remise_eau'
            type_display = 'Remise en eau'
        elif 'paiement descente bp' in type_label_norm:
            type_paiement = 'descente_bp'
            type_display = 'Descente BP'
        elif 'paiement reclamation compteur bp' in type_label_norm:
            type_paiement = 'reclamation_compteur'
            type_display = 'Reclamation compteur'

        if not type_paiement:
            return None

        return {
            'ouvrage_nom': ouvrage_nom or None,
            'point_eau_idxls': idxls,
            'nom_personne': nom_personne,
            'type_paiement': type_paiement,
            'type_display': type_display,
        }

    # Pattern 1: Paiement remise en eau
    # Format: _[Nom (facultatif)]_Paiement remise en eau_[IDxls (facultatif)]_[Nom ouvrage]
    # Note: "Paiement remise en eau" peut avoir des espaces ou des underscores
    pattern_remise_eau = r'(?:_([^_]+))?_Paiement[ _]remise[ _]en[ _]eau_([^_]*)_([^_]+)$'
    match_remise = re.search(pattern_remise_eau, description_clean, re.IGNORECASE)
    
    if match_remise:
        result['nom_personne'] = match_remise.group(1).strip() if match_remise.group(1) else None
        result['point_eau_idxls'] = match_remise.group(2) if match_remise.group(2) else None
        result['ouvrage_nom'] = match_remise.group(3).strip() if match_remise.group(3) else None
        result['type_paiement'] = 'remise_eau'
        result['info_supplementaire']['type_display'] = 'Remise en eau'
    else:
        # Pattern 2: Paiement descente BP
        # Format: _[Nom]_Paiement descente BP_[IDxls]_[Nom ouvrage]
        # Note: "Paiement descente BP" peut avoir des espaces ou des underscores
        pattern_descente_bp = r'(?:_([^_]+))?_Paiement[ _]descente[ _]BP_([^_]*)_([^_]+)$'
        match_descente = re.search(pattern_descente_bp, description_clean, re.IGNORECASE)
        
        if match_descente:
            result['nom_personne'] = match_descente.group(1).strip() if match_descente.group(1) else None
            result['point_eau_idxls'] = match_descente.group(2) if match_descente.group(2) else None
            result['ouvrage_nom'] = match_descente.group(3).strip() if match_descente.group(3) else None
            result['type_paiement'] = 'descente_bp'
            result['info_supplementaire']['type_display'] = 'Descente BP'
        else:
            # Pattern 3: Paiement réclamation compteur BP
            # Format: _[Nom]_Paiement réclamation compteur BP_[IDxls]_[Nom ouvrage]
            pattern_reclam = r'(?:_([^_]+))?_Paiement[ _]r[e\u00e9]clamation[ _]compteur[ _]BP_([^_]*)_([^_]+)$'
            match_reclam = re.search(pattern_reclam, description_clean, re.IGNORECASE)
            if not match_reclam and description_norm != description_clean:
                match_reclam = re.search(pattern_reclam, description_norm, re.IGNORECASE)
            
            if match_reclam:
                result['nom_personne'] = match_reclam.group(1).strip() if match_reclam.group(1) else None
                result['point_eau_idxls'] = match_reclam.group(2) if match_reclam.group(2) else None
                result['ouvrage_nom'] = match_reclam.group(3).strip() if match_reclam.group(3) else None
                result['type_paiement'] = 'reclamation_compteur'
                result['info_supplementaire']['type_display'] = 'Réclamation compteur'
    
    
                if not result['ouvrage_nom']:
                    match_bp = re.search(r'BP[_-]?([0-9]+)[_ -]?([A-Za-z0-9-]+)', description_clean)
                    if match_bp:
                        result['point_eau_idxls'] = result['point_eau_idxls'] or match_bp.group(1)
                        result['ouvrage_nom'] = match_bp.group(2).replace('_', ' ').strip()

    parsed_tail = _parse_from_underscore_tail(description_clean)
    if parsed_tail:
        if not result['ouvrage_nom']:
            result['ouvrage_nom'] = parsed_tail['ouvrage_nom']
        if not result['point_eau_idxls']:
            result['point_eau_idxls'] = parsed_tail['point_eau_idxls']
        if not result['nom_personne']:
            result['nom_personne'] = parsed_tail['nom_personne']
        if not result['type_paiement']:
            result['type_paiement'] = parsed_tail['type_paiement']
        if parsed_tail['type_display'] and not result['info_supplementaire'].get('type_display'):
            result['info_supplementaire']['type_display'] = parsed_tail['type_display']

    if not result['ouvrage_nom']:
        if re.search(r'reclamation', description_norm, re.IGNORECASE) and re.search(r'compteur', description_norm, re.IGNORECASE):
            match_bp = re.search(r'BP[_-]?([0-9]+)[_ -]?([A-Za-z0-9-]+)', description_norm)
            if match_bp:
                result['point_eau_idxls'] = result['point_eau_idxls'] or match_bp.group(1)
                result['ouvrage_nom'] = match_bp.group(2).replace('_', ' ').strip()

    # Si un ouvrage a été extrait, chercher dans la base de données
    if result['ouvrage_nom']:
        try:
            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=result['ouvrage_nom']).first()
            if not ouvrage:
                ouvrage = Ouvrage.objects.filter(nom_ouvrage__icontains=result['ouvrage_nom']).first()
            result['ouvrage_obj'] = ouvrage
            
            # Si on a trouvé l'ouvrage et un IDxls, chercher le point d'eau
            if ouvrage and result['point_eau_idxls']:
                try:
                    idxls_int = int(result['point_eau_idxls'])
                    point_eau = PointEau.objects.filter(
                        ouvrage=ouvrage,
                        idxls=idxls_int
                    ).first()
                    if not point_eau:
                        # Fallback: chercher par idxls seul
                        point_eau = PointEau.objects.filter(idxls=idxls_int).first()
                    result['point_eau_obj'] = point_eau
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass

    if result['point_eau_idxls']:
        try:
            idxls_int = int(result['point_eau_idxls'])
            if not result['point_eau_obj']:
                point_eau = None
                if result['ouvrage_obj']:
                    point_eau = PointEau.objects.filter(
                        ouvrage=result['ouvrage_obj'],
                        idxls=idxls_int
                    ).first()
                if not point_eau:
                    point_eau = PointEau.objects.filter(idxls=idxls_int).first()
                result['point_eau_obj'] = point_eau

            if result['point_eau_obj'] and not result['ouvrage_obj'] and result['point_eau_obj'].ouvrage:
                result['ouvrage_obj'] = result['point_eau_obj'].ouvrage
                result['ouvrage_nom'] = result['ouvrage_nom'] or result['point_eau_obj'].ouvrage.nom_ouvrage
        except (ValueError, TypeError):
            pass

    return result


def extraire_nom_abonne_underscore(description):
    """Extrait le nom d'abonne place autour du premier underscore."""
    description_clean = str(description or '').strip()
    if '_' not in description_clean:
        return None

    segments = description_clean.split('_')
    segment_index = 1 if description_clean.startswith('_') else 0
    if segment_index >= len(segments):
        return None
    return segments[segment_index].strip() or None


def enrichir_point_eau_par_nom_abonne(description, extraction):
    """Complete une extraction avec le point d'eau trouve par nom d'abonne."""
    if not isinstance(extraction, dict):
        return extraction

    nom_abonne = extraire_nom_abonne_underscore(description)
    if not nom_abonne:
        return extraction

    extraction['point_eau_nom_extrait'] = nom_abonne
    if extraction.get('point_eau_obj'):
        extraction['point_eau_nom'] = nom_abonne
        return extraction

    extraction['point_eau_nom'] = nom_abonne
    points_eau = PointEau.objects.all()
    ouvrage = extraction.get('ouvrage_obj')

    point_eau = None
    if ouvrage:
        point_eau = points_eau.filter(
            ouvrage=ouvrage,
            nomabonne__iexact=nom_abonne,
        ).first()
        if not point_eau:
            point_eau = points_eau.filter(
                ouvrage=ouvrage,
                code_point_eau__iexact=nom_abonne,
            ).first()

    if not point_eau:
        point_eau = points_eau.filter(nomabonne__iexact=nom_abonne).first()
    if not point_eau:
        point_eau = points_eau.filter(code_point_eau__iexact=nom_abonne).first()

    if point_eau:
        extraction['point_eau_obj'] = point_eau
        extraction['point_eau_idxls'] = point_eau.idxls
        extraction['point_eau_nom'] = point_eau.nomabonne or nom_abonne
        if not extraction.get('ouvrage_obj') and point_eau.ouvrage:
            extraction['ouvrage_obj'] = point_eau.ouvrage
            extraction['ouvrage_nom'] = point_eau.ouvrage.nom_ouvrage

    return extraction


def extraire_ouvrage_et_mois_generique(description, compte_code):
    """
    Extraction générique pour différents types de comptes
    À adapter selon les formats spécifiques de chaque compte

    Returns:
        dict: {
            'ouvrage_nom': str ou None,
            'ouvrage_obj': Ouvrage ou None,
            'mois': int ou None,
            'annee': int ou None,
            'info_supplementaire': dict
        }
    """
    result = {
        'ouvrage_nom': None,
        'ouvrage_obj': None,
        'mois': None,
        'annee': None,
        'date_str': None,
        'info_supplementaire': {}
    }

    extraction = result

    # Pour le compte 707401 (Paiement au volume)
    if compte_code == '707401':
        extraction = extraire_ouvrage_et_mois_paiement_volume(description)

    # Pour le compte 748411 (Paiement forfaitaire)
    elif compte_code == '748411':
        extraction = extraire_ouvrage_paiement_forfaitaire(description)

    # Pour le compte 748415 (Cartes sociales)
    elif compte_code == '748415':
        extraction = extraire_ouvrage_cartes_sociales(description)

    # Pour le compte 748201 (Installation BP/BF)
    elif compte_code == '748201':
        extraction = extraire_installation_bp_bf(description)

    # Pour le compte 621102 (Indemnité RBF/PPMH)
    elif compte_code == '621102':
        extraction = extraire_indemnite_rbf_ppmh(description)

    # Pour le compte 625107 (Indemnité Hors zone / Terrain)
    elif compte_code == '625107':
        extraction = extraire_indemnite_hors_zone(description)

    # Pour les comptes 761000/761002 (Paiement remise en eau / Paiement descente BP)
    elif compte_code in ('761000', '761002'):
        extraction = extraire_remise_eau_descente_bp(description)

    # TODO: Ajouter d'autres extracteurs selon les comptes
    # Exemple pour compte X: extraire_format_X(description)

    def finaliser(item):
        if isinstance(item, dict) and item.get('ouvrage_nom'):
            item = _rattacher_ouvrage_reconnu(item)
        return enrichir_point_eau_par_nom_abonne(description, item)

    if isinstance(extraction, list):
        return [finaliser(item) for item in extraction]
    return finaliser(extraction)


def tester_extracteur():
    """
    Fonction de test pour vérifier les extracteurs
    """
    test_cases = [
        "Paiement au volume Ambanja BP 01/03/2025",
        "Paiement au volume Nosy Be Kiosque 15/12/2024",
        "Paiement au volume Antsiranana Centre 2025 03",
        "Paiement au volume Site Test 2024 11",
    ]

    for desc in test_cases:
        result = extraire_ouvrage_et_mois_paiement_volume(desc)
        print(f"\nDescription: {desc}")
        print(f"Ouvrage: {result['ouvrage_nom']}")
        print(f"Trouvé: {result['ouvrage_obj'].nom_ouvrage if result['ouvrage_obj'] else 'NON'}")
        print(f"Mois: {result['mois']}, Année: {result['annee']}")


def extraire_point_eau_generique(description, compte_code=None):
    """
    Extrait le point d'eau depuis une description DiameX générique

    Formats possibles:
    - "Indemnité [NOM_POINT_EAU] [DATE]"
    - "Indemnités [NOM_POINT_EAU] [DATE]"
    - "[NOM_POINT_EAU] indemnité [DATE]"
    - Etc.

    Returns:
        dict: {
            'point_eau_nom': str ou None,
            'point_eau_obj': PointEau ou None,
            'extraction_reussie': bool
        }
    """
    from apps.billing.models import PointEau

    result = {
        'point_eau_nom': None,
        'point_eau_obj': None,
        'extraction_reussie': False
    }

    if not description:
        return result

    # Nettoyer la description
    desc_clean = description.strip()

    # Stratégie 1: Chercher pattern "Indemnit[éeès]+ [NOM_PE]"
    pattern1 = r'indemni[tT][éeès]+\s+([A-Za-zÀ-ÿ0-9\s\-_\']+?)(?:\s+\d{2}/\d{2}/\d{4}|\s+\d{4}\s+\d{2}|$)'
    match1 = re.search(pattern1, desc_clean, re.IGNORECASE)

    if match1:
        nom_extrait = match1.group(1).strip()
        # Nettoyer le nom (enlever mots-clés)
        nom_extrait = re.sub(r'\b(indemnite|indemnites|paiement|forfait|forfaitaire)\b', '', nom_extrait, flags=re.IGNORECASE).strip()

        if nom_extrait:
            result['point_eau_nom'] = nom_extrait

            # Chercher le point d'eau correspondant
            # Essayer d'abord par nomabonne
            pe = PointEau.objects.filter(nomabonne__iexact=nom_extrait).first()

            if not pe:
                # Essayer avec code_point_eau
                pe = PointEau.objects.filter(code_point_eau__iexact=nom_extrait).first()

            if not pe:
                # Recherche floue (contient)
                pe = PointEau.objects.filter(nomabonne__icontains=nom_extrait).first()

            if pe:
                result['point_eau_obj'] = pe
                result['extraction_reussie'] = True

    # Stratégie 2: Si pas trouvé, chercher pattern "[NOM_PE] indemn"
    if not result['extraction_reussie']:
        pattern2 = r'^([A-Za-zÀ-ÿ0-9\s\-_\']+?)\s+indemn'
        match2 = re.search(pattern2, desc_clean, re.IGNORECASE)

        if match2:
            nom_extrait = match2.group(1).strip()
            result['point_eau_nom'] = nom_extrait

            # Chercher le point d'eau
            pe = PointEau.objects.filter(
                Q(nomabonne__iexact=nom_extrait) |
                Q(code_point_eau__iexact=nom_extrait) |
                Q(nomabonne__icontains=nom_extrait)
            ).first()

            if pe:
                result['point_eau_obj'] = pe
                result['extraction_reussie'] = True

    return result


def generer_suggestions_reformulation(description):
    """
    Génère des suggestions de reformulation pour aider l'utilisateur
    à saisir des descriptions compatibles avec l'algorithme d'extraction.

    Analyse le contenu de la description et propose 1 à 3 formats
    qui pourraient fonctionner avec l'algorithme.

    Args:
        description: La description à analyser

    Returns:
        Liste de dictionnaires avec 'format' et 'exemple'
        Maximum 3 suggestions, ordonnées par pertinence
    """
    suggestions = []

    if not description:
        return suggestions

    desc_lower = description.lower()

    # Détecter les mots-clés
    has_rbf = 'rbf' in desc_lower
    has_bf = 'bf' in desc_lower and 'rbf' not in desc_lower
    has_pmh = 'pmh' in desc_lower
    has_savon = 'savon' in desc_lower
    has_nettoyage = 'nettoyage' in desc_lower
    has_indemnite = 'indemn' in desc_lower
    has_u = '_u_' in desc_lower or ' u ' in desc_lower

    # Détecter la présence de chiffres (potentiellement IDXLS)
    has_digits = any(char.isdigit() for char in description)

    # Suggérer formats RBF
    if has_rbf or (has_indemnite and not has_bf):
        if has_u and has_digits:
            suggestions.append({
                'format': 'Indemnité RBF_U_[numéro]_[montant]_[Ouvrage]',
                'exemple': 'Indemnité RBF_U_5_20000_Ambinanisalohy'
            })
        elif has_digits:
            suggestions.append({
                'format': 'Indemnité RBF[numéro]_[Ouvrage]',
                'exemple': 'Indemnité RBF1_Ambalahady'
            })
        else:
            suggestions.append({
                'format': 'Indemnité RBF_[Ouvrage]',
                'exemple': 'Indemnité RBF_Antsahalava'
            })

    # Suggérer formats BF savon
    if (has_bf and has_savon) or (has_savon and not has_rbf):
        if 'pour gestion' in desc_lower:
            suggestions.append({
                'format': 'Indemnité de Savon BF[num]_[code]_[montant]_pour gestion [Ouvrage]',
                'exemple': 'Indemnité de Savon BF1_Fft_20000_pour gestion Ambalatenina Nord'
            })
        elif has_u:
            suggestions.append({
                'format': 'Indemnité savon_U_[numéro]_[Ouvrage]',
                'exemple': 'Indemnité savon_U_2_Vohibaribe'
            })
        elif has_digits:
            suggestions.append({
                'format': 'Indemnité de savon BF[num]_[montant]_[Ouvrage]',
                'exemple': 'Indemnité de savon BF1_20000_Ambalamanasy'
            })
        else:
            suggestions.append({
                'format': 'Indemnité savon_[Ouvrage]',
                'exemple': 'Indemnité savon_Ambinanisakoana'
            })

    # Suggérer formats Nettoyage
    if has_nettoyage and has_bf:
        suggestions.append({
            'format': 'Nettoyage BF_[Ouvrage]',
            'exemple': 'Nettoyage BF_Ambalafary Mahambo'
        })

    # Suggérer formats PMH
    if has_pmh:
        if has_digits:
            suggestions.append({
                'format': 'Indemnité PMH[num]_[Ouvrage]',
                'exemple': 'Indemnité PMH2_Antsohimbondrona'
            })
        else:
            suggestions.append({
                'format': 'Indemnité PMH_[Ouvrage]',
                'exemple': 'Indemnité PMH_Ambodihazina'
            })

    # Si aucune suggestion spécifique, proposer format générique
    if not suggestions and has_indemnite:
        suggestions.append({
            'format': 'Indemnité [Type][num]_[Ouvrage]',
            'exemple': 'Indemnité RBF1_NomOuvrage ou Indemnité BF2_NomOuvrage'
        })

    # Limiter à 3 suggestions max
    return suggestions[:3]


# =============================================================================
# EXTRACTION DU LIEU (Commune/District/Region) POUR LES REUNIONS
# Comptes concernés : 608004, 625300, 625302
# =============================================================================
#
# Formats reels observes (variables, pas de regex de position fixe fiable) :
#   625300 : "ISI PREST_RATSIFERANA Sylvain_Repas bilan restitution_Fft_140000_Ar pour Ambohipihaonana"
#   625300 : "ISI PREST_SIZA CORINE RICA_Pause café et déjeuner_Fft_423000_pour membre SMR restitution Vohilengo"
#   608004 : "NIF_LANDY HOTEL_Repas_U_160_20000_Atelier Soakoja Analamanga"  (Analamanga = Region, pas Commune)
#   625302 : "Indemnité SMR atelier Vohilengo_39 x 15 000 Ar"
#
# Le nom du lieu (Commune, ou parfois District/Region pour les ateliers) apparait
# en fin de libelle, mais sa position exacte (avant/apres "pour", nombre de mots)
# varie. Plutot que des regex fragiles, on recherche par correspondance de noms
# connus (Commune/District/Region), en privilegiant le match le plus specifique
# (Commune > District > Region) et le plus proche de la fin du texte.

_geo_reunion_cache = {'communes': None, 'districts': None, 'regions': None}


def _get_geo_reunion_lookup():
    """
    Charge et met en cache (process Python) les noms de Commune/District/Region
    normalises (minuscule, sans accents), pour une recherche rapide sur un grand
    nombre de lignes DiameX sans re-requeter la base a chaque appel.
    """
    if _geo_reunion_cache['communes'] is None:
        from apps.geography.models import Commune, District, Region

        def _norm(txt):
            txt = unicodedata.normalize('NFKD', txt or '').encode('ascii', 'ignore').decode('ascii')
            return txt.strip().lower()

        _geo_reunion_cache['communes'] = [
            (_norm(nom), obj_id) for obj_id, nom in Commune.objects.values_list('id', 'nom_commune')
        ]
        _geo_reunion_cache['districts'] = [
            (_norm(nom), obj_id) for obj_id, nom in District.objects.values_list('id', 'nom_district')
        ]
        _geo_reunion_cache['regions'] = [
            (_norm(nom), obj_id) for obj_id, nom in Region.objects.values_list('id', 'nom_region')
        ]
    return _geo_reunion_cache


def reset_geo_reunion_cache():
    """A appeler si la geographie est modifiee pendant la duree de vie du process (tests, scripts)."""
    _geo_reunion_cache['communes'] = None
    _geo_reunion_cache['districts'] = None
    _geo_reunion_cache['regions'] = None


def extraire_lieu_reunion(description):
    """
    Recherche dans une description DiameX (comptes 608004/625300/625302) le nom
    d'une Commune, d'un District ou d'une Region, en privilegiant :
      1. Le niveau le plus specifique (Commune > District > Region)
      2. Le nom le plus long trouve (evite qu'un nom court soit ecrase par hasard)
      3. Le match situe le plus a droite dans le texte (le lieu est generalement en fin de libelle)

    Returns:
        dict: {
            'commune_id': UUID ou None,
            'commune_nom': str ou None,
            'district_id': UUID ou None,
            'district_nom': str ou None,
            'region_id': UUID ou None,
            'region_nom': str ou None,
            'niveau': 'commune' | 'district' | 'region' | None,
        }
    """
    result = {
        'commune_id': None,
        'commune_nom': None,
        'district_id': None,
        'district_nom': None,
        'region_id': None,
        'region_nom': None,
        'niveau': None,
    }

    if not description:
        return result

    description_clean = nettoyer_suffixe_paiement_volume(description)
    description_norm = unicodedata.normalize('NFKD', description_clean).encode('ascii', 'ignore').decode('ascii').lower()

    lookup = _get_geo_reunion_lookup()

    def _meilleur_match(candidats):
        """Retourne (nom_norm, obj_id, position) du match le plus long puis le plus a droite."""
        meilleur = None
        for nom_norm, obj_id in candidats:
            if not nom_norm or len(nom_norm) < 3:
                continue
            # Recherche par limites de mots pour eviter les faux positifs sur sous-chaines
            pattern = r'(?<![a-z0-9])' + re.escape(nom_norm) + r'(?![a-z0-9])'
            matches = list(re.finditer(pattern, description_norm))
            if not matches:
                continue
            position = matches[-1].start()
            candidat = (len(nom_norm), position, nom_norm, obj_id)
            if meilleur is None or candidat > meilleur:
                meilleur = candidat
        return meilleur

    match_commune = _meilleur_match(lookup['communes'])
    if match_commune:
        _, _, nom_norm, obj_id = match_commune
        from apps.geography.models import Commune
        commune = Commune.objects.filter(id=obj_id).first()
        if commune:
            result.update({
                'commune_id': commune.id,
                'commune_nom': commune.nom_commune,
                'niveau': 'commune',
            })
            return result

    match_district = _meilleur_match(lookup['districts'])
    if match_district:
        _, _, nom_norm, obj_id = match_district
        from apps.geography.models import District
        district = District.objects.filter(id=obj_id).first()
        if district:
            result.update({
                'district_id': district.id,
                'district_nom': district.nom_district,
                'niveau': 'district',
            })
            return result

    match_region = _meilleur_match(lookup['regions'])
    if match_region:
        _, _, nom_norm, obj_id = match_region
        from apps.geography.models import Region
        region = Region.objects.filter(id=obj_id).first()
        if region:
            result.update({
                'region_id': region.id,
                'region_nom': region.nom_region,
                'niveau': 'region',
            })
            return result

    return result
