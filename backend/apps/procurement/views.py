import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.billing.models import Fournisseur
from apps.organization.models import Base
from apps.planning.models import Designation

from .models import (
    BonCommande,
    BonCommandeItem,
    DemandeAchat,
    DemandeAchatItem,
    Proforma,
    ProformaItem,
)


def _get_employe(request):
    return getattr(request.user, 'employe', None)


def _get_user_organisation(request):
    employe = _get_employe(request)
    if employe and employe.base:
        return employe.base.organisation
    return None


def _bases_disponibles(request):
    """Bases sélectionnables pour une demande d'achat : celles de l'organisation
    de l'utilisateur connecté, ou toutes les bases pour un superuser sans organisation."""
    organisation = _get_user_organisation(request)
    if organisation:
        return Base.objects.filter(organisation=organisation).order_by('nom_base')
    if request.user.is_superuser:
        return Base.objects.all().order_by('nom_base')
    return Base.objects.none()


def _get_demande_or_404(request, demande_id, queryset=None):
    """Récupère une DemandeAchat en vérifiant qu'elle appartient à l'organisation
    de l'utilisateur connecté (isolation multi-organisation). Un superuser voit tout."""
    base_queryset = queryset if queryset is not None else DemandeAchat.objects
    demande = get_object_or_404(base_queryset, id=demande_id)

    if not request.user.is_superuser:
        organisation = _get_user_organisation(request)
        if organisation is None or demande.base.organisation_id != organisation.id:
            raise Http404("Demande d'achat introuvable.")

    return demande


# ---------------------------------------------------------------------------
# Liste des demandes d'achat (tableau de bord du workflow)
# ---------------------------------------------------------------------------

@login_required
def demande_achat_list(request):
    bases_disponibles = _bases_disponibles(request)
    demandes = DemandeAchat.objects.filter(
        base__in=bases_disponibles
    ).select_related('base', 'demandeur').prefetch_related('items')

    statut_filter = request.GET.get('statut', '')
    if statut_filter:
        demandes = demandes.filter(statut=statut_filter)

    base_filter = request.GET.get('base', '')
    if base_filter:
        demandes = demandes.filter(base_id=base_filter)

    context = {
        'demandes': demandes,
        'bases': bases_disponibles,
        'statut_choices': DemandeAchat.STATUT_CHOICES,
        'statut_filter': statut_filter,
        'base_filter': base_filter,
    }
    return render(request, 'procurement/demande_achat_list.html', context)


# ---------------------------------------------------------------------------
# Étape 1 : Création de la Demande d'Achat
# ---------------------------------------------------------------------------

@login_required
def demande_achat_create(request):
    if request.method == 'POST':
        base_id = request.POST.get('base')
        motif = request.POST.get('motif', '').strip()
        designations_ids = request.POST.getlist('designation[]')
        quantites = request.POST.getlist('quantite[]')
        remarques_list = request.POST.getlist('remarques[]')

        if not base_id or not motif:
            messages.error(request, "La base et le motif sont obligatoires.")
            return redirect('procurement:demande_achat_create')

        if not designations_ids:
            messages.error(request, "Veuillez ajouter au moins un article à la demande.")
            return redirect('procurement:demande_achat_create')

        employe = _get_employe(request)
        if employe is None:
            messages.error(request, "Votre compte n'est lié à aucun employé, impossible de créer une demande.")
            return redirect('procurement:demande_achat_list')

        try:
            with transaction.atomic():
                demande = DemandeAchat.objects.create(
                    base_id=base_id,
                    demandeur=employe,
                    motif=motif,
                    statut='brouillon',
                )

                for idx, designation_id in enumerate(designations_ids):
                    if not designation_id:
                        continue
                    quantite_raw = quantites[idx] if idx < len(quantites) else '0'
                    try:
                        quantite = Decimal(str(quantite_raw).replace(',', '.'))
                    except InvalidOperation:
                        quantite = Decimal('0')
                    if quantite <= 0:
                        continue

                    DemandeAchatItem.objects.create(
                        demande=demande,
                        designation_id=designation_id,
                        quantite=quantite,
                        remarques=(remarques_list[idx] if idx < len(remarques_list) else '').strip() or None,
                    )

                if not demande.items.exists():
                    raise ValueError("Aucun article valide n'a été fourni.")

                demande.statut = 'proformas'
                demande.save(update_fields=['statut'])

            messages.success(request, f"Demande d'achat {demande.numero_demande} créée avec succès.")
            return redirect('procurement:demande_achat_detail', demande_id=demande.id)

        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('procurement:demande_achat_create')

    context = {
        'bases': _bases_disponibles(request),
        'designations': Designation.objects.filter(actif=True).order_by('nom'),
    }
    return render(request, 'procurement/demande_form.html', context)


