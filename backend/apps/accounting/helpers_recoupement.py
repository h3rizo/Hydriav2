"""
Fonctions d'aide pour les recoupements bidirectionnels DiameX <-> Application
"""

import os
from decimal import Decimal
from django.db.models import Sum, Q
from apps.accounting.models import BaseDiameX
from apps.organization.models import CompteTable
from apps.employees.models import EmployeBaseDiameX


def verifier_recoupement_inverse(comptes_cat, fichiers_sources=None, type_recoupement='planning', allowed_progs=None):
    """
    Vérification inverse : pour chaque ligne DiameX (avec comptes donnés),
    chercher si elle correspond à des données de l'application.

    Args:
        comptes_cat (list): Liste de codes de compte (ex: ['625200', '625100'])
        fichiers_sources (list): Liste de fichiers sources à filtrer (optionnel)
        type_recoupement (str): Type de recoupement pour déterminer quelle table vérifier
            - 'planning' → plannings_details (frais de déplacement, etc.)
            - 'salaires' → salaires
            - 'indemnites' → indemnites
            - 'frais_medicaux' → frais_medicaux
            - 'frais_scolarite' → frais_scolarite
            - 'releves' → releves
            - 'achats' → achats
            - 'cartes_sociales' → conso_carte_sociale
            - 'demandes_bp' → points_eau (demandes)
            - 'devis_bp' → points_eau (devis)

    Returns:
        dict: {
            'recoupements_inverses': [
                {
                    'id_diamex': int,
                    'id_access': int,
                    'prog': str,
                    'date_m': date,
                    'description': str,
                    'montant_in': float,
                    'montant_out': float,
                    'compte_code': str,
                    'fichier_source': str,
                    'application_trouve': bool,
                    'application_records': [],  # Liste des enregistrements correspondants
                    'total_application_in': Decimal,
                    'total_application_out': Decimal,
                    'ecart_in': Decimal,
                    'ecart_out': Decimal,
                    'status': 'ok' | 'warning' | 'error' | 'missing'
                },
                ...
            ],
            'stats': {
                'total': int,
                'ok': int,
                'warning': int,
                'error': int,
                'missing': int
            }
        }
    """

    # Récupérer toutes les lignes DiameX avec ces comptes
    diamex_query = BaseDiameX.objects.filter(
        compte_code__in=comptes_cat
    ).select_related('compte')

    # Filtrer par fichiers sources si demandé
    if fichiers_sources:
        diamex_query = diamex_query.filter(fichier_source__in=fichiers_sources)
    if allowed_progs is not None:
        diamex_query = diamex_query.filter(prog__in=allowed_progs)

    diamex_entries = diamex_query.order_by('-date_m', '-id_access')

    # Récupérer les chemins de base pour reconstituer les scans
    bases_employe = EmployeBaseDiameX.objects.all()
    if allowed_progs is not None:
        bases_employe = bases_employe.filter(base_diamex__in=allowed_progs)
    bases_dict = {}
    for base in bases_employe:
        bases_dict[base.base_diamex] = {
            'chemin': base.chemin_base_diamex or '',
            'chemin_complet': base.chemin_complet or ''
        }

    # Initialiser les résultats
    recoupements_inverses = []
    stats = {
        'total': 0,
        'trouves': 0,  # Entrées DiameX qui existent dans l'application (ignorées)
        'non_trouves': 0,  # Entrées DiameX sans correspondance (anomalies affichées)
        'ecart_total': Decimal('0')  # Somme des montants non trouvés
    }

    # Pour chaque ligne DiameX, chercher la correspondance dans l'application
    for entry in diamex_entries:
        id_access = entry.id_access
        prog = entry.prog

        # Reconstituer le chemin complet du scan
        full_scan_path = None
        scan_relatif = entry.scan or ''

        if scan_relatif:
            # Essayer de trouver la base correspondante
            base_info = bases_dict.get(prog)

            # Si pas de match exact, chercher par mots-clés dans le prog
            if not base_info or not base_info['chemin']:
                # Extraire les mots-clés du prog (ex: "EHA-Soakoja-Tana" → "Tana")
                prog_keywords = prog.split('-')
                for keyword in reversed(prog_keywords):  # Commencer par la fin (ex: "Tana")
                    if len(keyword) > 3:  # Ignorer les mots trop courts
                        for base_name, base_data in bases_dict.items():
                            if keyword.lower() in base_name.lower():
                                base_info = base_data
                                break
                        if base_info and base_info['chemin']:
                            break

            if base_info and base_info['chemin']:
                chemin_base = base_info['chemin']
                # Nettoyer le chemin relatif (enlever le "." au début)
                scan_clean = scan_relatif.lstrip('.')
                # Si scan contient déjà le chemin absolu, ne pas concaténer
                if scan_relatif.startswith(chemin_base):
                    full_scan_path = scan_relatif
                else:
                    full_scan_path = chemin_base + scan_clean
            else:
                # Si chemin base non trouvé, garder le chemin relatif tel quel
                full_scan_path = scan_relatif

        # Initialiser le résultat pour cette ligne
        result = {
            'id_diamex': entry.id,
            'id_access': id_access,
            'prog': prog,
            'date_m': entry.date_m,
            'description': entry.description,
            'montant_in': entry.montant_in,
            'montant_out': entry.montant_out,
            'compte_code': entry.compte_code,
            'fichier_source': entry.fichier_source,
            'scan': full_scan_path,  # Chemin complet vers le justificatif
            'application_trouve': False,
            'application_records': [],
            'total_application_in': Decimal('0'),
            'total_application_out': Decimal('0'),
            'ecart_in': None,
            'ecart_out': None,
            'status': 'missing'
        }

        # Chercher les correspondances selon le type de recoupement
        if type_recoupement == 'planning':
            result = _verifier_planning_inverse(entry, result)
        elif type_recoupement == 'salaires':
            result = _verifier_salaires_inverse(entry, result)
        elif type_recoupement == 'indemnites':
            result = _verifier_indemnites_inverse(entry, result)
        elif type_recoupement == 'frais_medicaux':
            result = _verifier_frais_medicaux_inverse(entry, result)
        elif type_recoupement == 'frais_scolarite':
            result = _verifier_frais_scolarite_inverse(entry, result)
        elif type_recoupement == 'releves':
            result = _verifier_releves_inverse(entry, result)
        elif type_recoupement == 'achats':
            result = _verifier_achats_inverse(entry, result)
        elif type_recoupement == 'cartes_sociales':
            result = _verifier_cartes_sociales_inverse(entry, result)
        elif type_recoupement in ['demandes_bp', 'devis_bp']:
            result = _verifier_points_eau_inverse(entry, result, type_recoupement)

        # ✅ VÉRIFICATION INVERSE : On garde UNIQUEMENT les entrées NON trouvées dans l'application
        # Si application_trouve = True, cela signifie que l'entrée existe déjà dans le recoupement normal
        # L'objectif de la vérification inverse est de trouver les transactions DiameX orphelines
        stats['total'] += 1

        if not result['application_trouve']:
            # Entrée DiameX sans correspondance dans l'application = vraie anomalie
            result['status'] = 'missing'
            recoupements_inverses.append(result)
            stats['non_trouves'] += 1

            # Calculer le montant de l'écart (montant DiameX non enregistré dans l'application)
            montant_ecart = abs(Decimal(str(entry.montant_in))) + abs(Decimal(str(entry.montant_out)))
            stats['ecart_total'] += montant_ecart
        else:
            # Entrée trouvée dans l'application = déjà dans le recoupement normal, on l'ignore
            stats['trouves'] += 1

    return {
        'recoupements_inverses': recoupements_inverses,
        'stats': stats
    }


