from django import forms
from django.db.models import Case, IntegerField, Q, When
import unicodedata
from .models import (
    Poste,
    Employe,
    Contrat,
    GrilleSalaire,
    Salaire,
    ContratArticleModele,
    ContratTravail,
    AvenantContratTravail,
    HierarchieEmploye,
    EmployeOuvrages,
)
from apps.organization.models import Base, Ouvrage
from apps.geography.models import Commune


def _normalize_sort_text(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _hierarchie_superieur_label(employe):
    return employe.surnom or employe.nom_employe or employe.nom_complet


class EmployeSurnomChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return _hierarchie_superieur_label(obj)


class OuvrageChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.nom_ouvrage


class CommuneChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        district_nom = getattr(obj.district, 'nom_district', '')
        if district_nom:
            return f"{obj.nom_commune} ({district_nom})"
        return obj.nom_commune


class PosteForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['type_poste'].choices = [('', 'Non classé')] + list(Poste.TYPE_POSTE_CHOICES)
        self.fields['niveau_poste'].choices = [('', 'Non classé')] + list(Poste.NIVEAU_POSTE_CHOICES)

    class Meta:
        model = Poste
        fields = [
            'nom_poste', 'organisation', 'ordre_affichage', 'categorie_professionnelle',
            'type_poste', 'niveau_poste',
            'tarif_indemnite', 'tarif_indemnite_demi_journee', 'tarif_indemnite_nuitee',
            'prefixe', 'compte_salaire', 'compte_irsa',
            'compte_cnaps_fmfp_sante', 'compte_indemnite', 'competences_attributions',
        ]
        widgets = {
            'nom_poste': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom du poste'
            }),
            'organisation': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'ordre_affichage': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0',
                'min': '0'
            }),
            'categorie_professionnelle': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'type_poste': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'niveau_poste': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'tarif_indemnite': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'tarif_indemnite_demi_journee': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '4000',
                'step': '0.01',
                'min': '0'
            }),
            'tarif_indemnite_nuitee': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '8000',
                'step': '0.01',
                'min': '0'
            }),
            'prefixe': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Préfixe'
            }),
            'compte_salaire': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compte_irsa': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compte_cnaps_fmfp_sante': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compte_indemnite': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'competences_attributions': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 4,
                'placeholder': "Description des compétences requises et des attributions du poste"
            }),
        }


class EmployeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Formater les dates pour les inputs HTML5 type="date" (YYYY-MM-DD)
        if self.instance and self.instance.pk:
            if self.instance.date_embauche:
                self.initial['date_embauche'] = self.instance.date_embauche.strftime('%Y-%m-%d')
            if self.instance.date_debauchage:
                self.initial['date_debauchage'] = self.instance.date_debauchage.strftime('%Y-%m-%d')
            if self.instance.date_naissance:
                # Format DD/MM/YYYY pour date_naissance
                self.initial['date_naissance'] = self.instance.date_naissance.strftime('%d/%m/%Y')
            if self.instance.date_delivrance_cin:
                self.initial['date_delivrance_cin'] = self.instance.date_delivrance_cin.strftime('%Y-%m-%d')

    def clean_date_naissance(self):
        """Convertir le format DD/MM/YYYY en objet date"""
        from datetime import datetime
        import datetime as dt
        import re

        date_str = self.cleaned_data.get('date_naissance')

        if not date_str:
            return None

        # Si c'est déjà un objet date, le retourner tel quel
        if isinstance(date_str, dt.date):
            return date_str

        # Vérifier le format avec regex (DD/MM/YYYY strict)
        date_str = str(date_str).strip()
        if not re.match(r'^\d{2}/\d{2}/\d{4}$', date_str):
            raise forms.ValidationError('Format de date invalide. Utilisez DD/MM/YYYY (ex: 25/12/1990)')

        # Parser le format DD/MM/YYYY
        try:
            return datetime.strptime(date_str, '%d/%m/%Y').date()
        except ValueError:
            raise forms.ValidationError('Date invalide. Vérifiez le jour, mois et année.')

    class Meta:
        model = Employe
        fields = [
            'nom_employe', 'nom', 'prenom', 'surnom', 'genre', 'date_naissance', 'adresse', 'lieu_naissance',
            'signature', 'numero_cin', 'lieu_delivrance_cin', 'date_delivrance_cin', 'code_tiers', 'telephone', 'mail',
            'base', 'poste', 'volet', 'date_embauche', 'date_debauchage', 'salarie',
            'personnes_charge', 'numero_cnaps', 'mutuelle_sante', 'idxlsx'
        ]
        widgets = {
            'nom_employe': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom complet employé'
            }),
            'nom': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom de famille'
            }),
            'prenom': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Prénom'
            }),
            'surnom': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Surnom'
            }),
            'signature': forms.FileInput(attrs={
                'class': 'file-input file-input-bordered w-full',
                'accept': 'image/*'
            }),
            'numero_cin': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro CIN'
            }),
            'code_tiers': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Code tiers (6 chiffres)',
                'maxlength': '6',
                'pattern': r'\d{6}'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro de téléphone'
            }),
            'mail': forms.EmailInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Adresse email'
            }),
            'base': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'poste': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'volet': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Volet',
                'maxlength': '20'
            }),
            'date_embauche': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'date_debauchage': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'salarie': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'personnes_charge': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0'
            }),
            'numero_cnaps': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro CNAPS'
            }),
            'mutuelle_sante': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'genre': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'date_naissance': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'JJ/MM/AAAA (ex: 25/12/1990)',
                'pattern': r'\d{2}/\d{2}/\d{4}'
            }),
            'adresse': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Adresse'
            }),
            'lieu_naissance': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Lieu de naissance'
            }),
            'lieu_delivrance_cin': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Lieu de delivrance CIN'
            }),
            'date_delivrance_cin': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'idxlsx': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'ID Excel'
            })
        }


