from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from apps.accounting.models import BaseDiameX
from apps.accounting.views import (
    _build_imported_scan_storage_name,
    _clear_imported_scan,
    _convert_tiff_bytes_to_pdf_content,
    _is_tiff_file,
    _resolve_entry_scan_path,
)


class Command(BaseCommand):
    help = "Convertit les TIFF historiques references par le champ scan vers scan_importe en PDF."

    def add_arguments(self, parser):
        parser.add_argument("--entry-id", type=int, help="Convertir une seule entree BaseDiameX.")
        parser.add_argument("--limit", type=int, default=0, help="Nombre max d'entrees a traiter (0=toutes).")
        parser.add_argument("--dry-run", action="store_true", help="N'ecrit rien, affiche seulement.")
        parser.add_argument(
            "--replace-existing",
            action="store_true",
            help="Remplace scan_importe existant meme s'il est deja renseigne.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        replace_existing = options["replace_existing"]

        qs = BaseDiameX.objects.filter(scan__iregex=r"\.(tif|tiff)$").order_by("id")
        if options.get("entry_id"):
            qs = qs.filter(id=options["entry_id"])

        converted = 0
        skipped = 0
        missing = 0
        scanned = 0

        for entry in qs.iterator():
            if limit and scanned >= limit:
                break
            scanned += 1

            scan_importe_name = (getattr(getattr(entry, "scan_importe", None), "name", "") or "").strip()
            if scan_importe_name and not replace_existing and scan_importe_name.lower().endswith(".pdf"):
                skipped += 1
                continue

            full_scan_path, candidates = _resolve_entry_scan_path(entry)
            if not full_scan_path or not _is_tiff_file(full_scan_path):
                missing += 1
                self.stdout.write(self.style.WARNING(f"Introuvable/non-TIFF: {entry.id} candidates={candidates[:3]}"))
                continue

            if dry_run:
                self.stdout.write(f"[DRY] {entry.id} -> {full_scan_path}")
                converted += 1
                continue

            with open(full_scan_path, "rb") as fh:
                pdf_content = _convert_tiff_bytes_to_pdf_content(fh.read(), full_scan_path)

            if scan_importe_name:
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

        self.stdout.write(
            self.style.SUCCESS(
                f"Termine. convertis={converted} skipped={skipped} missing={missing} scanned={scanned}"
            )
        )