@login_required
def demande_achat_edit(request, demande_id):
    demande = _get_demande_or_404(request, demande_id, DemandeAchat.objects.prefetch_related('items__designation'))

    if demande.statut == 'termine':
        messages.error(request, "Cette demande est terminée (bons de commande déjà générés) et ne peut plus être modifiée.")
        return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    if request.method == 'POST':
        base_id = request.POST.get('base')
        motif = request.POST.get('motif', '').strip()
        designations_ids = request.POST.getlist('designation[]')
        quantites = request.POST.getlist('quantite[]')
        remarques_list = request.POST.getlist('remarques[]')

        if not base_id or not motif:
            messages.error(request, "La base et le motif sont obligatoires.")
            return redirect('procurement:demande_achat_edit', demande_id=demande.id)

        if not designations_ids:
            messages.error(request, "Veuillez conserver au moins un article dans la demande.")
            return redirect('procurement:demande_achat_edit', demande_id=demande.id)

        try:
            with transaction.atomic():
                demande.base_id = base_id
                demande.motif = motif
                demande.save(update_fields=['base', 'motif'])

                # Synchronise les lignes par désignation plutôt que de tout recréer :
                # un article conservé garde le même DemandeAchatItem.id, donc les
                # ProformaItem (prix déjà saisis) qui lui sont liés restent intacts.
                # Seuls les articles réellement retirés perdent leurs offres (CASCADE).
                designations_soumises = {}
                for idx, designation_id in enumerate(designations_ids):
                    if not designation_id:
                        continue
                    quantite_raw = quantites[idx] if idx < len(quantites) else '0'
                    try:
                        quantite = Decimal(str(quantite_raw).replace(',', '.'))
                    except InvalidOperation:
                        quantite = Decimal('0')
                    if quantite <= 0:
                        continue
                    designations_soumises[designation_id] = {
                        'quantite': quantite,
                        'remarques': (remarques_list[idx] if idx < len(remarques_list) else '').strip() or None,
                    }

                items_existants = {str(item.designation_id): item for item in demande.items.all()}

                # Supprimer les articles retirés (entraîne la suppression en cascade de leurs offres)
                for designation_id, item in items_existants.items():
                    if designation_id not in designations_soumises:
                        item.delete()

                # Mettre à jour les articles conservés, créer les nouveaux
                for designation_id, valeurs in designations_soumises.items():
                    if designation_id in items_existants:
                        item = items_existants[designation_id]
                        item.quantite = valeurs['quantite']
                        item.remarques = valeurs['remarques']
                        item.save(update_fields=['quantite', 'remarques'])
                    else:
                        DemandeAchatItem.objects.create(
                            demande=demande,
                            designation_id=designation_id,
                            quantite=valeurs['quantite'],
                            remarques=valeurs['remarques'],
                        )

                if not demande.items.exists():
                    raise ValueError("Aucun article valide n'a été fourni.")

                # Si des proformas existaient déjà, un article a pu être retiré/modifié :
                # repasser la demande en statut d'analyse pour forcer une re-vérification
                # de la sélection avant de générer les bons de commande.
                if demande.proformas.exists() and demande.statut == 'analyse':
                    demande.statut = 'proformas'
                    demande.save(update_fields=['statut'])

            messages.success(request, f"Demande d'achat {demande.numero_demande} mise à jour avec succès.")
            return redirect('procurement:demande_achat_detail', demande_id=demande.id)

        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('procurement:demande_achat_edit', demande_id=demande.id)

    context = {
        'demande': demande,
        'bases': _bases_disponibles(request),
        'designations': Designation.objects.filter(actif=True).order_by('nom'),
    }
    return render(request, 'procurement/demande_edit_form.html', context)


