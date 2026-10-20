"""
Vue unifiée de vérification comptable
Combine les 4 workflows :
1. Vérification scans (pièces justificatives)
2. Vérification paiements employés (charte + comptes)
3. Vérification fournisseurs (charte + comptes)
4. Vérification autres comptes (charte + comptes)
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Sum, Case, When, IntegerField
from collections import defaultdict
from decimal import Decimal
import re

from .models import BaseDiameX, ScanVerificationCache
from apps.employees.models import Employe, Poste, EmployeBaseDiameX
from apps.billing.models import Fournisseur
from apps.organization.models import Compte
import os


# ===== PATTERNS DE VÉRIFICATION =====

# Patterns pour paiements employés
PATTERNS_PAIEMENTS_EMPLOYES = {
    'salaire': r'_Salaire_(\d{4})\s+(\d{1,2})',
    'irsa': r'_IRSA_(\d{4})\s+(\d{1,2})',
    'cnaps': r'_Charge CNaPS_(\d{4})\s+(\d{1,2})',
    'fmfp': r'_Charge FMFP_(\d{4})\s+(\d{1,2})',
    'mutuelle_sante': [
        r'_Charge AMIT_(\d{4})\s+(\d{1,2})',
        r'_Charge OSIEFSoVa_(\d{4})\s+(\d{1,2})',
    ],
    'frais_medicaux': [
        r'_(?:[Rr]emboursement )?[Ff]rais médicaux_(\d{4})\s+(\d{1,2})',  # Format: 2025 09
        r'_(?:[Rr]emboursement )?[Ff]rais médicaux_(?:Janvier|Février|Mars|Avril|Mai|Juin|Juillet|Août|Septembre|Octobre|Novembre|Décembre)\s+(\d{4})',  # Format: Septembre 2025
    ],
    'frais_scolarite': r'_(?:Remboursement )?[Ff]rais (?:de )?scolarité_(\d{4})\s+(\d{1,2})',
    'frais_deplacement': r'_[Ff]rais de déplacement_(\d{4})\s+(\d{1,2})',
    'solde_tout_compte': r'_[Ss]olde (?:de )?tout compte',  # Nouveau pattern pour solde de tout compte
    'prime': r'_[Pp]rime',  # Pattern pour primes (tous types)
    'indemnite_terrain': [
        r'_Indemnité terrain_+(\d{4})\s+(\d{1,2})',  # Accepte un ou plusieurs underscores
        r'_Indemnité terrain_+\d+\s*x\s*[\d\s]+Ar_(\d{4})\s+(\d{1,2})',  # Accepte un ou plusieurs underscores
    ],
    'indemnite_hors_zone': [
        r'_Indemnité [Hh]ors zone_(\d{4})\s+(\d{1,2})',
        r'_Indemnité [Hh]ors zone_+\d+\s*x\s*[\d\s]+Ar_',
    ],
}

COMPTES_PAIEMENTS_EMPLOYES = {
    'salaire': ['641613', '641612', '641611', '641900'],  # Ajout 641900
    'irsa': ['631411'],
    'cnaps': ['646311'],
    'fmfp': ['646311'],
    'mutuelle_sante': ['646312', '646311'],
    'frais_medicaux': ['646312'],
    'frais_scolarite': ['646313'],
    'frais_deplacement': ['625200', '625100'],
    'solde_tout_compte': [],  # Sera validé via compte_salaire du poste
    'prime': [],  # Sera validé via compte_salaire du poste
    'indemnite_terrain': ['625107'],
    'indemnite_hors_zone': ['625107'],
}

# Patterns pour fournisseurs
PATTERNS_FOURNISSEURS = {
    'achat_materiel': r'_Achat\s+(?:de\s+)?matériel',
    'achat_fourniture': r'_Achat\s+(?:de\s+)?fourniture',
    'prestation': r'_Prestation',
    'location': r'_Location',
    'carburant': r'_Carburant',
}

COMPTES_FOURNISSEURS = {
    'achat_materiel': ['220000', '605000'],
    'achat_fourniture': ['606000', '607000'],
    'prestation': ['604000', '628000'],
    'location': ['613000', '614000'],
    'carburant': ['606100'],
}


def verifier_pattern_description(description, patterns):
    """
    Vérifie si la description correspond à un des patterns
    Retourne (True/False, type_trouve, match_object)
    """
    if not description:
        return False, None, None

    for type_paiement, pattern_list in patterns.items():
        # Si pattern_list est une liste, tester tous les patterns
        if isinstance(pattern_list, list):
            for pattern in pattern_list:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    return True, type_paiement, match
        else:
            # Sinon, tester le pattern unique
            match = re.search(pattern_list, description, re.IGNORECASE)
            if match:
                return True, type_paiement, match

    return False, None, None


def verifier_compte_cat(compte_code, comptes_attendus):
    """
    Vérifie si le compte Cat correspond à un des comptes attendus
    """
    if not compte_code or not comptes_attendus:
        return False

    for compte_attendu in comptes_attendus:
        if compte_code.startswith(compte_attendu):
            return True

    return False


def enrichir_avec_scan(entry, bases_dict):
    """
    Enrichit une entrée avec les informations de scan
    Retourne (scan_status, full_scan_path)
    """
    has_scan = entry.scan and entry.scan.strip()
    full_scan_path = None
    scan_status = 'missing'  # missing, invalid, exists, dead

    from .scan_resolution import copie_serveur_existe
    if has_scan and copie_serveur_existe(entry):
        # Copie serveur (VPS) presente : prioritaire sur le chemin local
        return 'exists', entry.scan_importe.name

    if has_scan:
        # Trouver la base correspondante via fichier_source
        base_info = bases_dict.get(entry.fichier_source)

        if base_info and base_info['chemin']:
            chemin_base = base_info['chemin']
            scan_relatif = entry.scan

            # Nettoyer les caractères # au début et à la fin
            scan_relatif = scan_relatif.strip('#')

            # Enlever le "." au début si présent
            if scan_relatif.startswith('.'):
                scan_relatif = scan_relatif[1:]

            # Construire le chemin complet
            if scan_relatif.startswith(chemin_base):
                full_scan_path = scan_relatif
            else:
                full_scan_path = chemin_base + scan_relatif

            # Vérifier si le fichier existe
            if os.path.exists(full_scan_path):
                scan_status = 'exists'
            else:
                scan_status = 'dead'
        else:
            scan_status = 'invalid'  # Prog introuvable ou chemin base manquant

    return scan_status, full_scan_path


@login_required
def verification_unifiee(request):
    """
    Page unifiée de vérification comptable avec tous les contrôles
    """
    # Récupérer les filtres
    filter_mois = request.GET.get('mois', '')
    filter_fichier = request.GET.get('fichier', '')
    filter_prog = request.GET.get('prog', '')
    filter_type = request.GET.get('type', 'tous')  # tous/scans/employes/fournisseurs/autres

    # Base queryset
    entries = BaseDiameX.objects.all().select_related('compte', 'journal')

    # Appliquer les filtres de base
    if filter_mois:
        year, month = filter_mois.split('-')
        entries = entries.filter(date_m__year=int(year), date_m__month=int(month))

    if filter_fichier:
        entries = entries.filter(fichier_source=filter_fichier)

    if filter_prog:
        entries = entries.filter(prog=filter_prog)

    # Filtrer seulement les entrées avec montant
    entries = entries.filter(Q(montant_in__gt=0) | Q(montant_out__gt=0))

    # Récupérer toutes les bases DiameX pour matcher base_diamex -> chemin (pour enrichissement scan)
    bases_dict = {}
    for base in EmployeBaseDiameX.objects.all():
        if base.base_diamex:
            bases_dict[base.base_diamex] = {
                'chemin': base.chemin_base_diamex or '',
                'nom': base.base_diamex,
            }

    # ===== SECTION 1: VÉRIFICATION SCANS =====
    # Exclure les comptes qui n'ont pas besoin de scan
    entries_scan = entries.exclude(
        Q(compte_code__icontains='00BOOK') |
        Q(compte_code__icontains='00PERS')
    )

    # Récupérer le cache des scans
    cache = ScanVerificationCache.objects.first()
    scans_valides_ids = set(cache.scans_valides_ids) if cache and cache.scans_valides_ids else set()
    liens_morts_ids = set(cache.liens_morts_ids) if cache and cache.liens_morts_ids else set()

    stats_scans = {
        'total': entries_scan.count(),
        'scans_valides': entries_scan.filter(id__in=scans_valides_ids).count() if scans_valides_ids else 0,
        'liens_morts': entries_scan.filter(id__in=liens_morts_ids).count() if liens_morts_ids else 0,
        'sans_scan': entries_scan.filter(Q(scan__isnull=True) | Q(scan='')).count(),
    }
    stats_scans['taux_scans_valides'] = int((stats_scans['scans_valides'] / stats_scans['total'] * 100) if stats_scans['total'] > 0 else 0)

    # ===== SECTION 2: VÉRIFICATION PAIEMENTS EMPLOYÉS =====
    # Récupérer tous les comptes avec employe_obligatoire=True
    comptes_employes_obligatoires = Compte.objects.filter(
        employe_obligatoire=True
    ).values_list('compte', flat=True)

    # Filtrer les entries qui ont un compte employé obligatoire
    entries_employes = entries.filter(
        compte_code__in=comptes_employes_obligatoires
    )

    anomalies_employes = []
    conformes_employes = 0

    # Créer un mapping employe.surnom -> (nom_complet, prefixe_poste, comptes actuels + historiques)
    employes_dict = {}
    for emp in Employe.objects.select_related('poste__compte_salaire', 'poste__compte_cnaps_fmfp_sante', 'poste__compte_indemnite', 'poste__compte_irsa').prefetch_related('contrats__poste__compte_salaire', 'contrats__poste__compte_cnaps_fmfp_sante', 'contrats__poste__compte_indemnite', 'contrats__poste__compte_irsa').all():
        if emp.surnom:
            nom_complet = f"{emp.prenom or ''} {emp.nom or ''}".strip()
            prefixe_poste = emp.poste.prefixe if emp.poste else ''

            # Récupérer les comptes du poste ACTUEL
            comptes_salaire_set = set()
            comptes_cnaps_fmfp_sante_set = set()
            comptes_indemnite_set = set()
            comptes_irsa_set = set()

            if emp.poste:
                if emp.poste.compte_salaire:
                    comptes_salaire_set.add(emp.poste.compte_salaire.compte)
                if emp.poste.compte_cnaps_fmfp_sante:
                    comptes_cnaps_fmfp_sante_set.add(emp.poste.compte_cnaps_fmfp_sante.compte)
                if emp.poste.compte_indemnite:
                    comptes_indemnite_set.add(emp.poste.compte_indemnite.compte)
                if emp.poste.compte_irsa:
                    comptes_irsa_set.add(emp.poste.compte_irsa.compte)

            # Récupérer les comptes des postes HISTORIQUES (via contrats)
            for contrat in emp.contrats.all():
                if contrat.poste:
                    if contrat.poste.compte_salaire:
                        comptes_salaire_set.add(contrat.poste.compte_salaire.compte)
                    if contrat.poste.compte_cnaps_fmfp_sante:
                        comptes_cnaps_fmfp_sante_set.add(contrat.poste.compte_cnaps_fmfp_sante.compte)
                    if contrat.poste.compte_indemnite:
                        comptes_indemnite_set.add(contrat.poste.compte_indemnite.compte)
                    if contrat.poste.compte_irsa:
                        comptes_irsa_set.add(contrat.poste.compte_irsa.compte)

            employes_dict[emp.surnom] = {
                'nom_complet': nom_complet,
                'prefixe': prefixe_poste,
                'comptes_salaire': list(comptes_salaire_set),  # Liste de tous les comptes salaire (actuel + historiques)
                'comptes_cnaps_fmfp_sante': list(comptes_cnaps_fmfp_sante_set),
                'comptes_indemnite': list(comptes_indemnite_set),
                'comptes_irsa': list(comptes_irsa_set)
            }

    # Récupérer dynamiquement tous les comptes depuis les postes
    comptes_salaires_postes = set()
    comptes_indemnites_postes = set()
    comptes_irsa_postes = set()
    comptes_cnaps_postes = set()

    for poste in Poste.objects.select_related('compte_salaire', 'compte_indemnite', 'compte_irsa', 'compte_cnaps_fmfp_sante').all():
        if poste.compte_salaire and poste.compte_salaire.compte:
            comptes_salaires_postes.add(poste.compte_salaire.compte)
        if poste.compte_indemnite and poste.compte_indemnite.compte:
            comptes_indemnites_postes.add(poste.compte_indemnite.compte)
        if poste.compte_irsa and poste.compte_irsa.compte:
            comptes_irsa_postes.add(poste.compte_irsa.compte)
        if poste.compte_cnaps_fmfp_sante and poste.compte_cnaps_fmfp_sante.compte:
            comptes_cnaps_postes.add(poste.compte_cnaps_fmfp_sante.compte)

    # Enrichir les listes statiques avec les comptes dynamiques
    COMPTES_PAIEMENTS_EMPLOYES['salaire'].extend(list(comptes_salaires_postes))
    COMPTES_PAIEMENTS_EMPLOYES['salaire'] = list(set(COMPTES_PAIEMENTS_EMPLOYES['salaire']))

    COMPTES_PAIEMENTS_EMPLOYES['indemnite_terrain'].extend(list(comptes_indemnites_postes))
    COMPTES_PAIEMENTS_EMPLOYES['indemnite_terrain'] = list(set(COMPTES_PAIEMENTS_EMPLOYES['indemnite_terrain']))

    COMPTES_PAIEMENTS_EMPLOYES['indemnite_hors_zone'].extend(list(comptes_indemnites_postes))
    COMPTES_PAIEMENTS_EMPLOYES['indemnite_hors_zone'] = list(set(COMPTES_PAIEMENTS_EMPLOYES['indemnite_hors_zone']))

    COMPTES_PAIEMENTS_EMPLOYES['irsa'].extend(list(comptes_irsa_postes))
    COMPTES_PAIEMENTS_EMPLOYES['irsa'] = list(set(COMPTES_PAIEMENTS_EMPLOYES['irsa']))

    COMPTES_PAIEMENTS_EMPLOYES['cnaps'].extend(list(comptes_cnaps_postes))
    COMPTES_PAIEMENTS_EMPLOYES['cnaps'] = list(set(COMPTES_PAIEMENTS_EMPLOYES['cnaps']))

    COMPTES_PAIEMENTS_EMPLOYES['fmfp'].extend(list(comptes_cnaps_postes))
    COMPTES_PAIEMENTS_EMPLOYES['fmfp'] = list(set(COMPTES_PAIEMENTS_EMPLOYES['fmfp']))

    COMPTES_PAIEMENTS_EMPLOYES['mutuelle_sante'].extend(list(comptes_cnaps_postes))
    COMPTES_PAIEMENTS_EMPLOYES['mutuelle_sante'] = list(set(COMPTES_PAIEMENTS_EMPLOYES['mutuelle_sante']))

    for entry in entries_employes:
        conforme_description, type_trouve, _ = verifier_pattern_description(
            entry.description,
            PATTERNS_PAIEMENTS_EMPLOYES
        )

        # Récupérer les infos employé via entry.detail (qui contient le surnom)
        employe_info = employes_dict.get(entry.detail, {})
        employe_surnom = entry.detail or ''
        comptes_salaire_employe = employe_info.get('comptes_salaire', [])
        comptes_cnaps_fmfp_sante_employe = employe_info.get('comptes_cnaps_fmfp_sante', [])
        comptes_indemnite_employe = employe_info.get('comptes_indemnite', [])
        comptes_irsa_employe = employe_info.get('comptes_irsa', [])

        conforme_compte = False
        if type_trouve and type_trouve in COMPTES_PAIEMENTS_EMPLOYES:
            # Vérifier si le compte correspond aux comptes attendus pour ce type
            conforme_compte = verifier_compte_cat(
                entry.compte_code,
                COMPTES_PAIEMENTS_EMPLOYES[type_trouve]
            )

            # RÈGLES STRICTES selon le type de paiement :
            # Chaque type de paiement doit UNIQUEMENT utiliser son compte spécifique (actuel OU historique)
            if not conforme_compte:
                # 1. Pour salaire, ajustement_salaire, frais_medicaux, frais_scolarite, solde_tout_compte, prime : accepter les comptes salaire du poste (actuel + historiques)
                if type_trouve in ['salaire', 'ajustement_salaire', 'frais_medicaux', 'frais_scolarite', 'solde_tout_compte', 'prime'] and comptes_salaire_employe:
                    conforme_compte = (entry.compte_code in comptes_salaire_employe)

                # 2. Pour IRSA : accepter les comptes irsa du poste (actuel + historiques)
                elif type_trouve == 'irsa' and comptes_irsa_employe:
                    conforme_compte = (entry.compte_code in comptes_irsa_employe)

                # 3. Pour CNaPS, FMFP, mutuelle_sante : accepter les comptes cnaps_fmfp_sante du poste (actuel + historiques)
                elif type_trouve in ['cnaps', 'fmfp', 'mutuelle_sante'] and comptes_cnaps_fmfp_sante_employe:
                    conforme_compte = (entry.compte_code in comptes_cnaps_fmfp_sante_employe)

                # 4. Pour indemnités : accepter les comptes indemnite du poste (actuel + historiques)
                elif type_trouve in ['indemnite_terrain', 'indemnite_hors_zone'] and comptes_indemnite_employe:
                    conforme_compte = (entry.compte_code in comptes_indemnite_employe)

        if conforme_description and conforme_compte:
            conformes_employes += 1
        else:
            # Enrichir avec informations scan
            scan_status, full_scan_path = enrichir_avec_scan(entry, bases_dict)

            anomalies_employes.append({
                'entry': entry,
                'type_trouve': type_trouve,
                'conforme_description': conforme_description,
                'conforme_compte': conforme_compte,
                'comptes_attendus': COMPTES_PAIEMENTS_EMPLOYES.get(type_trouve, []) if type_trouve else [],
                'scan_status': scan_status,
                'full_scan_path': full_scan_path,
                'employe_surnom': employe_surnom,  # Afficher le surnom
                'employe_prefixe': employe_info.get('prefixe', ''),
            })

    stats_employes = {
        'total': entries_employes.count(),
        'conformes': conformes_employes,
        'anomalies': len(anomalies_employes),
        'taux_conformite': int((conformes_employes / entries_employes.count() * 100) if entries_employes.count() > 0 else 0)
    }

    # ===== SECTION 3: VÉRIFICATION FOURNISSEURS =====
    # Comptes fournisseurs et achats
    entries_fournisseurs = entries.filter(
        Q(compte_code__startswith='220') |  # Immobilisations
        Q(compte_code__startswith='60') |   # Achats
        Q(compte_code__startswith='61') |   # Services externes
        Q(compte_code__startswith='628')    # Autres services
    ).exclude(
        # Exclure les comptes employés déjà traités
        Q(compte_code__startswith='641') |
        Q(compte_code__startswith='631') |
        Q(compte_code__startswith='646')
    )

    anomalies_fournisseurs = []
    conformes_fournisseurs = 0

    for entry in entries_fournisseurs:
        conforme_description, type_trouve, _ = verifier_pattern_description(
            entry.description,
            PATTERNS_FOURNISSEURS
        )

        conforme_compte = False
        if type_trouve and type_trouve in COMPTES_FOURNISSEURS:
            conforme_compte = verifier_compte_cat(
                entry.compte_code,
                COMPTES_FOURNISSEURS[type_trouve]
            )

        if conforme_description and conforme_compte:
            conformes_fournisseurs += 1
        else:
            # Enrichir avec informations scan
            scan_status, full_scan_path = enrichir_avec_scan(entry, bases_dict)
            anomalies_fournisseurs.append({
                'entry': entry,
                'type_trouve': type_trouve,
                'conforme_description': conforme_description,
                'conforme_compte': conforme_compte,
                'comptes_attendus': COMPTES_FOURNISSEURS.get(type_trouve, []) if type_trouve else [],
                'scan_status': scan_status,
                'full_scan_path': full_scan_path,
            })

    stats_fournisseurs = {
        'total': entries_fournisseurs.count(),
        'conformes': conformes_fournisseurs,
        'anomalies': len(anomalies_fournisseurs),
        'taux_conformite': int((conformes_fournisseurs / entries_fournisseurs.count() * 100) if entries_fournisseurs.count() > 0 else 0)
    }

    # ===== SECTION 4: VÉRIFICATION AUTRES COMPTES =====
    # Tous les autres comptes non traités
    entries_autres = entries.exclude(
        # Exclure ce qui a déjà été vérifié
        Q(id__in=entries_employes.values_list('id', flat=True)) |
        Q(id__in=entries_fournisseurs.values_list('id', flat=True)) |
        Q(compte_code__icontains='00BOOK') |
        Q(compte_code__icontains='00PERS')
    )

    # Pour les autres, juste vérifier la présence de description et PERS
    anomalies_autres = []
    for entry in entries_autres:
        if not entry.description or not entry.pers:
            # Enrichir avec informations scan
            scan_status, full_scan_path = enrichir_avec_scan(entry, bases_dict)
            anomalies_autres.append({
                'entry': entry,
                'manque_description': not entry.description,
                'manque_pers': not entry.pers,
                'scan_status': scan_status,
                'full_scan_path': full_scan_path,
            })

    stats_autres = {
        'total': entries_autres.count(),
        'conformes': entries_autres.count() - len(anomalies_autres),
        'anomalies': len(anomalies_autres),
        'taux_conformite': int(((entries_autres.count() - len(anomalies_autres)) / entries_autres.count() * 100) if entries_autres.count() > 0 else 0)
    }

    # ===== REGROUPEMENTS =====
    # Regroupement par PROG
    regroupement_prog = defaultdict(lambda: {
        'total': 0,
        'montant_total': Decimal('0'),
        'anomalies_scans': 0,
        'anomalies_employes': 0,
        'anomalies_fournisseurs': 0,
        'anomalies_autres': 0
    })

    for entry in entries:
        prog = entry.prog or '(Sans prog)'
        regroupement_prog[prog]['total'] += 1
        regroupement_prog[prog]['montant_total'] += Decimal(str(entry.montant_out or 0))

    # Ajouter les anomalies dans les regroupements
    for anomalie in anomalies_employes:
        prog = anomalie['entry'].prog or '(Sans prog)'
        regroupement_prog[prog]['anomalies_employes'] += 1

    for anomalie in anomalies_fournisseurs:
        prog = anomalie['entry'].prog or '(Sans prog)'
        regroupement_prog[prog]['anomalies_fournisseurs'] += 1

    for anomalie in anomalies_autres:
        prog = anomalie['entry'].prog or '(Sans prog)'
        regroupement_prog[prog]['anomalies_autres'] += 1

    # Regroupement par COMPTE
    regroupement_compte = defaultdict(lambda: {
        'total': 0,
        'montant_total': Decimal('0'),
        'anomalies': 0
    })

    for entry in entries:
        compte = entry.compte_code or '(Sans compte)'
        regroupement_compte[compte]['total'] += 1
        regroupement_compte[compte]['montant_total'] += Decimal(str(entry.montant_out or 0))

    # Créer un dictionnaire de mapping compte (numéro) -> nom_compte
    comptes_dict_mapping = {}
    for compte in Compte.objects.all():
        if compte.compte:  # S'assurer que le numéro de compte existe
            comptes_dict_mapping[compte.compte] = compte.nom_compte

    # ===== REGROUPEMENTS À 2 NIVEAUX (PROG → COMPTE) =====
    # Grouper les anomalies employés par Prog puis par Compte avec totaux
    anomalies_employes_groupees = {}
    prog_temp = defaultdict(lambda: defaultdict(list))
    for anomalie in anomalies_employes:
        prog = anomalie['entry'].prog or '(Sans prog)'
        compte = anomalie['entry'].compte_code or '(Sans compte)'
        prog_temp[prog][compte].append(anomalie)

    # Calculer les totaux par prog et enrichir avec noms des comptes
    for prog, comptes_dict in prog_temp.items():
        total_prog = sum(len(anomalies) for anomalies in comptes_dict.values())
        # Enrichir chaque compte avec son nom
        comptes_enrichis = {}
        for compte_code, anomalies_list in comptes_dict.items():
            nom_compte = comptes_dict_mapping.get(compte_code, '')
            comptes_enrichis[compte_code] = {
                'anomalies': anomalies_list,
                'nom_compte': nom_compte
            }

        anomalies_employes_groupees[prog] = {
            'comptes': comptes_enrichis,
            'total': total_prog
        }

    # Grouper les anomalies fournisseurs par Prog puis par Compte avec totaux
    anomalies_fournisseurs_groupees = {}
    prog_temp = defaultdict(lambda: defaultdict(list))
    for anomalie in anomalies_fournisseurs:
        prog = anomalie['entry'].prog or '(Sans prog)'
        compte = anomalie['entry'].compte_code or '(Sans compte)'
        prog_temp[prog][compte].append(anomalie)

    for prog, comptes_dict in prog_temp.items():
        total_prog = sum(len(anomalies) for anomalies in comptes_dict.values())
        comptes_enrichis = {}
        for compte_code, anomalies_list in comptes_dict.items():
            nom_compte = comptes_dict_mapping.get(compte_code, '')
            comptes_enrichis[compte_code] = {
                'anomalies': anomalies_list,
                'nom_compte': nom_compte
            }
        anomalies_fournisseurs_groupees[prog] = {
            'comptes': comptes_enrichis,
            'total': total_prog
        }

    # Grouper les anomalies autres par Prog puis par Compte avec totaux
    anomalies_autres_groupees = {}
    prog_temp = defaultdict(lambda: defaultdict(list))
    for anomalie in anomalies_autres:
        prog = anomalie['entry'].prog or '(Sans prog)'
        compte = anomalie['entry'].compte_code or '(Sans compte)'
        prog_temp[prog][compte].append(anomalie)

    for prog, comptes_dict in prog_temp.items():
        total_prog = sum(len(anomalies) for anomalies in comptes_dict.values())
        comptes_enrichis = {}
        for compte_code, anomalies_list in comptes_dict.items():
            nom_compte = comptes_dict_mapping.get(compte_code, '')
            comptes_enrichis[compte_code] = {
                'anomalies': anomalies_list,
                'nom_compte': nom_compte
            }
        anomalies_autres_groupees[prog] = {
            'comptes': comptes_enrichis,
            'total': total_prog
        }

    # Listes pour filtres
    fichiers_list = sorted(set(
        f for f in BaseDiameX.objects.values_list('fichier_source', flat=True).distinct() if f
    ))
    progs_list = sorted(set(
        p for p in BaseDiameX.objects.values_list('prog', flat=True).distinct() if p
    ))

    # Listes pour le modal d'édition
    comptes_list = Compte.objects.filter(organisation__isnull=False).select_related('organisation').order_by('compte', 'nom_compte')
    employes_list = Employe.objects.filter(surnom__isnull=False).exclude(surnom='').order_by('surnom')

    return render(request, 'accounting/verification_unifiee.html', {
        # Filtres
        'filter_mois': filter_mois,
        'filter_fichier': filter_fichier,
        'filter_prog': filter_prog,
        'filter_type': filter_type,
        'fichiers_list': fichiers_list,
        'progs_list': progs_list,

        # Stats globales
        'stats_scans': stats_scans,
        'stats_employes': stats_employes,
        'stats_fournisseurs': stats_fournisseurs,
        'stats_autres': stats_autres,

        # Anomalies détaillées
        'anomalies_employes': anomalies_employes[:100],  # Limiter pour performance
        'anomalies_fournisseurs': anomalies_fournisseurs[:100],
        'anomalies_autres': anomalies_autres[:100],

        # Anomalies groupées par Prog → Compte
        'anomalies_employes_groupees': dict(anomalies_employes_groupees),
        'anomalies_fournisseurs_groupees': dict(anomalies_fournisseurs_groupees),
        'anomalies_autres_groupees': dict(anomalies_autres_groupees),

        # Regroupements
        'regroupement_prog': dict(sorted(regroupement_prog.items())),
        'regroupement_compte': dict(sorted(regroupement_compte.items())),

        # Données pour le modal d'édition
        'comptes_list': comptes_list,
        'employes_list': employes_list,

        # Autres
        'date_derniere_verif_scans': cache.date_verification if cache else None,
    })
