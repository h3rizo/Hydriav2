"""
Vue pour la version imprimable de la vérification autres comptes
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Q
from apps.accounting.models import BaseDiameX
from apps.organization.models import Compte
from apps.accounting.charte_verification import verifier_charte_compte
from datetime import datetime


@login_required
def verification_autres_print(request):
    """
    Version imprimable de la vérification autres comptes
    Filtres: prog, mois, annee, conformite, compte, type
    """
    # Récupérer les filtres
    prog_filter = request.GET.get('prog', '').strip()
    mois_filter = request.GET.get('mois', '').strip()
    annee_filter = request.GET.get('annee', str(datetime.now().year)).strip()
    conformite_filter = request.GET.get('conformite', '').strip()  # '', 'conforme', 'non_conforme'
    compte_filter = request.GET.get('compte', '').strip()
    type_filter = request.GET.get('type', '').strip()  # 'entree', 'sortie'

    # Récupérer les codes à exclure (comptes employés + fournisseurs)
    codes_employes = list(Compte.objects.filter(employe_obligatoire=True).values_list('compte', flat=True))
    codes_fournisseurs = list(Compte.objects.filter(fournisseur_obligatoire=True).values_list('compte', flat=True))
    codes_exclus = set(codes_employes + codes_fournisseurs)

    # Requête de base
    entries_qs = BaseDiameX.objects.exclude(
        compte_code__in=codes_exclus
    ).exclude(
        Q(compte_code__istartswith='00BOOK') |
        Q(compte_code__istartswith='00PERS') |
        Q(compte_code__istartswith='00SPLITBOOK') |
        Q(compte_code__istartswith='00FND1')
    ).select_related('imported_by')

    # Filtres
    if prog_filter and prog_filter != 'all':
        entries_qs = entries_qs.filter(prog=prog_filter)

    if compte_filter and compte_filter != 'all':
        entries_qs = entries_qs.filter(compte_code=compte_filter)

    if annee_filter:
        entries_qs = entries_qs.filter(date_rec__year=int(annee_filter))

    if mois_filter:
        entries_qs = entries_qs.filter(date_rec__month=int(mois_filter))

    if type_filter and type_filter != 'all':
        if type_filter == 'entree':
            entries_qs = entries_qs.filter(Q(montant_in__isnull=False) | Q(montant_in__gt=0))
        elif type_filter == 'sortie':
            entries_qs = entries_qs.filter(Q(montant_out__isnull=False) | Q(montant_out__gt=0))

    # Récupérer et analyser
    all_entries = entries_qs.order_by('date_rec', 'description')

    resultats = []
    stats = {
        'total': 0,
        'conformes': 0,
        'non_conformes': 0,
        'total_entrees': 0,
        'total_sorties': 0,
    }

    for entry in all_entries:
        # Déterminer le type
        is_entree = entry.montant_in and entry.montant_in > 0
        is_sortie = entry.montant_out and entry.montant_out > 0
        entry_type = 'Entrée' if is_entree else 'Sortie' if is_sortie else 'Inconnu'

        if is_entree:
            stats['total_entrees'] += 1
        if is_sortie:
            stats['total_sorties'] += 1

        # Essayer de trouver le compte
        compte_obj = None
        try:
            compte_obj = Compte.objects.get(compte=entry.compte_code)
        except Compte.DoesNotExist:
            pass

        # Vérification de la charte
        charte_result = None
        conforme = None
        if compte_obj and compte_obj.charte_verification:
            charte_result = verifier_charte_compte(
                description=entry.description or '',
                charte_type=compte_obj.charte_verification,
                compte_code=entry.compte_code
            )
            conforme = charte_result['conforme']

        # Filtre conformité
        if conformite_filter:
            if conformite_filter == 'conforme' and not conforme:
                continue
            if conformite_filter == 'non_conforme' and conforme:
                continue

        resultat = {
            'date': entry.date_rec,
            'prog': entry.prog,
            'compte_code': entry.compte_code,
            'compte_libelle': compte_obj.nom_compte if compte_obj else '',
            'pers': entry.pers,
            'detail': entry.detail,
            'description': entry.description,
            'montant_in': entry.montant_in or 0,
            'montant_out': entry.montant_out or 0,
            'type': entry_type,
            'conforme': conforme,
            'charte_type': compte_obj.get_charte_verification_display() if compte_obj and compte_obj.charte_verification else None,
        }

        resultats.append(resultat)
        stats['total'] += 1
        if conforme == True:
            stats['conformes'] += 1
        elif conforme == False:
            stats['non_conformes'] += 1

    # Pourcentages
    if stats['total'] > 0:
        stats['taux_conformite'] = int((stats['conformes'] / stats['total']) * 100)
        stats['taux_non_conformite'] = int((stats['non_conformes'] / stats['total']) * 100)
        stats['taux_entrees'] = int((stats['total_entrees'] / stats['total']) * 100)
        stats['taux_sorties'] = int((stats['total_sorties'] / stats['total']) * 100)
    else:
        stats['taux_conformite'] = 0
        stats['taux_non_conformite'] = 0
        stats['taux_entrees'] = 0
        stats['taux_sorties'] = 0

    # Nom du mois
    mois_nom = ''
    if mois_filter:
        mois_int = int(mois_filter)
        mois_noms = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                     'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        mois_nom = mois_noms[mois_int]

    # Préparer les données pour les dropdowns
    # Années disponibles
    annees_qs = BaseDiameX.objects.exclude(
        compte_code__in=codes_exclus
    ).filter(
        date_rec__isnull=False
    ).values_list('date_rec__year', flat=True).distinct()
    annees_disponibles = sorted(set(annees_qs), reverse=True)

    # Programmes disponibles
    progs_disponibles = BaseDiameX.objects.exclude(
        compte_code__in=codes_exclus
    ).values_list('prog', flat=True).distinct().order_by('prog')
    progs_disponibles = [p for p in progs_disponibles if p]  # Retirer les valeurs None

    # Comptes disponibles
    comptes_disponibles = BaseDiameX.objects.exclude(
        compte_code__in=codes_exclus
    ).values_list('compte_code', flat=True).distinct().order_by('compte_code')
    comptes_disponibles = [c for c in comptes_disponibles if c]  # Retirer les valeurs None

    # Grouper les résultats par Prog → Compte
    resultats_groupes = {}
    for resultat in resultats:
        prog = resultat['prog'] or 'Sans Prog'
        compte = resultat['compte_code'] or 'Sans Compte'

        if prog not in resultats_groupes:
            resultats_groupes[prog] = {}

        if compte not in resultats_groupes[prog]:
            resultats_groupes[prog][compte] = []

        # Ajouter date_m formatée pour le template
        resultat['date_m'] = resultat['date']
        # Ajouter type en minuscules pour le template
        resultat['type'] = 'entree' if resultat['type'] == 'Entrée' else 'sortie'

        resultats_groupes[prog][compte].append(resultat)

    context = {
        'resultats': resultats,
        'resultats_groupes': resultats_groupes,
        'stats': stats,
        'prog_filter': prog_filter,
        'compte_filter': compte_filter,
        'type_filter': type_filter,
        'mois_filter': mois_filter,
        'mois_nom': mois_nom,
        'annee_filter': annee_filter,
        'conformite_filter': conformite_filter,
        'date_impression': datetime.now(),
        'annees_disponibles': annees_disponibles,
        'progs_disponibles': progs_disponibles,
        'comptes_disponibles': comptes_disponibles,
    }

    return render(request, 'accounting/verification_autres_print.html', context)