class ContratForm(forms.ModelForm):
    class Meta:
        model = Contrat
        fields = ['employe', 'debut_contrat', 'fin_contrat', 'poste', 'type_contrat', 'categorie_professionnel', 'salaire_brut_base']
        widgets = {
            'employe': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'debut_contrat': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'fin_contrat': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'poste': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'type_contrat': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'categorie_professionnel': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'salaire_brut_base': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Ex: 500000'
            })
        }

    def clean_salaire_brut_base(self):
        """Convertir les valeurs vides en None au lieu de supprimer"""
        value = self.cleaned_data.get('salaire_brut_base')
        if value == '' or value is None:
            # Si on est en édition et que le champ est vide, garder la valeur existante
            if self.instance and self.instance.pk and self.instance.salaire_brut_base:
                return self.instance.salaire_brut_base
            return None
        return value


class ContratArticleModeleForm(forms.ModelForm):
    class Meta:
        model = ContratArticleModele
        fields = ['numero_article', 'contenu_article', 'actif']
        widgets = {
            'numero_article': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'min': '1'
            }),
            'contenu_article': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 5,
                'placeholder': "Contenu de l'article avec variables, ex: [Salaire brut]"
            }),
            'actif': forms.CheckboxInput(attrs={'class': 'checkbox'}),
        }


class ContratTravailCreateForm(forms.ModelForm):
    DUREE_CHOICES = [
        ('determinee', 'Determinee'),
        ('3 mois', '3 mois'),
        ('6 mois', '6 mois'),
        ('12 mois', '12 mois'),
        ('24 mois', '24 mois'),
        ('36 mois', '36 mois'),
        ('indeterminee', 'Indeterminee'),
    ]

    districts_affectation = forms.ChoiceField(
        required=False,
        choices=[('', 'Selectionner une base...')],
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'})
    )
    duree_contrat_texte = forms.ChoiceField(
        required=False,
        choices=DUREE_CHOICES,
        widget=forms.Select(attrs={'class': 'select select-bordered w-full'})
    )

    class Meta:
        model = ContratTravail
        fields = [
            'contrat',
            'nom_directeur',
            'poste_directeur',
            'districts_affectation',
            'adresse_employe',
            'lieu_naissance_employe',
            'lieu_delivrance_cin',
            'date_delivrance_cin',
            'duree_contrat_texte',
            'lieu_contrat',
            'date_signature',
        ]
        widgets = {
            'contrat': forms.Select(attrs={'class': 'select select-bordered w-full'}),
            'nom_directeur': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'poste_directeur': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'adresse_employe': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'lieu_naissance_employe': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'lieu_delivrance_cin': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'date_delivrance_cin': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'lieu_contrat': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'date_signature': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
        }

    def __init__(self, *args, organisation=None, contrat_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)

        if contrat_queryset is not None:
            self.fields['contrat'].queryset = contrat_queryset

        # Bases de l'organisation pour le champ districts_affectation (liste deroulante)
        base_choices = [('', 'Selectionner une base...')]
        if organisation:
            bases = Base.objects.filter(organisation=organisation).order_by('nom_base')
            base_choices.extend([(base.nom_base, base.nom_base) for base in bases])

        initial_base = self.initial.get('districts_affectation')
        if initial_base and initial_base not in {value for value, _ in base_choices}:
            base_choices.append((initial_base, initial_base))
        self.fields['districts_affectation'].choices = base_choices

        # Duree de contrat: conserver une valeur initiale calculee si elle n'est pas dans la liste standard.
        duree_choices = list(self.DUREE_CHOICES)
        initial_duree = self.initial.get('duree_contrat_texte')
        if initial_duree and initial_duree not in {value for value, _ in duree_choices}:
            duree_choices.append((initial_duree, initial_duree))
        self.fields['duree_contrat_texte'].choices = duree_choices


