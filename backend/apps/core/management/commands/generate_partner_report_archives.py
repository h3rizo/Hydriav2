from django.core.management.base import BaseCommand, CommandError

from apps.core.partner_report_archives import (
    PartnerReportArchiveError,
    PartnerReportQuarterSpec,
    generate_due_partner_report_archives,
    generate_partner_report_archives_for_organisation,
    get_partner_report_quarter_due_date,
)
from apps.organization.models import Organisation


class Command(BaseCommand):
    help = "Genere et stocke les PDF trimestriels du rapport partenaires."

    def add_arguments(self, parser):
        parser.add_argument(
            '--organisation-id',
            dest='organisation_id',
            help="Limite la generation a une organisation racine donnee.",
        )
        parser.add_argument(
            '--year',
            dest='report_year',
            type=int,
            help="Force l'annee du rapport.",
        )
        parser.add_argument(
            '--quarter',
            dest='report_quarter',
            type=int,
            choices=[1, 2, 3, 4],
            help="Force le trimestre du rapport (1 a 4).",
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help="Regenerer les PDF meme si une archive existe deja.",
        )

    def handle(self, *args, **options):
        organisation_qs = Organisation.objects.order_by('type_organisation', 'nom_organisation')
        organisation_id = (options.get('organisation_id') or '').strip()
        if organisation_id:
            organisation_qs = organisation_qs.filter(id=organisation_id)
            if not organisation_qs.exists():
                raise CommandError("Organisation introuvable pour --organisation-id.")

        overwrite = bool(options.get('overwrite'))
        report_year = options.get('report_year')
        report_quarter = options.get('report_quarter')

        try:
            if report_year and report_quarter:
                period_spec = PartnerReportQuarterSpec(
                    report_year=report_year,
                    report_quarter=report_quarter,
                    due_date=get_partner_report_quarter_due_date(report_year, report_quarter),
                )
                for organisation in organisation_qs:
                    summary = generate_partner_report_archives_for_organisation(
                        organisation=organisation,
                        period_specs=[period_spec],
                        overwrite=overwrite,
                        automatic=True,
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"{organisation.nom_organisation}: {summary['created_count']} genere(s), "
                            f"{summary['skipped_count']} ignore(s)"
                        )
                    )
                return

            if report_year or report_quarter:
                raise CommandError("--year et --quarter doivent etre fournis ensemble.")

            result = generate_due_partner_report_archives(
                organisations=organisation_qs,
                overwrite=overwrite,
                automatic=True,
            )
            for item in result['results']:
                organisation = item['organisation']
                if item.get('error'):
                    self.stdout.write(
                        self.style.WARNING(
                            f"{organisation.nom_organisation}: ignore ({item['error']})"
                        )
                    )
                    continue
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{organisation.nom_organisation}: {item['created_count']} genere(s), "
                        f"{item['skipped_count']} ignore(s)"
                    )
                )
        except PartnerReportArchiveError as exc:
            raise CommandError(str(exc)) from exc