@login_required
def demande_achat_detail(request, demande_id):
    demande = _get_demande_or_404(
        request, demande_id,
        DemandeAchat.objects.select_related('base', 'demandeur').prefetch_related(
            'items__designation', 'items__offres', 'proformas__fournisseur',
        ),
    )
    # "Offre" = un fournisseur a effectivement proposé un prix pour cet article. Un ProformaItem
    # peut exister avec prix_unitaire=None (article non rempli lors d'une saisie multi-articles),
    # ce n'est donc pas une vraie offre : on ne compte que les prix effectivement renseignés.
    items = list(demande.items.all())
    for item in items:
        item.nb_offres_avec_prix = sum(1 for offre in item.offres.all() if offre.prix_unitaire is not None)
    items_sans_offre = [item for item in items if item.nb_offres_avec_prix == 0]

    context = {
        'demande': demande,
        'items': items,
        'nb_fournisseurs': demande.proformas.values('fournisseur_id').distinct().count(),
        'items_sans_offre': items_sans_offre,
    }
    return render(request, 'procurement/demande_detail.html', context)


# ---------------------------------------------------------------------------
# Étape 2 : Saisie des Proformas
# ---------------------------------------------------------------------------

@login_required
def proforma_create(request, demande_id):
    demande = _get_demande_or_404(request, demande_id, DemandeAchat.objects.prefetch_related('items__designation'))

    if demande.statut in ('termine', 'annule'):
        messages.error(request, "Cette demande d'achat n'accepte plus de nouveaux proformas.")
        return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    # Mode "achat direct" : formulaire restreint à un seul article sans offre, ouvert
    # à tous les fournisseurs actifs (pas seulement ceux marqués Devis), puisqu'il s'agit
    # d'un achat ponctuel hors mise en concurrence plutôt que d'une réponse à consultation.
    item_id_restriction = request.GET.get('item') or request.POST.get('item_restriction') or None
    item_unique = None
    if item_id_restriction:
        item_unique = demande.items.filter(id=item_id_restriction).select_related('designation').first()
        if item_unique is None:
            messages.error(request, "Article introuvable pour cette demande.")
            return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    if request.method == 'POST':
        fournisseur_id = request.POST.get('fournisseur')
        date_reception = request.POST.get('date_reception') or None
        scan_document = request.FILES.get('scan_document')

        if not fournisseur_id:
            messages.error(request, "Veuillez sélectionner un fournisseur.")
            return redirect(request.get_full_path())

        items_a_traiter = [item_unique] if item_unique else list(demande.items.all())

        if item_unique:
            prix_raw = request.POST.get(f'prix_{item_unique.id}', '').strip()
            if not prix_raw:
                messages.error(request, "Veuillez indiquer le prix pour cet achat direct.")
                return redirect(request.get_full_path())

        proforma_existant = Proforma.objects.filter(demande_achat=demande, fournisseur_id=fournisseur_id).first()

        if proforma_existant and not item_unique:
            messages.error(request, "Ce fournisseur a déjà soumis un proforma pour cette demande. Modifiez-le plutôt.")
            return redirect('procurement:demande_achat_detail', demande_id=demande.id)

        try:
            with transaction.atomic():
                if proforma_existant:
                    # Le fournisseur a déjà un proforma pour cette DA (autre article) :
                    # on complète son proforma existant au lieu d'en créer un second
                    # (contrainte d'unicité demande_achat/fournisseur).
                    proforma = proforma_existant
                    if scan_document:
                        proforma.scan_document = scan_document
                    if date_reception:
                        proforma.date_reception = date_reception
                    proforma.save()
                else:
                    proforma_kwargs = {
                        'demande_achat': demande,
                        'fournisseur_id': fournisseur_id,
                        'scan_document': scan_document,
                    }
                    if date_reception:
                        proforma_kwargs['date_reception'] = date_reception
                    proforma = Proforma.objects.create(**proforma_kwargs)

                for item in items_a_traiter:
                    prix_raw = request.POST.get(f'prix_{item.id}', '').strip()
                    prix_unitaire = None
                    if prix_raw:
                        try:
                            prix_unitaire = Decimal(prix_raw.replace(',', '.'))
                        except InvalidOperation:
                            prix_unitaire = None

                    offre_existante = ProformaItem.objects.filter(proforma=proforma, demande_item=item).first()
                    if offre_existante is not None:
                        if offre_existante.prix_unitaire is not None and prix_unitaire is not None:
                            # Un vrai prix était déjà renseigné : ne pas l'écraser silencieusement,
                            # l'utilisateur doit passer par la modification du proforma pour le changer.
                            messages.warning(request, f"Ce fournisseur avait déjà un prix pour '{item.designation.nom}', il n'a pas été modifié ici.")
                            continue
                        if prix_unitaire is not None:
                            # L'offre existait sans prix (article non rempli lors de la saisie initiale) :
                            # on la complète plutôt que d'échouer sur la contrainte d'unicité.
                            offre_existante.prix_unitaire = prix_unitaire
                            offre_existante.save(update_fields=['prix_unitaire'])
                        continue

                    ProformaItem.objects.create(
                        proforma=proforma,
                        demande_item=item,
                        prix_unitaire=prix_unitaire,
                    )

                if demande.statut == 'brouillon':
                    demande.statut = 'proformas'
                    demande.save(update_fields=['statut'])

            if item_unique:
                messages.success(request, f"Achat direct enregistré pour '{item_unique.designation.nom}' auprès de {proforma.fournisseur}.")
            else:
                messages.success(request, f"Proforma de {proforma.fournisseur} enregistré.")
            return redirect('procurement:demande_achat_detail', demande_id=demande.id)

        except Exception as exc:  # pragma: no cover - garde-fou générique
            messages.error(request, f"Erreur lors de l'enregistrement du proforma : {exc}")
            return redirect(request.get_full_path())

    fournisseurs_deja_soumis = demande.proformas.values_list('fournisseur_id', flat=True)
    if item_unique:
        # Achat direct : tous les fournisseurs actifs, y compris ceux ayant déjà
        # répondu pour d'autres articles (on complètera alors leur proforma existant).
        fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom_fournisseur')
    else:
        fournisseurs = Fournisseur.objects.filter(actif=True, devis=True).exclude(id__in=fournisseurs_deja_soumis).order_by('nom_fournisseur')

    context = {
        'demande': demande,
        'fournisseurs': fournisseurs,
        'item_unique': item_unique,
    }
    return render(request, 'procurement/proforma_form.html', context)


