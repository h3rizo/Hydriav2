"""
Phase B - CRUD des regles de saisie guidee par compte + fournisseurs autorises.

Pages :
  GET  /comptabilite/regles-saisie/                      -> liste
  GET  /comptabilite/regles-saisie/<id>/                 -> editeur
APIs :
  GET  .../api/list/                                     -> regles de l'organisation
  GET  .../api/<id>/                                     -> une regle (config complete)
  POST .../api/<id>/update/                              -> maj mode/sens/libelle/actif/config
  POST .../api/<id>/preview/                             -> {valeurs} -> ecriture composee
  GET  .../api/<id>/fournisseurs/                        -> fournisseurs autorises + total
  POST .../api/<id>/fournisseurs/                        -> {ajouter:[ids]} / {retirer:[ids]}
  GET  .../api/fournisseurs-search/?q=                   -> autocompletion fournisseur
"""
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from apps.billing.models import Fournisseur
from apps.organization.models import Compte, Organisation
from apps.organization.scoping import get_user_organisation

from .models_regles_saisie import CompteFournisseurAutorise, RegleSaisieCompte
from .regles_saisie.engine import composer_ecriture, resoudre_regle
from .regles_saisie.schema import valider_config
from .regles_saisie.seed_fournisseurs import peupler_fournisseurs_pour_compte


def _org(request):
    org = get_user_organisation(request.user)
    if org is None and request.user.is_superuser:
        oid = request.GET.get("organisation") or request.POST.get("organisation")
        org = Organisation.objects.filter(id=oid).first() if oid else Organisation.objects.first()
    return org


def _regle_qs(request):
    org = _org(request)
    if org is None:
        return RegleSaisieCompte.objects.none()
    return RegleSaisieCompte.objects.filter(organisation=org)


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #

@login_required
def regles_saisie_list(request):
    org = _org(request)
    return render(request, "accounting/regles_saisie_list.html", {
        "organisation": org,
        "organisations": Organisation.objects.all() if request.user.is_superuser else None,
    })


@login_required
def regle_saisie_edit(request, regle_id):
    regle = get_object_or_404(_regle_qs(request), id=regle_id)
    return render(request, "accounting/regles_saisie_edit.html", {"regle": regle})


# --------------------------------------------------------------------------- #
# APIs
# --------------------------------------------------------------------------- #

def _regle_pour_code(regles, compte_code):
    """Meme logique que resoudre_regle() mais sur une liste deja chargee (evite N+1)."""
    exact = next((r for r in regles if not r.est_prefixe and r.compte_cible == compte_code), None)
    if exact:
        return exact, False
    prefixes = [r for r in regles if r.est_prefixe and compte_code.startswith(r.compte_cible)]
    prefixes.sort(key=lambda r: -len(r.compte_cible))
    return (prefixes[0], True) if prefixes else (None, False)


@login_required
@require_http_methods(["GET"])
def api_regles_list(request):
    org = _org(request)
    if org is None:
        return JsonResponse({"success": False, "error": "Aucune organisation"}, status=400)

    cfa = {}
    for row in (CompteFournisseurAutorise.objects
                .filter(organisation=org).values("compte_code")):
        cfa[row["compte_code"]] = cfa.get(row["compte_code"], 0) + 1

    regles = list(_regle_qs(request))

    data = []
    for c in (Compte.objects.filter(organisation=org)
              .exclude(compte__isnull=True).exclude(compte="")
              .order_by("compte")):
        r, herite = _regle_pour_code(regles, c.compte)
        data.append({
            "compte": c.compte,
            "nom_compte": c.nom_compte,
            "id": str(r.id) if r else None,
            "compte_cible": r.compte_cible if r else None,
            "est_prefixe": r.est_prefixe if r else False,
            "herite": herite,
            "mode": r.mode if r else None,
            "sens": r.sens if r else None,
            "libelle": r.libelle if r else "",
            "actif": r.actif if r else False,
            "nb_champs": len((r.config or {}).get("champs", [])) if r else 0,
            "nb_fournisseurs": cfa.get(r.compte_cible, 0) if r else 0,
        })
    return JsonResponse({"success": True, "organisation": org.nom_organisation, "regles": data})


