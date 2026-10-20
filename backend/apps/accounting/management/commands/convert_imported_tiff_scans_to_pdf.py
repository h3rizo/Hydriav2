from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from apps.accounting.models import BaseDiameX
from apps.accounting.views import (
    _build_imported_scan_storage_name,
    _clear_imported_scan,
    _convert_tiff_bytes_to_pdf_content,
    _is_tiff_file,
)


class Command(BaseCommand):
    help = "Convertit les scan_importe TIFF existants en PDF pour la consultation web."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Nombre maximum d'entrees a convertir (0 = toutes).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les conversions sans ecrire les fichiers.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]

        qs = BaseDiameX.objects.exclude(scan_importe="").exclude(scan_importe__isnull=True).order_by("id")
        converted = 0
        scanned = 0

        for entry in qs.iterator():
            if limit and scanned >= limit:
                break
            scanned += 1

            scan_name = (getattr(entry.scan_importe, "name", "") or "").strip()
            if not scan_name or not _is_tiff_file(scan_name):
                continue
            if not default_storage.exists(scan_name):
                self.stdout.write(self.style.WARNING(f"Introuvable: {entry.id} -> {scan_name}"))
                continue

            if dry_run:
                self.stdout.write(f"[DRY] {entry.id} -> {scan_name}")
                converted += 1
                continue

            with default_storage.open(scan_name, "rb") as fh:
                pdf_content = _convert_tiff_bytes_to_pdf_content(fh.read(), scan_name)

            _clear_imported_scan(entry)
            target_name = _build_imported_scan_storage_name(
                entry.fichier_source,
                entry.id_access,
                getattr(pdf_content, "name", f"{entry.id_access}.pdf"),
            )
            saved_name = default_storage.save(target_name, pdf_content)
            entry.scan_importe.name = saved_name
            entry.save(update_fields=["scan_importe"])
            converted += 1
            self.stdout.write(self.style.SUCCESS(f"Converti: {entry.id} -> {saved_name}"))

        self.stdout.write(self.style.SUCCESS(f"Conversions effectuees: {converted}"))