def _verifier_planning_inverse(entry, result):
    """
    Cherche les PlanningDetails correspondant à une ligne DiameX
    Clé: entry.id_access = numeroDiameX, entry.prog = BaseDiameX
    """
    from apps.planning.models import PlanningDetail

    details = PlanningDetail.objects.filter(
        numeroDiameX=entry.id_access,
        BaseDiameX=entry.prog
    ).select_related('designation', 'planning', 'planning__employe')

    if details.exists():
        result['application_trouve'] = True

        # Grouper par type (recette/dépense)
        for detail in details:
            result['application_records'].append({
                'type': 'PlanningDetail',
                'id': str(detail.id),
                'designation': detail.designation.nom if detail.designation else 'Sans désignation',
                'employe': detail.planning.employe.nom_complet if detail.planning and detail.planning.employe else 'Sans employé',
                'date': detail.planning.date if detail.planning else None,
                'montant': float(detail.montant),
                'type_designation': detail.designation.type_avance_caissiere if detail.designation else None
            })

            # Sommer selon type
            if detail.designation and detail.designation.type_avance_caissiere == 'recette':
                result['total_application_in'] += Decimal(str(detail.montant))
            else:
                result['total_application_out'] += Decimal(str(detail.montant))

    return result


def _verifier_salaires_inverse(entry, result):
    """
    Cherche les Salaires correspondant à une ligne DiameX
    """
    from apps.employees.models import Salaire

    salaires = Salaire.objects.filter(
        numero_diamex=entry.id_access,
        base_diamex=entry.prog
    ).select_related('employe', 'poste')

    if salaires.exists():
        result['application_trouve'] = True

        for salaire in salaires:
            result['application_records'].append({
                'type': 'Salaire',
                'id': str(salaire.id),
                'employe': salaire.employe.nom_complet if salaire.employe else 'Sans employé',
                'poste': salaire.poste.nom_poste if salaire.poste else 'Sans poste',
                'mois': salaire.mois,
                'annee': salaire.annee,
                'montant': float(salaire.salaire_net),
            })

            # Salaires sont toujours des dépenses (OUT)
            result['total_application_out'] += Decimal(str(salaire.salaire_net))

    return result


