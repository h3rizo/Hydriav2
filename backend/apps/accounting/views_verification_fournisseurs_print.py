"""
Vue pour la version imprimable de la vérification fournisseurs
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from apps.accounting.models import BaseDiameX
from apps.organization.models import Compte
from datetime import datetime

from .views_verification_fournisseurs import verifier_format_charte_fournisseur


@login_required
def verification_fournisseurs_print(request):
    """
    Version imprimable de la vérification fournisseurs
    Filtres: prog, mois, annee, conformite, compte
    """
    # Récupérer les filtres
    prog_filter = request.GET.get('prog', '').strip()
    mois_filter = request.GET.get('mois', '').strip()
    annee_filter = request.GET.get('annee', str(datetime.now().year)).strip()
    conformite_filter = request.GET.get('conformite', '').strip()  # '', 'conforme', 'non_conforme'
    compte_filter = request.GET.get('compte', '').strip()

    # Récupérer les codes fournisseurs
    codes_fournisseurs = list(Compte.objects.filter(fournisseur_obligatoire=True).values_list('compte', flat=True))

    # Requête de base
    entries_qs = BaseDiameX.objects.filter(compte_code__in=codes_fournisseurs).select_related('imported_by')

    # Filtres
    if prog_filter and prog_filter != 'all':
        entries_qs = entries_qs.filter(prog=prog_filter)

    if compte_filter and compte_filter != 'all':
        entries_qs = entries_qs.filter(compte_code=compte_filter)

    if annee_filter:
        entries_qs = entries_qs.filter(date_rec__year=int(annee_filter))

    if mois_filter:
        entries_qs = entries_qs.filter(date_rec__month=int(mois_filter))

    # Récupérer et analyser
    all_entries = entries_qs.order_by('date_rec', 'description')

    resultats = []
    stats = {
        'total': 0,
        'conformes': 0,
        'non_conformes': 0,
    }

    for entry in all_entries:
        # Vérifier la conformité
        verification = verifier_format_charte_fournisseur(
            description=entry.description or '',
            fournisseur_idxls=entry.fournisseur,
            compte_code=entry.compte_code
        )

        conforme = verification['conforme']

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
            'fournisseur': entry.fournisseur,
            'description': entry.description,
            'montant_out': entry.montant_out or 0,
            'conforme': conforme,
            'erreurs': verification.get('erreurs', []),
            'suggestion': verification.get('details', {}).get('nom_fournisseur_attendu'),  # Suggestion en rouge
        }

        resultats.append(resultat)
        stats['total'] += 1
        if conforme:
            stats['conformes'] += 1
        else:
            stats['non_conformes'] += 1

    # Pourcentages
    if stats['total'] > 0:
        stats['taux_conformite'] = int((stats['conformes'] / stats['total']) * 100)
        stats['taux_non_conformite'] = int((stats['non_conformes'] / stats['total']) * 100)
    else:
        stats['taux_conformite'] = 0
        stats['taux_non_conformite'] = 0

    # Nom du mois
    mois_nom = ''
    if mois_filter:
        mois_int = int(mois_filter)
        mois_noms = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                     'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        mois_nom = mois_noms[mois_int]

    # Préparer les données pour les dropdowns
    # Années disponibles
    annees_qs = BaseDiameX.objects.filter(
        compte_code__in=codes_fournisseurs,
        date_rec__isnull=False
    ).values_list('date_rec__year', flat=True).distinct()
    annees_disponibles = sorted(set(annees_qs), reverse=True)

    # Programmes disponibles
    progs_disponibles = BaseDiameX.objects.filter(
        compte_code__in=codes_fournisseurs
    ).values_list('prog', flat=True).distinct().order_by('prog')
    progs_disponibles = [p for p in progs_disponibles if p]  # Retirer les valeurs None

    # Comptes disponibles
    comptes_disponibles = BaseDiameX.objects.filter(
        compte_code__in=codes_fournisseurs
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

        resultats_groupes[prog][compte].append(resultat)

    context = {
        'resultats': resultats,
        'resultats_groupes': resultats_groupes,
        'stats': stats,
        'prog_filter': prog_filter,
        'compte_filter': compte_filter,
        'mois_filter': mois_filter,
        'mois_nom': mois_nom,
        'annee_filter': annee_filter,
        'conformite_filter': conformite_filter,
        'date_impression': datetime.now(),
        'annees_disponibles': annees_disponibles,
        'progs_disponibles': progs_disponibles,
        'comptes_disponibles': comptes_disponibles,
    }

    return render(request, 'accounting/verification_fournisseurs_print.html', context)