@login_required
@require_http_methods(["POST"])
def api_regle_creer_pour_compte(request):
    """Cree (ou recupere) la regle exacte du compte donne, pour permettre l'edition
    d'un compte qui n'a pas encore de regle configuree."""
    org = _org(request)
    if org is None:
        return JsonResponse({"success": False, "error": "Aucune organisation"}, status=400)
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON invalide"}, status=400)
    compte_code = (payload.get("compte") or "").strip()
    if not compte_code:
        return JsonResponse({"success": False, "error": "Code compte manquant"}, status=400)
    if not Compte.objects.filter(organisation=org, compte=compte_code).exists():
        return JsonResponse({"success": False, "error": "Compte introuvable pour cette organisation"}, status=404)

    r, _created = RegleSaisieCompte.objects.get_or_create(
        organisation=org, compte_cible=compte_code,
        defaults={"mode": "libre", "sens": "out", "config": {}, "actif": True},
    )
    return JsonResponse({"success": True, "id": str(r.id)})


@login_required
@require_http_methods(["POST"])
def api_regle_peupler_fournisseurs(request):
    """Pour un compte pas encore configure : cree la regle (mode fournisseur) et
    autorise automatiquement les fournisseurs deja utilises sur ce compte dans
    l'historique BaseDiameX (meme logique que la commande
    seed_compte_fournisseurs_autorises, appliquee ici a un seul compte)."""
    org = _org(request)
    if org is None:
        return JsonResponse({"success": False, "error": "Aucune organisation"}, status=400)
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON invalide"}, status=400)
    compte_code = (payload.get("compte") or "").strip()
    if not compte_code:
        return JsonResponse({"success": False, "error": "Code compte manquant"}, status=400)
    if not Compte.objects.filter(organisation=org, compte=compte_code).exists():
        return JsonResponse({"success": False, "error": "Compte introuvable pour cette organisation"}, status=404)

    if resoudre_regle(org.id, compte_code) is not None:
        return JsonResponse({"success": False, "error": "Ce compte a deja une regle configuree"}, status=400)

    min_occ = max(1, int(payload.get("min_occurrences") or 1))
    stats = peupler_fournisseurs_pour_compte(org, compte_code, min_occurrences=min_occ, dry_run=True)
    if not stats["nb_ecritures"]:
        return JsonResponse({
            "success": False,
            "error": "Aucune ecriture DiameX historique pour ce compte.",
        }, status=404)

    r = RegleSaisieCompte.objects.create(
        organisation=org, compte_cible=compte_code, mode="fournisseur",
        sens=stats["sens_suggere"] or "out", config={}, actif=True,
    )
    stats = peupler_fournisseurs_pour_compte(org, compte_code, min_occurrences=min_occ)
    return JsonResponse({
        "success": True,
        "id": str(r.id),
        "sens": r.sens,
        "nb_ecritures": stats["nb_ecritures"],
        "crees": stats["crees"],
        "trouves": stats["trouves"],
        "ignores": stats["ignores"],
        "inconnus": [{"libelle": raw, "occurrences": n} for raw, n in stats["inconnus"][:10]],
    })


@login_required
@require_http_methods(["GET"])
def api_regle_detail(request, regle_id):
    r = get_object_or_404(_regle_qs(request), id=regle_id)
    return JsonResponse({
        "success": True,
        "regle": {
            "id": str(r.id),
            "compte_cible": r.compte_cible,
            "est_prefixe": r.est_prefixe,
            "mode": r.mode,
            "sens": r.sens,
            "libelle": r.libelle,
            "actif": r.actif,
            "config": r.config or {},
        },
        "modes": [c[0] for c in RegleSaisieCompte.MODE_CHOICES],
        "sens_choices": [c[0] for c in RegleSaisieCompte.SENS_CHOICES],
    })


