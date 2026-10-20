from django import forms
from apps.organization.models import Ouvrage, Organisation, TypeOuvrage as OrgTypeOuvrage
from apps.infrastructure.models import EquipementConstitutif
from apps.billing.models import PointEau, CompteurTete, Fournisseur, TarifVolumetrique, TarifVolumetrique2, ModaliteGestion


class TypeOuvrageForm(forms.ModelForm):
    # Support pour l'ancien champ nomtype (pour compatibilité template)
    nomtype = forms.CharField(
        label='Nom du type d\'ouvrage',
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'Ex: Forage, Puits traditionnel, Adduction d\'eau...',
            'maxlength': 255
        })
    )

    class Meta:
        model = OrgTypeOuvrage
        fields = ['nom_type_ouvrage', 'existe']
        labels = {
            'nom_type_ouvrage': 'Nom du type d\'ouvrage',
            'existe': 'Existe'
        }
        widgets = {
            'nom_type_ouvrage': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Ex: Forage, Puits traditionnel, Adduction d\'eau...',
                'maxlength': 255
            }),
            'existe': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-success'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si on édite une instance existante, pré-remplir nomtype
        if self.instance and self.instance.pk:
            self.fields['nomtype'].initial = self.instance.nom_type_ouvrage
            # Le champ existe est automatiquement pré-rempli par Django

    def clean_nomtype(self):
        nomtype = self.cleaned_data.get('nomtype')
        if nomtype:
            nomtype = nomtype.strip()
            if len(nomtype) < 3:
                raise forms.ValidationError("Le nom du type d'ouvrage doit contenir au moins 3 caractères.")

            # Vérifier l'unicité (en excluant l'instance actuelle si c'est une modification)
            queryset = OrgTypeOuvrage.objects.filter(nom_type_ouvrage__iexact=nomtype)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise forms.ValidationError("Un type d'ouvrage avec ce nom existe déjà.")

        return nomtype

    def clean(self):
        cleaned_data = super().clean()
        # Copier nomtype vers nom_type_ouvrage
        if 'nomtype' in cleaned_data:
            cleaned_data['nom_type_ouvrage'] = cleaned_data['nomtype']
        # Le champ existe est géré automatiquement par Django
        # Pas besoin de traitement spécial
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            # Synchroniser automatiquement avec l'app organization
            self._sync_to_organization(instance)
        return instance

    def _sync_to_organization(self, instance):
        """Synchronise le type d'ouvrage avec l'app organization"""
        try:
            from apps.organization.models import TypeOuvrage as OrgTypeOuvrage

            # Si c'est une modification et que le nom a changé, supprimer l'ancien
            if instance.pk and hasattr(self, 'initial') and 'nomtype' in self.initial:
                old_name = self.initial['nomtype']
                if old_name != instance.nomtype:
                    OrgTypeOuvrage.objects.filter(nom_type_ouvrage=old_name).delete()
                    print(f"Ancien type supprimé: {old_name}")

            # Créer ou mettre à jour dans organization
            org_type, created = OrgTypeOuvrage.objects.get_or_create(
                nom_type_ouvrage=instance.nomtype
            )
            if created:
                print(f"Type synchronisé: {instance.nomtype}")

        except Exception as e:
            print(f"Erreur de synchronisation: {e}")


class OuvrageForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # S'assurer que les types d'ouvrages sont bien chargés
        from apps.organization.models import TypeOuvrage as OrgTypeOuvrage
        self.fields['type_ouvrage'].queryset = OrgTypeOuvrage.objects.all().order_by('nom_type_ouvrage')

    class Meta:
        model = Ouvrage
        fields = [
            'nom_ouvrage', 'type_ouvrage', 'annee_realisation',
            'annee_realisation_avant', 'intervenant', 'saisonnier', 'observation'
        ]
        labels = {
            'nom_ouvrage': 'Nom de l\'ouvrage',
            'type_ouvrage': 'Type d\'ouvrage',
            'annee_realisation': 'Année de réalisation',
            'annee_realisation_avant': 'Année de réalisation (avant)',
            'intervenant': 'Intervenant',
            'saisonnier': 'Ouvrage saisonnier',
            'observation': 'Observations'
        }
        widgets = {
            'nom_ouvrage': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom de l\'ouvrage'
            }),
            'type_ouvrage': forms.Select(attrs={
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
            })
        }


class PointEauForm(forms.ModelForm):
    class Meta:
        model = PointEau
        fields = [
            'nomabonne', 'contactabonne', 'ouvrage', 'compteur_tete', 'typeabonne',
            'datebranchement', 'datearretbranchement', 'latitude', 'longitude',
            'estbranchementinstitutionnel', 'tarifforfaitaire', 'montantdemandepaye',
            'montantdevispaye'
        ]
        widgets = {
            'nomabonne': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom de l\'abonné'
            }),
            'contactabonne': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Contact de l\'abonné'
            }),
            'ouvrage': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'compteur_tete': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'typeabonne': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'datebranchement': forms.DateTimeInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'datetime-local'
            }),
            'datearretbranchement': forms.DateTimeInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'datetime-local'
            }),
            'latitude': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Latitude',
                'step': 'any'
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Longitude',
                'step': 'any'
            }),
            'estbranchementinstitutionnel': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            }),
            'tarifforfaitaire': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'montantdemandepaye': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            }),
              'montantdevispaye': forms.NumberInput(attrs={
                  'class': 'input input-bordered w-full',
                  'placeholder': '0.00',
                  'step': '0.01'
              })
          }


