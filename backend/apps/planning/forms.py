from django import forms
from .models import Planning, PlanningEmploye, Indemnite, TypeActivite, ActivitePoste
from apps.employees.models import Employe
from apps.organization.models import Ouvrage


class PlanningForm(forms.ModelForm):
    class Meta:
        model = Planning
        fields = ['date', 'employe', 'type_activite', 'ouvrage', 'remarque', 'estvalide', 'statut']
        widgets = {
            'date': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'input input-bordered w-full'
            }),
            'employe': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'type_activite': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'ouvrage': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'remarque': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Remarques sur le planning'
            }),
            'estvalide': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'statut': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
        }
        labels = {
            'date': 'Date du planning',
            'employe': 'Employé',
            'type_activite': 'Type d\'activité',
            'ouvrage': 'Ouvrage',
            'remarque': 'Remarques',
            'estvalide': 'Planning validé',
            'statut': 'Statut',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Charger les querysets pour les ForeignKey
        self.fields['employe'].queryset = Employe.objects.all().order_by('nom', 'prenom')
        self.fields['type_activite'].queryset = TypeActivite.objects.all().order_by('nomtype')
        self.fields['ouvrage'].queryset = Ouvrage.objects.all().order_by('nom_ouvrage')

        # Rendre les champs optionnels
        self.fields['employe'].required = False
        self.fields['type_activite'].required = False
        self.fields['ouvrage'].required = False


class PlanningEmployeForm(forms.ModelForm):
    class Meta:
        model = PlanningEmploye
        fields = ['employee', 'is_present', 'notes']
        widgets = {
            'employee': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'is_present': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 2,
                'placeholder': 'Notes sur la participation'
            }),
        }


class IndemniteForm(forms.ModelForm):
    class Meta:
        model = Indemnite
        fields = ['indemnite_type', 'indemnite_amount', 'indemnite_date', 'indemnite_description', 'indemnite_status', 'employee']
        widgets = {
            'indemnite_type': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'indemnite_amount': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'indemnite_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'input input-bordered w-full'
            }),
            'indemnite_description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Description de l\'indemnité'
            }),
            'indemnite_status': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'employee': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
        }