class ContratTravailForm(forms.ModelForm):
    class Meta:
        model = ContratTravail
        fields = [
            'nom_directeur',
            'poste_directeur',
            'districts_affectation',
            'adresse_employe',
            'lieu_naissance_employe',
            'lieu_delivrance_cin',
            'date_delivrance_cin',
            'duree_contrat_texte',
            'lieu_contrat',
            'date_signature',
        ]
        widgets = {
            'nom_directeur': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'poste_directeur': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'districts_affectation': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'adresse_employe': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'lieu_naissance_employe': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'lieu_delivrance_cin': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'date_delivrance_cin': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'duree_contrat_texte': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'lieu_contrat': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'date_signature': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
        }


class AvenantContratTravailForm(forms.ModelForm):
    class Meta:
        model = AvenantContratTravail
        fields = ['motif', 'date_effet', 'date_signature', 'lieu_signature']
        widgets = {
            'motif': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': "Motif de l'avenant"
            }),
            'date_effet': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'date_signature': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'lieu_signature': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
        }


class GrilleSalaireForm(forms.ModelForm):
    """Formulaire pour la grille de salaire avec calculs automatiques"""
    nb_jours_feries_gardien = forms.IntegerField(required=False)
    nb_heures_remplacement_gardien = forms.DecimalField(required=False)

    class Meta:
        model = GrilleSalaire
        fields = [
            'contrat', 'date_salaire', 'personnes_charge',
            'salaire_net_cible', 'salaire_brut_base', 'nb_jours_presence', 'est_prorata',
            'nb_jours_feries_gardien', 'a_travaille_1er_mai', 'nb_heures_remplacement_gardien'
        ]
        widgets = {
            'contrat': forms.Select(attrs={
                'class': 'select select-bordered w-full',
                'required': True
            }),
            'date_salaire': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date',
                'required': True
            }),
            'personnes_charge': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0',
                'min': '0'
            }),
            'salaire_net_cible': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Salaire net souhaité (Ar)',
                'step': '0.01'
            }),
            'salaire_brut_base': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Salaire brut de base (Ar)',
                'step': '0.01',
                'min': '0'
            }),
            'nb_jours_presence': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nombre de jours',
                'min': '0'
            }),
            'est_prorata': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'nb_jours_feries_gardien': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Jours fériés travaillés',
                'min': '0'
            }),
            'nb_heures_remplacement_gardien': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Heures de remplacement',
                'step': '0.01',
                'min': '0'
            })
        }
        labels = {
            'contrat': 'Contrat',
            'date_salaire': 'Date du salaire',
            'personnes_charge': 'Personnes à charge',
            'salaire_net_cible': 'Salaire net souhaité (Ar)',
            'nb_jours_presence': 'Nombre de jours de présence',
            'est_prorata': 'Calcul au prorata',
            'nb_jours_feries_gardien': 'Jours fériés gardien',
            'nb_heures_remplacement_gardien': 'Heures remplacement gardien'
        }
        help_texts = {
            'personnes_charge': 'Valeur par défaut récupérée depuis l\'employé',
            'salaire_net_cible': 'Le salaire brut sera calculé automatiquement',
            'nb_jours_presence': 'Pour journaliers: jours travaillés. Pour temps plein/partiel: jours de présence si prorata',
            'est_prorata': 'Cocher si absence partielle (salaire = brut base × nb_jours / 30)',
            'nb_jours_feries_gardien': 'Uniquement pour gardiens',
            'nb_heures_remplacement_gardien': 'Uniquement pour gardiens'
        }


