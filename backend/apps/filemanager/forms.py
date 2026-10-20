from django import forms
from django.core.validators import FileExtensionValidator
from .models import Tag, File


class FileUploadForm(forms.Form):
    """Formulaire d'upload de fichiers"""
    file = forms.FileField(
        label="Fichier",
        widget=forms.ClearableFileInput(attrs={
            'class': 'file-input file-input-bordered w-full',
            'accept': '*/*'
        }),
        help_text="Sélectionnez un fichier à uploader dans Supabase Storage"
    )
    
    tags = forms.CharField(
        label="Tags",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'documents, pdf, contrat (séparés par des virgules)',
            'autocomplete': 'off'
        }),
        help_text="Tags séparés par des virgules pour catégoriser le fichier"
    )
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Limite de taille (50 MB)
            max_size = 50 * 1024 * 1024  # 50 MB
            if file.size > max_size:
                raise forms.ValidationError(
                    f"Le fichier est trop volumineux. Taille maximum: 50 MB. "
                    f"Taille actuelle: {file.size / (1024*1024):.1f} MB"
                )
        return file
    
    def clean_tags(self):
        tags_input = self.cleaned_data.get('tags', '')
        if tags_input:
            tag_names = [tag.strip() for tag in tags_input.split(',') if tag.strip()]
            
            # Vérifier la longueur des tags
            for tag_name in tag_names:
                if len(tag_name) > 100:
                    raise forms.ValidationError(
                        f"Le tag '{tag_name}' est trop long (maximum 100 caractères)"
                    )
                
                # Vérifier les caractères autorisés
                if not tag_name.replace(' ', '').replace('-', '').replace('_', '').isalnum():
                    raise forms.ValidationError(
                        f"Le tag '{tag_name}' contient des caractères non autorisés. "
                        "Utilisez uniquement des lettres, chiffres, espaces, tirets et underscores."
                    )
            
            return tags_input
        return ''


class TagForm(forms.ModelForm):
    """Formulaire pour créer/modifier un tag"""
    class Meta:
        model = Tag
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom du tag',
                'maxlength': 100
            })
        }
    
    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if name:
            # Vérifier les caractères autorisés
            if not name.replace(' ', '').replace('-', '').replace('_', '').isalnum():
                raise forms.ValidationError(
                    "Le nom du tag contient des caractères non autorisés. "
                    "Utilisez uniquement des lettres, chiffres, espaces, tirets et underscores."
                )
        return name


class FileSearchForm(forms.Form):
    """Formulaire de recherche de fichiers"""
    query = forms.CharField(
        label="Recherche",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'Nom du fichier...',
            'autocomplete': 'off'
        })
    )
    
    tags = forms.CharField(
        label="Tags",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'documents, pdf (séparés par des virgules)',
            'autocomplete': 'off'
        })
    )
    
    file_type = forms.ChoiceField(
        label="Type de fichier",
        required=False,
        choices=[
            ('', 'Tous les types'),
            ('image/', 'Images'),
            ('video/', 'Vidéos'),
            ('audio/', 'Audio'),
            ('application/pdf', 'PDF'),
            ('application/msword', 'Documents Word'),
            ('application/vnd.ms-excel', 'Fichiers Excel'),
            ('text/', 'Fichiers texte'),
            ('application/zip', 'Archives ZIP'),
        ],
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        })
    )