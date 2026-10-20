import re
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.billing.models import PointEau, Releve

# En dessous de ce seuil de similarite texte, on considere que ce n'est PAS
# une simple faute de frappe / variante, mais probablement un vrai changement
# d'abonne (nouveau titulaire). Ces cas ne sont jamais corriges automatiquement.
SEUIL_SIMILARITE = 0.5

# Libelles qui ne sont clairement pas des noms d'abonne (bug de saisie/import ou
# une description de paiement/transaction a ete stockee a la place du nom).
PATTERNS_NON_NOM = [
    re.compile(r'paiement', re.IGNORECASE),
    re.compile(r'installation', re.IGNORECASE),
    re.compile(r'devis', re.IGNORECASE),
]

# Placeholder generique de type "BF1", "BF 2 Antanetipatara", "BP3", ... utilise
# avant que le vrai nom d'abonne ne soit renseigne sur le point d'eau.
PATTERN_PLACEHOLDER_BF = re.compile(r'^\s*B[FP]\s?\d+\b', re.IGNORECASE)


def _normalise(texte):
    return re.sub(r'\s+', ' ', (texte or '').strip().lower())


def _est_probable_erreur(ancien_nom, nom_actuel):
    """
    Retourne True si l'ecart entre ancien_nom (fige sur le releve) et
    nom_actuel (PointEau.nomabonne) ressemble a une erreur de saisie
    (faute de frappe, casse, libelle de paiement injecte, placeholder
    generique de type BF1/BP2, precision ajoutee/retiree) plutot qu'a
    un vrai changement de titulaire.
    """
    ancien_norm = _normalise(ancien_nom)
    actuel_norm = _normalise(nom_actuel)

    if not ancien_norm or not actuel_norm:
        return True

    # Libelle de paiement/transaction injecte a la place du nom -> toujours une erreur.
    if any(p.search(ancien_nom or '') for p in PATTERNS_NON_NOM):
        return True

    # Placeholder generique "BF1 ...", "BP2 ..." -> toujours une erreur (nom pas
    # encore renseigne au moment de la creation du releve).
    if PATTERN_PLACEHOLDER_BF.match(ancien_nom or ''):
        return True

    # L'un est inclus dans l'autre (ex: "NADIVA Marc Richard" -> "NADIVA Marc Richard ( JOSUAN )")
    if ancien_norm in actuel_norm or actuel_norm in ancien_norm:
        return True

    ratio = SequenceMatcher(None, ancien_norm, actuel_norm).ratio()
    return ratio >= SEUIL_SIMILARITE


