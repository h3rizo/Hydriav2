"""
Vues pour la gestion des transactions DiameX temporaires
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.utils import timezone
from django.core.paginator import Paginator
from .models import DiameXTemporaire
import csv
from datetime import datetime


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _filter_transactions_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset

    from apps.organization.models import Base
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

    scope_q = (
        Q(planning_detail__planning__employe__base__organisation_id=organisation_id) |
        Q(salaire__grille_salaire__contrat__employe__base__organisation_id=organisation_id) |
        Q(paiement_irsa__organisation_id=organisation_id) |
        Q(paiement_cnaps_fmfp__organisation_id=organisation_id) |
        Q(paiement_mutuelle_sante__organisation_id=organisation_id) |
        Q(created_by__base__organisation_id=organisation_id) |
        Q(validated_by__base__organisation_id=organisation_id)
    )
    if allowed_progs:
        scope_q = scope_q | Q(prog__in=allowed_progs)

    return queryset.filter(scope_q).distinct()


def creer_transaction_depuis_planning_detail(planning_detail, type_transaction='avance', created_by=None):
    """
    Fonction utilitaire pour créer une transaction temporaire depuis un PlanningDetail

    Args:
        planning_detail: Instance de PlanningDetail
        type_transaction: Type de transaction ('avance', 'depense', 'recette', 'transfert')
        created_by: Instance d'Employe qui crée la transaction

    Returns:
        Instance de DiameXTemporaire créée
    """
    from apps.planning.models import PlanningDetail

    # Récupérer les informations du planning detail
    planning = planning_detail.planning
    employe = planning.employe if planning else None

    # Déterminer le compte selon le type
    compte_code = '00PERS'  # Par défaut pour avances

    # Calculer les montants IN/OUT selon le type
    montant = planning_detail.montant or 0
    montant_in = 0
    montant_out = 0

    if type_transaction == 'avance':
        montant_out = montant  # Avance = sortie d'argent
    elif type_transaction == 'recette':
        montant_in = montant  # Recette = entrée d'argent
    elif type_transaction == 'depense':
        montant_out = montant

    # Construire la description
    designation_nom = planning_detail.designation.nom if planning_detail.designation else 'Sans désignation'
    employe_nom = f"{employe.surnom or employe.prenom} {employe.nom}" if employe else "Inconnu"
    description = f"{designation_nom} - {employe_nom}"

    # Créer la transaction temporaire
    transaction = DiameXTemporaire.objects.create(
        planning_detail=planning_detail,
        type_transaction=type_transaction,
        journal_code='CA',  # Journal Caisse par défaut
        date_m=planning.date if planning else timezone.now().date(),
        date_rec=timezone.now().date(),
        description=description,
        montant_in=montant_in,
        montant_out=montant_out,
        compte_code=compte_code,
        pers=employe.surnom if employe and employe.surnom else (employe.prenom if employe else ''),
        detail='',  # PlanningDetail n'a pas de champ detail
        info='',  # PlanningDetail n'a pas de champ info
        prog=employe.base.prog_diamex if employe and hasattr(employe, 'base') and employe.base else '',
        created_by=created_by,
        statut='en_attente'
    )

    return transaction


@login_required
def transactions_temporaires_list(request):
    """
    Page de gestion des transactions temporaires DiameX
    - Liste avec filtres
    - Sélection pour validation/rejet/export
    """
    from apps.organization.models import Journal, Compte
    from apps.employees.models import EmployeBaseDiameX

    # Filtres
    statut_filter = request.GET.get('statut', '')
    type_filter = request.GET.get('type', '')
    search = request.GET.get('search', '').strip()
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    # Queryset de base - Exclure les transactions exportées par défaut
    # ET exclure les transactions liées aux salaires/IRSA (page dédiée)
    transactions = DiameXTemporaire.objects.select_related(
        'planning_detail__planning__employe',
        'created_by',
        'validated_by'
    ).exclude(statut='exporte').exclude(
        Q(salaire__isnull=False) |
        Q(paiement_irsa__isnull=False) |
        Q(description__icontains='_Salaire_') |  # Filtre par description aussi
        Q(description__icontains='_IRSA_')       # (pour transactions anciennes sans FK)
    )  # ✅ Masquer exportées + salaires/IRSA

    transactions = _filter_transactions_by_scope(transactions, request.user)

    # Liste des journaux pour le modal
    journaux = Journal.objects.all()
    comptes = Compte.objects.all()
    if not request.user.is_superuser:
        organisation_id = _get_user_organisation_id(request.user)
        if organisation_id:
            journaux = journaux.filter(base__organisation_id=organisation_id)
            comptes = comptes.filter(organisation_id=organisation_id)
        else:
            journaux = journaux.none()
            comptes = comptes.none()
    journaux = journaux.order_by('code')
    comptes = comptes.order_by('compte')

    # Bases DiameX de l'employé connecté pour l'export
    employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None
    bases_employe = []
    if employe:
        bases_qs = EmployeBaseDiameX.objects.filter(employe=employe)
        for base in bases_qs:
            bases_employe.append({
                'id': str(base.id),
                'base_diamex': base.base_diamex,
                'chemin_base_diamex': base.chemin_base_diamex,
                'chemin_complet': base.chemin_complet,
            })

    # Appliquer les filtres
    if statut_filter:
        transactions = transactions.filter(statut=statut_filter)

    if type_filter:
        transactions = transactions.filter(type_transaction=type_filter)

    if search:
        transactions = transactions.filter(
            Q(description__icontains=search) |
            Q(info__icontains=search) |
            Q(pers__icontains=search) |
            Q(detail__icontains=search)
        )

    if date_debut:
        transactions = transactions.filter(date_m__gte=date_debut)

    if date_fin:
        transactions = transactions.filter(date_m__lte=date_fin)

    # Statistiques
    total = transactions.count()
    en_attente = transactions.filter(statut='en_attente').count()
    valides = transactions.filter(statut='valide').count()
    rejetes = transactions.filter(statut='rejete').count()
    exportes = transactions.filter(statut='exporte').count()

    # Pagination
    paginator = Paginator(transactions, 50)
    page_number = request.GET.get('page', 1)

    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1

    page_obj = paginator.get_page(page_number)

    # Liste des comptes pour le dropdown deja cloisonnee ci-dessus

    return render(request, 'accounting/transactions_temporaires_list.html', {
        'page_obj': page_obj,
        'transactions': page_obj,
        'total': total,
        'en_attente': en_attente,
        'valides': valides,
        'rejetes': rejetes,
        'exportes': exportes,
        'journaux': journaux,
        'bases_employe': bases_employe,
        'comptes': comptes,  # Ajout des comptes pour le dropdown
    })


@login_required
@require_http_methods(["POST"])
def transaction_temporaire_change_status(request):
    """
    Changer le statut de transactions (valider/rejeter)
    """
    transaction_ids = request.POST.getlist('transaction_ids[]')
    action = request.POST.get('action')  # 'valider' ou 'rejeter'

    if not transaction_ids or not action:
        return JsonResponse({
            'success': False,
            'error': 'Paramètres manquants'
        }, status=400)

    # Déterminer le nouveau statut
    nouveau_statut = 'valide' if action == 'valider' else 'rejete'

    # Mettre à jour les transactions
    scoped_ids = _filter_transactions_by_scope(
        DiameXTemporaire.objects.all(),
        request.user
    ).values_list('id', flat=True)
    scoped_ids = set(scoped_ids)
    filtered_ids = [int(tid) for tid in transaction_ids if str(tid).isdigit() and int(tid) in scoped_ids]
    updated = DiameXTemporaire.objects.filter(
        id__in=filtered_ids,
        statut='en_attente'  # Seulement les transactions en attente
    ).update(
        statut=nouveau_statut,
        validated_at=timezone.now(),
        validated_by=request.user.employe if hasattr(request.user, 'employe') else None
    )

    return JsonResponse({
        'success': True,
        'updated': updated,
        'statut': nouveau_statut,
        'message': f'{updated} transaction(s) {nouveau_statut}(s)'
    })


@login_required
@require_http_methods(["POST"])
def transaction_temporaire_delete(request):
    """
    Supprimer des transactions temporaires
    """
    transaction_ids = request.POST.getlist('transaction_ids[]')

    if not transaction_ids:
        return JsonResponse({
            'success': False,
            'error': 'Aucune transaction sélectionnée'
        }, status=400)

    # Supprimer uniquement les transactions non exportées
    scoped_ids = _filter_transactions_by_scope(
        DiameXTemporaire.objects.all(),
        request.user
    ).values_list('id', flat=True)
    scoped_ids = set(scoped_ids)
    filtered_ids = [int(tid) for tid in transaction_ids if str(tid).isdigit() and int(tid) in scoped_ids]
    deleted_count, _ = DiameXTemporaire.objects.filter(
        id__in=filtered_ids
    ).exclude(statut='exporte').delete()

    return JsonResponse({
        'success': True,
        'deleted': deleted_count,
        'message': f'{deleted_count} transaction(s) supprimée(s)'
    })


@login_required
def export_transactions_csv(request):
    """
    Exporter les transactions validées vers un fichier CSV compatible DiameX
    """
    transaction_ids = request.GET.getlist('ids')

    if not transaction_ids:
        # Si aucun ID spécifié, exporter toutes les transactions validées
        transactions = _filter_transactions_by_scope(
            DiameXTemporaire.objects.filter(statut='valide'),
            request.user
        )
    else:
        transactions = _filter_transactions_by_scope(
            DiameXTemporaire.objects.all(),
            request.user
        ).filter(
            id__in=transaction_ids,
            statut='valide'
        )

    if not transactions.exists():
        return HttpResponse("Aucune transaction validée à exporter", status=400)

    # Créer la réponse CSV
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f'DiameX_Export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # Ajouter BOM UTF-8 pour Excel
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')

    # En-têtes (colonnes DiameX)
    writer.writerow([
        'Journal',
        'Date_M',
        'Rec',
        'Date_Rec',
        'Description',
        'In',
        'Out',
        'Compte',
        'PERS',
        'Detail',
        'Info',
        'Fin',
        'Scan',
        'Prog'
    ])

    # Générer un ID de lot d'export
    export_batch = f"EXP_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Données
    for transaction in transactions:
        writer.writerow([
            transaction.journal_code or '',
            transaction.date_m.strftime('%d/%m/%Y') if transaction.date_m else '',
            transaction.rec or '',
            transaction.date_rec.strftime('%d/%m/%Y') if transaction.date_rec else '',
            transaction.description or '',
            f"{transaction.montant_in:.2f}".replace('.', ',') if transaction.montant_in else '0',
            f"{transaction.montant_out:.2f}".replace('.', ',') if transaction.montant_out else '0',
            transaction.compte_code or '',
            transaction.pers or '',
            transaction.detail or '',
            transaction.info or '',
            transaction.fin or 'RL Activités',
            transaction.scan or '',
            transaction.prog or ''
        ])

        # Marquer comme exporté
        transaction.statut = 'exporte'
        transaction.export_batch = export_batch
        transaction.save(update_fields=['statut', 'export_batch'])

    return response


@login_required
def transaction_temporaire_get(request, transaction_id):
    """
    Récupérer les données d'une transaction pour l'édition
    """
    try:
        transaction = _filter_transactions_by_scope(DiameXTemporaire.objects.select_related(
            'planning_detail__planning__employe__base'
        ), request.user).get(id=transaction_id)

        # Récupérer les infos de la base de l'employé (pour auto-remplissage)
        base_diamex_value = ''
        volet_value = ''
        surnom_employe = ''
        if (transaction.planning_detail and
            transaction.planning_detail.planning and
            transaction.planning_detail.planning.employe):
            employe = transaction.planning_detail.planning.employe
            surnom_employe = employe.surnom or ''
            if employe.base:
                base_diamex_value = employe.base.base_diamex or ''
                volet_value = employe.base.volet or ''

        return JsonResponse({
            'success': True,
            'transaction': {
                'id': transaction.id,
                'journal_code': transaction.journal_code or '',
                'type_transaction': transaction.type_transaction,
                'date_m': transaction.date_m.strftime('%Y-%m-%d') if transaction.date_m else '',
                'date_rec': transaction.date_rec.strftime('%Y-%m-%d') if transaction.date_rec else '',
                'description': transaction.description or '',
                'montant_in': float(transaction.montant_in) if transaction.montant_in else 0,
                'montant_out': float(transaction.montant_out) if transaction.montant_out else 0,
                'compte_code': transaction.compte_code or '',
                'pers': transaction.pers or '',
                'detail': transaction.detail or '',
                'info': transaction.info or '',
                'prog': transaction.prog or '',
                'activ': transaction.activ or '',
                'fin': transaction.fin or '',
                'scan': transaction.scan or '',
                # Données de l'employé pour auto-remplissage
                'base_diamex_employe': base_diamex_value,
                'volet_employe': volet_value,
                'surnom_employe': surnom_employe,
            }
        })
    except DiameXTemporaire.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Transaction introuvable'
        }, status=404)


@login_required
@require_http_methods(["POST"])
def transaction_temporaire_update(request, transaction_id):
    """
    Mettre à jour une transaction temporaire
    """
    try:
        transaction = _filter_transactions_by_scope(
            DiameXTemporaire.objects.all(),
            request.user
        ).get(id=transaction_id)

        # Ne pas permettre la modification des transactions exportées
        if transaction.statut == 'exporte':
            return JsonResponse({
                'success': False,
                'error': 'Impossible de modifier une transaction déjà exportée'
            }, status=400)

        # Récupérer les données du formulaire
        transaction.journal_code = request.POST.get('journal_code', '')
        transaction.type_transaction = request.POST.get('type_transaction', 'avance')

        # Dates
        date_m_str = request.POST.get('date_m')
        if date_m_str:
            transaction.date_m = datetime.strptime(date_m_str, '%Y-%m-%d').date()

        date_rec_str = request.POST.get('date_rec')
        if date_rec_str:
            transaction.date_rec = datetime.strptime(date_rec_str, '%Y-%m-%d').date()

        transaction.description = request.POST.get('description', '')

        # Montants
        try:
            transaction.montant_in = float(request.POST.get('montant_in', 0))
        except (ValueError, TypeError):
            transaction.montant_in = 0

        try:
            transaction.montant_out = float(request.POST.get('montant_out', 0))
        except (ValueError, TypeError):
            transaction.montant_out = 0

        transaction.compte_code = request.POST.get('compte_code', '')
        transaction.pers = request.POST.get('pers', '')
        transaction.detail = request.POST.get('detail', '')
        transaction.info = request.POST.get('info', '')
        transaction.prog = request.POST.get('prog', '')
        transaction.activ = request.POST.get('activ', '')  # Nouveau champ ACTIV
        transaction.fin = request.POST.get('fin', '')  # Financement
        transaction.scan = request.POST.get('scan', '')

        transaction.save()

        return JsonResponse({
            'success': True,
            'message': 'Transaction mise à jour avec succès'
        })

    except DiameXTemporaire.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Transaction introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de la mise à jour: {str(e)}'
        }, status=500)


@login_required
def transactions_temporaires_salaires_list(request):
    """
    Vue pour lister les transactions DiameX temporaires liées aux SALAIRES, IRSA et CNaPS/FMFP.
    Page réservée aux administrateurs pour la gestion des exports paie & charges.
    """
    from apps.employees.models import EmployeBaseDiameX
    from apps.organization.models import Journal

    # Filtres
    statut_filter = request.GET.get('statut', '')
    type_filter = request.GET.get('type', '')
    search = request.GET.get('search', '').strip()
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    # Queryset de base - UNIQUEMENT les transactions liées aux salaires, IRSA ou CNaPS/FMFP
    transactions = DiameXTemporaire.objects.select_related(
        'salaire__grille_salaire__contrat__employe',
        'paiement_irsa__organisation',
        'paiement_cnaps_fmfp__organisation',
        'created_by',
        'validated_by'
    ).filter(
        Q(salaire__isnull=False) |
        Q(paiement_irsa__isnull=False) |
        Q(paiement_cnaps_fmfp__isnull=False) |
        Q(description__icontains='_Salaire_') |  # Inclure aussi par description
        Q(description__icontains='_IRSA_') |     # (pour transactions anciennes sans FK)
        Q(description__icontains='_Charge CNaPS_') |
        Q(description__icontains='_Charge FMFP_')
    ).exclude(statut='exporte')  # Masquer les exportées

    transactions = _filter_transactions_by_scope(transactions, request.user)

    # Liste des journaux pour le modal
    journaux = Journal.objects.all()
    if not request.user.is_superuser:
        organisation_id = _get_user_organisation_id(request.user)
        if organisation_id:
            journaux = journaux.filter(base__organisation_id=organisation_id)
        else:
            journaux = journaux.none()
    journaux = journaux.order_by('code')

    # Bases DiameX de l'employé connecté pour l'export
    employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None
    bases_employe = []
    if employe:
        bases_qs = EmployeBaseDiameX.objects.filter(employe=employe)
        for base in bases_qs:
            bases_employe.append({
                'id': str(base.id),
                'base_diamex': base.base_diamex,
                'chemin_base_diamex': base.chemin_base_diamex,
                'chemin_complet': base.chemin_complet,
            })

    # Appliquer les filtres
    if statut_filter:
        transactions = transactions.filter(statut=statut_filter)

    if type_filter:
        transactions = transactions.filter(type_transaction=type_filter)

    if search:
        transactions = transactions.filter(
            Q(description__icontains=search) |
            Q(info__icontains=search) |
            Q(pers__icontains=search) |
            Q(detail__icontains=search)
        )

    if date_debut:
        transactions = transactions.filter(date_m__gte=date_debut)

    if date_fin:
        transactions = transactions.filter(date_m__lte=date_fin)

    # Statistiques
    total = transactions.count()
    en_attente = transactions.filter(statut='en_attente').count()
    valides = transactions.filter(statut='valide').count()
    rejetes = transactions.filter(statut='rejete').count()
    exportes = _filter_transactions_by_scope(DiameXTemporaire.objects.filter(
        Q(salaire__isnull=False) | Q(paiement_irsa__isnull=False) | Q(paiement_cnaps_fmfp__isnull=False),
        statut='exporte'
    ), request.user).count()

    # Ordre chronologique inverse
    transactions = transactions.order_by('-created_at')

    # Pagination
    paginator = Paginator(transactions, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'transactions': page_obj,
        'page_obj': page_obj,
        'total': total,
        'en_attente': en_attente,
        'valides': valides,
        'rejetes': rejetes,
        'exportes': exportes,
        'journaux': journaux,
        'bases_employe': bases_employe,
    }

    return render(request, 'accounting/transactions_temporaires_salaires.html', context)


@login_required
@require_http_methods(["POST"])
def api_update_ids_diamex(request):
    """
    API pour sauvegarder les ID DiameX et Prog d'une transaction.
    Utilisé pour le workflow de copie depuis Access.
    """
    import json
    from django.views.decorators.csrf import csrf_exempt

    try:
        data = json.loads(request.body)
        transaction_id = data.get('transaction_id')
        id_diamex = data.get('id_diamex', '').strip()
        prog = data.get('prog', '').strip()

        if not transaction_id:
            return JsonResponse({
                'success': False,
                'error': 'ID de transaction manquant'
            }, status=400)

        # Récupérer la transaction
        transaction = _filter_transactions_by_scope(
            DiameXTemporaire.objects.all(),
            request.user
        ).get(id=transaction_id)

        # Mettre à jour les champs
        transaction.id_diamex = id_diamex if id_diamex else None
        transaction.prog = prog if prog else None
        transaction.save(update_fields=['id_diamex', 'prog'])

        # Si c'est un salaire, copier vers la table Salaire
        if transaction.salaire:
            transaction.salaire.numero_diamex_salaire = id_diamex if id_diamex else None
            transaction.salaire.base_diamex_salaire = prog if prog else None
            transaction.salaire.save(update_fields=['numero_diamex_salaire', 'base_diamex_salaire'])

        # Si c'est un paiement IRSA, copier vers la table Salaire (colonnes IRSA)
        if transaction.paiement_irsa:
            # Trouver le salaire correspondant via l'employé et le mois/année
            paiement_irsa = transaction.paiement_irsa
            employe = paiement_irsa.organisation.get_employe_from_detail(transaction.detail) if hasattr(paiement_irsa.organisation, 'get_employe_from_detail') else None

            if not employe:
                # Essayer de trouver l'employé via le champ detail (surnom ou prénom)
                from apps.employees.models import Employe
                employe = Employe.objects.filter(
                    Q(surnom=transaction.detail) | Q(prenom=transaction.detail)
                ).first()

            if employe:
                # Trouver le salaire correspondant au mois/année du paiement IRSA
                from apps.employees.models import Salaire
                salaire = Salaire.objects.filter(
                    grille_salaire__contrat__employe=employe,
                    date_paiement__year=paiement_irsa.annee,
                    date_paiement__month=paiement_irsa.mois
                ).first()

                if salaire:
                    salaire.numero_diamex_irsa = id_diamex if id_diamex else None
                    salaire.base_diamex_irsa = prog if prog else None
                    salaire.save(update_fields=['numero_diamex_irsa', 'base_diamex_irsa'])

        return JsonResponse({
            'success': True,
            'message': 'IDs sauvegardés avec succès'
        })

    except DiameXTemporaire.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Transaction introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur: {str(e)}'
        }, status=500)
