"""Peuple CompteFournisseurAutorise a partir de l'historique BaseDiameX.

Logique partagee par :
  - la commande `manage.py seed_compte_fournisseurs_autorises` (tous les comptes
    ayant deja une regle en mode "fournisseur") ;
  - le bouton "Peupler depuis l'historique DiameX" de /comptabilite/regles-saisie/
    (comptes pas encore configures, cf. views_regles_saisie.api_regle_peupler_fournisseurs).
"""
import re

from django.db.models import Count, Sum

from apps.accounting.models import BaseDiameX
from apps.accounting.models_regles_saisie import CompteFournisseurAutorise
from apps.billing.models import Fournisseur
from apps.organization.models import Base


def idxls_depuis_texte(value):
    """'58', '58 - ACME', ' 58' -> 58 ; sinon None."""
    s = str(value or "").strip()
    if s.isdigit():
        return int(s)
    m = re.match(r"^(\d+)\b", s)
    return int(m.group(1)) if m else None


def progs_organisation(org):
    return list(
        Base.objects.filter(organisation_id=org.id)
        .exclude(prog_diamex__isnull=True).exclude(prog_diamex="")
        .values_list("prog_diamex", flat=True).distinct()
    )


def peupler_fournisseurs_pour_compte(org, compte_code, *, est_prefixe=False,
                                      min_occurrences=1, reset=False, dry_run=False):
    """Autorise, pour ce compte, les fournisseurs deja utilises dans BaseDiameX.

    Retourne : {crees, trouves, ignores, inconnus:[(raw,n)], sens_suggere, nb_ecritures}
    sens_suggere ('in'|'out'|None) d'apres la dominance montant_in/montant_out.
    """
    progs = progs_organisation(org)
    if not progs:
        return {"crees": 0, "trouves": 0, "ignores": 0, "inconnus": [],
                "sens_suggere": None, "nb_ecritures": 0}

    lignes = BaseDiameX.objects.filter(prog__in=progs)
    lignes = (lignes.filter(compte_code__startswith=compte_code) if est_prefixe
              else lignes.filter(compte_code=compte_code))

    nb_ecritures = lignes.count()
    totaux = lignes.aggregate(total_in=Sum("montant_in"), total_out=Sum("montant_out"))
    total_in = totaux["total_in"] or 0
    total_out = totaux["total_out"] or 0
    sens_suggere = None
    if total_in or total_out:
        sens_suggere = "in" if total_in >= total_out else "out"

    fourn_par_idxls = {f.idxls: f for f in Fournisseur.objects.exclude(idxls__isnull=True)}
    fourn_par_nom = {}
    for f in Fournisseur.objects.all():
        fourn_par_nom.setdefault((f.nom_fournisseur or "").strip().casefold(), f)

    rows = (lignes.exclude(fournisseur__isnull=True).exclude(fournisseur="")
            .values("fournisseur").annotate(n=Count("id")).order_by("-n"))

    if reset and not dry_run:
        CompteFournisseurAutorise.objects.filter(
            organisation=org, compte_code=compte_code).delete()

    retenus, ignores, inconnus = [], 0, []
    for row in rows:
        raw, n = row["fournisseur"], row["n"]
        if n < max(1, min_occurrences):
            ignores += 1
            continue
        f = None
        idx = idxls_depuis_texte(raw)
        if idx is not None:
            f = fourn_par_idxls.get(idx)
        if f is None:
            f = fourn_par_nom.get(str(raw).strip().casefold())
        if f is None:
            inconnus.append((str(raw).strip(), n))
            continue
        retenus.append(f)

    crees = 0
    if not dry_run:
        for f in retenus:
            _, created = CompteFournisseurAutorise.objects.get_or_create(
                organisation=org, compte_code=compte_code, fournisseur=f)
            crees += int(created)
    else:
        crees = len(retenus)

    return {
        "crees": crees,
        "trouves": len(retenus),
        "ignores": ignores,
        "inconnus": inconnus,
        "sens_suggere": sens_suggere,
        "nb_ecritures": nb_ecritures,
    }