class PointEauProblematiqueForm(forms.ModelForm):
    class Meta:
        model = PointEau
        fields = ['problematique_paiement', 'problematique_commentaire']
        widgets = {
            'problematique_paiement': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'problematique_commentaire': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full min-h-32',
                'placeholder': 'Préciser le contexte de la problématique de paiement...'
            }),
        }


class EquipementConstitutifForm(forms.ModelForm):
    class Meta:
        model = EquipementConstitutif
        fields = [
            'nom', 'description', 'type_equipement', 'code_equipement', 'ouvrage',
            'statut', 'date_installation', 'derniere_maintenance', 'prochaine_maintenance',
            'responsable', 'nombre_nettoyages_annuels', 'particularite_equipement', 'temps_acces_heures', 'point_depart',
            'longueur_perimetre', 'haie_vive_cultivable', 'boite_a_vanne', 'boite_a_vanne_utile',
            'vanne_flotteur', 'duree_nettoyage', 'distance_materiaux_locaux'
        ]
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom de l\'équipement'
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Description de l\'équipement'
            }),
            'type_equipement': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'code_equipement': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Code unique de l\'équipement'
            }),
            'ouvrage': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'statut': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'date_installation': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'derniere_maintenance': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'prochaine_maintenance': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'responsable': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'nombre_nettoyages_annuels': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nombre de nettoyages par an',
                'min': '0'
            }),
            'particularite_equipement': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': "Préciser la particularité de l'équipement..."
            }),
            'temps_acces_heures': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Temps d\'accès en heures',
                'step': '0.1',
                'min': '0'
            }),
            'point_depart': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Point de départ pour accéder à l\'équipement'
            }),
            'longueur_perimetre': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Longueur du périmètre en mètres',
                'min': '0'
            }),
            'haie_vive_cultivable': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'boite_a_vanne': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'boite_a_vanne_utile': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'vanne_flotteur': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'duree_nettoyage': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Durée du nettoyage en heures',
                'step': '0.1',
                'min': '0'
            }),
            'distance_materiaux_locaux': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            })
        }


class EquipementMaintenanceForm(forms.ModelForm):
    class Meta:
        model = EquipementConstitutif
        fields = ['nombre_nettoyages_annuels', 'particularite_equipement']
        widgets = {
            'nombre_nettoyages_annuels': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'min': '0',
                'placeholder': 'Nombre de nettoyages par an'
            }),
            'particularite_equipement': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full min-h-32',
                'placeholder': "Préciser la particularité de l'équipement..."
            }),
        }


class CompteurTeteForm(forms.ModelForm):
    class Meta:
        model = CompteurTete
        fields = [
            'numerocompteur', 'ouvrage', 'marque', 'modele', 'date_installation',
            'index_initial', 'statut'
        ]
        widgets = {
            'numerocompteur': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro du compteur'
            }),
            'ouvrage': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'marque': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Marque du compteur'
            }),
            'modele': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Modèle du compteur'
            }),
            'date_installation': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'index_initial': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'statut': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            })
        }


class FournisseurForm(forms.ModelForm):
    class Meta:
        model = Fournisseur
        fields = [
            'nom_fournisseur', 'telephone', 'email', 'adresse',
            'type_fournisseur', 'numero_nif', 'numero_stat', 'actif'
        ]
        widgets = {
            'nom_fournisseur': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Nom du fournisseur'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro de téléphone'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Adresse email'
            }),
            'adresse': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Adresse complète'
            }),
            'type_fournisseur': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'numero_nif': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro NIF'
            }),
            'numero_stat': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Numéro STAT'
            }),
            'actif': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            })
        }


class TarifVolumetriqueForm(forms.ModelForm):
    class Meta:
        model = TarifVolumetrique
        fields = [
            'ouvrage', 'type_point_eau', 'datedebuttarif', 'datefintarif', 'prixabonnement', 'volume_minimum_facture', 'actif'
        ]
        widgets = {
            'ouvrage': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'type_point_eau': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'datedebuttarif': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'datefintarif': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'prixabonnement': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Prix en Ar'
            }),
            'volume_minimum_facture': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Volume minimal (m³)',
                'step': '0.01'
            }),
            'actif': forms.CheckboxInput(attrs={
                'class': 'checkbox'
            })
        }
        labels = {
            'volume_minimum_facture': 'Volume minimal facturé (m³)'
        }


class TarifVolumetrique2Form(forms.ModelForm):
    class Meta:
        model = TarifVolumetrique2
        fields = ['tarifvolumetrique', 'tranchesuperieur', 'tarif']
        widgets = {
            'tarifvolumetrique': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'tranchesuperieur': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Volume max (m³)'
            }),
            'tarif': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Tarif (Ar/m³)'
            })
        }


class ModaliteGestionForm(forms.ModelForm):
    class Meta:
        model = ModaliteGestion
        fields = [
            'ouvrage', 'type_gestion', 'gestionnaire', 'employe',
            'date_debut', 'date_fin', 'modalitepaiement'
        ]
        widgets = {
            'ouvrage': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'type_gestion': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'gestionnaire': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'employe': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'date_debut': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'date_fin': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'modalitepaiement': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            })
        }