@login_required
def proforma_edit(request, proforma_id):
    proforma = get_object_or_404(
        Proforma.objects.select_related('demande_achat', 'demande_achat__base__organisation', 'fournisseur')
        .prefetch_related('items__demande_item__designation'),
        id=proforma_id,
    )
    demande = _get_demande_or_404(request, proforma.demande_achat_id)

    if request.method == 'POST':
        date_reception = request.POST.get('date_reception') or None
        scan_document = request.FILES.get('scan_document')

        if date_reception:
            proforma.date_reception = date_reception
        if scan_document:
            proforma.scan_document = scan_document
        proforma.save()

        for item in proforma.items.select_related('demande_item').all():
            prix_raw = request.POST.get(f'prix_{item.demande_item_id}', '').strip()
            if prix_raw:
                try:
                    item.prix_unitaire = Decimal(prix_raw.replace(',', '.'))
                except InvalidOperation:
                    item.prix_unitaire = None
            else:
                item.prix_unitaire = None
            item.save(update_fields=['prix_unitaire'])

        messages.success(request, "Proforma mis à jour.")
        return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    context = {
        'demande': demande,
        'proforma': proforma,
    }
    return render(request, 'procurement/proforma_edit_form.html', context)


# ---------------------------------------------------------------------------
# Étape 3 : Comparatif et sélection
# ---------------------------------------------------------------------------

