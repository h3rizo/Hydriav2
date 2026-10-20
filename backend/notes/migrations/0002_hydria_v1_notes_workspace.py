import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0030_ouvrage_ouvrage_source'),
        ('notes', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name='tag',
            name='is_system',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tag',
            name='slug',
            field=models.SlugField(blank=True, default='', max_length=90, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='note',
            name='favorited_by',
            field=models.ManyToManyField(blank=True, related_name='favorite_notes', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='note',
            name='is_archived',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='note',
            name='is_favorite',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='note',
            name='note_type',
            field=models.CharField(choices=[('page', 'Page'), ('note', 'Note'), ('decision', 'Décision')], default='note', max_length=20),
        ),
        migrations.AddField(
            model_name='note',
            name='shared_with_base',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='shared_notes', to='organization.base'),
        ),
        migrations.AddField(
            model_name='note',
            name='status',
            field=models.CharField(choices=[('draft', 'Brouillon'), ('active', 'Active'), ('archived', 'Archivée')], default='draft', max_length=20),
        ),
        migrations.AddField(
            model_name='note',
            name='team_label',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='note',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_notes', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='note',
            name='visible_role_name',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AlterField(
            model_name='note',
            name='content_json',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name='note',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_notes', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='note',
            name='visibility',
            field=models.CharField(choices=[('private', 'Privée'), ('team', 'Partagée équipe'), ('all', 'Visible par tous'), ('antenne', 'Visible par antenne'), ('role', 'Visible par rôle')], default='private', max_length=20),
        ),
        migrations.AddField(
            model_name='notelink',
            name='entity_id',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='notelink',
            name='entity_type',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AlterField(
            model_name='notelink',
            name='content_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype'),
        ),
        migrations.AlterField(
            model_name='notelink',
            name='label',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='notelink',
            name='object_id',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='notelink',
            index=models.Index(fields=['entity_type', 'entity_id'], name='note_links_entity__5d70f7_idx'),
        ),
        migrations.AddField(
            model_name='notetask',
            name='entity_id',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='notetask',
            name='entity_type',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='notedecision',
            name='entity_id',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='notedecision',
            name='entity_type',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.CreateModel(
            name='NoteAttachment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('file', models.FileField(upload_to='notes/attachments/%Y/%m/')),
                ('label', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('note', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='notes.note')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name='note',
            index=models.Index(fields=['note_type'], name='notes_note_ty_1156b6_idx'),
        ),
        migrations.AddIndex(
            model_name='note',
            index=models.Index(fields=['status'], name='notes_status_c41bea_idx'),
        ),
        migrations.AddIndex(
            model_name='note',
            index=models.Index(fields=['visibility'], name='notes_visibil_abebd7_idx'),
        ),
        migrations.AddIndex(
            model_name='note',
            index=models.Index(fields=['is_archived'], name='notes_is_arch_da2b38_idx'),
        ),
        migrations.AddIndex(
            model_name='note',
            index=models.Index(fields=['updated_at'], name='notes_updated_9a6ec7_idx'),
        ),
    ]