def _verifier_indemnites_inverse(entry, result):
    """
    Cherche les Indemnités correspondant à une ligne DiameX
    """
    from apps.employees.models import Indemnite

    indemnites = Indemnite.objects.filter(
        numero_diamex=entry.id_access,
        base_diamex=entry.prog
    ).select_related('employe', 'type_indemnite')

    if indemnites.exists():
        result['application_trouve'] = True

        for indemnite in indemnites:
            result['application_records'].append({
                'type': 'Indemnite',
                'id': str(indemnite.id),
                'employe': indemnite.employe.nom_complet if indemnite.employe else 'Sans employé',
                'type': indemnite.type_indemnite.nom if indemnite.type_indemnite else 'Sans type',
                'mois': indemnite.mois,
                'annee': indemnite.annee,
                'montant': float(indemnite.montant),
            })

            # Indemnités sont des dépenses (OUT)
            result['total_application_out'] += Decimal(str(indemnite.montant))

    return result


def _verifier_frais_medicaux_inverse(entry, result):
    """
    Cherche les FraisMedicaux correspondant à une ligne DiameX
    """
    from apps.employees.models import FraisMedicaux

    frais = FraisMedicaux.objects.filter(
        numero_diamex=entry.id_access,
        base_diamex=entry.prog
    ).select_related('employe')

    if frais.exists():
        result['application_trouve'] = True

        for fm in frais:
            result['application_records'].append({
                'type': 'FraisMedicaux',
                'id': str(fm.id),
                'employe': fm.employe.nom_complet if fm.employe else 'Sans employé',
                'date': fm.date_soin,
                'montant': float(fm.montant),
            })

            # Frais médicaux sont des dépenses (OUT)
            result['total_application_out'] += Decimal(str(fm.montant))

    return result


def _verifier_frais_scolarite_inverse(entry, result):
    """
    Cherche les FraisScolarite correspondant à une ligne DiameX
    """
    from apps.employees.models import FraisScolarite

    frais = FraisScolarite.objects.filter(
        numero_diamex=entry.id_access,
        base_diamex=entry.prog
    ).select_related('employe')

    if frais.exists():
        result['application_trouve'] = True

        for fs in frais:
            result['application_records'].append({
                'type': 'FraisScolarite',
                'id': str(fs.id),
                'employe': fs.employe.nom_complet if fs.employe else 'Sans employé',
                'enfant': fs.nom_enfant,
                'annee_scolaire': fs.annee_scolaire,
                'montant': float(fs.montant),
            })

            # Frais de scolarité sont des dépenses (OUT)
            result['total_application_out'] += Decimal(str(fs.montant))

    return result


def _verifier_releves_inverse(entry, result):
    """
    Cherche les Relevés correspondant à une ligne DiameX
    """
    from apps.billing.models import Releve

    releves = Releve.objects.filter(
        numeroDiameX=entry.id_access,
        baseDiameX=entry.prog
    ).select_related('point_eau', 'point_eau__ouvrage')

    if releves.exists():
        result['application_trouve'] = True

        for releve in releves:
            # Récupérer le nom du point d'eau (utiliser code_point_eau ou nomabonne)
            point_eau_nom = 'Sans point d\'eau'
            if releve.point_eau:
                if releve.point_eau.code_point_eau:
                    point_eau_nom = releve.point_eau.code_point_eau
                elif releve.point_eau.nomabonne:
                    point_eau_nom = releve.point_eau.nomabonne

            result['application_records'].append({
                'type': 'Releve',
                'id': str(releve.id),
                'point_eau': point_eau_nom,
                'date_releve': releve.datereleve,
                'nouvel_index': float(releve.nouvelindex) if releve.nouvelindex else 0,
                'volume': float(releve.consommation) if releve.consommation else 0,
                'montant': float(releve.montant) if releve.montant else 0,
            })

            # Relevés sont des recettes (IN)
            if releve.montant:
                result['total_application_in'] += Decimal(str(releve.montant))

    return result


