from decimal import Decimal
import json
from datetime import datetime

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.billing.models import TypePointEau
from apps.infrastructure.models import TypeEquipement
from apps.planning.models import Designation
from .models import Tacheron
from .models_workflow import (
    ChantierBesoinLigne,
    ChantierDocument,
    ChantierMouvement,
    ChantierSurplusLigne,
    ChantierWorkflow,
    ChantierSelectionEquipement,
    CiterneDimensionnement,
    CiterneParametrageReference,
    PosteMainOeuvre,
    build_citerne_dimensions_from_volume,
    generer_besoins_chantier,
)


def _json_error(message, status=400):
    return JsonResponse({"success": False, "error": str(message)}, status=status)


def _to_decimal(value, default="0"):
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def _parse_datetime(value):
    if not value:
        return timezone.now()
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    return datetime.fromisoformat(text)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_create(request):
    try:
        data = json.loads(request.body or "{}")
        ouvrage_id = data.get("ouvrage_id")
        if not ouvrage_id:
            return _json_error("ouvrage_id est obligatoire.")

        with transaction.atomic():
            workflow = None
            for _ in range(5):
                try:
                    workflow = ChantierWorkflow.objects.create(
                        code=ChantierWorkflow.next_code(),
                        ouvrage_id=ouvrage_id,
                        caracteristique_chantier_id=data.get("caracteristique_chantier_id"),
                        notes=data.get("notes", ""),
                    )
                    break
                except IntegrityError:
                    continue
            if workflow is None:
                return _json_error("Impossible de generer un code workflow unique.", status=500)

        return JsonResponse({"success": True, "id": str(workflow.id), "code": workflow.code})
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["GET"])
def workflow_detail(request, workflow_id):
    try:
        workflow = get_object_or_404(
            ChantierWorkflow.objects.select_related("ouvrage", "caracteristique_chantier"),
            id=workflow_id,
        )
        return JsonResponse({
            "success": True,
            "data": {
                "id": str(workflow.id),
                "code": workflow.code,
                "statut": workflow.statut,
                "ouvrage": {
                    "id": str(workflow.ouvrage_id),
                    "nom": workflow.ouvrage.nom_ouvrage if workflow.ouvrage else None,
                },
                "caracteristique_chantier_id": str(workflow.caracteristique_chantier_id) if workflow.caracteristique_chantier_id else None,
                "notes": workflow.notes,
                "stats": {
                    "selections": workflow.selections.count(),
                    "besoins": workflow.besoins.count(),
                    "surplus": workflow.surplus.count(),
                    "documents": workflow.documents.count(),
                    "mouvements": workflow.mouvements.count(),
                },
            }
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_add_selection(request, workflow_id):
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        data = json.loads(request.body or "{}")

        type_equipement_id = data.get("type_equipement_id")
        if not type_equipement_id:
            return _json_error("type_equipement_id est obligatoire.")
        get_object_or_404(TypeEquipement, id=type_equipement_id)

        type_point_eau_id = data.get("type_point_eau_id")
        if type_point_eau_id:
            get_object_or_404(TypePointEau, id=type_point_eau_id)

        citerne_dimensionnement_id = data.get("citerne_dimensionnement_id")
        citerne_payload = data.get("citerne_dimensionnement")

        with transaction.atomic():
            citerne_obj = None
            if citerne_dimensionnement_id:
                citerne_obj = get_object_or_404(CiterneDimensionnement, id=citerne_dimensionnement_id)
            elif isinstance(citerne_payload, dict):
                volume_cible = citerne_payload.get("volume_cible_m3")
                if volume_cible in (None, ""):
                    return _json_error("volume_cible_m3 est obligatoire pour une citerne.")

                reference = None
                reference_id = citerne_payload.get("reference_id")
                if reference_id:
                    reference = get_object_or_404(CiterneParametrageReference, id=reference_id)

                dims = build_citerne_dimensions_from_volume(volume_cible, reference=reference)
                citerne_obj = CiterneDimensionnement.objects.create(
                    reference=dims["reference"],
                    volume_cible_m3=dims["volume_cible_m3"],
                    diametre_interieur_m=dims["diametre_interieur_m"],
                    hauteur_eau_m=dims["hauteur_eau_m"],
                )

            selection = ChantierSelectionEquipement.objects.create(
                chantier=workflow,
                type_equipement_id=type_equipement_id,
                type_point_eau_id=type_point_eau_id,
                quantite=_to_decimal(data.get("quantite", 1), default="1"),
                citerne_dimensionnement=citerne_obj,
            )

        return JsonResponse({
            "success": True,
            "selection_id": str(selection.id),
            "workflow_id": str(workflow.id),
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_generate_besoins(request, workflow_id):
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        data = json.loads(request.body or "{}")
        reset_auto = bool(data.get("reset_auto", True))
        created = generer_besoins_chantier(workflow, reset_auto=reset_auto)
        workflow.refresh_from_db(fields=["statut"])
        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "created": created,
            "statut": workflow.statut,
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["GET"])
def workflow_besoins(request, workflow_id):
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        type_ligne = request.GET.get("type_ligne")
        qs = workflow.besoins.select_related("designation", "poste_main_oeuvre", "selection__type_equipement").order_by("type_ligne", "id")
        if type_ligne in {"designation", "main_oeuvre"}:
            qs = qs.filter(type_ligne=type_ligne)

        results = []
        total = Decimal("0")
        for b in qs:
            montant = Decimal("0")
            if b.prix_unitaire is not None:
                montant = Decimal(b.quantite) * Decimal(b.prix_unitaire)
            total += montant
            results.append({
                "id": str(b.id),
                "type_ligne": b.type_ligne,
                "designation_id": str(b.designation_id) if b.designation_id else None,
                "designation_nom": b.designation.nom if b.designation else None,
                "poste_main_oeuvre_id": str(b.poste_main_oeuvre_id) if b.poste_main_oeuvre_id else None,
                "poste_main_oeuvre_libelle": b.poste_main_oeuvre.libelle if b.poste_main_oeuvre else None,
                "selection_id": str(b.selection_id) if b.selection_id else None,
                "type_equipement_nom": b.selection.type_equipement.nom_type if b.selection else None,
                "quantite": float(b.quantite),
                "prix_unitaire": float(b.prix_unitaire) if b.prix_unitaire is not None else None,
                "montant": float(montant),
                "origine": b.origine,
                "statut": b.statut,
            })

        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "count": len(results),
            "total_montant": float(total),
            "results": results,
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_surplus_add(request, workflow_id):
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        data = json.loads(request.body or "{}")
        type_ligne = data.get("type_ligne")
        if type_ligne not in {"designation", "main_oeuvre"}:
            return _json_error("type_ligne doit être 'designation' ou 'main_oeuvre'.")

        designation_id = data.get("designation_id")
        poste_main_oeuvre_id = data.get("poste_main_oeuvre_id")
        if type_ligne == "designation" and not designation_id:
            return _json_error("designation_id est obligatoire pour type_ligne=designation.")
        if type_ligne == "main_oeuvre" and not poste_main_oeuvre_id:
            return _json_error("poste_main_oeuvre_id est obligatoire pour type_ligne=main_oeuvre.")

        if designation_id:
            get_object_or_404(Designation, id=designation_id)
        if poste_main_oeuvre_id:
            get_object_or_404(PosteMainOeuvre, id=poste_main_oeuvre_id)

        surplus = ChantierSurplusLigne.objects.create(
            chantier=workflow,
            type_ligne=type_ligne,
            designation_id=designation_id,
            poste_main_oeuvre_id=poste_main_oeuvre_id,
            quantite=_to_decimal(data.get("quantite")),
            prix_unitaire=_to_decimal(data.get("prix_unitaire")) if data.get("prix_unitaire") not in (None, "") else None,
            justification=data.get("justification", ""),
        )
        return JsonResponse({"success": True, "surplus_id": str(surplus.id), "workflow_id": str(workflow.id)})
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["GET"])
def workflow_surplus_list(request, workflow_id):
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        qs = workflow.surplus.select_related("designation", "poste_main_oeuvre").order_by("-id")
        total = Decimal("0")
        results = []
        for s in qs:
            montant = Decimal("0")
            if s.prix_unitaire is not None:
                montant = Decimal(s.quantite) * Decimal(s.prix_unitaire)
            total += montant
            results.append({
                "id": str(s.id),
                "type_ligne": s.type_ligne,
                "designation_id": str(s.designation_id) if s.designation_id else None,
                "designation_nom": s.designation.nom if s.designation else None,
                "poste_main_oeuvre_id": str(s.poste_main_oeuvre_id) if s.poste_main_oeuvre_id else None,
                "poste_main_oeuvre_libelle": s.poste_main_oeuvre.libelle if s.poste_main_oeuvre else None,
                "quantite": float(s.quantite),
                "prix_unitaire": float(s.prix_unitaire) if s.prix_unitaire is not None else None,
                "montant": float(montant),
                "justification": s.justification,
            })
        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "count": len(results),
            "total_montant": float(total),
            "results": results,
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_surplus_integrate(request, workflow_id):
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        data = json.loads(request.body or "{}")
        reset_surplus = bool(data.get("reset_surplus", True))
        created = 0

        with transaction.atomic():
            if reset_surplus:
                workflow.besoins.filter(origine="surplus").delete()
            for s in workflow.surplus.all():
                ChantierBesoinLigne.objects.create(
                    chantier=workflow,
                    selection=None,
                    type_ligne=s.type_ligne,
                    designation=s.designation,
                    poste_main_oeuvre=s.poste_main_oeuvre,
                    quantite=s.quantite,
                    prix_unitaire=s.prix_unitaire,
                    origine="surplus",
                    statut="a_commander",
                )
                created += 1
        return JsonResponse({"success": True, "workflow_id": str(workflow.id), "created": created})
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_generate_devis(request, workflow_id):
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        data = json.loads(request.body or "{}")
        include_only = data.get("include_only")
        qs = workflow.besoins.all()
        if include_only in {"designation", "main_oeuvre"}:
            qs = qs.filter(type_ligne=include_only)

        total = Decimal("0")
        for b in qs:
            if b.prix_unitaire is not None:
                total += Decimal(b.quantite) * Decimal(b.prix_unitaire)

        with transaction.atomic():
            idx = workflow.documents.filter(type_document="devis").count() + 1
            numero = f"DEV-{workflow.code}-{idx:03d}"
            doc = ChantierDocument.objects.create(
                chantier=workflow,
                type_document="devis",
                numero=numero,
                montant=total,
                statut="brouillon",
            )
            workflow.statut = "devis"
            workflow.save(update_fields=["statut"])

        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "document_id": str(doc.id),
            "numero": doc.numero,
            "montant": float(doc.montant),
            "statut_workflow": workflow.statut,
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["GET"])
def workflow_documents_list(request, workflow_id):
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        type_document = request.GET.get("type_document")
        qs = workflow.documents.select_related("tacheron", "parent").order_by("-id")
        if type_document:
            qs = qs.filter(type_document=type_document)

        results = []
        for d in qs:
            results.append({
                "id": str(d.id),
                "type_document": d.type_document,
                "numero": d.numero,
                "date_document": d.date_document.isoformat() if d.date_document else None,
                "montant": float(d.montant),
                "statut": d.statut,
                "tacheron_id": str(d.tacheron_id) if d.tacheron_id else None,
                "tacheron_nom": d.tacheron.nom if d.tacheron else None,
                "parent_id": str(d.parent_id) if d.parent_id else None,
            })

        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_create_contrat(request, workflow_id):
    """
    Créer un document contrat tâcheron.
    body: {"numero":"CTR-...","montant":12345,"tacheron_id":"<uuid>","date_document":"YYYY-MM-DD"}
    """
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        data = json.loads(request.body or "{}")
        numero = data.get("numero")
        tacheron_id = data.get("tacheron_id")
        if not numero:
            return _json_error("numero est obligatoire.")
        if tacheron_id:
            get_object_or_404(Tacheron, id=tacheron_id)

        doc = ChantierDocument.objects.create(
            chantier=workflow,
            type_document="contrat",
            numero=str(numero).strip(),
            date_document=data.get("date_document"),
            tacheron_id=tacheron_id,
            montant=_to_decimal(data.get("montant", 0)),
            statut=data.get("statut", "brouillon"),
        )
        workflow.statut = "contrat"
        workflow.save(update_fields=["statut"])
        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "document_id": str(doc.id),
            "numero": doc.numero,
            "statut_workflow": workflow.statut,
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_create_avenant(request, workflow_id):
    """
    Créer un avenant lié à un contrat.
    body: {"numero":"AV-...","contrat_document_id":"<uuid>","montant":1000,"date_document":"YYYY-MM-DD"}
    """
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        data = json.loads(request.body or "{}")
        numero = data.get("numero")
        contrat_document_id = data.get("contrat_document_id")
        if not numero or not contrat_document_id:
            return _json_error("numero et contrat_document_id sont obligatoires.")

        contrat_doc = get_object_or_404(
            ChantierDocument,
            id=contrat_document_id,
            chantier=workflow,
            type_document="contrat",
        )

        doc = ChantierDocument.objects.create(
            chantier=workflow,
            type_document="avenant",
            numero=str(numero).strip(),
            date_document=data.get("date_document"),
            tacheron=contrat_doc.tacheron,
            montant=_to_decimal(data.get("montant", 0)),
            statut=data.get("statut", "brouillon"),
            parent=contrat_doc,
        )
        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "document_id": str(doc.id),
            "numero": doc.numero,
            "parent_contrat_id": str(contrat_doc.id),
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_create_facture_tranche(request, workflow_id):
    """
    Créer une facture de tranche liée à un contrat (ou avenant).
    body: {"numero":"FTR-...","parent_document_id":"<uuid>","montant":5000,"date_document":"YYYY-MM-DD"}
    """
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        data = json.loads(request.body or "{}")
        numero = data.get("numero")
        parent_document_id = data.get("parent_document_id")
        if not numero or not parent_document_id:
            return _json_error("numero et parent_document_id sont obligatoires.")

        parent_doc = get_object_or_404(
            ChantierDocument,
            id=parent_document_id,
            chantier=workflow,
        )
        if parent_doc.type_document not in {"contrat", "avenant"}:
            return _json_error("parent_document_id doit référencer un contrat ou un avenant.")

        doc = ChantierDocument.objects.create(
            chantier=workflow,
            type_document="facture_tranche",
            numero=str(numero).strip(),
            date_document=data.get("date_document"),
            tacheron=parent_doc.tacheron,
            montant=_to_decimal(data.get("montant", 0)),
            statut=data.get("statut", "brouillon"),
            parent=parent_doc,
        )
        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "document_id": str(doc.id),
            "numero": doc.numero,
            "parent_document_id": str(parent_doc.id),
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_update_document_statut(request, workflow_id, document_id):
    """Mettre à jour le statut d'un document workflow."""
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        doc = get_object_or_404(ChantierDocument, id=document_id, chantier=workflow)
        data = json.loads(request.body or "{}")
        statut = data.get("statut")
        if statut not in {"brouillon", "valide", "annule"}:
            return _json_error("statut doit être brouillon, valide ou annule.")
        doc.statut = statut
        doc.save(update_fields=["statut"])
        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "document_id": str(doc.id),
            "statut": doc.statut,
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["GET"])
def workflow_contrat_suivi(request, workflow_id):
    """
    Suivi synthétique: contrat, avenants, factures de tranches.
    Retourne les totaux par statut et le reste à facturer.
    """
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        contrats = workflow.documents.filter(type_document="contrat")
        avenants = workflow.documents.filter(type_document="avenant")
        factures = workflow.documents.filter(type_document="facture_tranche")

        total_contrats = sum((d.montant for d in contrats), Decimal("0"))
        total_avenants = sum((d.montant for d in avenants), Decimal("0"))
        total_factures = sum((d.montant for d in factures), Decimal("0"))
        total_valide_factures = sum((d.montant for d in factures.filter(statut="valide")), Decimal("0"))
        total_reference = total_contrats + total_avenants
        reste_a_facturer = total_reference - total_factures

        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "totaux": {
                "contrats": float(total_contrats),
                "avenants": float(total_avenants),
                "base_contractuelle": float(total_reference),
                "factures_tranches": float(total_factures),
                "factures_validees": float(total_valide_factures),
                "reste_a_facturer": float(reste_a_facturer),
            },
            "counts": {
                "contrats": contrats.count(),
                "avenants": avenants.count(),
                "factures_tranches": factures.count(),
            }
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_add_mouvement(request, workflow_id):
    """
    Ajouter un mouvement chantier.
    body: {"besoin_id":"<uuid>","type_mouvement":"commande|livraison|utilisation|retour|recollement","quantite":1,"date_mouvement":"ISO optional","reference_document":"..."}
    """
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        data = json.loads(request.body or "{}")
        type_mouvement = data.get("type_mouvement")
        if type_mouvement not in {"commande", "livraison", "utilisation", "retour", "recollement"}:
            return _json_error("type_mouvement invalide.")

        besoin_id = data.get("besoin_id")
        if not besoin_id:
            return _json_error("besoin_id est obligatoire.")
        besoin = get_object_or_404(ChantierBesoinLigne, id=besoin_id, chantier=workflow)

        mouvement = ChantierMouvement.objects.create(
            chantier=workflow,
            besoin=besoin,
            type_mouvement=type_mouvement,
            date_mouvement=_parse_datetime(data.get("date_mouvement")),
            quantite=_to_decimal(data.get("quantite")),
            reference_document=data.get("reference_document", ""),
        )
        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "mouvement_id": str(mouvement.id),
            "type_mouvement": mouvement.type_mouvement,
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["GET"])
def workflow_mouvements_list(request, workflow_id):
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        type_mouvement = request.GET.get("type_mouvement")
        qs = workflow.mouvements.select_related("besoin__designation", "besoin__poste_main_oeuvre").order_by("-date_mouvement", "-id")
        if type_mouvement in {"commande", "livraison", "utilisation", "retour", "recollement"}:
            qs = qs.filter(type_mouvement=type_mouvement)

        results = []
        for m in qs:
            b = m.besoin
            results.append({
                "id": str(m.id),
                "type_mouvement": m.type_mouvement,
                "date_mouvement": m.date_mouvement.isoformat() if m.date_mouvement else None,
                "quantite": float(m.quantite),
                "reference_document": m.reference_document,
                "besoin_id": str(m.besoin_id) if m.besoin_id else None,
                "type_ligne": b.type_ligne if b else None,
                "designation_nom": b.designation.nom if b and b.designation else None,
                "poste_main_oeuvre_libelle": b.poste_main_oeuvre.libelle if b and b.poste_main_oeuvre else None,
            })

        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["GET"])