class SalaireForm(forms.ModelForm):
    class Meta:
        model = Salaire
        fields = [
            'grille_salaire', 'date_paiement', 'salaire_net_paye', 'irsa_paye',
            'cnaps_paye', 'fmfp_paye', 'mutuelle_sante_paye',
            'numero_diamex_salaire', 'numero_diamex_irsa', 'numero_diamex_cnaps',
            'numero_diamex_fmfp', 'numero_diamex_mutuelle_sante',
            'base_diamex_salaire', 'base_diamex_irsa', 'base_diamex_cnaps',
            'base_diamex_fmfp', 'base_diamex_mutuelle_sante'
        ]
        widgets = {
            'grille_salaire': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'date_paiement': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'salaire_net_paye': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01',
                'readonly': True
            }),
            'irsa_paye': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01',
                'readonly': True
            }),
            'cnaps_paye': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01',
                'readonly': True
            }),
            'fmfp_paye': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01',
                'readonly': True
            }),
            'mutuelle_sante_paye': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01',
                'readonly': True
            }),
            'numero_diamex_salaire': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro DiameX'
            }),
            'numero_diamex_irsa': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro DiameX'
            }),
            'numero_diamex_cnaps': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro DiameX'
            }),
            'numero_diamex_fmfp': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro DiameX'
            }),
            'numero_diamex_mutuelle_sante': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro DiameX'
            }),
            'base_diamex_salaire': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Base DiameX'
            }),
            'base_diamex_irsa': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Base DiameX'
            }),
            'base_diamex_cnaps': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Base DiameX'
            }),
            'base_diamex_fmfp': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Base DiameX'
            }),
            'base_diamex_mutuelle_sante': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Base DiameX'
            })
        }
class HierarchieEmployeForm(forms.ModelForm):
    superieur = EmployeSurnomChoiceField(
        queryset=Employe.objects.none(),
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        })
    )
    class Meta:
        model = HierarchieEmploye
        fields = ['superieur', 'date_debut', 'date_fin', 'commentaire']
        widgets = {
            'date_debut': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'date_fin': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'commentaire': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 2,
                'placeholder': 'Commentaire ou motif...'
            })
        }

    def __init__(self, *args, **kwargs):
        self.employe = kwargs.pop('employe', None)
        super().__init__(*args, **kwargs)
        if self.employe:
            # Filtrer les supérieurs : 
            # 1. Actifs (pas de date de débauchage)
            # 2. Même organisation
            # 3. Pas soi-même
            qs = Employe.objects.filter(
                date_debauchage__isnull=True
            ).exclude(pk=self.employe.pk)

            if self.employe.base and self.employe.base.organisation:
                qs = qs.filter(base__organisation=self.employe.base.organisation)
            elif self.employe.base:
                qs = qs.filter(base=self.employe.base)

            employes = list(qs)
            employes.sort(
                key=lambda item: (
                    _normalize_sort_text(_hierarchie_superieur_label(item)),
                    _normalize_sort_text(item.nom_employe),
                    str(item.pk),
                )
            )
            ordered_ids = [employe.pk for employe in employes]
            if ordered_ids:
                preserved_order = Case(
                    *[When(pk=pk, then=position) for position, pk in enumerate(ordered_ids)],
                    output_field=IntegerField(),
                )
                self.fields['superieur'].queryset = Employe.objects.filter(pk__in=ordered_ids).order_by(preserved_order)
            else:
                self.fields['superieur'].queryset = Employe.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        if self.employe:
            # Attacher l'employé à l'instance pour que model.clean() puisse s'exécuter sans erreur
            self.instance.employe = self.employe
        return cleaned_data