def _verifier_achats_inverse(entry, result):
    """
    Cherche les Achats correspondant à une ligne DiameX
    """
    from apps.inventory.models import Purchase

    achats = Purchase.objects.filter(
        numeroDiameX=entry.id_access,  # ✅ Corrigé: CamelCase
        baseDiameX=entry.prog  # ✅ Corrigé: CamelCase
    ).select_related('fournisseur')  # ✅ Corrigé: fournisseur au lieu de supplier

    if achats.exists():
        result['application_trouve'] = True

        for achat in achats:
            result['application_records'].append({
                'type': 'Purchase',
                'id': str(achat.id),
                'fournisseur': achat.fournisseur.nom_fournisseur if achat.fournisseur else 'Sans fournisseur',  # ✅ Corrigé
                'date': achat.purchase_date,
                'montant': float(achat.total_amount),
            })

            # Achats sont des dépenses (OUT)
            result['total_application_out'] += Decimal(str(achat.total_amount))

    return result


def _verifier_cartes_sociales_inverse(entry, result):
    """
    Cherche les ConsommationsCarteSociale correspondant à une ligne DiameX
    """
    from apps.billing.models import ConsoCarteSociale as ConsommationCarteSociale

    consommations = ConsommationCarteSociale.objects.filter(
        numeroDiameX=str(entry.id_access),  # Convertir en string car numeroDiameX est CharField
        baseDiameX=entry.prog
    ).select_related('carte_sociale')

    if consommations.exists():
        result['application_trouve'] = True

        for conso in consommations:
            # Récupérer le point d'eau via carte_sociale
            point_eau_nom = 'Sans point d\'eau'
            if conso.carte_sociale and hasattr(conso.carte_sociale, 'point_eau') and conso.carte_sociale.point_eau:
                point_eau_nom = conso.carte_sociale.point_eau.code_point_eau

            result['application_records'].append({
                'type': 'ConsommationCarteSociale',
                'id': str(conso.id),
                'carte': conso.carte_sociale.numero_carte if conso.carte_sociale else 'Sans carte',
                'point_eau': point_eau_nom,
                'date': conso.date,  # Champ correct : 'date' pas 'date_consommation'
                'mois': conso.date.strftime('%Y-%m') if conso.date else '',
                'volume': float(conso.volume_total) if conso.volume_total else 0,
                'montant': float(conso.montant_paye) if conso.montant_paye else 0,
            })

            # Cartes sociales sont des recettes (IN)
            if conso.montant_paye:
                result['total_application_in'] += Decimal(str(conso.montant_paye))

    return result


def _verifier_points_eau_inverse(entry, result, type_recoupement):
    """
    Cherche les PointsEau correspondant à une ligne DiameX
    (pour demandes BP ou devis BP)
    """
    from apps.billing.models import PointEau

    # Les champs numero DiameX des points d'eau sont numériques.
    # Si id_access n'est pas numérique (ex: ''), on ignore cette entrée.
    try:
        id_access_num = int(str(entry.id_access).strip())
    except (TypeError, ValueError):
        return result

    if type_recoupement == 'demandes_bp':
        points_eau = PointEau.objects.filter(
            numero_diamex_demande=id_access_num,
            base_diamex_demande=entry.prog
        ).select_related('ouvrage')
    else:  # devis_bp
        points_eau = PointEau.objects.filter(
            numero_diamex_devis=id_access_num,
            base_diamex_devis=entry.prog
        ).select_related('ouvrage')

    if points_eau.exists():
        result['application_trouve'] = True

        for pe in points_eau:
            if type_recoupement == 'demandes_bp':
                montant = float(pe.montant_demande) if pe.montant_demande else 0
            else:
                montant = float(pe.montant_devis) if pe.montant_devis else 0

            # Récupérer le nom du point d'eau (utiliser code_point_eau ou nomabonne)
            point_eau_nom = 'Sans nom'
            if pe.code_point_eau:
                point_eau_nom = pe.code_point_eau
            elif pe.nomabonne:
                point_eau_nom = pe.nomabonne

            result['application_records'].append({
                'type': 'PointEau',
                'id': str(pe.id),
                'nom': point_eau_nom,
                'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'Sans ouvrage',
                'type_transaction': type_recoupement,
                'montant': montant,
            })

            # Demandes et devis peuvent être des recettes ou dépenses selon le contexte
            # Par défaut considérés comme recettes (IN)
            result['total_application_in'] += Decimal(str(montant))

    return result
