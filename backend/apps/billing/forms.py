from django import forms
from .models import Client, Compteur, Releve
from django.db import connection


def get_bases_choices():
    """Récupère les choix de bases disponibles"""
    cursor = connection.cursor()
    cursor.execute('SELECT id, nom FROM bases ORDER BY nom;')
    choices = [('', '--- Sélectionner une base ---')]
    choices.extend([(row[0], f"{row[1]}") for row in cursor.fetchall()])
    return choices


class ClientForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Charger les choix de bases dynamiquement
        self.fields['base'].widget = forms.Select(choices=get_bases_choices(), attrs={
            'class': 'select select-bordered w-full'
        })

    class Meta:
        model = Client
        fields = ['client_id', 'client_name', 'client_type', 'client_address', 'client_phone', 'client_email', 'base']
        widgets = {
            'client_id': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'ID unique du client (ex: CL001)'
            }),
            'client_name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom complet du client'
            }),
            'client_type': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'client_address': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Adresse complète du client'
            }),
            'client_phone': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '034 12 345 67'
            }),
            'client_email': forms.EmailInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'email@example.com'
            }),
        }
        labels = {
            'client_id': 'ID Client',
            'client_name': 'Nom du client',
            'client_type': 'Type de client',
            'client_address': 'Adresse',
            'client_phone': 'Téléphone',
            'client_email': 'Email',
            'base': 'Base d\'affectation',
        }


class CompteurForm(forms.ModelForm):
    class Meta:
        model = Compteur
        fields = ['compteur_number', 'compteur_type', 'compteur_model', 'installation_date', 'client']
        widgets = {
            'compteur_number': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro du compteur'
            }),
            'compteur_type': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compteur_model': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Modèle du compteur'
            }),
            'installation_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'input input-bordered w-full'
            }),
            'client': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
        }


class ReleveForm(forms.ModelForm):
    class Meta:
        model = Releve
        fields = ['compteur', 'releve_date', 'releve_value', 'previous_value', 'releve_type', 'notes']
        widgets = {
            'compteur': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'releve_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'input input-bordered w-full'
            }),
            'releve_value': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'previous_value': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'releve_type': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Remarques sur le relevé'
            }),
        }
        labels = {
            'compteur': 'Compteur',
            'releve_date': 'Date du relevé',
            'releve_value': 'Valeur du relevé',
            'previous_value': 'Valeur précédente',
            'releve_type': 'Type de relevé',
            'notes': 'Remarques',
        }