class EmployeOuvrageForm(forms.ModelForm):
    commune = CommuneChoiceField(
        queryset=Commune.objects.none(),
        required=False,
        empty_label='Toutes les communes',
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        })
    )
    ouvrage = OuvrageChoiceField(
        queryset=Ouvrage.objects.none(),
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        })
    )

    class Meta:
        model = EmployeOuvrages
        fields = ['ouvrage', 'date_debut', 'date_fin', 'est_responsable_principal', 'recevoir_alertes', 'notes']
        widgets = {
            'date_debut': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'date_fin': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'est_responsable_principal': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'recevoir_alertes': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 2,
                'placeholder': 'Notes sur cette responsabilité...'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.employe = kwargs.pop('employe', None)
        self.bulk_mode = kwargs.pop('bulk_mode', False)
        super().__init__(*args, **kwargs)

        ouvrages_qs = Ouvrage.objects.select_related('type_ouvrage').distinct()
        if self.employe and self.employe.base and self.employe.base.organisation:
            organisation = self.employe.base.organisation
            scoped_ouvrages_qs = ouvrages_qs.filter(
                Q(modalites_gestion__gestionnaire=organisation) |
                Q(modalites_gestion__employe__base__organisation=organisation)
            ).distinct()
            if scoped_ouvrages_qs.exists():
                ouvrages_qs = scoped_ouvrages_qs

        self.ouvrages_scope_qs = ouvrages_qs.order_by('nom_ouvrage')
        communes_qs = Commune.objects.filter(
            fokontanys__villages__parcelles__pointeau__ouvrage__in=self.ouvrages_scope_qs
        ).select_related('district').distinct().order_by('nom_commune')
        self.fields['commune'].queryset = communes_qs

        selected_commune_id = (
            self.data.get('commune')
            or self.initial.get('commune')
        )
        if selected_commune_id:
            ouvrages_qs = self.get_commune_ouvrages(selected_commune_id)
            self.fields['commune'].initial = selected_commune_id
        else:
            ouvrages_qs = self.ouvrages_scope_qs

        ouvrage_rows = self.ouvrages_scope_qs.filter(
            pointeau__parcelle__village__fokontany__commune__isnull=False
        ).values(
            'id',
            'nom_ouvrage',
            'pointeau__parcelle__village__fokontany__commune_id',
            'pointeau__parcelle__village__fokontany__commune__nom_commune',
        ).order_by('nom_ouvrage', 'pointeau__parcelle__village__fokontany__commune__nom_commune')

        ouvrage_map = {}
        for row in ouvrage_rows:
            ouvrage_id = str(row['id'])
            ouvrage_data = ouvrage_map.setdefault(ouvrage_id, {
                'id': ouvrage_id,
                'label': row['nom_ouvrage'],
                'commune_ids': [],
                'commune_labels': [],
            })
            commune_id = row['pointeau__parcelle__village__fokontany__commune_id']
            commune_nom = row['pointeau__parcelle__village__fokontany__commune__nom_commune']
            if commune_id and str(commune_id) not in ouvrage_data['commune_ids']:
                ouvrage_data['commune_ids'].append(str(commune_id))
                if commune_nom:
                    ouvrage_data['commune_labels'].append(commune_nom)

        for ouvrage in self.ouvrages_scope_qs.values('id', 'nom_ouvrage'):
            ouvrage_id = str(ouvrage['id'])
            ouvrage_map.setdefault(ouvrage_id, {
                'id': ouvrage_id,
                'label': ouvrage['nom_ouvrage'],
                'commune_ids': [],
                'commune_labels': [],
            })

        self.ouvrage_autocomplete_data = sorted(
            ouvrage_map.values(),
            key=lambda item: _normalize_sort_text(item['label']),
        )

        self.fields['ouvrage'].queryset = ouvrages_qs.order_by('nom_ouvrage')
        # Le select est masque derriere l autocompletion, donc on evite la validation HTML5 native.
        # La contrainte "ouvrage obligatoire" reste geree dans clean() pour l ajout unitaire.
        self.fields['ouvrage'].required = False
        self.fields['est_responsable_principal'].initial = False
        self.fields['recevoir_alertes'].initial = True

    def get_commune_ouvrages(self, commune_or_id):
        commune_id = getattr(commune_or_id, 'id', commune_or_id)
        if not commune_id:
            return self.ouvrages_scope_qs.none()
        return self.ouvrages_scope_qs.filter(
            pointeau__parcelle__village__fokontany__commune_id=commune_id
        ).distinct()

    def clean(self):
        cleaned_data = super().clean()
        if self.employe:
            self.instance.employe = self.employe
        commune = cleaned_data.get('commune')
        ouvrage = cleaned_data.get('ouvrage')
        date_debut = cleaned_data.get('date_debut')
        date_fin = cleaned_data.get('date_fin')
        if self.bulk_mode and not commune:
            self.add_error('commune', 'Veuillez selectionner une commune pour l ajout groupe.')
        if not self.bulk_mode and not ouvrage:
            self.add_error('ouvrage', 'Veuillez selectionner un ouvrage.')
        if commune and ouvrage:
            ouvrage_in_commune = Commune.objects.filter(
                id=commune.id,
                fokontanys__villages__parcelles__pointeau__ouvrage=ouvrage,
            ).exists()
            if not ouvrage_in_commune:
                self.add_error('ouvrage', 'L ouvrage selectionne ne correspond pas a la commune choisie.')
        if date_debut and date_fin and date_fin < date_debut:
            self.add_error('date_fin', 'La date de fin doit etre posterieure ou egale a la date de debut.')
        return cleaned_data