def workflow_recollement_synthese(request, workflow_id):
    """
    Synthèse prévu vs commandé/livré/utilisé/retourné.
    """
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        besoins = workflow.besoins.select_related("designation", "poste_main_oeuvre").order_by("type_ligne", "id")
        mouvements = workflow.mouvements.select_related("besoin")

        by_besoin = {}
        for m in mouvements:
            if not m.besoin_id:
                continue
            by_besoin.setdefault(m.besoin_id, {
                "commande": Decimal("0"),
                "livraison": Decimal("0"),
                "utilisation": Decimal("0"),
                "retour": Decimal("0"),
                "recollement": Decimal("0"),
            })
            by_besoin[m.besoin_id][m.type_mouvement] += Decimal(m.quantite)

        lines = []
        total_prevu = Decimal("0")
        total_utilise = Decimal("0")
        total_valeur_finale = Decimal("0")
        for b in besoins:
            agg = by_besoin.get(b.id, {
                "commande": Decimal("0"),
                "livraison": Decimal("0"),
                "utilisation": Decimal("0"),
                "retour": Decimal("0"),
                "recollement": Decimal("0"),
            })
            utilise_reel = agg["recollement"] if agg["recollement"] > 0 else agg["utilisation"]
            ecart = utilise_reel - Decimal(b.quantite)
            total_prevu += Decimal(b.quantite)
            total_utilise += utilise_reel
            valeur_finale = Decimal("0")
            if b.prix_unitaire is not None:
                valeur_finale = utilise_reel * Decimal(b.prix_unitaire)
                total_valeur_finale += valeur_finale

            lines.append({
                "besoin_id": str(b.id),
                "type_ligne": b.type_ligne,
                "designation_nom": b.designation.nom if b.designation else None,
                "poste_main_oeuvre_libelle": b.poste_main_oeuvre.libelle if b.poste_main_oeuvre else None,
                "quantite_prevue": float(b.quantite),
                "quantite_commandee": float(agg["commande"]),
                "quantite_livree": float(agg["livraison"]),
                "quantite_utilisee": float(agg["utilisation"]),
                "quantite_recollee": float(agg["recollement"]),
                "quantite_retournee": float(agg["retour"]),
                "quantite_utilisee_reelle": float(utilise_reel),
                "ecart": float(ecart),
                "valeur_finale": float(valeur_finale),
            })

        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "count": len(lines),
            "totaux": {
                "quantite_prevue": float(total_prevu),
                "quantite_utilisee_reelle": float(total_utilise),
                "valeur_finale": float(total_valeur_finale),
            },
            "results": lines,
        })
    except Exception as e:
        return _json_error(e)