@login_required
@require_http_methods(["POST"])
def api_regle_update(request, regle_id):
    r = get_object_or_404(_regle_qs(request), id=regle_id)
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON invalide"}, status=400)

    config = payload.get("config", r.config)
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError as exc:
            return JsonResponse({"success": False, "error": f"config : JSON invalide ({exc})"}, status=400)

    errs = valider_config(config)
    if errs:
        return JsonResponse({"success": False, "error": "Config invalide", "details": errs}, status=400)

    if payload.get("mode") in dict(RegleSaisieCompte.MODE_CHOICES):
        r.mode = payload["mode"]
    if payload.get("sens") in dict(RegleSaisieCompte.SENS_CHOICES):
        r.sens = payload["sens"]
    if "libelle" in payload:
        r.libelle = (payload["libelle"] or "")[:255]
    if "actif" in payload:
        r.actif = bool(payload["actif"])
    r.config = config
    r.save()
    return JsonResponse({"success": True})


@login_required
@require_http_methods(["POST"])
def api_regle_preview(request, regle_id):
    r = get_object_or_404(_regle_qs(request), id=regle_id)
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON invalide"}, status=400)

    # config editee non encore sauvee : on l'utilise si fournie
    config = payload.get("config")
    if config:
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = None
        if config and not valider_config(config):
            r = RegleSaisieCompte(compte_cible=r.compte_cible, mode=r.mode, sens=r.sens, config=config)

    out = composer_ecriture(r, payload.get("valeurs", {}) or {})
    return JsonResponse({"success": True, "resultat": out.as_dict()})


@login_required
@require_http_methods(["GET", "POST"])
def api_regle_fournisseurs(request, regle_id):
    r = get_object_or_404(_regle_qs(request), id=regle_id)
    org = r.organisation

    if request.method == "POST":
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "JSON invalide"}, status=400)
        for fid in payload.get("ajouter", []) or []:
            f = Fournisseur.objects.filter(id=fid).first()
            if f:
                CompteFournisseurAutorise.objects.get_or_create(
                    organisation=org, compte_code=r.compte_cible, fournisseur=f)
        if payload.get("retirer"):
            CompteFournisseurAutorise.objects.filter(
                organisation=org, compte_code=r.compte_cible,
                fournisseur_id__in=payload["retirer"]).delete()

    liens = (CompteFournisseurAutorise.objects
             .filter(organisation=org, compte_code=r.compte_cible)
             .select_related("fournisseur"))
    return JsonResponse({
        "success": True,
        "compte": r.compte_cible,
        "fournisseurs": [
            {"id": str(l.fournisseur_id), "idxls": l.fournisseur.idxls,
             "nom": l.fournisseur.nom_fournisseur}
            for l in liens
        ],
        "note": "Liste vide = tous les fournisseurs sont autorises pour ce compte.",
    })


@login_required
@require_http_methods(["GET"])
def api_fournisseurs_search(request):
    q = (request.GET.get("q") or "").strip()
    qs = Fournisseur.objects.filter(actif=True)
    if q:
        qs = qs.filter(nom_fournisseur__icontains=q)
    qs = qs.order_by("nom_fournisseur")[:25]
    return JsonResponse({"success": True, "fournisseurs": [
        {"id": str(f.id), "idxls": f.idxls, "nom": f.nom_fournisseur} for f in qs
    ]})


# --------------------------------------------------------------------------- #
# Phase C - integration au formulaire de saisie guidee
# --------------------------------------------------------------------------- #

def _regle_public(r):
    return {
        "compte_cible": r.compte_cible,
        "est_prefixe": r.est_prefixe,
        "mode": r.mode,
        "sens": r.sens,
        "libelle": r.libelle,
        "config": r.config or {},
    }


@login_required
@require_http_methods(["GET"])
def api_regle_pour_compte(request):
    """Regle applicable au compte cat selectionne (ou null -> saisie libre)."""
    org = _org(request)
    compte = (request.GET.get("compte") or "").strip()
    if org is None or not compte:
        return JsonResponse({"success": True, "regle": None})
    r = resoudre_regle(org.id, compte)
    return JsonResponse({"success": True, "regle": _regle_public(r) if r else None})


