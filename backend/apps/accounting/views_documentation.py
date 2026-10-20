"""
Vues pour la gestion de la documentation comptable justificative.
"""
import os
import json
import re
from datetime import datetime
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.db.models import Q, Count, Case, When, Value, IntegerField
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from .models import DocumentationComptable, BaseDiameX
from apps.employees.models import Employe
from apps.organization.models import Base
from django.db.models import Sum

# Imports pour OCR
try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_allowed_progs(user):
    if getattr(user, 'is_superuser', False):
        return None
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return []
    return list(
        Base.objects.filter(organisation_id=organisation_id)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )


def _scope_diamex_queryset(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    allowed_progs = _get_allowed_progs(user)
    if not allowed_progs:
        return queryset.none()
    return queryset.filter(prog__in=allowed_progs)


def _scope_documentation_queryset(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    allowed_progs = _get_allowed_progs(user)
    if not allowed_progs:
        return queryset.none()
    return queryset.filter(fichier_source__in=allowed_progs)


def _file_in_scope(user, fichier_source):
    if getattr(user, 'is_superuser', False):
        return True
    allowed_progs = _get_allowed_progs(user)
    return bool(allowed_progs and fichier_source in allowed_progs)


@login_required
def documentation_saisie(request):
    """
    Page de saisie des documents justificatifs par mois/fichier.
    Permet de renseigner les chemins vers les documents comptables.
    """
    # Récupérer les filtres
    mois_filter = request.GET.get('mois')
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    fichier_filter = request.GET.get('fichier')

    # Liste des fichiers sources disponibles
    fichiers_sources = _scope_diamex_queryset(
        BaseDiameX.objects,
        request.user
    ).values_list('fichier_source', flat=True).distinct().order_by('fichier_source')

    # Si on a des filtres, charger les documents avec données de comparaison
    documents = None
    comparaisons_soldes = None
    avances_tiers = None

    prog_fichier = None
    if mois_filter and annee_filter and fichier_filter:
        mois = int(mois_filter)
        annee = int(annee_filter)

        # Récupérer le prog associé au fichier
        prog_fichier = _scope_diamex_queryset(
            BaseDiameX.objects,
            request.user
        ).filter(
            fichier_source=fichier_filter
        ).values_list('prog', flat=True).first()

        # Récupérer ou créer les documents attendus
        documents = generer_documents_attendus(annee, mois, fichier_filter, request.user)

        # Charger les données de comparaison des soldes pour ce mois
        comparaisons_soldes = get_comparaison_soldes_mois(annee, mois, fichier_filter, request.user)

        # Charger les avances PERS pour ce mois
        avances_tiers = get_avances_pers_mois(annee, mois, fichier_filter, request.user)

    context = {
        'fichiers_sources': fichiers_sources,
        'mois_filter': mois_filter,
        'annee_filter': annee_filter,
        'fichier_filter': fichier_filter,
        'prog_fichier': prog_fichier,
        'documents': documents,
        'comparaisons_soldes': comparaisons_soldes,
        'avances_tiers': avances_tiers,
    }

    return render(request, 'accounting/documentation_saisie.html', context)


def generer_documents_attendus(annee, mois, fichier_source, user=None):
    """
    Génère la liste des documents attendus pour un mois/fichier donné.
    Scanner les journaux spécifiques à ce fichier pour déterminer les documents nécessaires.

    Règles:
    - Grands livres: RL Activités + RL Autres = 1 seul GL "RL"
    - Comptage caisse: Uniquement journaux commençant par C (exclure 00PERS, 00SPLITBOOK-MGA)
    - Relevés bancaires: Uniquement journaux commençant par B
    """
    from datetime import date
    documents = []

    # ✅ CORRECTION : Scanner les journaux utilisés UNIQUEMENT pour ce mois spécifique
    # Utiliser set() pour garantir l'unicité
    diamex_qs = BaseDiameX.objects.all()
    if user is not None:
        diamex_qs = _scope_diamex_queryset(diamex_qs, user)

    journaux_fichier = sorted(set(diamex_qs.filter(
        fichier_source=fichier_source,
        date_m__year=annee,
        date_m__month=mois,
        journal_code__isnull=False
    ).exclude(
        journal_code=''
    ).values_list('journal_code', flat=True)))

    # ✅ CORRECTION : Scanner les valeurs Fin utilisées UNIQUEMENT pour ce mois spécifique
    # Utiliser set() pour garantir l'unicité
    valeurs_fin = sorted(set(diamex_qs.filter(
        fichier_source=fichier_source,
        date_m__year=annee,
        date_m__month=mois,
        fin__isnull=False
    ).values_list('fin', flat=True)))

    # Ajouter les Fin vides si elles existent pour ce mois
    if diamex_qs.filter(
        fichier_source=fichier_source,
        date_m__year=annee,
        date_m__month=mois,
        fin__isnull=True
    ).exists():
        valeurs_fin = [''] + valeurs_fin

    # Récupérer le prog associé à ce fichier source
    prog_fichier = diamex_qs.filter(
        fichier_source=fichier_source
    ).values_list('prog', flat=True).first()

    # ✅ 1. Grands livres par Fin - REGROUPER RL Activités et RL Autres en un seul "RL"
    fins_uniques = set()
    for valeur_fin in valeurs_fin:
        # Regrouper "RL Activités" et "RL Autres" en un seul "RL"
        if valeur_fin in ['RL Activités', 'RL Autres']:
            fins_uniques.add('RL')
        else:
            fins_uniques.add(valeur_fin)

    for valeur_fin in sorted(fins_uniques):
        doc, created = DocumentationComptable.objects.get_or_create(
            annee=annee,
            mois=mois,
            fichier_source=fichier_source,
            type_document='grand_livre',
            valeur_fin=valeur_fin if valeur_fin else None,
            journal_code=None,
            defaults={'statut': 'manquant'}
        )
        documents.append(doc)

    # 2. Fiche de rapprochement de solde (1 par mois/fichier)
    doc, created = DocumentationComptable.objects.get_or_create(
        annee=annee,
        mois=mois,
        fichier_source=fichier_source,
        type_document='rapprochement_solde',
        valeur_fin=None,
        journal_code=None,
        defaults={'statut': 'manquant'}
    )
    documents.append(doc)

    # 3. Fiche récapitulatif compte de tiers (1 par mois/fichier)
    doc, created = DocumentationComptable.objects.get_or_create(
        annee=annee,
        mois=mois,
        fichier_source=fichier_source,
        type_document='recap_tiers',
        valeur_fin=None,
        journal_code=None,
        defaults={'statut': 'manquant'}
    )
    documents.append(doc)

    # ✅ 4. Comptages de caisse - Uniquement journaux C* (exclure 00PERS et 00SPLITBOOK-MGA)
    journaux_caisse = [j for j in journaux_fichier
                      if j.startswith('C')
                      and j not in ['00PERS', '00SPLITBOOK-MGA']]

    for journal_code in journaux_caisse:
        doc, created = DocumentationComptable.objects.get_or_create(
            annee=annee,
            mois=mois,
            fichier_source=fichier_source,
            type_document='comptage_caisse',
            valeur_fin=None,
            journal_code=journal_code,
            defaults={'statut': 'manquant'}
        )
        documents.append(doc)

    # ✅ 5. Relevés bancaires - Uniquement journaux B*
    journaux_banque = [j for j in journaux_fichier if j.startswith('B')]

    for journal_code in journaux_banque:
        doc, created = DocumentationComptable.objects.get_or_create(
            annee=annee,
            mois=mois,
            fichier_source=fichier_source,
            type_document='releve_bancaire',
            valeur_fin=None,
            journal_code=journal_code,
            defaults={'statut': 'manquant'}
        )
        documents.append(doc)

    # 6. Fiche de suivi carburant (1 par mois/fichier)
    doc, created = DocumentationComptable.objects.get_or_create(
        annee=annee,
        mois=mois,
        fichier_source=fichier_source,
        type_document='suivi_carburant',
        valeur_fin=None,
        journal_code=None,
        defaults={'statut': 'manquant'}
    )
    documents.append(doc)

    return documents


def get_comparaison_soldes_mois(annee, mois, fichier_source, user=None):
    """
    Récupère les données de comparaison des soldes pour un mois/fichier donné.
    Retourne une liste de dictionnaires avec les données pour chaque journal.
    """
    from .models import SoldesReels
    from django.db.models import Sum
    from datetime import date
    from collections import defaultdict

    # Créer la date du mois
    date_mois = date(annee, mois, 1)

    # Exclure 00PERS et 00SPLITBOOK-MGA
    soldes_reels_qs = SoldesReels.objects.filter(
        fichier_source=fichier_source,
        date_m__year=annee,
        date_m__month=mois
    ).exclude(journal__in=['00PERS', '00SPLITBOOK-MGA'])

    diamex_qs = BaseDiameX.objects.all()
    if user is not None:
        diamex_qs = _scope_diamex_queryset(diamex_qs, user)

    entries_qs = diamex_qs.filter(
        fichier_source=fichier_source,
        date_m__year=annee,
        date_m__month=mois
    ).exclude(journal_code__in=['00PERS', '00SPLITBOOK-MGA'])

    # Calculer les soldes réels par journal
    soldes_reels_dict = {}
    for solde in soldes_reels_qs.values('journal').annotate(total=Sum('ccy')):
        soldes_reels_dict[solde['journal']] = float(solde['total'] or 0)

    # Calculer les soldes calculés par journal (somme cumulée jusqu'à ce mois)
    soldes_calcules_dict = {}

    # Récupérer tous les journaux
    journaux_data = set(j['journal_code'] for j in entries_qs.values('journal_code').distinct())
    journaux_soldes = set(s['journal'] for s in soldes_reels_qs.values('journal').distinct())
    tous_journaux = journaux_data | journaux_soldes

    for journal_code in tous_journaux:
        # Calculer le solde cumulé jusqu'à ce mois inclus
        ecritures_cumul = diamex_qs.filter(
            journal_code=journal_code,
            fichier_source=fichier_source,
            date_m__lte=date_mois
        ).aggregate(
            total_in=Sum('montant_in'),
            total_out=Sum('montant_out')
        )

        solde_cumul = float(ecritures_cumul['total_in'] or 0) - float(ecritures_cumul['total_out'] or 0)
        soldes_calcules_dict[journal_code] = solde_cumul

    # Construire la liste de comparaisons
    comparaisons = []
    tous_journaux_sorted = sorted(tous_journaux)

    for journal_code in tous_journaux_sorted:
        solde_reel = soldes_reels_dict.get(journal_code, 0)
        solde_calcule = soldes_calcules_dict.get(journal_code, 0)
        ecart = solde_reel - solde_calcule

        comparaisons.append({
            'journal': journal_code,
            'solde_reel': solde_reel,
            'solde_calcule': solde_calcule,
            'ecart': ecart,
            'conforme': abs(ecart) < 0.01  # Tolérance de 1 centime
        })

    return comparaisons


def get_avances_pers_cumul(annee, mois, fichier_source, user=None):
    """
    Récupère les avances PERS CUMULÉES depuis le début jusqu'à la fin du mois spécifié.
    Retourne un dictionnaire avec les soldes par tiers.
    """
    from collections import defaultdict
    from apps.billing.models import Fournisseur

    # Charger les fournisseurs pour mapping
    fournisseurs_dict = {
        str(f.idxls): f.nom_fournisseur
        for f in Fournisseur.objects.filter(idxls__isnull=False)
    }

    # Filtrer les entrées 00PERS JUSQU'À la fin du mois (cumul)
    diamex_qs = BaseDiameX.objects.all()
    if user is not None:
        diamex_qs = _scope_diamex_queryset(diamex_qs, user)

    pers_entries = diamex_qs.filter(
        fichier_source=fichier_source,
        date_m__year__lte=annee
    ).filter(
        Q(compte_code__startswith='00PERS') | Q(journal_code__startswith='00PERS')
    ).filter(
        Q(date_m__year__lt=annee) | Q(date_m__year=annee, date_m__month__lte=mois)
    )

    # Calculer solde par tiers
    soldes_par_tiers = defaultdict(lambda: {
        'org_doit': Decimal('0'),
        'tiers_doit': Decimal('0'),
        'solde': Decimal('0'),
        'type': 'inconnu',
        'nom_original': ''
    })

    for entry in pers_entries:
        # Ignorer les lignes avec Match non vide
        if entry.match:
            continue

        tiers_original = entry.pers or 'Non spécifié'
        tiers = tiers_original.lower()
        montant_in = Decimal(str(entry.montant_in or 0))
        montant_out = Decimal(str(entry.montant_out or 0))

        # Garder le premier nom rencontré
        if not soldes_par_tiers[tiers]['nom_original']:
            nom_affichage = tiers_original
            if tiers_original != 'Non spécifié':
                try:
                    int(tiers_original)
                    nom_fournisseur = fournisseurs_dict.get(tiers_original)
                    if nom_fournisseur:
                        nom_affichage = f"{nom_fournisseur} ({tiers_original})"
                    else:
                        nom_affichage = f"Fournisseur #{tiers_original}"
                except (ValueError, TypeError):
                    pass
            soldes_par_tiers[tiers]['nom_original'] = nom_affichage

        # Déterminer le type
        if tiers_original != 'Non spécifié':
            try:
                int(tiers_original)
                soldes_par_tiers[tiers]['type'] = 'fournisseur'
            except (ValueError, TypeError):
                soldes_par_tiers[tiers]['type'] = 'employe'

        # Calculer les soldes
        if montant_in > 0:
            soldes_par_tiers[tiers]['org_doit'] += montant_in
        if montant_out > 0:
            soldes_par_tiers[tiers]['tiers_doit'] += montant_out

    # Calculer le solde net
    for tiers, data in soldes_par_tiers.items():
        data['solde'] = data['org_doit'] - data['tiers_doit']

    # Convertir en liste triée
    avances_liste = []
    for tiers, data in sorted(soldes_par_tiers.items(), key=lambda x: x[1]['nom_original']):
        avances_liste.append({
            'tiers': data['nom_original'],
            'type': data['type'],
            'org_doit': float(data['org_doit']),
            'tiers_doit': float(data['tiers_doit']),
            'solde': float(data['solde'])
        })

    return avances_liste


def get_avances_pers_mois(annee, mois, fichier_source, user=None):
    """
    Récupère les avances PERS pour un mois/fichier donné.
    Retourne un dictionnaire avec les soldes par tiers.
    """
    from collections import defaultdict
    from apps.billing.models import Fournisseur

    # Charger les fournisseurs pour mapping
    fournisseurs_dict = {
        str(f.idxls): f.nom_fournisseur
        for f in Fournisseur.objects.filter(idxls__isnull=False)
    }

    # Filtrer les entrées 00PERS pour ce mois
    diamex_qs = BaseDiameX.objects.all()
    if user is not None:
        diamex_qs = _scope_diamex_queryset(diamex_qs, user)

    pers_entries = diamex_qs.filter(
        fichier_source=fichier_source,
        date_m__year=annee,
        date_m__month=mois
    ).filter(
        Q(compte_code__startswith='00PERS') | Q(journal_code__startswith='00PERS')
    )

    # Calculer solde par tiers
    soldes_par_tiers = defaultdict(lambda: {
        'org_doit': Decimal('0'),
        'tiers_doit': Decimal('0'),
        'solde': Decimal('0'),
        'type': 'inconnu',
        'nom_original': ''
    })

    for entry in pers_entries:
        # Ignorer les lignes avec Match non vide
        if entry.match:
            continue

        tiers_original = entry.pers or 'Non spécifié'
        tiers = tiers_original.lower()
        montant_in = Decimal(str(entry.montant_in or 0))
        montant_out = Decimal(str(entry.montant_out or 0))

        # Garder le premier nom rencontré
        if not soldes_par_tiers[tiers]['nom_original']:
            nom_affichage = tiers_original
            if tiers_original != 'Non spécifié':
                try:
                    int(tiers_original)
                    nom_fournisseur = fournisseurs_dict.get(tiers_original)
                    if nom_fournisseur:
                        nom_affichage = f"{nom_fournisseur} ({tiers_original})"
                    else:
                        nom_affichage = f"Fournisseur #{tiers_original}"
                except (ValueError, TypeError):
                    pass
            soldes_par_tiers[tiers]['nom_original'] = nom_affichage

        # Déterminer le type
        if tiers_original != 'Non spécifié':
            try:
                int(tiers_original)
                soldes_par_tiers[tiers]['type'] = 'fournisseur'
            except (ValueError, TypeError):
                soldes_par_tiers[tiers]['type'] = 'employe'

        # Calculer les soldes
        if montant_in > 0:
            soldes_par_tiers[tiers]['org_doit'] += montant_in
        if montant_out > 0:
            soldes_par_tiers[tiers]['tiers_doit'] += montant_out

    # Calculer le solde net
    for tiers, data in soldes_par_tiers.items():
        data['solde'] = data['org_doit'] - data['tiers_doit']

    # Convertir en liste triée
    avances_liste = []
    for tiers, data in sorted(soldes_par_tiers.items(), key=lambda x: x[1]['nom_original']):
        avances_liste.append({
            'tiers': data['nom_original'],
            'type': data['type'],
            'org_doit': float(data['org_doit']),
            'tiers_doit': float(data['tiers_doit']),
            'solde': float(data['solde'])
        })

    return avances_liste


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_update_document(request, doc_id):
    """
    API pour mettre à jour un document comptable (chemin, notes).
    """
    try:
        document = get_object_or_404(
            _scope_documentation_queryset(DocumentationComptable.objects.all(), request.user),
            id=doc_id
        )

        # Récupérer les données
        chemin_document = request.POST.get('chemin_document', '').strip()
        notes = request.POST.get('notes', '').strip()

        # Mettre à jour
        if chemin_document:
            document.chemin_document = chemin_document
            document.verifier_chemin()

        if notes:
            document.notes = notes

        # Associer l'utilisateur si disponible
        if request.user.is_authenticated:
            try:
                employe = Employe.objects.get(user=request.user)
                document.created_by = employe
            except Employe.DoesNotExist:
                pass

        document.save()

        return JsonResponse({
            'success': True,
            'message': 'Document mis à jour avec succès',
            'statut': document.statut,
            'statut_label': document.get_statut_display()
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_verifier_documents(request):
    """
    API pour vérifier l'existence des documents et mettre à jour les statuts.
    """
    try:
        data = json.loads(request.body)
        doc_ids = data.get('doc_ids', [])

        if not doc_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucun document fourni'
            }, status=400)

        # Vérifier chaque document
        nb_updated = 0
        results = []

        for doc_id in doc_ids:
            try:
                document = _scope_documentation_queryset(
                    DocumentationComptable.objects.all(),
                    request.user
                ).get(id=doc_id)
                ancien_statut = document.statut
                nouveau_statut = document.verifier_chemin()
                document.save()

                if ancien_statut != nouveau_statut:
                    nb_updated += 1

                results.append({
                    'id': str(document.id),
                    'statut': nouveau_statut,
                    'changed': ancien_statut != nouveau_statut
                })

            except DocumentationComptable.DoesNotExist:
                results.append({
                    'id': doc_id,
                    'error': 'Document introuvable'
                })

        return JsonResponse({
            'success': True,
            'message': f'{nb_updated} document(s) mis à jour',
            'nb_updated': nb_updated,
            'results': results
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def documentation_rapport(request):
    """
    Page de rapport des documents manquants et liens morts.
    Affiche les statistiques globales et détails par fichier/mois.
    """
    # Récupérer les filtres
    fichier_filter = request.GET.get('fichier')
    annee_filter = request.GET.get('annee')
    statut_filter = request.GET.get('statut')

    # Construire la requête
    docs_scope = _scope_documentation_queryset(DocumentationComptable.objects.all(), request.user)
    documents = docs_scope

    if fichier_filter:
        documents = documents.filter(fichier_source=fichier_filter)

    if annee_filter:
        documents = documents.filter(annee=int(annee_filter))

    if statut_filter:
        documents = documents.filter(statut=statut_filter)

    # Statistiques globales
    stats = {
        'total': docs_scope.count(),
        'presents': docs_scope.filter(statut='present').count(),
        'manquants': docs_scope.filter(statut='manquant').count(),
        'liens_morts': docs_scope.filter(statut='lien_mort').count(),
    }

    # Calculer les taux
    if stats['total'] > 0:
        stats['taux_presents'] = int((stats['presents'] / stats['total']) * 100)
        stats['taux_manquants'] = int((stats['manquants'] / stats['total']) * 100)
        stats['taux_liens_morts'] = int((stats['liens_morts'] / stats['total']) * 100)
    else:
        stats['taux_presents'] = 0
        stats['taux_manquants'] = 0
        stats['taux_liens_morts'] = 0

    # Statistiques par fichier source
    stats_par_fichier = docs_scope.values('fichier_source').annotate(
        total=Count('id'),
        presents=Count(Case(When(statut='present', then=1), output_field=IntegerField())),
        manquants=Count(Case(When(statut='manquant', then=1), output_field=IntegerField())),
        liens_morts=Count(Case(When(statut='lien_mort', then=1), output_field=IntegerField())),
    ).order_by('fichier_source')

    # Statistiques par type de document
    stats_par_type = docs_scope.values('type_document').annotate(
        total=Count('id'),
        presents=Count(Case(When(statut='present', then=1), output_field=IntegerField())),
        manquants=Count(Case(When(statut='manquant', then=1), output_field=IntegerField())),
        liens_morts=Count(Case(When(statut='lien_mort', then=1), output_field=IntegerField())),
    ).order_by('type_document')

    # Liste des fichiers sources pour le filtre
    fichiers_sources = _scope_diamex_queryset(
        BaseDiameX.objects,
        request.user
    ).values_list('fichier_source', flat=True).distinct().order_by('fichier_source')

    # Liste des années disponibles
    annees = docs_scope.values_list('annee', flat=True).distinct().order_by('-annee')

    context = {
        'documents': documents.order_by('-annee', '-mois', 'fichier_source', 'type_document'),
        'stats': stats,
        'stats_par_fichier': stats_par_fichier,
        'stats_par_type': stats_par_type,
        'fichiers_sources': fichiers_sources,
        'annees': annees,
        'fichier_filter': fichier_filter,
        'annee_filter': annee_filter,
        'statut_filter': statut_filter,
    }

    return render(request, 'accounting/documentation_rapport.html', context)


@login_required
@require_http_methods(["GET"])
def api_generer_grand_livre(request):
    """
    API pour générer le Grand Livre avec calculs de soldes et regroupements.

    Paramètres:
    - prog: Code du programme (Fin)
    - annee: Année
    - mois: Mois (1-12)
    - fichier: Fichier source
    """
    try:
        prog = request.GET.get('prog')
        annee = int(request.GET.get('annee'))
        mois = int(request.GET.get('mois'))
        fichier_source = request.GET.get('fichier')

        if not all([prog, annee, mois, fichier_source]):
            return JsonResponse({
                'success': False,
                'error': 'Parametres manquants'
            }, status=400)

        if not _file_in_scope(request.user, fichier_source):
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse pour ce fichier source'
            }, status=403)

        diamex_qs = _scope_diamex_queryset(BaseDiameX.objects.all(), request.user)

        # 1. Calcul du solde de départ (solde fin mois précédent)
        from datetime import date
        if mois == 1:
            mois_precedent = 12
            annee_precedente = annee - 1
        else:
            mois_precedent = mois - 1
            annee_precedente = annee

        # Solde fin mois précédent = cumul jusqu'à la fin du mois précédent
        solde_precedent_qs = diamex_qs.filter(
            prog=prog,
            fichier_source=fichier_source,
            date_m__year__lte=annee_precedente if mois == 1 else annee,
            date_m__month__lte=mois_precedent if mois > 1 or annee_precedente < annee else 12
        ).aggregate(
            total_in=Sum('montant_in'),
            total_out=Sum('montant_out')
        )

        # Convertir en Decimal pour éviter les erreurs de type
        total_in_precedent = Decimal(str(solde_precedent_qs['total_in'])) if solde_precedent_qs['total_in'] else Decimal('0')
        total_out_precedent = Decimal(str(solde_precedent_qs['total_out'])) if solde_precedent_qs['total_out'] else Decimal('0')
        solde_depart = total_in_precedent - total_out_precedent

        # 2. Récupérer les transactions du mois en cours
        # Exclusions: Cat = 00BOOK, 00PERS, (00FND1 qui ne contient pas 'EDF' dans Description)
        transactions_qs = diamex_qs.filter(
            prog=prog,
            fichier_source=fichier_source,
            date_m__year=annee,
            date_m__month=mois
        ).exclude(
            Q(compte_code='00BOOK') |
            Q(compte_code='00PERS') |
            (Q(compte_code='00FND1') & ~Q(description__icontains='EDF'))
        ).select_related().order_by('date_m', 'id_access')

        # 3. Récupérer les libellés des comptes
        from apps.organization.models import Compte
        comptes_dict = {}
        codes_comptes = transactions_qs.values_list('compte_code', flat=True).distinct()
        for code in codes_comptes:
            if code:
                try:
                    compte = Compte.objects.get(code=code)
                    comptes_dict[code] = compte.nom_compte
                except Compte.DoesNotExist:
                    comptes_dict[code] = ''

        # 4. Calculer total période
        total_in = Decimal('0')
        total_out = Decimal('0')

        transactions_list = []
        for trans in transactions_qs:
            montant_in = Decimal(str(trans.montant_in or 0))
            montant_out = Decimal(str(trans.montant_out or 0))
            total_in += montant_in
            total_out += montant_out

            compte_code = trans.compte_code or ''
            transactions_list.append({
                'date': trans.date_m.strftime('%d/%m/%Y') if trans.date_m else '',
                'rec': trans.id_access,
                'description': trans.description or '',
                'detail': trans.detail or '',
                'fournisseur': trans.pers or '',
                'activ': trans.activ or '',
                'cat': compte_code,
                'cat_libelle': comptes_dict.get(compte_code, ''),
                'ccy': float(montant_in - montant_out),
                'in': float(montant_in) if montant_in > 0 else None,
                'out': float(montant_out) if montant_out > 0 else None,
            })

        total_periode = total_in - total_out
        solde_fin = solde_depart + total_periode

        # 4. Regrouper par Dépenses/Recettes puis par Cat
        depenses = []  # Cat commence par 6
        recettes = []  # Cat commence par 7
        edf = []  # Cat 00FND1 avec 'EDF' dans Description

        for trans in transactions_list:
            cat = trans['cat']
            if cat and cat.startswith('6'):
                depenses.append(trans)
            elif cat and cat.startswith('7'):
                recettes.append(trans)
            elif cat == '00FND1' and 'EDF' in (trans['description'] or '').upper():
                edf.append(trans)

        # Grouper par Cat dans chaque section
        def grouper_par_cat(transactions):
            groupes = {}
            for trans in transactions:
                cat = trans['cat'] or 'Sans catégorie'
                if cat not in groupes:
                    groupes[cat] = []
                groupes[cat].append(trans)
            return groupes

        depenses_par_cat = grouper_par_cat(depenses)
        recettes_par_cat = grouper_par_cat(recettes)
        edf_par_cat = grouper_par_cat(edf)

        return JsonResponse({
            'success': True,
            'grand_livre': {
                'prog': prog,
                'mois': mois,
                'annee': annee,
                'titre': f"Grand Livre {prog} - {mois:02d}/{annee}",
                'solde_depart': float(solde_depart),
                'total_periode': float(total_periode),
                'solde_fin': float(solde_fin),
                'depenses': {
                    'total': float(sum(t['ccy'] for t in depenses)),
                    'par_cat': {cat: [t for t in trans] for cat, trans in depenses_par_cat.items()}
                },
                'recettes': {
                    'total': float(sum(t['ccy'] for t in recettes)),
                    'par_cat': {cat: [t for t in trans] for cat, trans in recettes_par_cat.items()}
                },
                'edf': {
                    'total': float(sum(t['ccy'] for t in edf)),
                    'par_cat': {cat: [t for t in trans] for cat, trans in edf_par_cat.items()}
                }
            }
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_rapprochement_solde(request):
    """
    API pour afficher le detail du rapprochement de solde.
    Retourne la comparaison des soldes entre SoldesReels et calculs DiameX.
    """
    try:
        annee = int(request.GET.get('annee'))
        mois = int(request.GET.get('mois'))
        fichier_source = request.GET.get('fichier')

        if not all([annee, mois, fichier_source]):
            return JsonResponse({
                'success': False,
                'error': 'Parametres manquants'
            }, status=400)

        if not _file_in_scope(request.user, fichier_source):
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse pour ce fichier source'
            }, status=403)

        comparaisons = get_comparaison_soldes_mois(annee, mois, fichier_source, request.user)

        return JsonResponse({
            'success': True,
            'titre': f"Rapprochement de solde - {mois:02d}/{annee}",
            'comparaisons': comparaisons
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_compte_tiers(request):
    """
    API pour afficher le recapitulatif des comptes de tiers.
    Calcule le cumul depuis le debut jusqu'a la fin du mois specifie.
    """
    try:
        annee = int(request.GET.get('annee'))
        mois = int(request.GET.get('mois'))
        fichier_source = request.GET.get('fichier')

        if not all([annee, mois, fichier_source]):
            return JsonResponse({
                'success': False,
                'error': 'Parametres manquants'
            }, status=400)

        if not _file_in_scope(request.user, fichier_source):
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse pour ce fichier source'
            }, status=403)

        avances_tiers = get_avances_pers_cumul(annee, mois, fichier_source, request.user)

        return JsonResponse({
            'success': True,
            'titre': f"Recapitulatif compte de tiers - {mois:02d}/{annee}",
            'avances': avances_tiers
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_comptage_caisse(request):
    """
    API pour afficher le detail du comptage de caisse.
    Retourne toutes les transactions des journaux commencant par C pour le mois.
    """
    try:
        annee = int(request.GET.get('annee'))
        mois = int(request.GET.get('mois'))
        fichier_source = request.GET.get('fichier')
        journal_code = request.GET.get('journal')

        if not all([annee, mois, fichier_source, journal_code]):
            return JsonResponse({
                'success': False,
                'error': 'Parametres manquants'
            }, status=400)

        if not _file_in_scope(request.user, fichier_source):
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse pour ce fichier source'
            }, status=403)

        diamex_qs = _scope_diamex_queryset(BaseDiameX.objects.all(), request.user)

        if mois == 1:
            mois_precedent = 12
            annee_precedente = annee - 1
        else:
            mois_precedent = mois - 1
            annee_precedente = annee

        solde_precedent_qs = diamex_qs.filter(
            fichier_source=fichier_source,
            journal_code=journal_code,
            date_m__year__lte=annee_precedente if mois == 1 else annee,
            date_m__month__lte=mois_precedent if mois > 1 or annee_precedente < annee else 12
        ).aggregate(
            total_in=Sum('montant_in'),
            total_out=Sum('montant_out')
        )

        total_in_precedent = Decimal(str(solde_precedent_qs['total_in'])) if solde_precedent_qs['total_in'] else Decimal('0')
        total_out_precedent = Decimal(str(solde_precedent_qs['total_out'])) if solde_precedent_qs['total_out'] else Decimal('0')
        solde_depart = total_in_precedent - total_out_precedent

        transactions_qs = diamex_qs.filter(
            fichier_source=fichier_source,
            journal_code=journal_code,
            date_m__year=annee,
            date_m__month=mois
        ).select_related().order_by('date_m', 'id_access')

        total_in = Decimal('0')
        total_out = Decimal('0')
        transactions_list = []

        for trans in transactions_qs:
            montant_in = Decimal(str(trans.montant_in or 0))
            montant_out = Decimal(str(trans.montant_out or 0))
            total_in += montant_in
            total_out += montant_out

            transactions_list.append({
                'date': trans.date_m.strftime('%d/%m/%Y') if trans.date_m else '',
                'rec': trans.id_access,
                'description': trans.description or '',
                'detail': trans.detail or '',
                'pers': trans.pers or '',
                'compte': trans.compte_code or '',
                'in': float(montant_in) if montant_in > 0 else None,
                'out': float(montant_out) if montant_out > 0 else None,
            })

        total_periode = total_in - total_out
        solde_fin = solde_depart + total_periode

        from .models import SoldesReels
        scan_path = None
        dernier_solde = SoldesReels.objects.filter(
            fichier_source=fichier_source,
            journal=journal_code,
            date_m__year=annee,
            date_m__month=mois
        ).order_by('-date_m', '-rec').first()

        if dernier_solde and dernier_solde.scan:
            scan_relatif = dernier_solde.scan.lstrip('.')
            if scan_relatif.startswith(dernier_solde.chemin_base or ''):
                scan_path = scan_relatif
            else:
                scan_path = (dernier_solde.chemin_base or '') + scan_relatif

        return JsonResponse({
            'success': True,
            'titre': f"Comptage caisse {journal_code} - {mois:02d}/{annee}",
            'journal': journal_code,
            'solde_depart': float(solde_depart),
            'total_in': float(total_in),
            'total_out': float(total_out),
            'total_periode': float(total_periode),
            'solde_fin': float(solde_fin),
            'transactions': transactions_list,
            'scan_path': scan_path
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_releve_bancaire(request):
    """
    API pour afficher le detail du releve bancaire.
    Retourne toutes les transactions des journaux commencant par B pour le mois.
    """
    try:
        annee = int(request.GET.get('annee'))
        mois = int(request.GET.get('mois'))
        fichier_source = request.GET.get('fichier')
        journal_code = request.GET.get('journal')

        if not all([annee, mois, fichier_source, journal_code]):
            return JsonResponse({
                'success': False,
                'error': 'Parametres manquants'
            }, status=400)

        if not _file_in_scope(request.user, fichier_source):
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse pour ce fichier source'
            }, status=403)

        diamex_qs = _scope_diamex_queryset(BaseDiameX.objects.all(), request.user)

        if mois == 1:
            mois_precedent = 12
            annee_precedente = annee - 1
        else:
            mois_precedent = mois - 1
            annee_precedente = annee

        solde_precedent_qs = diamex_qs.filter(
            fichier_source=fichier_source,
            journal_code=journal_code,
            date_m__year__lte=annee_precedente if mois == 1 else annee,
            date_m__month__lte=mois_precedent if mois > 1 or annee_precedente < annee else 12
        ).aggregate(
            total_in=Sum('montant_in'),
            total_out=Sum('montant_out')
        )

        total_in_precedent = Decimal(str(solde_precedent_qs['total_in'])) if solde_precedent_qs['total_in'] else Decimal('0')
        total_out_precedent = Decimal(str(solde_precedent_qs['total_out'])) if solde_precedent_qs['total_out'] else Decimal('0')
        solde_depart = total_in_precedent - total_out_precedent

        transactions_qs = diamex_qs.filter(
            fichier_source=fichier_source,
            journal_code=journal_code,
            date_m__year=annee,
            date_m__month=mois
        ).select_related().order_by('date_m', 'id_access')

        total_in = Decimal('0')
        total_out = Decimal('0')
        transactions_list = []

        for trans in transactions_qs:
            montant_in = Decimal(str(trans.montant_in or 0))
            montant_out = Decimal(str(trans.montant_out or 0))
            total_in += montant_in
            total_out += montant_out

            transactions_list.append({
                'date': trans.date_m.strftime('%d/%m/%Y') if trans.date_m else '',
                'rec': trans.id_access,
                'description': trans.description or '',
                'detail': trans.detail or '',
                'pers': trans.pers or '',
                'compte': trans.compte_code or '',
                'in': float(montant_in) if montant_in > 0 else None,
                'out': float(montant_out) if montant_out > 0 else None,
            })

        total_periode = total_in - total_out
        solde_fin = solde_depart + total_periode

        from .models import SoldesReels
        scan_path = None
        dernier_solde = SoldesReels.objects.filter(
            fichier_source=fichier_source,
            journal=journal_code,
            date_m__year=annee,
            date_m__month=mois
        ).order_by('-date_m', '-rec').first()

        if dernier_solde and dernier_solde.scan:
            scan_relatif = dernier_solde.scan.lstrip('.')
            if scan_relatif.startswith(dernier_solde.chemin_base or ''):
                scan_path = scan_relatif
            else:
                scan_path = (dernier_solde.chemin_base or '') + scan_relatif

        return JsonResponse({
            'success': True,
            'titre': f"Releve bancaire {journal_code} - {mois:02d}/{annee}",
            'journal': journal_code,
            'solde_depart': float(solde_depart),
            'total_in': float(total_in),
            'total_out': float(total_out),
            'total_periode': float(total_periode),
            'solde_fin': float(solde_fin),
            'transactions': transactions_list,
            'scan_path': scan_path
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)
