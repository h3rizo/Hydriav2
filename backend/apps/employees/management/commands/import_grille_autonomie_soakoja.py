"""Importe la grille d'autonomie Soakoja preparee pour le BP 2027."""

import re
import unicodedata
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.employees.models import Poste
from apps.employees.models_autonomie import GrilleAutonomie, StadeAutonomie
from apps.organization.models import Organisation


PRIME_CIBLE = Decimal("60000")
PRIME_MAXIMALE = Decimal("72000")  # Prime cible plafonnee a 120 %.


STADES = (
    {
        "ordre": 1,
        "nom": "1. Junior / apprentissage",
        "couleur": "#3B82F6",
        "description": (
            "85 % du salaire cible. Decouvre le poste et a encore besoin "
            "d'accompagnement. Condition de passage : prise de poste."
        ),
    },
    {
        "ordre": 2,
        "nom": "2A. En progression - minimum (92 %)",
        "couleur": "#06B6D4",
        "description": (
            "Borne basse du stade En progression. Maitrise une bonne partie de "
            "la fiche de poste. Condition de passage : score global >= 60 %."
        ),
    },
    {
        "ordre": 3,
        "nom": "2B. En progression - maximum (95 %)",
        "couleur": "#14B8A6",
        "description": (
            "Borne haute du stade En progression avant l'autonomie complete."
        ),
    },
    {
        "ordre": 4,
        "nom": "3. Autonome (100 %)",
        "couleur": "#22C55E",
        "declenche_anciennete": True,
        "description": (
            "Maitrise l'ensemble de sa fiche de poste et travaille normalement "
            "sans accompagnement. Maitrise des taches >= 80 % et score global 80-89 %. "
            "A partir de ce stade, la remuneration ne plafonne plus : majoration "
            "d'anciennete comptee depuis la date de premier acces a ce stade."
        ),
    },
    {
        "ordre": 5,
        "nom": "4. Confirme / performant (110 %)",
        "couleur": "#F59E0B",
        "description": (
            "Maitrise le poste et obtient durablement de bons resultats. "
            "Maitrise des taches >= 90 %, resultats >= 85 % et score global >= 90 %."
        ),
    },
    {
        "ordre": 6,
        "nom": "5. Referent / expert (120 %)",
        "couleur": "#8B5CF6",
        "description": (
            "Tres performant, transmet son savoir et resout les situations "
            "complexes ; niveau valide par le RA ou la Coordination."
        ),
    },
)


# Montants issus des colonnes H a M du classeur fourni, dans l'ordre de STADES.
GRILLES_POSTES = (
    {
        "source": "Responsable d'Antenne (RA)",
        "aliases": ("Directeur d'antenne", "Responsable d'antenne"),
        "salaires": (1070000, 1160000, 1200000, 1260000, 1390000, 1510000),
    },
    {
        "source": "RAF (Responsable Administratif et Financier)",
        "aliases": ("Responsable administratif et financier", "RAF"),
        "salaires": (740000, 800000, 830000, 870000, 960000, 1040000),
    },
    {
        "source": "Superviseur technique (ST)",
        "aliases": ("Superviseur technique",),
        "salaires": (660000, 720000, 740000, 780000, 860000, 940000),
    },
    {
        "source": "Admin",
        "aliases": ("Admin", "Assistant(e) admin", "Assisitant(e) admin", "Assistant admin"),
        "salaires": (410000, 440000, 460000, 480000, 530000, 580000),
    },
    {
        "source": "Caissiere",
        "aliases": ("Caissiere",),
        "salaires": (630000, 680000, 700000, 740000, 810000, 890000),
    },
    {
        "source": "Agent de recouvrement (AR)",
        "aliases": ("Agent de recouvrement",),
        "salaires": (430000, 470000, 480000, 510000, 560000, 610000),
    },
    {
        "source": "Agent polyvalent Recouvrement / Supervision (AR/ST)",
        "aliases": (
            "Agent de recouvrement superviseur technique",
            "Agent polyvalent recouvrement supervision",
        ),
        "salaires": (430000, 470000, 480000, 510000, 560000, 610000),
    },
    {
        "source": "Agent de maintenance (AM)",
        "aliases": ("Agent de maintenance",),
        "salaires": (420000, 450000, 470000, 490000, 540000, 590000),
    },
    {
        "source": "Mpikojakoja Ifotony (MI)",
        "aliases": ("Mpikojakoja Ifotony",),
        "salaires": (430000, 470000, 480000, 510000, 560000, 610000),
    },
    {
        "source": "Gardien",
        "aliases": ("Gardien",),
        "salaires": (360000, 390000, 400000, 420000, 460000, 500000),
    },
    {
        "source": "Agent de menage / entretien des locaux",
        "aliases": ("Femme de menage", "Agent de menage", "Agent d'entretien"),
        "salaires": (350000, 380000, 390000, 410000, 450000, 490000),
    },
)