@login_required
def comparatif(request, demande_id):
    demande = _get_demande_or_404(
        request, demande_id,
        DemandeAchat.objects.prefetch_related(
            'items__designation',
            'items__offres__proforma__fournisseur',
        ),
    )

    fournisseurs = Fournisseur.objects.filter(
        id__in=demande.proformas.values_list('fournisseur_id', flat=True)
    ).order_by('nom_fournisseur')

    lignes = []
    for item in demande.items.all():
        prix_par_fournisseur = {}
        offre_par_fournisseur = {}
        for offre in item.offres.all():
            prix_par_fournisseur[str(offre.proforma.fournisseur_id)] = offre.prix_unitaire
            offre_par_fournisseur[str(offre.proforma.fournisseur_id)] = offre

        prix_valides = [p for p in prix_par_fournisseur.values() if p is not None]
        prix_min = min(prix_valides) if prix_valides else None

        lignes.append({
            'item': item,
            'prix_min': prix_min,
            'offres': [
                {
                    'fournisseur': fournisseur,
                    'offre': offre_par_fournisseur.get(str(fournisseur.id)),
                    'prix': prix_par_fournisseur.get(str(fournisseur.id)),
                    'est_min': (
                        prix_par_fournisseur.get(str(fournisseur.id)) is not None
                        and prix_min is not None
                        and prix_par_fournisseur.get(str(fournisseur.id)) == prix_min
                    ),
                }
                for fournisseur in fournisseurs
            ],
        })

    context = {
        'demande': demande,
        'fournisseurs': fournisseurs,
        'lignes': lignes,
    }
    return render(request, 'procurement/comparatif.html', context)


@login_required
@require_http_methods(['POST'])
def comparatif_enregistrer_selection(request, demande_id):
    """API appelée par le comparatif pour enregistrer les sélections (radio + justification) sans générer les BC."""
    demande = _get_demande_or_404(request, demande_id)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'success': False, 'error': 'Payload JSON invalide.'}, status=400)

    selections = payload.get('selections', [])
    if not selections:
        return JsonResponse({'success': False, 'error': 'Aucune sélection fournie.'}, status=400)

    erreurs = []
    with transaction.atomic():
        for selection in selections:
            demande_item_id = selection.get('demande_item_id')
            proforma_item_id = selection.get('proforma_item_id')
            justification = (selection.get('justification') or '').strip()

            try:
                item = DemandeAchatItem.objects.get(id=demande_item_id, demande=demande)
            except DemandeAchatItem.DoesNotExist:
                erreurs.append(f"Article {demande_item_id} introuvable pour cette demande.")
                continue

            # Désélectionner toutes les offres existantes pour cet article
            ProformaItem.objects.filter(demande_item=item).update(
                est_selectionne=False, justification_non_moins_cher=None
            )

            if not proforma_item_id:
                continue

            try:
                offre = ProformaItem.objects.get(id=proforma_item_id, demande_item=item)
            except ProformaItem.DoesNotExist:
                erreurs.append(f"Offre {proforma_item_id} introuvable pour l'article {item.designation}.")
                continue

            moins_cher = item.prix_le_plus_bas
            if moins_cher is not None and moins_cher.id != offre.id and not justification:
                erreurs.append(
                    f"Une justification est requise pour l'article '{item.designation}' "
                    f"car l'offre choisie n'est pas la moins chère."
                )
                continue

            offre.est_selectionne = True
            offre.justification_non_moins_cher = justification or None
            offre.save(update_fields=['est_selectionne', 'justification_non_moins_cher'])

    if erreurs:
        return JsonResponse({'success': False, 'error': ' / '.join(erreurs)}, status=400)

    demande.statut = 'analyse'
    demande.save(update_fields=['statut'])

    return JsonResponse({'success': True, 'message': 'Sélection enregistrée avec succès.'})


# ---------------------------------------------------------------------------
# Étape 4 : Génération des Bons de Commande
# ---------------------------------------------------------------------------

