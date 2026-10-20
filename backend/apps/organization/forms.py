from django import forms
from .models import (
    Organisation,
    TypeOuvrage,
    Ouvrage,
    Base,
    Magasin,
    Journal,
    Compte,
    OuvrageGradingAnnuel,
)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data if item]
        if not data:
            return []
        return [single_file_clean(data, initial)]


class OrganisationForm(forms.ModelForm):
    class Meta:
        model = Organisation
        fields = [
            'nom_organisation', 'type_organisation', 'logo', 'telephone', 'mail', 'adresse1', 'adresse2',
            'code_postal', 'localite', 'province', 'nif', 'stat', 'numero_cnaps',
            'tarif_carte_sociale', 'tarif_demande', 'tarif_minimum_bp',
            'tarif_devis_bp', 'tarif_metre_supplementaire',
            'plafond_soins_simples', 'plafond_lunettes'
        ]
        widgets = {
            'nom_organisation': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom de l\'organisation'
            }),
            'type_organisation': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'logo': forms.FileInput(attrs={
                'class': 'file-input file-input-bordered w-full',
                'accept': 'image/*'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro de téléphone'
            }),
            'mail': forms.EmailInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Adresse email'
            }),
            'adresse1': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Adresse ligne 1'
            }),
            'adresse2': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Adresse ligne 2'
            }),
            'code_postal': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Code postal'
            }),
            'localite': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Localité'
            }),
            'province': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Province'
            }),
            'nif': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro NIF'
            }),
            'stat': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro STAT'
            }),
            'numero_cnaps': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro CNAPS'
            }),
            'tarif_carte_sociale': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'tarif_demande': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'tarif_minimum_bp': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'tarif_devis_bp': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'tarif_metre_supplementaire': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'plafond_soins_simples': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'plafond_lunettes': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            })
        }


class TypeOuvrageForm(forms.ModelForm):
    class Meta:
        model = TypeOuvrage
        fields = ['nom_type_ouvrage']
        widgets = {
            'nom_type_ouvrage': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom du type d\'ouvrage'
            })
        }


class OuvrageForm(forms.ModelForm):
    dossier_technique_files = MultipleFileField(
        required=False,
        label='Dossier technique',
        widget=MultipleFileInput(attrs={
            'class': 'file-input file-input-bordered w-full',
            'multiple': True,
        }),
    )

    class Meta:
        model = Ouvrage
        fields = [
            'nom_ouvrage', 'type_ouvrage', 'ouvrage_source', 'annee_realisation',
            'annee_realisation_avant', 'intervenant', 'saisonnier', 'observation',
            'photo', 'idxlsx'
        ]
        widgets = {
            'nom_ouvrage': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom de l\'ouvrage'
            }),
            'type_ouvrage': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'ouvrage_source': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'annee_realisation': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '2024'
            }),
            'annee_realisation_avant': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '2023'
            }),
            'intervenant': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom de l\'intervenant'
            }),
            'saisonnier': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'observation': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Observations'
            }),
            'photo': forms.FileInput(attrs={
                'class': 'file-input file-input-bordered w-full'
            }),
            'idxlsx': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'ID Excel'
            }),
        }


class BaseForm(forms.ModelForm):
    class Meta:
        model = Base
        fields = [
            'nom_base', 'organisation', 'ouvrage', 'ouvrage_correspondant', 'volet', 'telephone',
            'prog_diamex', 'journal_retour',
            'compte_avance', 'compte_indemnites', 'compte_frais_deplacement',
            'compte_demande_bp', 'compte_facture_volumetrique', 'compte_conso_carte_sociale'
        ]
        widgets = {
            'nom_base': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom de la base'
            }),
            'organisation': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'ouvrage': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'ouvrage_correspondant': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'volet': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Volet'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro de téléphone'
            }),
            'prog_diamex': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Programme Diamex'
            }),
            'journal_retour': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compte_avance': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compte_indemnites': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compte_frais_deplacement': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compte_demande_bp': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compte_facture_volumetrique': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compte_conso_carte_sociale': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            })
        }


class MagasinForm(forms.ModelForm):
    class Meta:
        model = Magasin
        fields = ['nom_magasin', 'base']
        widgets = {
            'nom_magasin': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom du magasin'
            }),
            'base': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            })
        }


class JournalForm(forms.ModelForm):
    class Meta:
        model = Journal
        fields = ['nom_journal', 'base', 'compte', 'code']
        widgets = {
            'nom_journal': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom du journal'
            }),
            'base': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compte': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Compte'
            }),
            'code': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Code'
            })
        }


class CompteForm(forms.ModelForm):
    class Meta:
        model = Compte
        fields = ['nom_compte', 'compte', 'organisation', 'financement', 'achat', 'a_recouper_hydria_diamex', 'detail', 'employe_obligatoire', 'fournisseur_obligatoire', 'compte_vehicule', 'compte_ouvrage_analyse', 'necessite_ouvrage', 'nature_declaration']
        widgets = {
            'nom_compte': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom du compte'
            }),
            'compte': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro de compte'
            }),
            'organisation': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'financement': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'achat': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'a_recouper_hydria_diamex': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'detail': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Détails'
            }),
            'employe_obligatoire': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'fournisseur_obligatoire': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'necessite_ouvrage': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'compte_vehicule': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'compte_ouvrage_analyse': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            })
        }


class OuvrageGradingAnnuelForm(forms.ModelForm):
    class Meta:
        model = OuvrageGradingAnnuel
        fields = ['ouvrage', 'annee', 'grade', 'observation']
        widgets = {
            'ouvrage': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'annee': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '2026',
                'min': '1900',
                'max': '2200'
            }),
            'grade': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'observation': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Observation (optionnel)'
            }),
        }