def normaliser_libelle(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


class Command(BaseCommand):
    help = (
        "Importe la grille salariale Soakoja par autonomie (BP 2027), "
        "en brouillon et sans ecraser les grilles deja soumises ou appliquees."
    )

    def add_arguments(self, parser):
        parser.add_argument("--organisation", default="Soakoja")
        parser.add_argument("--date-debut", default="2027-01-01")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Verifie les correspondances sans modifier la base.",
        )

    def handle(self, *args, **options):
        try:
            date_debut = date.fromisoformat(options["date_debut"])
        except ValueError as exc:
            raise CommandError("--date-debut doit etre au format AAAA-MM-JJ.") from exc

        organisation = Organisation.objects.filter(
            nom_organisation__iexact=options["organisation"].strip()
        ).first()
        if organisation is None:
            raise CommandError(f"Organisation introuvable : {options['organisation']}")

        postes = list(Poste.objects.filter(organisation=organisation))
        index_postes = {}
        for poste in postes:
            index_postes.setdefault(normaliser_libelle(poste.nom_poste), []).append(poste)

        correspondances = []
        erreurs = []
        for ligne in GRILLES_POSTES:
            candidats = []
            for alias in ligne["aliases"]:
                candidats.extend(index_postes.get(normaliser_libelle(alias), []))
            candidats = list({poste.id: poste for poste in candidats}.values())
            if len(candidats) != 1:
                erreurs.append(
                    f"{ligne['source']} : {len(candidats)} poste(s) correspondant(s) "
                    f"pour les alias {', '.join(ligne['aliases'])}"
                )
                continue
            correspondances.append((ligne, candidats[0]))

        if erreurs:
            raise CommandError("Import annule :\n- " + "\n- ".join(erreurs))

        total_grilles = len(correspondances) * len(STADES)
        self.stdout.write(
            f"Organisation : {organisation.nom_organisation} | "
            f"{len(correspondances)} postes | {len(STADES)} paliers | "
            f"{total_grilles} grilles"
        )
        for ligne, poste in correspondances:
            self.stdout.write(f"  {ligne['source']} -> {poste.nom_poste}")

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Verification terminee : aucune modification effectuee."))
            return

        crees = 0
        mis_a_jour = 0
        ignores = 0

        with transaction.atomic():
            stades = []
            for definition in STADES:
                stade, _ = StadeAutonomie.objects.update_or_create(
                    organisation=organisation,
                    ordre=definition["ordre"],
                    defaults={
                        "nom_stade": definition["nom"],
                        "description": definition["description"],
                        "couleur_hex": definition["couleur"],
                        "declenche_anciennete": definition.get("declenche_anciennete", False),
                    },
                )
                stades.append(stade)

            # Un seul stade pivot par organisation : ordre minimal des stades coches.
            pivot_ordre = min(
                (d["ordre"] for d in STADES if d.get("declenche_anciennete")),
                default=None,
            )
            if pivot_ordre is not None:
                StadeAutonomie.objects.filter(
                    organisation=organisation, declenche_anciennete=True,
                ).exclude(ordre=pivot_ordre).update(declenche_anciennete=False)

            for ligne, poste in correspondances:
                if poste.mode_reference_salariale != "autonomie":
                    poste.mode_reference_salariale = "autonomie"
                    poste.save(update_fields=["mode_reference_salariale"])

                for stade, montant in zip(stades, ligne["salaires"]):
                    queryset = GrilleAutonomie.objects.filter(
                        organisation=organisation,
                        poste=poste,
                        stade=stade,
                        date_debut_validite=date_debut,
                    ).order_by("-date_creation")
                    grille = queryset.first()

                    if grille and grille.statut != "brouillon":
                        ignores += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"Ignore : {poste.nom_poste} / {stade.nom_stade} "
                                f"est deja au statut {grille.get_statut_display()}."
                            )
                        )
                        continue

                    if grille is None:
                        grille = GrilleAutonomie(
                            organisation=organisation,
                            poste=poste,
                            stade=stade,
                            date_debut_validite=date_debut,
                            statut="brouillon",
                        )
                        crees += 1
                    else:
                        mis_a_jour += 1

                    grille.salaire_net_fixe = Decimal(montant)
                    grille.prime_cible = PRIME_CIBLE
                    grille.prime_maximale = PRIME_MAXIMALE
                    # A partir du stade pivot "Autonome 100 %", activer la majoration
                    # d'anciennete (taux et plafond herites de ConfigSalaire : 3 %/an,
                    # plafonne a 15 ans) pour eviter le plafonnement en haut de grille.
                    if pivot_ordre is not None and stade.ordre >= pivot_ordre:
                        grille.anciennete_activee = True
                    grille.full_clean()
                    grille.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Import termine : {crees} creees, {mis_a_jour} mises a jour, "
                f"{ignores} ignorees. Toutes les nouvelles grilles restent en brouillon."
            )
        )
