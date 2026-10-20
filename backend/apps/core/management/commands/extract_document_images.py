from django.core.management.base import BaseCommand, CommandError

from apps.core.services.document_image_extractor import run_extraction, validate_source_path


class Command(BaseCommand):
    help = "Extract images from PDF and DOCX documents in a source folder."

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True, help='Source folder to scan')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--recursive', action='store_true', default=True)
        parser.add_argument('--skip-duplicates', action='store_true')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--extensions', nargs='+', default=['pdf', 'docx', 'doc'])
        parser.add_argument('--verbose', action='store_true')

    def handle(self, *args, **options):
        source = options['source']
        try:
            validated = validate_source_path(source)
        except ValueError as exc:
            raise CommandError(str(exc))

        stats = run_extraction(
            validated,
            recursive=options['recursive'],
            extensions=options['extensions'],
            limit=options['limit'],
            dry_run=options['dry_run'],
            skip_duplicates=options['skip_duplicates'],
        )

        self.stdout.write(f"Source: {validated}")
        self.stdout.write(f"Fichiers trouves: {stats.found_files}")
        self.stdout.write(f"PDF: {stats.pdf_files}")
        self.stdout.write(f"DOCX: {stats.docx_files}")
        self.stdout.write(f"Unsupported (.doc): {stats.unsupported_files}")
        self.stdout.write(f"Images extraites: {stats.extracted_images}")
        self.stdout.write(f"Doublons: {stats.duplicate_images}")
        self.stdout.write(f"Erreurs: {stats.errors}")
