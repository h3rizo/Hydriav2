from django import forms
from .models import ExProvince, Region, District, Commune, Fokontany, Village, Parcelle


class VillageModelChoiceField(forms.ModelChoiceField):
    """Affiche toute la hierarchie pour distinguer les villages homonymes."""

    def label_from_instance(self, village):
        fokontany = getattr(village, 'fokontany', None)
        commune = getattr(fokontany, 'commune', None) if fokontany else None
        district = getattr(commune, 'district', None) if commune else None
        region = getattr(district, 'region', None) if district else None
        hierarchy = [
            getattr(fokontany, 'nom_fokontany', ''),
            getattr(commune, 'nom_commune', ''),
            getattr(district, 'nom_district', ''),
            getattr(region, 'nom_region', ''),
        ]
        location = ' / '.join(str(value) for value in hierarchy if value)
        return f'{village.nom_village} — {location}' if location else village.nom_village


class ExProvinceForm(forms.ModelForm):
    class Meta:
        model = ExProvince
        fields = ['nom_ex_province']
        widgets = {
            'nom_ex_province': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': "Nom de l'ex-province"
            })
        }


class RegionForm(forms.ModelForm):
    class Meta:
        model = Region
        fields = ['nom_region', 'ex_province']
        widgets = {
            'nom_region': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom de la région'
            }),
            'ex_province': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            })
        }


class DistrictForm(forms.ModelForm):
    class Meta:
        model = District
        fields = ['nom_district', 'region']
        widgets = {
            'nom_district': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom du district'
            }),
            'region': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            })
        }


class CommuneForm(forms.ModelForm):
    class Meta:
        model = Commune
        fields = ['nom_commune', 'district']
        widgets = {
            'nom_commune': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom de la commune'
            }),
            'district': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            })
        }


class FokontanyForm(forms.ModelForm):
    class Meta:
        model = Fokontany
        fields = ['nom_fokontany', 'commune']
        widgets = {
            'nom_fokontany': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom du fokontany'
            }),
            'commune': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            })
        }


class VillageForm(forms.ModelForm):
    class Meta:
        model = Village
        fields = ['nom_village', 'fokontany', 'latitude', 'longitude', 'altitude', 'accessibilite', 'distance_dernier_point']
        widgets = {
            'nom_village': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom du village'
            }),
            'fokontany': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'latitude': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Latitude (ex: -18.9332847)',
                'step': '0.0000001'
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Longitude (ex: 47.5360256)',
                'step': '0.0000001'
            }),
            'altitude': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Altitude en mètres',
                'step': '0.01'
            }),
            'accessibilite': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'distance_dernier_point': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Distance en km',
                'step': '0.01',
                'min': '0'
            })
        }


class ParcelleForm(forms.ModelForm):
    village = VillageModelChoiceField(
        queryset=Village.objects.select_related(
            'fokontany__commune__district__region'
        ).only(
            'id',
            'nom_village',
            'fokontany__id',
            'fokontany__nom_fokontany',
            'fokontany__commune__id',
            'fokontany__commune__nom_commune',
            'fokontany__commune__district__id',
            'fokontany__commune__district__nom_district',
            'fokontany__commune__district__region__id',
            'fokontany__commune__district__region__nom_region',
        ).order_by('nom_village', 'fokontany__nom_fokontany'),
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'}),
        empty_label='Choisir un village',
    )

    class Meta:
        model = Parcelle
        fields = ['reference_parcelle', 'village', 'nombre_habitants', 'nombre_menages', 'source_donnees']
        widgets = {
            'reference_parcelle': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Référence de la parcelle'
            }),
            'nombre_habitants': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nombre d\'habitants',
                'min': '0'
            }),
            'nombre_menages': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nombre de ménages',
                'min': '0'
            }),
            'source_donnees': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Source des données (ex: Recensement 2018)'
            })
        }