@login_required
@require_http_methods(["POST"])
def api_composer_compte(request):
    """{compte, valeurs} -> ecriture composee (description + colonnes + sens)."""
    org = _org(request)
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON invalide"}, status=400)
    compte = (payload.get("compte") or "").strip()
    r = resoudre_regle(org.id, compte) if org else None
    if r is None:
        return JsonResponse({"success": True, "regle": None})
    out = composer_ecriture(r, payload.get("valeurs", {}) or {})
    return JsonResponse({
        "success": True,
        "regle": {"mode": r.mode, "sens": r.sens, "compte_cible": r.compte_cible},
        "resultat": out.as_dict(),
    })


@login_required
@require_http_methods(["GET"])
def api_ac(request):
    """Autocompletion pour les champs du formulaire guide.

    ?kind=fournisseur|ouvrage|employe|vehicule &q= &compte= [&filtre_poste= &filtre=]
    """
    org = _org(request)
    kind = (request.GET.get("kind") or "").strip()
    q = (request.GET.get("q") or "").strip()
    compte = (request.GET.get("compte") or "").strip()
    items = []

    if kind == "fournisseur":
        qs = Fournisseur.objects.filter(actif=True)
        if org and compte:
            # la liste blanche est stockee sous la cle de la regle (compte_cible),
            # qui peut etre un prefixe -> resoudre d'abord.
            r = resoudre_regle(org.id, compte)
            cle = r.compte_cible if r else compte
            autorises = list(
                CompteFournisseurAutorise.objects
                .filter(organisation=org, compte_code__in={compte, cle})
                .values_list("fournisseur_id", flat=True)
            )
            if autorises:
                qs = qs.filter(id__in=autorises)
        if q:
            qs = qs.filter(nom_fournisseur__icontains=q)
        for f in qs.order_by("nom_fournisseur")[:25]:
            label = f"{f.idxls} - {f.nom_fournisseur}" if f.idxls is not None else f.nom_fournisseur
            items.append({"id": str(f.id), "label": label})

    elif kind == "ouvrage":
        from apps.organization.models import Ouvrage
        qs = Ouvrage.objects.all()
        if org:
            scoped = qs.filter(modalites_gestion__gestionnaire=org).distinct()
            if scoped.exists():
                qs = scoped
        if q:
            qs = qs.filter(nom_ouvrage__icontains=q)
        for o in qs.order_by("nom_ouvrage")[:25]:
            items.append({"id": str(o.id), "label": o.nom_ouvrage})

    elif kind == "employe":
        from apps.employees.models import Employe
        qs = Employe.objects.filter(date_debauchage__isnull=True).select_related("poste")
        if org:
            qs = qs.filter(base__organisation_id=org.id)
        fp = (request.GET.get("filtre_poste") or "").strip()
        if fp in {"compte_salaire", "compte_irsa", "compte_cnaps_fmfp_sante"} and compte:
            qs = qs.filter(**{f"poste__{fp}__compte__startswith": compte})
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(surnom__icontains=q))
        for e in qs.order_by("nom", "prenom")[:25]:
            nom = (getattr(e, "nom_complet", "") or e.nom or "").strip()
            if e.surnom:
                nom = f"{nom} ({e.surnom})"
            items.append({"id": str(e.id), "label": nom})

    elif kind == "vehicule":
        from apps.inventory.models_vehicles import Vehicule
        qs = Vehicule.objects.filter(actif=True)
        if (request.GET.get("filtre") or "") == "voiture":
            qs = qs.filter(type_vehicule="voiture")
        if q:
            qs = qs.filter(immatriculation__icontains=q)
        for v in qs.order_by("immatriculation")[:25]:
            libra = f"{v.immatriculation} - {v.marque} {v.modele}".strip(" -")
            items.append({"id": str(v.id), "label": libra})

    return JsonResponse({"success": True, "kind": kind, "items": items})