@login_required
def generation_bc(request, demande_id):
    demande = _get_demande_or_404(
        request, demande_id,
        DemandeAchat.objects.prefetch_related(
            'items__designation',
            'items__offres__proforma__fournisseur',
        ),
    )

    offres_selectionnees = ProformaItem.objects.filter(
        demande_item__demande=demande, est_selectionne=True
    ).select_related('proforma__fournisseur', 'demande_item__designation')

    if not offres_selectionnees.exists():
        messages.warning(request, "Aucune offre n'a encore été sélectionnée pour cette demande. Retournez au comparatif.")
        return redirect('procurement:comparatif', demande_id=demande.id)

    nb_items_sans_selection = demande.items.exclude(
        id__in=offres_selectionnees.values_list('demande_item_id', flat=True)
    ).count()

    groupes_par_fournisseur = {}
    for offre in offres_selectionnees:
        fournisseur = offre.proforma.fournisseur
        groupes_par_fournisseur.setdefault(fournisseur, []).append(offre)

    montant_par_fournisseur = {
        fournisseur: sum((o.montant_ligne for o in offres), start=0)
        for fournisseur, offres in groupes_par_fournisseur.items()
    }

    bons_existants = BonCommande.objects.filter(demande_achat=demande).select_related('fournisseur')

    context = {
        'demande': demande,
        'groupes': [
            {'fournisseur': fournisseur, 'offres': offres, 'montant_total': montant_par_fournisseur[fournisseur]}
            for fournisseur, offres in groupes_par_fournisseur.items()
        ],
        'nb_items_sans_selection': nb_items_sans_selection,
        'bons_existants': bons_existants,
    }
    return render(request, 'procurement/generation_bc.html', context)


@login_required
@require_http_methods(['POST'])
def generation_bc_valider(request, demande_id):
    demande = _get_demande_or_404(request, demande_id)

    if BonCommande.objects.filter(demande_achat=demande).exists():
        messages.error(request, "Des bons de commande ont déjà été générés pour cette demande.")
        return redirect('procurement:generation_bc', demande_id=demande.id)

    offres_selectionnees = ProformaItem.objects.filter(
        demande_item__demande=demande, est_selectionne=True
    ).select_related('proforma__fournisseur', 'demande_item__designation')

    if not offres_selectionnees.exists():
        messages.error(request, "Aucune offre sélectionnée : impossible de générer les bons de commande.")
        return redirect('procurement:comparatif', demande_id=demande.id)

    employe = _get_employe(request)

    groupes_par_fournisseur = {}
    for offre in offres_selectionnees:
        fournisseur = offre.proforma.fournisseur
        groupes_par_fournisseur.setdefault(fournisseur, []).append(offre)

    bons_crees = []
    with transaction.atomic():
        for fournisseur, offres in groupes_par_fournisseur.items():
            bon = BonCommande.objects.create(
                demande_achat=demande,
                fournisseur=fournisseur,
                cree_par=employe,
            )
            for offre in offres:
                BonCommandeItem.objects.create(
                    bon_commande=bon,
                    proforma_item=offre,
                    designation=offre.demande_item.designation,
                    quantite=offre.demande_item.quantite,
                    prix_unitaire=offre.prix_unitaire,
                )
            bons_crees.append(bon)

        demande.statut = 'termine'
        demande.save(update_fields=['statut'])

    messages.success(
        request,
        f"{len(bons_crees)} bon(s) de commande généré(s) : "
        + ', '.join(b.numero_bc for b in bons_crees),
    )
    return redirect('procurement:demande_achat_detail', demande_id=demande.id)


@login_required
def bon_commande_detail(request, bon_id):
    bon = get_object_or_404(
        BonCommande.objects.select_related(
            'fournisseur', 'demande_achat', 'demande_achat__base', 'demande_achat__base__organisation', 'cree_par'
        ).prefetch_related('items__designation'),
        id=bon_id,
    )
    # Vérifie l'isolation multi-organisation via la DA d'origine du bon de commande
    _get_demande_or_404(request, bon.demande_achat_id)

    context = {'bon': bon, 'organisation': bon.demande_achat.base.organisation}
    return render(request, 'procurement/bon_commande_detail.html', context)