@csrf_exempt
@require_http_methods(["POST"])
def workflow_generate_devis_final(request, workflow_id):
    """
    Génère le devis final depuis la synthèse de récolement.
    """
    try:
        workflow = get_object_or_404(ChantierWorkflow, id=workflow_id)
        mouvements = workflow.mouvements.select_related("besoin")
        by_besoin = {}
        for m in mouvements:
            if not m.besoin_id:
                continue
            by_besoin.setdefault(m.besoin_id, {"utilisation": Decimal("0"), "recollement": Decimal("0")})
            if m.type_mouvement in {"utilisation", "recollement"}:
                by_besoin[m.besoin_id][m.type_mouvement] += Decimal(m.quantite)

        total = Decimal("0")
        for b in workflow.besoins.all():
            if b.prix_unitaire is None:
                continue
            agg = by_besoin.get(b.id, {"utilisation": Decimal("0"), "recollement": Decimal("0")})
            utilise_reel = agg["recollement"] if agg["recollement"] > 0 else agg["utilisation"]
            if utilise_reel == 0:
                utilise_reel = Decimal(b.quantite)
            total += utilise_reel * Decimal(b.prix_unitaire)

        with transaction.atomic():
            idx = workflow.documents.filter(type_document="devis_final").count() + 1
            numero = f"DFIN-{workflow.code}-{idx:03d}"
            doc = ChantierDocument.objects.create(
                chantier=workflow,
                type_document="devis_final",
                numero=numero,
                montant=total,
                statut="brouillon",
            )
            workflow.statut = "recollement"
            workflow.save(update_fields=["statut"])

        return JsonResponse({
            "success": True,
            "workflow_id": str(workflow.id),
            "document_id": str(doc.id),
            "numero": doc.numero,
            "montant": float(doc.montant),
            "statut_workflow": workflow.statut,
        })
    except Exception as e:
        return _json_error(e)
