from django.db import migrations, models
import django.db.models.deletion
import uuid
from django.utils import timezone
import apps.core.models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_partnerquarterlyreportarchive_html_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentSource',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('source_file_name', models.CharField(db_index=True, max_length=255)),
                ('source_file_path', models.TextField(unique=True)),
                ('source_folder_path', models.TextField()),
                ('relative_path', models.TextField(blank=True, default='')),
                ('file_type', models.CharField(choices=[('pdf', 'PDF'), ('docx', 'DOCX'), ('doc', 'DOC')], max_length=10)),
                ('file_size', models.PositiveBigIntegerField(default=0)),
                ('file_hash_sha256', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('scanned_at', models.DateTimeField(db_index=True, default=timezone.now)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('extracted', 'Extracted'), ('unsupported', 'Unsupported'), ('error', 'Error')], db_index=True, default='pending', max_length=20)),
                ('error_message', models.TextField(blank=True, default='')),
                ('images_count', models.PositiveIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'Document source extrait',
                'verbose_name_plural': 'Documents source extraits',
                'db_table': 'core_document_sources',
                'ordering': ['-scanned_at'],
            },
        ),
        migrations.CreateModel(
            name='ExtractedDocumentImage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('image_file', models.ImageField(blank=True, null=True, upload_to=apps.core.models.extracted_document_image_upload_to)),
                ('extracted_file_name', models.CharField(max_length=255)),
                ('original_internal_name', models.CharField(blank=True, default='', max_length=255)),
                ('source_page_number', models.PositiveIntegerField(blank=True, null=True)),
                ('image_index', models.PositiveIntegerField(default=1)),
                ('image_extension', models.CharField(blank=True, default='', max_length=20)),
                ('image_size', models.PositiveBigIntegerField(default=0)),
                ('width', models.PositiveIntegerField(blank=True, null=True)),
                ('height', models.PositiveIntegerField(blank=True, null=True)),
                ('image_hash_sha256', models.CharField(db_index=True, max_length=64)),
                ('is_duplicate', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(db_index=True, default=timezone.now)),
                ('status', models.CharField(choices=[('extracted', 'Extracted'), ('duplicate', 'Duplicate'), ('error', 'Error')], db_index=True, default='extracted', max_length=20)),
                ('error_message', models.TextField(blank=True, default='')),
                ('document_source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='extracted_images', to='core.documentsource')),
                ('duplicate_of', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='duplicate_children', to='core.extracteddocumentimage')),
            ],
            options={
                'verbose_name': 'Image extraite depuis document',
                'verbose_name_plural': 'Images extraites depuis documents',
                'db_table': 'core_extracted_document_images',
                'ordering': ['-created_at'],
            },
        ),
    ]