class Command(BaseCommand):
    help = (
        "Resynchronise le champ Releve.abonne (nom fige a la creation du releve) "
        "avec le nom actuel de PointEau.nomabonne, pour les releves dont l'ecart "
        "ressemble a une erreur de saisie (faute de frappe, casse, libelle de "
        "paiement injecte par erreur). Les ecarts qui ressemblent a un vrai "
        "changement d'abonne (nom totalement different) sont signales mais jamais "
        "corriges automatiquement."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--point-eau-nom',
            type=str,
            default=None,
            help="Filtrer par nom d'abonne actuel (recherche insensible a la casse, "
                 "correspondance partielle).",
        )
        parser.add_argument(
            '--point-eau-id',
            type=str,
            default=None,
            help="Filtrer par UUID exact du point d'eau.",
        )
        parser.add_argument(
            '--ouvrage-nom',
            type=str,
            default=None,
            help="Filtrer par nom d'ouvrage (recherche insensible a la casse, "
                 "correspondance partielle). Cible tous les points d'eau de cet ouvrage.",
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help="Applique reellement les corrections sur les ecarts classes 'erreur "
                 "probable'. Sans cette option, le script fonctionne en mode dry-run.",
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help="Analyse tous les points d'eau de la base (sans filtre). "
                 "Affiche un resume condense par ouvrage au lieu du detail ligne par ligne.",
        )
        parser.add_argument(
            '--show-suspects',
            action='store_true',
            help="Affiche le detail des ecarts classes 'probable vrai changement "
                 "d'abonne' (jamais corriges automatiquement), pour revue manuelle.",
        )

    def handle(self, *args, **options):
        nom = options.get('point_eau_nom')
        point_eau_id = options.get('point_eau_id')
        ouvrage_nom = options.get('ouvrage_nom')
        apply_changes = options.get('apply')
        analyse_globale = options.get('all')
        show_suspects = options.get('show_suspects')

        if not nom and not point_eau_id and not ouvrage_nom and not analyse_globale:
            raise CommandError(
                "Fournissez --point-eau-nom <nom>, --point-eau-id <uuid>, "
                "--ouvrage-nom <nom>, ou --all pour analyser toute la base."
            )

        points_eau = PointEau.objects.all()
        if point_eau_id:
            points_eau = points_eau.filter(id=point_eau_id)
        if nom:
            points_eau = points_eau.filter(nomabonne__icontains=nom)
        if ouvrage_nom:
            points_eau = points_eau.filter(ouvrage__nom_ouvrage__icontains=ouvrage_nom)

        points_eau = points_eau.select_related('ouvrage')

        total_corrections = 0
        total_suspects = 0
        total_points_eau_touches = 0
        resume_par_ouvrage = {}

        for point_eau in points_eau.iterator():
            nom_actuel = point_eau.nomabonne or ''
            releves_ecart = Releve.objects.filter(
                point_eau=point_eau
            ).exclude(
                Q(abonne=nom_actuel)
            ).order_by('datereleve')

            if not releves_ecart.exists():
                continue

            a_corriger = []
            suspects = []
            for releve in releves_ecart:
                if _est_probable_erreur(releve.abonne, nom_actuel):
                    a_corriger.append(releve)
                else:
                    suspects.append(releve)

            if not a_corriger and not suspects:
                continue

            total_points_eau_touches += 1
            ouvrage_label = point_eau.ouvrage.nom_ouvrage if point_eau.ouvrage else 'Sans ouvrage'

            if not analyse_globale:
                self.stdout.write(self.style.NOTICE(
                    f"\nPoint d'eau: {point_eau.code_point_eau or point_eau.id} "
                    f"(nom actuel: '{nom_actuel}')"
                ))
                for releve in a_corriger:
                    self.stdout.write(
                        f"  [ERREUR PROBABLE] {releve.id} du {releve.datereleve}: "
                        f"'{releve.abonne}' -> '{nom_actuel}'"
                    )
                if show_suspects:
                    for releve in suspects:
                        self.stdout.write(self.style.WARNING(
                            f"  [SUSPECT: vrai changement ?] {releve.id} du {releve.datereleve}: "
                            f"'{releve.abonne}' (non touche)"
                        ))
                elif suspects:
                    self.stdout.write(self.style.WARNING(
                        f"  ({len(suspects)} releve(s) suspect(s) non affiche(s), "
                        "utilisez --show-suspects pour les voir)"
                    ))

            total_corrections += len(a_corriger)
            total_suspects += len(suspects)

            if apply_changes:
                for releve in a_corriger:
                    releve.abonne = nom_actuel
                    releve.save(update_fields=['abonne'])

            if analyse_globale:
                resume_par_ouvrage.setdefault(
                    ouvrage_label, {'points_eau': 0, 'releves_a_corriger': 0, 'releves_suspects': 0}
                )
                resume_par_ouvrage[ouvrage_label]['points_eau'] += 1
                resume_par_ouvrage[ouvrage_label]['releves_a_corriger'] += len(a_corriger)
                resume_par_ouvrage[ouvrage_label]['releves_suspects'] += len(suspects)

        if analyse_globale and resume_par_ouvrage:
            self.stdout.write(self.style.NOTICE(
                "\nResume par ouvrage (points d'eau touches / a corriger / suspects):"
            ))
            for ouvrage_label, stats in sorted(
                resume_par_ouvrage.items(),
                key=lambda item: item[1]['releves_a_corriger'] + item[1]['releves_suspects'],
                reverse=True,
            ):
                self.stdout.write(
                    f"  - {ouvrage_label}: {stats['points_eau']} point(s) d'eau, "
                    f"{stats['releves_a_corriger']} a corriger, "
                    f"{stats['releves_suspects']} suspect(s)"
                )

        if total_corrections == 0 and total_suspects == 0:
            self.stdout.write(self.style.SUCCESS("Aucune incoherence trouvee."))
            return

        self.stdout.write(
            f"\nTotal: {total_points_eau_touches} point(s) d'eau concerne(s), "
            f"{total_corrections} releve(s) a corriger (erreur probable), "
            f"{total_suspects} releve(s) suspect(s) (probable vrai changement d'abonne, "
            "non touches)."
        )

        if apply_changes:
            self.stdout.write(self.style.SUCCESS(
                f"{total_corrections} releve(s) corrige(s)."
            ))
            if total_suspects:
                self.stdout.write(self.style.WARNING(
                    f"{total_suspects} releve(s) suspect(s) laisse(s) inchange(s) "
                    "(revue manuelle recommandee, utilisez --show-suspects)."
                ))
        else:
            self.stdout.write(self.style.WARNING(
                "[DRY-RUN] Aucune modification appliquee. "
                "Relancez avec --apply pour corriger uniquement les erreurs probables."
            ))
