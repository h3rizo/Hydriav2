"""
Vues pour la vérification de conformité des paiements aux employés
Vérifie que les descriptions DiameX respectent la charte et que les comptes Cat sont corrects
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from apps.accounting.models import BaseDiameX
from apps.employees.models import Employe, Poste, Contrat
from apps.organization.models import Compte, Base
import re
from datetime import datetime


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _filter_employes_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()
    return queryset.filter(base__organisation_id=organisation_id)


def _filter_comptes_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()
    return queryset.filter(organisation_id=organisation_id)


def _filter_diamex_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()
    allowed_progs = list(
        Base.objects.filter(organisation_id=organisation_id)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )
    if not allowed_progs:
        return queryset.none()
    return queryset.filter(prog__in=allowed_progs)


# Mapping des types de paiement vers les patterns de description attendus
# Note: Tous les patterns acceptent du texte optionnel après la période (ex: "[-813600 split 1/25]")
PATTERNS_DESCRIPTION = {
    'salaire': [
        r'_Salaire_(\d{4})\s+(\d{1,2})',  # Format standard
        r'_Salaire_.*?(\d{4})\s+(\d{1,2})',  # Salaire avec détails (ex: 17j x 12 700Ar 2025 03)
        r'_Solde de tout compte_(\d{4})\s+(\d{1,2})',  # Solde de tout compte avec année/mois
        r'_.*?[Ss]olde de tout compte_(\d{4})\s+(\d{1,2})',  # Ajustement solde de tout compte avec texte avant
        r'_.*?[Ss]olde de tout compte_(\d{4})(?:\s|$)',  # Solde de tout compte sans mois
        r'_Prime_(\d{4})',  # Prime (sans mois obligatoire)
        r'_Allocation terrain_(\d{4})\s+(\d{1,2})',  # Allocation terrain
        r'_Indemnit[ée] compensatrice de cong[ée]_(\d{4})',  # Indemnité compensatrice de congé (sans mois)
        r'_Indemnit[ée] compensatrice de cong[ée](?:\s+[^_]+)?_(\d{4})',  # Variantes type "congé non pris" (sans mois)
        r'_[Pp]restation admin.*',  # Prestation admin à l'essai (pas de période obligatoire)
        r'_.*?[Ss]alaire_(\d{4})\s+(\d{1,2})(?:\s+\d{1,2})*',  # Ajustement salaire avec multiple mois (capture le premier)
    ],
    'irsa': r'_IRSA_(\d{4})\s+(\d{1,2})',
    'cnaps': [
        r'_Charge CNaPS_(\d{4})\s+(\d{1,2})',
        r'_CNaPS_(\d{4})\s+(\d{1,2})',  # CNaPS sans "Charge" avec mois
        r'_CNaPS_(\d{4})\s+([1-4]e?\s+trimestre)',  # CNaPS avec trimestre (année avant)
        r'_Charge [Cc][Nn][Aa][Pp][Ss]_([1-4])(?:er|è|e)?\s+trimestre\s+(\d{4})',  # CNaPS avec trimestre (année après, insensible à la casse)
        r'_[Cc][Nn][Aa][Pp][Ss]_([1-4])(?:er|è|e)?\s+trimestre\s+(\d{4})',  # CNaPS sans "Charge" avec trimestre (année après, insensible à la casse)
    ],
    'fmfp': [
        r'_Charge FMFP_(\d{4})\s+(\d{1,2})',
        r'_FMFP_(\d{4})\s+(\d{1,2})',  # FMFP sans "Charge" avec mois
        r'_FMFP_(\d{4})\s+([1-4]e?\s+trimestre)',  # FMFP avec trimestre (année avant)
        r'_Charge FMFP_([1-4])(?:er|è|e)?\s+trimestre\s+(\d{4})',  # FMFP avec trimestre (année après)
        r'_FMFP_([1-4])(?:er|è|e)?\s+trimestre\s+(\d{4})',  # FMFP sans "Charge" avec trimestre (année après)
    ],
    'mutuelle_sante': [
        r'_Charge AMIT_(\d{4})\s+(\d{1,2})(?:\s|$)',
        r'_Charge [Oo][Ss][Ii][Ee][Ff][Ss][Oo][Vv][Aa]_(\d{4})\s+(\d{1,2})(?:\s|$)',
        r'_AMIT_(\d{4})\s+(\d{1,2})(?:\s|$)',  # AMIT sans "Charge" avec mois (format strict)
        r'_AMIT_(\d{4})\s+([1-4]e?\s+trimestre)',  # AMIT avec trimestre
        r'_AMIT\s+.*?(\d{4})\s+(\d{1,2})',  # AMIT avec texte descriptif (ex: "part employeur 6%")
        r'_[Oo][Ss][Ii][Ee][Ff][Ss][Oo][Vv][Aa]_(\d{4})\s+(\d{1,2})(?:\s|$)',  # OSIEFSoVa sans "Charge" avec mois (tolère la casse)
        r'_[Oo][Ss][Ii][Ee][Ff][Ss][Oo][Vv][Aa]_(\d{4})\s+([1-4]e?\s+trimestre)',  # OSIEFSoVa avec trimestre (tolère la casse)
        r'_[Oo][Ss][Ii][Ee][Ff][Ss][Oo][Vv][Aa]\s+.*?(\d{4})\s+(\d{1,2})',  # OSIEFSoVa avec texte descriptif (tolère la casse)
        r'_[Ss]ant[ée]_(\d{4})\s+(\d{1,2})(?:\s|$)',  # Santé/Sante avec mois
        r'_[Ss]ant[ée]_(\d{4})\s+([1-4]e?\s+trimestre)',  # Santé/Sante avec trimestre
        r"_Droit d['\"]?adh[ée]sion",  # Droit d'adhésion (paiement unique, sans année/mois)
    ],
    'frais_medicaux': [
        r'_(?:Remboursement )?[Ff]rais m[ée]dicaux(?:\s*\([^)]+\))?[_\s](?:.*?[_\s])?(\d{4})\s+(\d{1,2})',  # Format standard (séparateur _ ou espace après type et entre parties)
        r'_(?:Remboursement )?[Ff]rais m[ée]dicaux.*?(?:/|au\s+\d+/)(\d{4})',  # Avec période complète
        r'_[Rr]emboursement\s+(?:pour\s+)?.*?(\d{4})\s+(\d{1,2})',  # Remboursement générique avec texte libre (accident, dommages, etc.)
        r'_[Ff]rais m[ée]dicaux_[^_]+(?:/[^_]+)*',  # Libellé libre sans période
    ],
    'frais_scolarite': [
        r'_(?:Remboursement )?[Ff]rais (?:de )?scolarit[ée](?:\s*\([^)]+\))?[_\s](?:.*?[_\s])?(\d{4})\s+(\d{1,2})',  # Format standard (séparateur _ ou espace après type et entre parties)
        r'_(?:Remboursement )?[Ff]rais (?:de )?scolarit[ée].*?(?:/|au\s+\d+/)(\d{4})',  # Avec période complète
        r'_(?:Remboursement )?[Ff]rais (?:de )?scolarit[ée][_\s](\d{4})-\d{4}',  # Format année scolaire (2025-2026)
        r'_(?:Remboursement )?[Ff]rais (?:de )?scolarit[ée]_([1-4])e?\s+trimestre[_\s](\d{4})-\d{4}',  # Trimestre + année scolaire (ex: 3e trimestre_2024-2025)
    ],
    'frais_deplacement': [
        r'_[Ff]rais (?:de )?d[ée]placement(?:\s*\([^)]+\))?[_\s](?:.*?[_\s])?(\d{4})\s+(\d{1,2})',  # Format standard (séparateur _ ou espace après type et entre parties)
        r'_[Ff]rais (?:de )?d[ée]placement.*?(?:/|au\s+\d+/)(\d{4})',  # Avec période complète
    ],
    'indemnite_terrain': [
        r'_Indemn[ie]t[ée] terrain_(?:.*?_)?(\d{4})\s+(\d{1,2})',  # Format standard avec texte optionnel
        r'_Indemn[ie]t[ée] terrain_\s*\d+\s*x\s*[\d\s]+Ar?\s*(?:du\s+)?(?:\d{1,2}(?:/\d{1,2}/\d{4})?\s*)?(?:(?:au|et|,)\s*\d+\s*)*(\d{4})\s+(\d{1,2})',  # Avec période (avec "au", "et" ou virgule, multiple)
    ],
    'indemnite_hors_zone': [
        r'_Indemn[ie]t[ée] [Hh]ors zone_.*?/(\d{1,2})/(\d{2})_',  # Format avec dates courtes DD/MM/YY (ex: 25/09/25) - PRIORITÉ
        r'_Indemn[ie]t[ée] [Hh]ors zone_.*?(?:[Jj]anvier|[Ff][ée]vrier|[Mm]ars|[Aa]vril|[Mm]ai|[Jj]uin|[Jj]uillet|[Aa]o[uû]t|[Ss]eptembre|[Oo]ctobre|[Nn]ovembre|[Dd][ée]cembre)\s+(\d{4})',  # Avec mois en texte - PRIORITÉ
        r'_Indemn[ie]t[ée] [Hh]ors zone_(?:.*?_)?(\d{4})\s+(\d{1,2})$',  # Format standard (année mois à la fin)
        r'_Indemn[ie]t[ée] [Hh]ors zone_.*?(\d{4})\s+(\d{1,2})',  # Année mois n'importe où dans la description
        r'_Indemn[ie]t[ée] [Hh]ors zone_.*?(?:/|au\s+\d+/)(\d{4})',  # Format avec période complète (année 4 chiffres)
    ],
    'indemnite_stage': [
        r'_Indemn[ie]t[ée] de stage_(?:.*?_)?(\d{4})\s+(\d{1,2})',  # Format standard
        r'_Indemn[ie]t[ée] de stage_\s*\d+\s*x\s*[\d\s]+Ar?\s*(?:du\s+\d+)?.*?(\d{4})\s+(\d{1,2})',  # Avec période
    ],
}

# Comptes DiameX correspondants (à ajuster selon les données réelles)
COMPTES_TYPES_PAIEMENT = {
    'salaire': ['641613', '641612', '641611', '641200'],  # Salaires
    'irsa': ['631411', '631305'],  # IRSA
    'cnaps': ['646311'],  # CNaPS
    'fmfp': ['646311'],  # FMFP (même compte que CNaPS)
    'mutuelle_sante': ['646312', '646311'],  # Mutuelle santé (AMIT, OSIEFSoVa)
    'frais_medicaux': ['641613', '641612', '641611', '641200', '646312'],  # Frais médicaux (mêmes comptes que salaires)
    'frais_scolarite': ['641613', '641612', '641611', '641200', '646313'],  # Frais de scolarité (mêmes comptes que salaires)
    'frais_deplacement': ['625200', '625100'],  # Frais de déplacement
    'indemnite_terrain': [],  # Indemnités terrain (utilise compte_indemnite du poste)
    'indemnite_hors_zone': [],  # Indemnités hors zone (utilise compte_indemnite du poste, même que terrain)
    'indemnite_stage': ['625124'],  # Indemnités de stage
}


def normaliser_texte(texte):
    """
    Normalise un texte en supprimant les accents et en le mettant en minuscules
    Ex: "Fénérive" → "fenerive"
    """
    import unicodedata
    # Décomposer les caractères accentués (é → e + ´)
    nfkd = unicodedata.normalize('NFKD', texte)
    # Supprimer les caractères diacritiques (accents)
    sans_accents = nfkd.encode('ASCII', 'ignore').decode('ASCII')
    return sans_accents.lower()


def trouver_base_access_par_prog(prog):
    """
    Trouve la base Access correspondant au mieux à un prog donné
    Utilise un algorithme de scoring basé sur les mots-clés avec normalisation des accents
    """
    from apps.employees.models import EmployeBaseDiameX

    # Chercher correspondance exacte d'abord
    base_diamex = EmployeBaseDiameX.objects.filter(
        base_diamex__icontains=prog
    ).first()

    if base_diamex:
        return base_diamex

    # Essayer par mots-clés avec scoring et normalisation des accents
    # Ex: "EHA-Soakoja-Fenerive Est" → chercher "Fenerive" en priorité
    prog_keywords = prog.split('-')

    # Nettoyer et filtrer les mots-clés
    # Découper aussi les mots composés (ex: "Fenerive Est" → ["Fenerive", "Est"])
    keywords_clean = []
    for kw in prog_keywords:
        kw = kw.strip()
        if len(kw) > 3 and kw.upper() not in ['EHA', 'SKJ']:
            # Essayer de découper les mots composés
            sub_words = kw.split()
            if len(sub_words) > 1:
                # Ajouter chaque sous-mot séparément
                for sub in sub_words:
                    if len(sub) > 3:
                        keywords_clean.append(sub)
            else:
                keywords_clean.append(kw)

    # Chercher la base qui correspond au MAXIMUM de mots-clés
    # Donner plus de poids au dernier mot-clé (commune)
    if keywords_clean:
        bases = EmployeBaseDiameX.objects.all()
        best_match = None
        best_score = 0

        for base in bases:
            score = 0
            # Normaliser le nom de la base (supprimer les accents)
            base_normalise = normaliser_texte(base.base_diamex)

            for idx, kw in enumerate(keywords_clean):
                # Normaliser le mot-clé aussi (supprimer les accents)
                kw_normalise = normaliser_texte(kw)

                # Chercher correspondances avec textes normalisés
                if kw_normalise in base_normalise:
                    # Poids : dernier mot (commune) x3, autres mots x1
                    poids = 3 if idx == len(keywords_clean) - 1 else 1
                    score += len(kw) * poids

            if score > best_score:
                best_score = score
                best_match = base

        if best_match:
            return best_match

    return None


def detecter_type_paiement(description):
    """Détecte le type de paiement à partir de la description"""
    if not description:
        return None

    # Normaliser le texte pour gérer les accents
    description_norm = normaliser_texte(description)

    # Ordre de priorité pour éviter les faux positifs
    if 'irsa' in description_norm:
        return 'irsa'
    elif 'cnaps' in description_norm or '_cnaps_' in description_norm:
        return 'cnaps'
    elif 'fmfp' in description_norm or '_fmfp_' in description_norm:
        return 'fmfp'
    elif ('charge amit' in description_norm or 'charge osiefsova' in description_norm or
          '_amit_' in description_norm or '_amit ' in description_norm or
          '_osiefsova_' in description_norm or '_osiefsova ' in description_norm or
          '_sante_' in description_norm or
          "droit d'adhesion" in description_norm or 'droit adhesion' in description_norm):
        return 'mutuelle_sante'
    elif ('remboursement frais medicaux' in description_norm or 'frais medicaux' in description_norm or
          'remboursement pour' in description_norm):  # Remboursement générique (accident, dommages, etc.)
        return 'frais_medicaux'
    elif 'remboursement frais de scolarite' in description_norm or 'frais de scolarite' in description_norm or 'frais scolarite' in description_norm:
        return 'frais_scolarite'
    elif 'frais de deplacement' in description_norm or 'frais deplacement' in description_norm:
        return 'frais_deplacement'
    elif 'indemnite de stage' in description_norm:
        return 'indemnite_stage'
    elif 'indemnite terrain' in description_norm:
        return 'indemnite_terrain'
    elif 'indemnite hors zone' in description_norm:
        return 'indemnite_hors_zone'
    elif 'solde de tout compte' in description_norm:
        return 'salaire'  # Solde de tout compte = type de salaire
    elif '_prime_' in description_norm or description_norm.endswith('_prime'):
        return 'salaire'  # Prime = type de salaire
    elif 'allocation terrain' in description_norm:
        return 'salaire'  # Allocation terrain = type de salaire
    elif 'prestation admin' in description_norm:
        return 'salaire'  # Prestation admin = type de salaire
    elif 'indemnite compensatrice de conge' in description_norm:
        return 'salaire'  # Indemnité compensatrice de congé = type de salaire
    elif 'salaire' in description_norm:
        return 'salaire'

    return None


def convertir_trimestre_en_mois(trimestre_str):
    """
    Convertit un trimestre (1er, 2e, 3e, 4e) en numéro de mois (1-12)
    Retourne le dernier mois du trimestre
    """
    # Extraire le numéro du trimestre (1, 2, 3, 4)
    import re
    match = re.search(r'([1-4])e?\s*trimestre', trimestre_str, re.IGNORECASE)
    if match:
        trimestre_num = int(match.group(1))
        # Mapper trimestre vers dernier mois du trimestre
        # 1er trimestre = mars (3), 2e = juin (6), 3e = septembre (9), 4e = décembre (12)
        return trimestre_num * 3
    return None


def convertir_mois_texte_en_numero(description):
    """
    Convertit un mois en texte en numéro (1-12)
    Ex: "Juillet 2025" → 7
    """
    mois_mapping = {
        'janvier': 1, 'fevrier': 2, 'février': 2, 'mars': 3, 'avril': 4,
        'mai': 5, 'juin': 6, 'juillet': 7, 'aout': 8, 'août': 8,
        'septembre': 9, 'octobre': 10, 'novembre': 11, 'decembre': 12, 'décembre': 12
    }

    description_lower = description.lower()
    for mois_texte, mois_num in mois_mapping.items():
        if mois_texte in description_lower:
            return mois_num
    return None


def extraire_info_description(description):
    """
    Extrait les informations de la description selon la charte:
    [Prefixe du poste] [Nom de l'employé]_[Type]_[Année] [Mois|Trimestre]_...

    Retourne: {
        'prefixe': str,
        'nom_employe': str,
        'type_paiement': str,
        'annee': int,
        'mois': int,
        'conforme': bool,
        'erreurs': []
    }
    """
    if not description:
        return {
            'prefixe': None,
            'nom_employe': None,
            'type_paiement': None,
            'annee': None,
            'mois': None,
            'conforme': False,
            'erreurs': ['Description vide']
        }

    erreurs = []

    # Détecter le type de paiement
    type_paiement = detecter_type_paiement(description)
    if not type_paiement:
        erreurs.append('Type de paiement non identifié')

    # Extraire préfixe et nom (première partie avant _)
    # Nettoyer d'abord les underscores au début
    description_clean = description.lstrip('_')

    parties = description_clean.split('_', 1)
    if len(parties) < 2:
        erreurs.append('Format incorrect: manque séparateur _')
        return {
            'prefixe': None,
            'nom_employe': None,
            'type_paiement': type_paiement,
            'annee': None,
            'mois': None,
            'conforme': False,
            'erreurs': erreurs
        }

    premiere_partie = parties[0].strip()

    # Extraire préfixe (ex: "AR", "ARS", "RESP", "CM", "ASS", "ADMIN")
    # Format : [PREFIXE_COURT] [NOM COMPLET]
    # Le préfixe est typiquement 2-6 lettres en majuscules au début
    match_prefixe = re.match(r'^([A-Z]{2,6})\s+(.+)$', premiere_partie)
    if match_prefixe:
        prefixe = match_prefixe.group(1)
        nom_employe = match_prefixe.group(2)
    else:
        erreurs.append('Format préfixe/nom incorrect')
        prefixe = None
        nom_employe = premiere_partie

    # Extraire année et mois selon le type
    annee = None
    mois = None

    if type_paiement and type_paiement in PATTERNS_DESCRIPTION:
        patterns = PATTERNS_DESCRIPTION[type_paiement]

        # Gérer le cas où il y a plusieurs patterns (ex: mutuelle_sante)
        if isinstance(patterns, list):
            for pattern in patterns:
                match = re.search(pattern, description)
                if match:
                    groups = match.groups()

                    # Pour types avec période complète, gérer le cas spécial
                    types_avec_periode = ['indemnite_hors_zone', 'frais_medicaux', 'frais_scolarite', 'frais_deplacement']

                    if type_paiement in types_avec_periode and len(groups) == 1:
                        # Pattern 2: seulement l'année capturée depuis la période
                        annee = int(groups[0])
                        # Extraire le mois de la date de début (ex: "du 31/01 au..." → mois 01)
                        date_match = re.search(r'du\s+\d{1,2}/(\d{1,2})', description)
                        if date_match:
                            mois = int(date_match.group(1))
                        # Pour frais scolarité avec année scolaire (ex: 2025-2026), utiliser septembre (mois 9)
                        elif type_paiement == 'frais_scolarite' and re.search(r'\d{4}-\d{4}', description):
                            mois = 9  # Début année scolaire
                        # Pour mois en texte (ex: "Juillet 2025")
                        else:
                            mois_texte = convertir_mois_texte_en_numero(description)
                            if mois_texte:
                                mois = mois_texte
                    elif type_paiement in types_avec_periode and len(groups) == 2:
                        # Pattern 1: année et mois standard à la fin
                        groupe1 = groups[0]
                        groupe2 = groups[1]

                        # CAS SPÉCIAL: frais_scolarite avec trimestre + année scolaire (ex: 3e trimestre_2024-2025)
                        if type_paiement == 'frais_scolarite' and int(groupe1) >= 1 and int(groupe1) <= 4 and len(groupe2) == 4:
                            # (trimestre, année) pour frais scolarité
                            trimestre = int(groupe1)
                            annee = int(groupe2)
                            # Trimestre scolaire: 1=Sept, 2=Déc, 3=Mars
                            mois_mapping_scolaire = {1: 9, 2: 12, 3: 3}
                            mois = mois_mapping_scolaire.get(trimestre, 9)  # Défaut septembre
                        # Détecter le format: si groupe2 a 2 chiffres et groupe1 <= 12, c'est (mois, année YY)
                        elif len(groupe2) == 2 and int(groupe1) <= 12:
                            # Format DD/MM/YY → (mois, année sur 2 chiffres)
                            mois = int(groupe1)
                            annee = 2000 + int(groupe2)
                        else:
                            # Format standard (année, mois)
                            annee_str = groupe1
                            mois_str = groupe2

                            # Convertir année sur 2 chiffres en 4 chiffres (25 → 2025)
                            if len(annee_str) == 2:
                                annee = 2000 + int(annee_str)
                            else:
                                annee = int(annee_str)

                            # Convertir mois (peut être nombre ou sur 2 chiffres)
                            if len(mois_str) == 2 and int(mois_str) <= 12:
                                mois = int(mois_str)
                            else:
                                mois = int(mois_str)
                    elif len(groups) == 0:
                        # Pattern sans groupes de capture (ex: Droit d'adhésion)
                        # Pas d'année ni de mois - sera géré par la logique optionnelle plus bas
                        break
                    else:
                        # Logique standard pour autres types
                        # Vérifier si le premier groupe est un numéro 1-4 (trimestre avant année)
                        # Cela indique un pattern "trimestre YYYY" au lieu de "YYYY trimestre"
                        try:
                            premier_groupe_int = int(groups[0])
                            if premier_groupe_int >= 1 and premier_groupe_int <= 4 and len(groups) == 2:
                                # Pattern trimestre avec année après: (trimestre, année)
                                # groups[0] = numéro trimestre (1-4)
                                # groups[1] = année
                                annee = int(groups[1])

                                # Convertir le trimestre en mois selon le type
                                if type_paiement == 'frais_scolarite':
                                    # Trimestre scolaire: 1=Sept, 2=Déc, 3=Mars
                                    mois_mapping_scolaire = {1: 9, 2: 12, 3: 3}
                                    mois = mois_mapping_scolaire.get(premier_groupe_int, 9)  # Défaut septembre
                                else:
                                    # Trimestre civil: 1=Jan, 2=Avr, 3=Juil, 4=Oct
                                    mois = (premier_groupe_int - 1) * 3 + 1
                            else:
                                # Pattern standard: (année, mois/trimestre)
                                annee = premier_groupe_int
                                # Le groupe 2 peut être un mois numérique ou un texte trimestre (ou absent pour Prime)
                                try:
                                    periode_str = groups[1]
                                    # Essayer d'abord de convertir comme mois numérique
                                    try:
                                        mois = int(periode_str)
                                    except (ValueError, TypeError):
                                        # Si pas un nombre, essayer comme trimestre
                                        mois_converti = convertir_trimestre_en_mois(periode_str)
                                        if mois_converti:
                                            mois = mois_converti
                                except IndexError:
                                    # Pas de groupe 2 (ex: Prime sans mois)
                                    mois = None
                        except (ValueError, TypeError):
                            # groups[0] n'est pas un int (cas très rare)
                            annee = None

                    if annee:
                        break
        else:
            # Un seul pattern
            pattern = patterns
            match = re.search(pattern, description)
            if match:
                annee = int(match.group(1))
                try:
                    mois = int(match.group(2))
                except (ValueError, IndexError):
                    pass

        if not annee:
            erreurs.append(f'Format date incorrect pour {type_paiement}')

    # Pour les Primes, Solde de tout compte et Indemnité compensatrice de congé, le mois n'est pas obligatoire
    # Pour Droit d'adhésion, ni année ni mois ne sont obligatoires (paiement unique)
    mois_requis = True
    annee_requise = True
    description_norm = normaliser_texte(description)
    prestation_admin_sans_periode = 'prestation admin' in description_norm
    frais_medicaux_libres = (
        type_paiement == 'frais_medicaux' and
        re.search(r'_[Ff]rais m[ée]dicaux_[^_]+(?:/[^_]+)*$', description) is not None
    )

    if type_paiement == 'salaire' and ('_prime_' in description_norm or 'solde de tout compte' in description_norm or 'indemnite compensatrice' in description_norm):
        mois_requis = False

    if prestation_admin_sans_periode:
        mois_requis = False
        annee_requise = False
        erreurs = [e for e in erreurs if 'Format date incorrect' not in e]

    if type_paiement == 'mutuelle_sante' and ("droit d'adhesion" in description_norm or 'droit adhesion' in description_norm):
        mois_requis = False
        annee_requise = False
        # Retirer l'erreur d'année si elle a été ajoutée
        erreurs = [e for e in erreurs if 'Format date incorrect' not in e]

    if frais_medicaux_libres:
        mois_requis = False
        annee_requise = False
        erreurs = [e for e in erreurs if 'Format date incorrect' not in e]

    conforme = len(erreurs) == 0 and prefixe and nom_employe and (annee or not annee_requise) and (mois or not mois_requis)

    return {
        'prefixe': prefixe,
        'nom_employe': nom_employe,
        'type_paiement': type_paiement,
        'annee': annee,
        'mois': mois,
        'conforme': conforme,
        'erreurs': erreurs
    }


def verifier_prefixe_employe(employe, prefixe):
    """
    Vérifie si le préfixe correspond au poste actuel OU à un ancien poste de l'employé
    Retourne True si le préfixe est valide pour cet employé
    """
    if not employe or not prefixe:
        return False

    # Vérifier le poste actuel
    if employe.poste and employe.poste.prefixe == prefixe:
        return True

    # Vérifier les anciens postes dans les contrats
    anciens_contrats = Contrat.objects.filter(
        employe=employe
    ).select_related('poste').exclude(poste__isnull=True)

    for contrat in anciens_contrats:
        if contrat.poste and contrat.poste.prefixe == prefixe:
            return True

    return False


def _get_postes_for_prefix(prefixe):
    if not prefixe:
        return []
    return list(
        Poste.objects.filter(prefixe=prefixe).select_related(
            'compte_salaire',
            'compte_irsa',
            'compte_cnaps_fmfp_sante',
            'compte_indemnite',
        )
    )


def _get_compte_config_for_poste(poste, type_paiement):
    if not poste:
        return None, None

    if type_paiement == 'salaire' and poste.compte_salaire:
        return poste.compte_salaire.compte, poste.compte_salaire.nom_compte
    if type_paiement == 'irsa' and poste.compte_irsa:
        return poste.compte_irsa.compte, poste.compte_irsa.nom_compte
    if type_paiement in ['cnaps', 'fmfp', 'mutuelle_sante'] and poste.compte_cnaps_fmfp_sante:
        return poste.compte_cnaps_fmfp_sante.compte, poste.compte_cnaps_fmfp_sante.nom_compte
    if type_paiement in ['indemnite_terrain', 'indemnite_hors_zone', 'indemnite_stage'] and poste.compte_indemnite:
        return poste.compte_indemnite.compte, poste.compte_indemnite.nom_compte
    if type_paiement in ['frais_scolarite', 'frais_medicaux'] and poste.compte_salaire:
        return poste.compte_salaire.compte, poste.compte_salaire.nom_compte

    return None, None


def _verifier_compte_cat_avec_postes(compte_code, type_paiement, postes, prefixe=None):
    comptes_generiques = COMPTES_TYPES_PAIEMENT.get(type_paiement, [])

    if type_paiement == 'frais_deplacement':
        if compte_code in comptes_generiques:
            return {'correct': True, 'attendu': compte_code, 'erreur': None}
        return {
            'correct': False,
            'attendu': ','.join(comptes_generiques),
            'erreur': f'Compte incorrect (attendu: {",".join(comptes_generiques)})'
        }

    comptes_attendus = []
    seen = set()
    for poste in postes or []:
        compte_attendu, nom_compte = _get_compte_config_for_poste(poste, type_paiement)
        if not compte_attendu:
            continue
        key = (compte_attendu, getattr(poste, 'nom_poste', ''))
        if key in seen:
            continue
        seen.add(key)
        comptes_attendus.append({
            'compte': compte_attendu,
            'nom_compte': nom_compte,
            'poste_nom': getattr(poste, 'nom_poste', ''),
        })

    if any(item['compte'] == compte_code for item in comptes_attendus):
        return {'correct': True, 'attendu': compte_code, 'erreur': None}

    if compte_code in comptes_generiques:
        return {'correct': True, 'attendu': compte_code, 'erreur': None}

    if comptes_attendus:
        attendu = ','.join(item['compte'] for item in comptes_attendus)
        if len(comptes_attendus) == 1:
            item = comptes_attendus[0]
            erreur = f"Compte incorrect (attendu: {item['compte']}"
            if item['nom_compte']:
                erreur += f" - {item['nom_compte']}"
            erreur += ')'
        else:
            details = ', '.join(
                f"{item['compte']} ({item['poste_nom']})" if item['poste_nom'] else item['compte']
                for item in comptes_attendus
            )
            erreur = f'Compte incorrect (attendu: {details})'
        return {
            'correct': False,
            'attendu': attendu,
            'erreur': erreur
        }

    if comptes_generiques:
        attendu = ','.join(comptes_generiques)
        return {
            'correct': False,
            'attendu': attendu,
            'erreur': f'Compte incorrect (attendu: {attendu})'
        }

    if prefixe:
        return {
            'correct': False,
            'attendu': None,
            'erreur': f'Compte non configuré pour le préfixe {prefixe}'
        }

    return None


def verifier_compte_cat(compte_code, type_paiement, employe_obj, prefixe=None):
    """
    Vérifie que le compte Cat correspond au bon compte selon:
    - Le type de paiement
    - Le poste de l'employé (actuel ou ancien si préfixe fourni)

    Retourne: {
        'correct': bool,
        'attendu': str,
        'erreur': str
    }
    """
    if not employe_obj:
        return {
            'correct': False,
            'attendu': None,
            'erreur': 'Employé introuvable'
        }

    # Déterminer le poste à utiliser
    poste = None

    # Pour tous les types de paiement, si un préfixe est fourni
    # et qu'il ne correspond pas au poste actuel, chercher dans les anciens contrats
    types_verification_historique = [
        'cnaps', 'fmfp', 'mutuelle_sante', 'irsa',
        'salaire',  # Inclut Prime, Ajustement salaire, Solde de tout compte, etc.
        'indemnite_terrain', 'indemnite_hors_zone', 'indemnite_stage',
        'frais_scolarite', 'frais_medicaux', 'frais_deplacement'
    ]

    if (type_paiement in types_verification_historique and
        prefixe and
        employe_obj.poste and
        employe_obj.poste.prefixe != prefixe):
        # Chercher dans les anciens contrats
        ancien_contrat = Contrat.objects.filter(
            employe=employe_obj,
            poste__prefixe=prefixe
        ).select_related('poste').first()

        if ancien_contrat and ancien_contrat.poste:
            poste = ancien_contrat.poste

    # Si pas d'ancien poste trouvé, utiliser le poste actuel
    if not poste:
        poste = employe_obj.poste

    if not poste:
        return {
            'correct': False,
            'attendu': None,
            'erreur': 'Poste introuvable'
        }

    compte_attendu = None

    # Récupérer le compte attendu selon le type de paiement
    if type_paiement == 'salaire':
        compte_attendu = poste.compte_salaire.compte if poste.compte_salaire else None
    elif type_paiement == 'irsa':
        compte_attendu = poste.compte_irsa.compte if poste.compte_irsa else None
    elif type_paiement in ['cnaps', 'fmfp', 'mutuelle_sante']:
        compte_attendu = poste.compte_cnaps_fmfp_sante.compte if poste.compte_cnaps_fmfp_sante else None
    elif type_paiement in ['indemnite_terrain', 'indemnite_hors_zone', 'indemnite_stage']:
        compte_attendu = poste.compte_indemnite.compte if poste.compte_indemnite else None
    elif type_paiement in ['frais_scolarite', 'frais_medicaux']:
        # Frais de scolarité et frais médicaux : utilisent le même compte que le salaire
        compte_attendu = poste.compte_salaire.compte if poste.compte_salaire else None
    elif type_paiement == 'frais_deplacement':
        # Pour les frais de déplacement, utiliser les comptes génériques
        comptes_possibles = COMPTES_TYPES_PAIEMENT.get(type_paiement, [])
        if compte_code in comptes_possibles:
            return {'correct': True, 'attendu': compte_code, 'erreur': None}
        else:
            return {
                'correct': False,
                'attendu': ','.join(comptes_possibles),
                'erreur': f'Compte incorrect (attendu: {",".join(comptes_possibles)})'
            }

    # Si pas de compte attendu configuré, vérifier dans les comptes génériques
    if not compte_attendu:
        comptes_generiques = COMPTES_TYPES_PAIEMENT.get(type_paiement, [])
        if compte_code in comptes_generiques:
            # Le compte est dans la liste des comptes valides pour ce type
            return {
                'correct': True,
                'attendu': compte_code,
                'erreur': None
            }
        else:
            # Message d'erreur différent selon si liste vide ou non
            if not comptes_generiques:
                # Liste vide = doit utiliser le compte du poste
                return {
                    'correct': False,
                    'attendu': None,
                    'erreur': f'Compte indemnité non configuré pour le poste {poste.nom_poste}'
                }
            else:
                # Liste non vide = compte invalide
                return {
                    'correct': False,
                    'attendu': ','.join(comptes_generiques),
                    'erreur': f'Compte non configuré pour le poste {poste.nom_poste}'
                }

    # Vérifier si le compte correspond exactement
    correct = compte_code == compte_attendu

    # Si le compte ne correspond pas exactement, vérifier s'il est dans les comptes génériques valides
    if not correct:
        comptes_generiques = COMPTES_TYPES_PAIEMENT.get(type_paiement, [])
        if compte_code in comptes_generiques:
            # Le compte est valide même s'il ne correspond pas exactement au compte configuré
            correct = True

    # Récupérer le nom du compte pour un message d'erreur plus clair
    nom_compte_attendu = ''
    if compte_attendu:
        if type_paiement == 'salaire' and poste.compte_salaire:
            nom_compte_attendu = poste.compte_salaire.nom_compte
        elif type_paiement == 'irsa' and poste.compte_irsa:
            nom_compte_attendu = poste.compte_irsa.nom_compte
        elif type_paiement in ['cnaps', 'fmfp', 'mutuelle_sante'] and poste.compte_cnaps_fmfp_sante:
            nom_compte_attendu = poste.compte_cnaps_fmfp_sante.nom_compte
        elif type_paiement in ['indemnite_terrain', 'indemnite_hors_zone', 'indemnite_stage'] and poste.compte_indemnite:
            nom_compte_attendu = poste.compte_indemnite.nom_compte
        elif type_paiement in ['frais_scolarite', 'frais_medicaux'] and poste.compte_salaire:
            nom_compte_attendu = poste.compte_salaire.nom_compte

    message_erreur = None
    if not correct:
        if nom_compte_attendu:
            message_erreur = f'Compte incorrect (attendu: {compte_attendu} - {nom_compte_attendu})'
        else:
            message_erreur = f'Compte incorrect (attendu: {compte_attendu})'

    return {
        'correct': correct,
        'attendu': compte_attendu,
        'erreur': message_erreur
    }


def verifier_compte_cat(compte_code, type_paiement, employe_obj, prefixe=None):
    """
    Surcharge la logique historique pour autoriser un fallback par préfixe
    quand l'employé n'est pas retrouvé ou quand plusieurs postes partagent
    le même préfixe avec la bonne configuration comptable.
    """
    postes_a_verifier = []

    types_verification_historique = [
        'cnaps', 'fmfp', 'mutuelle_sante', 'irsa',
        'salaire',
        'indemnite_terrain', 'indemnite_hors_zone', 'indemnite_stage',
        'frais_scolarite', 'frais_medicaux', 'frais_deplacement'
    ]

    if employe_obj and getattr(employe_obj, 'poste', None):
        postes_a_verifier.append(employe_obj.poste)

    if (
        type_paiement in types_verification_historique and
        employe_obj and
        prefixe and
        getattr(employe_obj, 'poste', None) and
        employe_obj.poste.prefixe != prefixe
    ):
        ancien_contrat = Contrat.objects.filter(
            employe=employe_obj,
            poste__prefixe=prefixe
        ).select_related('poste').first()
        if ancien_contrat and ancien_contrat.poste:
            postes_a_verifier.insert(0, ancien_contrat.poste)

    if prefixe:
        postes_existants = {getattr(poste, 'id', id(poste)) for poste in postes_a_verifier if poste}
        for poste_prefixe in _get_postes_for_prefix(prefixe):
            poste_key = getattr(poste_prefixe, 'id', id(poste_prefixe))
            if poste_key not in postes_existants:
                postes_a_verifier.append(poste_prefixe)
                postes_existants.add(poste_key)

    validation = _verifier_compte_cat_avec_postes(
        compte_code,
        type_paiement,
        postes_a_verifier,
        prefixe=prefixe,
    )
    if validation:
        return validation

    if not employe_obj:
        return {
            'correct': False,
            'attendu': None,
            'erreur': 'Employé introuvable'
        }

    return {
        'correct': False,
        'attendu': None,
        'erreur': 'Poste introuvable'
    }


@login_required
def verification_paiements_employes(request):
    """
    Page principale de vérification des paiements employés
    """
    # Filtres
    annee = request.GET.get('annee', str(datetime.now().year))
    mois = request.GET.get('mois', '')
    employe_id = request.GET.get('employe_id', '')
    type_paiement_filter = request.GET.get('type_paiement', '')
    statut_filter = request.GET.get('statut', '')  # conforme, non_conforme, compte_incorrect

    # Listes pour filtres
    # Employés actifs = sans date de débauchage
    employes = _filter_employes_by_scope(
        Employe.objects.filter(date_debauchage__isnull=True),
        request.user
    ).order_by('surnom')
    annees_disponibles = list(range(datetime.now().year, datetime.now().year - 5, -1))

    # Récupérer la liste des progs distincts depuis les comptes employés
    comptes_employes = list(_filter_comptes_by_scope(
        Compte.objects.filter(
        employe_obligatoire=True
    ), request.user).values_list('compte', flat=True))

    progs_disponibles = _filter_diamex_by_scope(BaseDiameX.objects.filter(
        compte_code__in=comptes_employes
    ), request.user).values_list('prog', flat=True).distinct().order_by('prog')
    progs_disponibles = [p for p in progs_disponibles if p]  # Enlever les valeurs None/vides

    context = {
        'employes': employes,
        'annees': annees_disponibles,
        'progs': progs_disponibles,
        'annee_selectionnee': annee,
        'mois_selectionne': mois,
        'employe_selectionne': employe_id,
        'type_paiement_selectionne': type_paiement_filter,
        'statut_selectionne': statut_filter,
    }

    return render(request, 'employees/verification_paiements_employes.html', context)


@login_required
def api_verification_paiements_employes(request):
    """
    API pour récupérer les résultats de la vérification
    """
    # Filtres
    annee = request.GET.get('annee', str(datetime.now().year))
    mois = request.GET.get('mois', '')
    employe_id = request.GET.get('employe_id', '')
    prog_filter = request.GET.get('prog', '')
    type_paiement_filter = request.GET.get('type_paiement', '')
    statut_filter = request.GET.get('statut', '')

    # Récupérer les comptes marqués comme "Compte employé" (employe_obligatoire=True)
    comptes_employes = list(_filter_comptes_by_scope(Compte.objects.filter(
        employe_obligatoire=True
    ), request.user).values_list('compte', flat=True))

    # Filtrer uniquement les paiements sur les comptes employés
    query = _filter_diamex_by_scope(BaseDiameX.objects.filter(
        compte_code__in=comptes_employes
    ), request.user).exclude(
        description__isnull=True
    ).exclude(
        description=''
    )

    # Filtrer par année
    if annee:
        query = query.filter(date_m__year=int(annee))

    # Filtrer par mois
    if mois:
        query = query.filter(date_m__month=int(mois))

    # Filtrer par prog
    if prog_filter:
        query = query.filter(prog=prog_filter)

    # Analyser chaque transaction
    resultats = []
    stats = {
        'total': 0,
        'conformes': 0,
        'non_conformes': 0,
        'compte_incorrect': 0,
        'prefixe_incorrect': 0,
        'type_inconnu': 0,
    }

    for entry in query.order_by('-date_m', '-id'):
        # Extraire infos de la description
        info = extraire_info_description(entry.description)

        # Chercher l'employé correspondant avec plusieurs stratégies
        employe_obj = None
        if info['nom_employe']:
            # Stratégie 1: Recherche exacte par surnom
            employes_scopes = _filter_employes_by_scope(Employe.objects.all(), request.user)
            employe_obj = employes_scopes.filter(surnom__iexact=info['nom_employe']).first()

            if not employe_obj:
                # Stratégie 2: Recherche par nom complet (nom + prénom ou prénom + nom)
                employe_obj = employes_scopes.filter(
                    Q(surnom__icontains=info['nom_employe']) |
                    Q(nom__icontains=info['nom_employe']) |
                    Q(prenom__icontains=info['nom_employe'])
                ).first()

            if not employe_obj:
                # Stratégie 3: Essayer de séparer les parties du nom
                parties = info['nom_employe'].split()
                if len(parties) >= 2:
                    # Essayer Nom Prénom
                    nom_part = parties[0]
                    prenom_part = ' '.join(parties[1:])
                    employe_obj = employes_scopes.filter(
                        Q(nom__icontains=nom_part, prenom__icontains=prenom_part) |
                        Q(prenom__icontains=nom_part, nom__icontains=prenom_part)
                    ).first()

                    # Essayer juste par surnom contenant une des parties
                    if not employe_obj:
                        for partie in parties:
                            if len(partie) > 3:  # Ignorer les parties trop courtes
                                employe_obj = employes_scopes.filter(
                                    surnom__icontains=partie
                                ).first()
                                if employe_obj:
                                    break

        # Filtrer par employé si sélectionné
        if employe_id and (not employe_obj or str(employe_obj.id) != employe_id):
            continue

        # Vérifier le compte Cat (en tenant compte du préfixe pour les anciens postes)
        verification_compte = verifier_compte_cat(
            entry.compte_code,
            info['type_paiement'],
            employe_obj,
            prefixe=info['prefixe']
        )

        # Vérifier si le préfixe correspond au poste actuel OU à un ancien poste
        prefixe_valide = False
        if employe_obj and info['prefixe']:
            prefixe_valide = verifier_prefixe_employe(employe_obj, info['prefixe'])

        # Filtrer par type de paiement
        if type_paiement_filter and info['type_paiement'] != type_paiement_filter:
            continue

        # Calculer le statut global
        # NOUVEAU: Un préfixe est considéré conforme s'il correspond au poste actuel OU à un ancien poste
        statut = 'conforme'
        if not info['conforme']:
            statut = 'non_conforme'
        elif not verification_compte['correct']:
            statut = 'compte_incorrect'
        elif employe_obj and info['prefixe'] and not prefixe_valide:
            # Le préfixe ne correspond ni au poste actuel ni à un ancien poste
            # Mais le reste de la description est conforme
            statut = 'prefixe_incorrect'

        # Filtrer par statut
        if statut_filter and statut != statut_filter:
            continue

        # Ajouter au résultat
        resultats.append({
            'id_diamex': entry.id,
            'prog': entry.prog,
            'date_m': entry.date_m.strftime('%Y-%m-%d') if entry.date_m else None,
            'description': entry.description,
            'detail': entry.detail,
            'compte_code': entry.compte_code,
            'montant_out': float(entry.montant_out) if entry.montant_out else 0,
            'prefixe': info['prefixe'],
            'nom_employe': info['nom_employe'],
            'type_paiement': info['type_paiement'],
            'annee': info['annee'],
            'mois': info['mois'],
            'employe_trouve': employe_obj is not None,
            'employe_id': str(employe_obj.id) if employe_obj else None,
            'employe_surnom': employe_obj.surnom if employe_obj else None,
            'poste': employe_obj.poste.nom_poste if employe_obj and employe_obj.poste else None,
            'prefixe_poste': employe_obj.poste.prefixe if employe_obj and employe_obj.poste else None,
            'prefixe_valide': prefixe_valide,  # NOUVEAU: Indique si le préfixe correspond au poste actuel OU ancien
            'compte_correct': verification_compte['correct'],
            'compte_attendu': verification_compte['attendu'],
            'erreur_compte': verification_compte['erreur'],
            'erreurs_description': info['erreurs'],
            'conforme': info['conforme'],
            'statut': statut,
        })

        # Mettre à jour les stats
        stats['total'] += 1
        if statut == 'conforme':
            stats['conformes'] += 1
        elif statut == 'non_conforme':
            stats['non_conformes'] += 1
        elif statut == 'compte_incorrect':
            stats['compte_incorrect'] += 1
        elif statut == 'prefixe_incorrect':
            stats['prefixe_incorrect'] += 1

        if not info['type_paiement']:
            stats['type_inconnu'] += 1

    # Récupérer les listes pour les filtres (utile pour la version print)
    comptes_employes_list = list(_filter_comptes_by_scope(Compte.objects.filter(
        employe_obligatoire=True
    ), request.user).values_list('compte', flat=True))

    # Années disponibles
    annees_qs = _filter_diamex_by_scope(BaseDiameX.objects.filter(
        compte_code__in=comptes_employes_list,
        date_m__isnull=False
    ), request.user).values_list('date_m__year', flat=True).distinct()
    annees_disponibles = sorted(set(annees_qs), reverse=True)

    # Programmes disponibles
    progs_qs = _filter_diamex_by_scope(BaseDiameX.objects.filter(
        compte_code__in=comptes_employes_list,
        prog__isnull=False
    ), request.user).exclude(prog='').values_list('prog', flat=True).distinct().order_by('prog')
    progs_disponibles = list(progs_qs)

    return JsonResponse({
        'success': True,
        'resultats': resultats,
        'stats': stats,
        'total': len(resultats),
        'annees_disponibles': annees_disponibles,
        'progs_disponibles': progs_disponibles,
    })


@login_required
@require_http_methods(["POST"])
def api_modifier_description_diamex(request):
    """
    API pour modifier la description d'une entrée DiameX
    Met à jour à la fois Django et Access
    """
    try:
        import json
        data = json.loads(request.body)

        entry_id = data.get('entry_id')
        nouvelle_description = data.get('description')

        if not entry_id or not nouvelle_description:
            return JsonResponse({
                'success': False,
                'error': 'ID et description requis'
            }, status=400)

        # Récupérer l'entrée DiameX
        try:
            entry = _filter_diamex_by_scope(BaseDiameX.objects.all(), request.user).get(id=entry_id)
        except BaseDiameX.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Entrée introuvable'
            }, status=404)

        # Récupérer aussi le compte Cat s'il est fourni
        nouveau_compte_cat = data.get('compte_cat')

        # Sauvegarder anciennes valeurs pour log
        ancienne_description = entry.description
        ancien_compte_cat = entry.compte_code

        # Mettre à jour Django (PostgreSQL)
        fields_updated = []
        if nouvelle_description != ancienne_description:
            entry.description = nouvelle_description
            fields_updated.append('description')

        if nouveau_compte_cat and nouveau_compte_cat != ancien_compte_cat:
            entry.compte_code = nouveau_compte_cat
            fields_updated.append('compte_code')

        if fields_updated:
            entry.save(update_fields=fields_updated)

        # Mettre à jour Access si prog disponible
        access_updated = False
        access_error = None

        if entry.prog:
            try:
                # Trouver la base Access correspondante
                base_diamex = trouver_base_access_par_prog(entry.prog)

                if base_diamex and base_diamex.chemin_base_diamex:
                    import pyodbc
                    import os

                    # Chemin complet vers la base Access (dossier + nom fichier)
                    chemin_dossier = base_diamex.chemin_base_diamex
                    nom_fichier = base_diamex.base_diamex
                    chemin_access = os.path.join(chemin_dossier, nom_fichier)

                    # Connexion à la base Access
                    conn_str = (
                        r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                        f'DBQ={chemin_access};'
                    )
                    conn = pyodbc.connect(conn_str)
                    cursor = conn.cursor()

                    # Construire la requête UPDATE dynamiquement
                    set_clauses = []
                    params = []

                    if nouvelle_description != ancienne_description:
                        set_clauses.append("Info = ?")
                        params.append(nouvelle_description)

                    if nouveau_compte_cat and nouveau_compte_cat != ancien_compte_cat:
                        set_clauses.append("Cat = ?")
                        params.append(nouveau_compte_cat)

                    if set_clauses:
                        params.append(entry.id_access)  # ID à la fin pour WHERE
                        sql = f"UPDATE DATA SET {', '.join(set_clauses)} WHERE ID = ?"
                        cursor.execute(sql, params)
                        conn.commit()

                    conn.close()

                    access_updated = True
                else:
                    access_error = "Base Access non trouvée pour prog: " + entry.prog

            except Exception as e:
                access_error = str(e)

        # Préparer la réponse
        response_data = {
            'success': True,
            'django_updated': True,
            'access_updated': access_updated,
            'message': 'Description mise à jour avec succès'
        }

        if access_error:
            response_data['access_error'] = access_error
            response_data['message'] = 'Django mis à jour, mais erreur Access: ' + access_error

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def api_get_base_access_info(request):
    """
    API pour récupérer les infos de la base Access correspondant à un prog
    """
    prog = request.GET.get('prog')

    if not prog:
        return JsonResponse({
            'success': False,
            'error': 'Prog requis'
        }, status=400)

    try:
        if not getattr(request.user, 'is_superuser', False):
            organisation_id = _get_user_organisation_id(request.user)
            allowed_progs = set(
                Base.objects.filter(organisation_id=organisation_id)
                .exclude(prog_diamex__isnull=True)
                .exclude(prog_diamex='')
                .values_list('prog_diamex', flat=True)
                .distinct()
            ) if organisation_id else set()
            if prog not in allowed_progs:
                return JsonResponse({
                    'success': False,
                    'error': 'Acces refuse pour ce programme'
                }, status=403)

        # Trouver la base Access correspondante
        base_diamex = trouver_base_access_par_prog(prog)

        if base_diamex:
            import os
            chemin_complet = os.path.join(
                base_diamex.chemin_base_diamex or '',
                base_diamex.base_diamex
            )

            return JsonResponse({
                'success': True,
                'nom_fichier': base_diamex.base_diamex,
                'chemin_dossier': base_diamex.chemin_base_diamex or '',
                'chemin_complet': chemin_complet
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Base Access non trouvée pour prog: ' + prog
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def api_suggerer_compte_cat(request):
    """
    API pour suggérer le compte Cat basé sur l'analyse de la description
    Retourne les comptes possibles selon le préfixe (poste) et le type de paiement
    """
    description = request.GET.get('description', '')
    employe_surnom = request.GET.get('employe_surnom', '')

    if not description:
        return JsonResponse({
            'success': False,
            'error': 'Description requise'
        }, status=400)

    try:
        # Extraire les informations de la description
        info = extraire_info_description(description)

        # Trouver l'employé par surnom (pour récupérer son poste)
        employe = None
        if employe_surnom:
            employe = _filter_employes_by_scope(
                Employe.objects.filter(surnom__iexact=employe_surnom),
                request.user
            ).first()

        # Si pas trouvé par surnom, essayer avec le préfixe extrait
        if not employe and info.get('prefixe'):
            # Chercher un poste avec ce préfixe
            poste = Poste.objects.filter(prefixe=info['prefixe']).first()
            if poste:
                # Prendre un employé de ce poste pour avoir les comptes
                employe = _filter_employes_by_scope(
                    Employe.objects.filter(poste=poste),
                    request.user
                ).first()

        comptes_suggeres = []
        explication = []

        if employe and employe.poste:
            poste = employe.poste
            type_paiement = info.get('type_paiement')

            # Récupérer le compte selon le type de paiement
            if type_paiement == 'salaire':
                if poste.compte_salaire:
                    comptes_suggeres.append(poste.compte_salaire.compte)
                    explication.append(f"Compte salaire du poste {poste.nom_poste}")

            elif type_paiement == 'irsa':
                if poste.compte_irsa:
                    comptes_suggeres.append(poste.compte_irsa.compte)
                    explication.append(f"Compte IRSA du poste {poste.nom_poste}")

            elif type_paiement in ['cnaps', 'fmfp', 'mutuelle_sante']:
                if poste.compte_cnaps_fmfp_sante:
                    comptes_suggeres.append(poste.compte_cnaps_fmfp_sante.compte)
                    explication.append(f"Compte charges sociales du poste {poste.nom_poste}")

            elif type_paiement in ['indemnite_terrain', 'indemnite_hors_zone', 'indemnite_stage']:
                if poste.compte_indemnite:
                    comptes_suggeres.append(poste.compte_indemnite.compte)
                    explication.append(f"Compte indemnités du poste {poste.nom_poste}")

            elif type_paiement in ['frais_scolarite', 'frais_medicaux']:
                if poste.compte_salaire:
                    comptes_suggeres.append(poste.compte_salaire.compte)
                    explication.append(f"Compte {type_paiement.replace('_', ' ')} (même que salaire) du poste {poste.nom_poste}")

            elif type_paiement == 'frais_deplacement':
                # Comptes génériques
                comptes_generiques = COMPTES_TYPES_PAIEMENT.get(type_paiement, [])
                comptes_suggeres.extend(comptes_generiques)
                explication.append(f"Comptes génériques pour {type_paiement}")

        # Si aucun compte trouvé via le poste, utiliser les comptes génériques
        if not comptes_suggeres and info.get('type_paiement'):
            type_paiement = info['type_paiement']
            comptes_generiques = COMPTES_TYPES_PAIEMENT.get(type_paiement, [])
            comptes_suggeres.extend(comptes_generiques)
            explication.append(f"Comptes génériques pour {type_paiement}")

        return JsonResponse({
            'success': True,
            'comptes_suggeres': comptes_suggeres,
            'compte_principal': comptes_suggeres[0] if comptes_suggeres else None,
            'explication': ' | '.join(explication) if explication else 'Aucune suggestion disponible',
            'type_paiement': info.get('type_paiement'),
            'prefixe': info.get('prefixe'),
            'conforme': info.get('conforme'),
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def api_suggerer_compte_cat(request):
    """
    Version surchargée: suggestion de compte basée sur l'employé trouvé
    puis sur tous les postes partageant le même préfixe.
    """
    description = request.GET.get('description', '')
    employe_surnom = request.GET.get('employe_surnom', '')

    if not description:
        return JsonResponse({
            'success': False,
            'error': 'Description requise'
        }, status=400)

    try:
        info = extraire_info_description(description)

        employe = None
        if employe_surnom:
            employe = _filter_employes_by_scope(
                Employe.objects.filter(surnom__iexact=employe_surnom),
                request.user
            ).first()

        comptes_suggeres = []
        explication = []
        type_paiement = info.get('type_paiement')

        postes_candidates = []
        postes_seen = set()
        if employe and employe.poste:
            postes_candidates.append(employe.poste)
            postes_seen.add(getattr(employe.poste, 'id', id(employe.poste)))

        if info.get('prefixe'):
            for poste_prefixe in _get_postes_for_prefix(info['prefixe']):
                poste_key = getattr(poste_prefixe, 'id', id(poste_prefixe))
                if poste_key not in postes_seen:
                    postes_candidates.append(poste_prefixe)
                    postes_seen.add(poste_key)

        if type_paiement == 'frais_deplacement':
            comptes_generiques = COMPTES_TYPES_PAIEMENT.get(type_paiement, [])
            comptes_suggeres.extend(comptes_generiques)
            explication.append(f"Comptes génériques pour {type_paiement}")
        else:
            for poste in postes_candidates:
                compte_suggere, _ = _get_compte_config_for_poste(poste, type_paiement)
                if compte_suggere and compte_suggere not in comptes_suggeres:
                    comptes_suggeres.append(compte_suggere)
                    explication.append(f"Compte {type_paiement.replace('_', ' ')} du poste {poste.nom_poste}")

        if not comptes_suggeres and type_paiement:
            comptes_generiques = COMPTES_TYPES_PAIEMENT.get(type_paiement, [])
            comptes_suggeres.extend(comptes_generiques)
            if comptes_generiques:
                explication.append(f"Comptes génériques pour {type_paiement}")

        return JsonResponse({
            'success': True,
            'comptes_suggeres': comptes_suggeres,
            'compte_principal': comptes_suggeres[0] if comptes_suggeres else None,
            'explication': ' | '.join(explication) if explication else 'Aucune suggestion disponible',
            'type_paiement': info.get('type_paiement'),
            'prefixe': info.get('prefixe'),
            'conforme': info.get('conforme'),
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)



@login_required
@require_http_methods(['GET'])
def api_comptes_employes(request):
    """API pour récupérer les comptes avec employe_obligatoire=True"""
    try:
        # Récupérer les comptes des employés, triés par code de compte
        comptes = _filter_comptes_by_scope(Compte.objects.filter(
            employe_obligatoire=True
        ), request.user).values('id', 'compte', 'nom_compte').order_by('compte')

        comptes_list = list(comptes)

        return JsonResponse({
            'success': True,
            'comptes': comptes_list
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

