from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.utils import timezone
from datetime import date
from decimal import Decimal
import json
from .models import Organisation, TypeOuvrage, Ouvrage, OuvrageGradingAnnuel, Base, Magasin, Journal, Compte
from apps.employees.models import Poste, Employe
from apps.employees.permissions import (
    employe_required,
    filter_queryset_by_permissions,
    is_directeur_poste,
)
from apps.billing.models import CompteurTete, Fournisseur, TarifVolumetrique, ModaliteGestion, PointEau, TypePointEau, PaiementForfaitaire, Releve
from apps.accounting.models import BaseDiameX
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
from apps.accounting.views_verification_ouvrages import diviser_paiement_volume_multi
from apps.infrastructure.models import EquipementConstitutif, Adresse, CarteSociale
from apps.geography.models import Parcelle, Region, District, Commune
from apps.ouvrages.models import TarifVolumetriqueTranche
from apps.employees.models import EmployeOuvrages
from .scoping import (
    get_active_employee_ouvrage_ids,
    get_active_employee_scope_ids,
    get_employe_ids_with_responsible_ouvrage_scope,
)

# Import pour Excel
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


def _exclude_fully_terminated_managements(queryset):
    """Exclut les ouvrages dont la derniere modalite connue est resiliee."""
    latest_management = ModaliteGestion.objects.filter(
        ouvrage_id=OuterRef('ouvrage_id'),
    ).order_by(
        '-date_debut',
        '-created_at',
        '-id',
    )
    return queryset.annotate(
        _latest_management_end=Subquery(latest_management.values('date_fin')[:1]),
    ).filter(
        _latest_management_end__isnull=True,
    )








def export_excel_data(request, model_name):
    """Export complet des données en Excel avec toutes les colonnes y compris les IDs"""
    models_export = {
        'organisations': {
            'model': Organisation,
            'fields': ['id', 'nom_organisation', 'telephone', 'mail', 'adresse1', 'adresse2', 'code_postal', 'localite', 'province', 'nif', 'stat', 'numero_cnaps', 'tarif_carte_sociale', 'tarif_demande', 'tarif_minimum_bp', 'salaire_minimum', 'deduction_irsa'],
            'filename': 'export_organisations.xlsx',
            'sheet_name': 'Organisations'
        },
        'bases': {
            'model': Base,
            'fields': ['id', 'nom_base', 'organisation__nom_organisation', 'organisation_id', 'ouvrage__nom_ouvrage', 'ouvrage_id', 'volet', 'base_diamex'],
            'filename': 'export_bases.xlsx',
            'sheet_name': 'Bases'
        },
        'magasins': {
            'model': Magasin,
            'fields': ['id', 'nom_magasin', 'base__nom_base', 'base_id', 'base__organisation__nom_organisation'],
            'filename': 'export_magasins.xlsx',
            'sheet_name': 'Magasins'
        },
        'journaux': {
            'model': Journal,
            'fields': ['id', 'nom_journal', 'base__nom_base', 'base_id', 'base__organisation__nom_organisation', 'compte', 'code'],
            'filename': 'export_journaux.xlsx',
            'sheet_name': 'Journaux'
        },
        'comptes': {
            'model': Compte,
            'fields': ['id', 'nom_compte', 'organisation__nom_organisation', 'organisation_id', 'compte', 'detail', 'financement', 'a_recouper_hydria_diamex', 'achat'],
            'filename': 'export_comptes.xlsx',
            'sheet_name': 'Comptes'
        },
        'postes': {
            'model': Poste,
            'fields': ['id', 'nom_poste', 'organisation__nom_organisation', 'organisation_id', 'tarif_indemnite', 'prefixe', 'compte_salaire__nom_compte', 'compte_salaire_id', 'compte_irsa__nom_compte', 'compte_irsa_id', 'compte_cnaps_fmfp_sante__nom_compte', 'compte_cnaps_fmfp_sante_id'],
            'filename': 'export_postes.xlsx',
            'sheet_name': 'Postes'
        },
        'equipements': {
            'model': EquipementConstitutif,
            'fields': [
                'id', 'nom', 'type_equipement__nom_type', 'code_equipement', 'statut', 'ouvrage__nom_ouvrage',
                'commune', 'village',  # Added Commune and Village
                'nombre_nettoyages_annuels', 'temps_acces_heures', 'point_depart', 'longueur_perimetre',
                'haie_vive_cultivable', 'boite_a_vanne', 'boite_a_vanne_utile', 'vanne_flotteur',
                'duree_nettoyage', 'distance_materiaux_locaux'
            ],
            'filename': 'export_equipements.xlsx',
            'sheet_name': 'Equipements'
        },
        'compteurtetes': {
            'model': CompteurTete,
            'fields': ['id', 'numerocompteur', 'marque', 'modele', 'statut', 'ouvrage__nom'],
            'filename': 'export_compteurtetes.xlsx',
            'sheet_name': 'Compteurs Tete'
        },
        'tarifs': {
            'model': TarifVolumetrique,
            'fields': ['id', 'ouvrage__nom_ouvrage', 'type_point_eau__nom_type', 'datedebuttarif', 'datefintarif', 'prixabonnement', 'volume_minimum_facture', 'actif'],
            'filename': 'export_tarifs.xlsx',
            'sheet_name': 'Tarifs'
        },
        'modalitegestion': {
            'model': ModaliteGestion,
            'fields': ['id', 'region', 'district', 'commune', 'ouvrage__nom_ouvrage', 'gestionnaire__nom_organisation', 'date_debut', 'date_fin', 'modalitepaiement', 'statut'],
            'filename': 'export_modalitegestion.xlsx',
            'sheet_name': 'Modalites Gestion'
        },
        'fournisseurs': {
            'model': Fournisseur,
            'fields': ['id', 'idxls', 'nom_fournisseur', 'type_fournisseur', 'telephone', 'email',
                      'nif_ou_isi', 'cin', 'date_cin', 'lieu_cin', 'code_postal', 'adresse', 'numero_nif', 'numero_stat',
                      'autre_information', 'tacheron', 'devis'],
            'filename': 'export_fournisseurs.xlsx',
            'sheet_name': 'Fournisseurs'
        },
        'adresses': {
            'model': Adresse,
            'fields': ['id', 'nomadresse', 'type_adresse_display', 'adresse_complete', 'latitude', 'longitude', 'ouvrage__nom_ouvrage'],
            'filename': 'export_adresses.xlsx',
            'sheet_name': 'Adresses'
        },
        'cartes_sociales': {
            'model': CarteSociale,
            'fields': ['id', 'numero_carte', 'nom_beneficiaire', 'point_eau__nomabonne', 'point_eau_id', 'date_creation', 'date_expiration', 'statut', 'observations', 'ouvrage__nom_ouvrage'],
            'filename': 'export_cartes_sociales.xlsx',
            'sheet_name': 'Cartes Sociales'
        },
        'tarifs_tranches': {
            'model': TarifVolumetriqueTranche,
            'fields': ['id', 'tarifvolumetrique_id', 'tranchesuperieur', 'tarif'],
            'filename': 'export_tarifs_tranches.xlsx',
            'sheet_name': 'Tarifs Tranches'
        },
        'ouvrages': {
            'model': Ouvrage,
            'fields': ['id', 'idxlsx', 'nom_ouvrage', 'type_ouvrage__nom_type_ouvrage', 'type_ouvrage_id', 'annee_realisation', 'annee_realisation_avant', 'intervenant', 'saisonnier', 'observation'],
            'filename': 'export_ouvrages.xlsx',
            'sheet_name': 'Ouvrages'
        },
        'pointseaus': {
            'model': PointEau,
            'fields': ['id', 'code_point_eau', 'nomabonne', 'numeroteleph', 'contactabonne', 'ouvrage__nom_ouvrage', 'ouvrage_id', 'type_point_eau__nom_type', 'type_point_eau_id', 'parcelle_id', 'commune', 'village', 'typeabonne', 'estbranchementinstitutionnel', 'datebranchement', 'datearretbranchement', 'tarifforfaitaire', 'compteur_tete__numerocompteur', 'compteur_tete_id', 'numerodiamexdemande', 'numerodiamexdevis', 'basediamexdemande', 'basediamexdevis', 'datepaiementdemande', 'datepaiementdevis', 'montantdemandepaye', 'montantdevispaye', 'nombre_consommateurs', 'nombre_menages_consommateurs', 'idxls', 'latitude', 'longitude'],
            'filename': 'export_pointseaus.xlsx',
            'sheet_name': 'Points Eau'
        }
    }

    if model_name not in models_export:
        return JsonResponse({'error': 'Type d\'export non reconnu'}, status=404)

    config = models_export[model_name]
    model_class = config['model']
    fields = list(config['fields'])

    # Les colonnes par type de point d'eau sont dynamiques : elles dependent
    # des ouvrages effectivement inclus dans l'export (et de l'organisation
    # choisie dans la fenetre d'export de la liste des ouvrages).
    modalite_export_point_types = []
    if model_name == 'modalitegestion':
        modalite_scope = _exclude_fully_terminated_managements(
            ModaliteGestion.objects.all()
        )
        organisation_id = (request.GET.get('organisation') or '').strip()
        if organisation_id and organisation_id != 'all':
            modalite_scope = modalite_scope.filter(gestionnaire_id=organisation_id)

        modalite_export_point_types = list(
            PointEau.objects.filter(
                ouvrage_id__in=modalite_scope.values('ouvrage_id'),
                type_point_eau__isnull=False,
            ).values(
                'type_point_eau_id',
                'type_point_eau__nom_type',
            ).distinct().order_by('type_point_eau__nom_type', 'type_point_eau_id')
        )

        gestionnaire_index = fields.index('gestionnaire__nom_organisation')
        extra_fields = [
            'date_realisation_ouvrage',
            'population_desservie',
        ] + [
            f"points_eau_type::{point_type['type_point_eau_id']}"
            for point_type in modalite_export_point_types
        ]
        fields[gestionnaire_index:gestionnaire_index] = extra_fields

    # Créer un workbook Excel
    wb = Workbook()
    ws = wb.active
    ws.title = config['sheet_name']

    # Créer les en-têtes avec des noms plus clairs
    headers = []
    for field in fields:
        if field == 'id':
            headers.append('ID')
        elif field == 'region':
            headers.append('Région')
        elif field == 'district':
            headers.append('District')
        elif field == 'commune':
            headers.append('Commune')
        elif field == 'date_realisation_ouvrage':
            headers.append('Année de réalisation de l\'ouvrage')
        elif field == 'population_desservie':
            headers.append('Population desservie')
        elif field.startswith('points_eau_type::'):
            point_type_id = field.split('::', 1)[1]
            point_type = next(
                (
                    item for item in modalite_export_point_types
                    if str(item['type_point_eau_id']) == point_type_id
                ),
                None,
            )
            point_type_name = (
                point_type['type_point_eau__nom_type'] if point_type else 'Non renseigne'
            )
            headers.append(f"Nombre PE - {point_type_name}")
        elif '__' in field:
            # Pour les relations, créer des noms plus lisibles
            if field.endswith('__nom_organisation'):
                headers.append('Organisation')
            elif field.endswith('__nom_base'):
                headers.append('Base')
            elif field.endswith('__nom_ouvrage'):
                headers.append('Ouvrage')
            elif field.endswith('__nom_compte'):
                field_name = field.split('__')[0].replace('_', ' ').title()
                headers.append(f'{field_name} (Nom)')
            else:
                headers.append(field.replace('__', ' - ').replace('_', ' ').title())
        elif field.endswith('_id'):
            field_name = field.replace('_id', '').replace('_', ' ').title()
            headers.append(f'{field_name} (ID)')
        else:
            headers.append(field.replace('_', ' ').title())

    # Styliser les en-têtes
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")

    # Ajouter les en-têtes
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    # Exporter toutes les données
    modalite_geographies_by_ouvrage = {}
    modalite_point_counts_by_ouvrage = {}
    modalite_population_by_ouvrage = {}
    modalite_commune_summary = {}
    try:
        if model_name == 'organisations':
            queryset = model_class.objects.all()
        elif model_name == 'bases':
            queryset = model_class.objects.select_related('organisation', 'ouvrage').all()
        elif model_name == 'magasins':
            queryset = model_class.objects.select_related('base', 'base__organisation').all()
        elif model_name == 'journaux':
            queryset = model_class.objects.select_related('base', 'base__organisation').all()
        elif model_name == 'comptes':
            queryset = model_class.objects.select_related('organisation').all()
        elif model_name == 'postes':
            queryset = model_class.objects.select_related('organisation', 'compte_salaire', 'compte_irsa', 'compte_cnaps_fmfp_sante').all()
        elif model_name == 'equipements':
            queryset = model_class.objects.select_related(
                'ouvrage', 'type_equipement'
            ).prefetch_related(
                'ouvrage__pointeau_set__parcelle__village__fokontany__commune'
            ).all()
        elif model_name == 'ouvrages':
            queryset = model_class.objects.select_related('type_ouvrage').all()
        elif model_name == 'pointseaus':
            queryset = model_class.objects.select_related(
                'ouvrage', 'type_point_eau', 'parcelle__village__fokontany__commune'
            ).all()
        elif model_name == 'modalitegestion':
            queryset = _exclude_fully_terminated_managements(
                model_class.objects.select_related(
                    'ouvrage', 'gestionnaire', 'employe'
                ).all()
            )
            organisation_id = (request.GET.get('organisation') or '').strip()
            if organisation_id and organisation_id != 'all':
                queryset = queryset.filter(gestionnaire_id=organisation_id)
            commune_rows = PointEau.objects.filter(
                ouvrage_id__in=queryset.values('ouvrage_id'),
                parcelle__village__fokontany__commune__isnull=False,
            ).values(
                'ouvrage_id',
                'parcelle__village__fokontany__commune__district__region__nom_region',
                'parcelle__village__fokontany__commune__district__nom_district',
                'parcelle__village__fokontany__commune__nom_commune',
            ).distinct()
            for commune_row in commune_rows:
                geography = (
                    commune_row[
                        'parcelle__village__fokontany__commune__district__region__nom_region'
                    ] or '',
                    commune_row[
                        'parcelle__village__fokontany__commune__district__nom_district'
                    ] or '',
                    commune_row[
                        'parcelle__village__fokontany__commune__nom_commune'
                    ] or '',
                )
                if any(geography):
                    modalite_geographies_by_ouvrage.setdefault(
                        commune_row['ouvrage_id'], set()
                    ).add(geography)

            point_rows = PointEau.objects.filter(
                ouvrage_id__in=queryset.values('ouvrage_id'),
            ).values(
                'id',
                'ouvrage_id',
                'type_point_eau_id',
                'parcelle_id',
                'parcelle__nombre_habitants',
                'parcelle__village__fokontany__commune_id',
                'parcelle__village__fokontany__commune__nom_commune',
                'parcelle__village__fokontany__commune__district__nom_district',
                'parcelle__village__fokontany__commune__district__region__nom_region',
            )
            populations_by_parcelle_and_ouvrage = {}
            communes_by_ouvrage = {}
            for point_row in point_rows:
                ouvrage_id = point_row['ouvrage_id']
                ouvrage_key = str(ouvrage_id)
                point_type_key = str(point_row['type_point_eau_id'] or '')
                counts = modalite_point_counts_by_ouvrage.setdefault(ouvrage_key, {})
                counts[point_type_key] = counts.get(point_type_key, 0) + 1

                parcelle_id = point_row['parcelle_id']
                if parcelle_id:
                    populations_by_parcelle_and_ouvrage[
                        (ouvrage_key, str(parcelle_id))
                    ] = int(point_row['parcelle__nombre_habitants'] or 0)

                commune_id = point_row[
                    'parcelle__village__fokontany__commune_id'
                ]
                if not commune_id:
                    continue
                commune_key = str(commune_id)
                communes_by_ouvrage.setdefault(ouvrage_key, set()).add(commune_key)
                summary = modalite_commune_summary.setdefault(commune_key, {
                    'region': point_row[
                        'parcelle__village__fokontany__commune__district__region__nom_region'
                    ] or '',
                    'district': point_row[
                        'parcelle__village__fokontany__commune__district__nom_district'
                    ] or '',
                    'commune': point_row[
                        'parcelle__village__fokontany__commune__nom_commune'
                    ] or '',
                    'ouvrage_ids': set(),
                    'point_counts': {},
                })
                summary['ouvrage_ids'].add(ouvrage_id)
                summary_counts = summary['point_counts']
                summary_counts[point_type_key] = summary_counts.get(point_type_key, 0) + 1

            for (ouvrage_key, _parcelle_id), population in populations_by_parcelle_and_ouvrage.items():
                modalite_population_by_ouvrage[ouvrage_key] = (
                    modalite_population_by_ouvrage.get(ouvrage_key, 0) + population
                )

            # Fusionner les periodes consecutives ayant le meme ouvrage, la
            # meme organisation et la meme modalite de paiement. La premiere
            # date de debut et la derniere date de fin sont conservees.
            from copy import copy

            modalites_ordonnees = list(queryset.order_by(
                'ouvrage__nom_ouvrage',
                'ouvrage_id',
                'date_debut',
                'created_at',
                'id',
            ))
            groupes_modalites = []
            groupe_courant = []
            cle_courante = None
            for modalite in modalites_ordonnees:
                cle_modalite = (
                    modalite.ouvrage_id,
                    modalite.gestionnaire_id,
                    modalite.modalitepaiement or '',
                )
                if groupe_courant and cle_modalite != cle_courante:
                    groupes_modalites.append(groupe_courant)
                    groupe_courant = []
                groupe_courant.append(modalite)
                cle_courante = cle_modalite
            if groupe_courant:
                groupes_modalites.append(groupe_courant)

            modalites_consolidees = []
            for groupe in groupes_modalites:
                premiere_modalite = copy(groupe[0])
                derniere_modalite = groupe[-1]
                premiere_modalite.id = ', '.join(str(item.id) for item in groupe)
                premiere_modalite.date_debut = groupe[0].date_debut
                premiere_modalite.date_fin = derniere_modalite.date_fin
                premiere_modalite.statut = derniere_modalite.statut
                modalites_consolidees.append(premiere_modalite)
            modalites_consolidees.sort(key=lambda item: (
                ', '.join(sorted(
                    {
                        geography[2]
                        for geography in modalite_geographies_by_ouvrage.get(item.ouvrage_id, set())
                        if geography[2]
                    },
                    key=str.casefold,
                )).casefold(),
                ', '.join(sorted(
                    {
                        geography[1]
                        for geography in modalite_geographies_by_ouvrage.get(item.ouvrage_id, set())
                        if geography[1]
                    },
                    key=str.casefold,
                )).casefold(),
                ', '.join(sorted(
                    {
                        geography[0]
                        for geography in modalite_geographies_by_ouvrage.get(item.ouvrage_id, set())
                        if geography[0]
                    },
                    key=str.casefold,
                )).casefold(),
                (getattr(getattr(item, 'ouvrage', None), 'nom_ouvrage', '') or '').casefold(),
                item.date_debut,
            ))
            queryset = modalites_consolidees
        else:
            queryset = model_class.objects.all()

        row_num = 2  # Commencer après les en-têtes
        for obj in queryset:
            for col_num, field in enumerate(fields, 1):
                try:
                    # Gérer les champs spéciaux 'commune' et 'village' pour Points d'eau et Équipements
                    if field in {'region', 'district'} and model_name == 'modalitegestion':
                        geography_index = 0 if field == 'region' else 1
                        geography_values = {
                            geography[geography_index]
                            for geography in modalite_geographies_by_ouvrage.get(
                                getattr(obj, 'ouvrage_id', None), set()
                            )
                            if geography[geography_index]
                        }
                        value = ', '.join(sorted(geography_values, key=str.casefold))
                        ws.cell(row=row_num, column=col_num, value=value)
                    elif field == 'commune':
                        if model_name == 'pointseaus':
                            # PointEau → parcelle → village → fokontany → commune
                            value = ''
                            if hasattr(obj, 'parcelle') and obj.parcelle:
                                if hasattr(obj.parcelle, 'village') and obj.parcelle.village:
                                    if hasattr(obj.parcelle.village, 'fokontany') and obj.parcelle.village.fokontany:
                                        if hasattr(obj.parcelle.village.fokontany, 'commune') and obj.parcelle.village.fokontany.commune:
                                            value = obj.parcelle.village.fokontany.commune.nom_commune
                            ws.cell(row=row_num, column=col_num, value=value)
                        elif model_name == 'equipements':
                            # EquipementConstitutif → ouvrage → pointeau (premier) → parcelle → village → fokontany → commune
                            value = ''
                            if hasattr(obj, 'ouvrage') and obj.ouvrage:
                                # Récupérer le premier point d'eau de l'ouvrage via la relation inverse
                                point_eau = PointEau.objects.filter(ouvrage=obj.ouvrage).select_related(
                                    'parcelle__village__fokontany__commune'
                                ).first()
                                if point_eau and hasattr(point_eau, 'parcelle') and point_eau.parcelle:
                                    if hasattr(point_eau.parcelle, 'village') and point_eau.parcelle.village:
                                        if hasattr(point_eau.parcelle.village, 'fokontany') and point_eau.parcelle.village.fokontany:
                                            if hasattr(point_eau.parcelle.village.fokontany, 'commune') and point_eau.parcelle.village.fokontany.commune:
                                                value = point_eau.parcelle.village.fokontany.commune.nom_commune
                            ws.cell(row=row_num, column=col_num, value=value)
                        elif model_name == 'modalitegestion':
                            commune_names = {
                                geography[2]
                                for geography in modalite_geographies_by_ouvrage.get(
                                    getattr(obj, 'ouvrage_id', None), set()
                                )
                                if geography[2]
                            }
                            value = ', '.join(sorted(commune_names, key=str.casefold))
                            ws.cell(row=row_num, column=col_num, value=value)
                    elif field == 'date_realisation_ouvrage' and model_name == 'modalitegestion':
                        ouvrage = getattr(obj, 'ouvrage', None)
                        annee_realisation = getattr(ouvrage, 'annee_realisation', None)
                        annee_avant = getattr(ouvrage, 'annee_realisation_avant', None)
                        value = annee_realisation or (f'Avant {annee_avant}' if annee_avant else '')
                        ws.cell(row=row_num, column=col_num, value=value)
                    elif field == 'population_desservie' and model_name == 'modalitegestion':
                        value = modalite_population_by_ouvrage.get(str(obj.ouvrage_id), 0)
                        ws.cell(row=row_num, column=col_num, value=value)
                    elif field.startswith('points_eau_type::') and model_name == 'modalitegestion':
                        point_type_id = field.split('::', 1)[1]
                        value = modalite_point_counts_by_ouvrage.get(
                            str(obj.ouvrage_id), {}
                        ).get(point_type_id, 0)
                        ws.cell(row=row_num, column=col_num, value=value)
                    elif field == 'village':
                        if model_name == 'pointseaus':
                            # PointEau → parcelle → village
                            value = ''
                            if hasattr(obj, 'parcelle') and obj.parcelle:
                                if hasattr(obj.parcelle, 'village') and obj.parcelle.village:
                                    value = obj.parcelle.village.nom_village
                            ws.cell(row=row_num, column=col_num, value=value)
                        elif model_name == 'equipements':
                            # EquipementConstitutif → ouvrage → pointeau (premier) → parcelle → village
                            value = ''
                            if hasattr(obj, 'ouvrage') and obj.ouvrage:
                                # Récupérer le premier point d'eau de l'ouvrage via la relation inverse
                                point_eau = PointEau.objects.filter(ouvrage=obj.ouvrage).select_related(
                                    'parcelle__village'
                                ).first()
                                if point_eau and hasattr(point_eau, 'parcelle') and point_eau.parcelle:
                                    if hasattr(point_eau.parcelle, 'village') and point_eau.parcelle.village:
                                        value = point_eau.parcelle.village.nom_village
                            ws.cell(row=row_num, column=col_num, value=value)
                    elif '__' in field:
                        # Gérer les relations
                        field_parts = field.split('__')
                        value = obj
                        for part in field_parts:
                            if value is None:
                                break
                            value = getattr(value, part, None)
                        # Convertir en string et échapper les formules Excel potentielles
                        if value is not None:
                            str_value = str(value)
                            if str_value and str_value[0] in ['=', '+', '-', '@']:
                                str_value = "'" + str_value
                            ws.cell(row=row_num, column=col_num, value=str_value)
                        else:
                            ws.cell(row=row_num, column=col_num, value='')
                    else:
                        value = getattr(obj, field, '')
                        if value is None:
                            ws.cell(row=row_num, column=col_num, value='')
                        elif isinstance(value, bool):
                            ws.cell(row=row_num, column=col_num, value='Oui' if value else 'Non')
                        else:
                            # Formater les dates au format dd/mm/yyyy
                            from datetime import datetime, date
                            if isinstance(value, (datetime, date)):
                                str_value = value.strftime('%d/%m/%Y')
                            else:
                                # Convertir en string et échapper les formules Excel potentielles
                                str_value = str(value)
                                # Si la valeur commence par =, +, -, @ (caractères de formule Excel), ajouter un apostrophe
                                if str_value and str_value[0] in ['=', '+', '-', '@']:
                                    str_value = "'" + str_value
                            ws.cell(row=row_num, column=col_num, value=str_value)
                except Exception:
                    ws.cell(row=row_num, column=col_num, value='')
            row_num += 1

        # Auto-ajuster la largeur des colonnes
        for column in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)  # Largeur max de 50
            ws.column_dimensions[column_letter].width = adjusted_width

        if model_name == 'modalitegestion':
            # Conserver les identifiants dans le classeur, mais ne pas les
            # afficher par defaut a l'utilisateur.
            ws.column_dimensions['A'].hidden = True
            ws.freeze_panes = 'B2'

            # Creer un vrai tableau Excel avec filtres et lignes alternees.
            if row_num > 2:
                last_column = get_column_letter(len(fields))
                table = Table(
                    displayName='ModalitesGestionExport',
                    ref=f'A1:{last_column}{row_num - 1}',
                )
                table.tableStyleInfo = TableStyleInfo(
                    name='TableStyleMedium2',
                    showFirstColumn=False,
                    showLastColumn=False,
                    showRowStripes=True,
                    showColumnStripes=False,
                )
                ws.add_table(table)

            # Onglet recapitulatif : une ligne par commune. Les ouvrages sont
            # dedoublonnes meme s'ils possedent plusieurs modalites historiques.
            summary_ws = wb.create_sheet('Synthese par commune')
            summary_headers = [
                'Région',
                'District',
                'Commune',
                "Nombre d'ouvrages",
                "Nombre total de points d'eau",
            ] + [
                f"Nombre PE - {point_type['type_point_eau__nom_type']}"
                for point_type in modalite_export_point_types
            ] + [
                'Âge moyen des ouvrages (ans)',
            ]
            for col_num, header in enumerate(summary_headers, 1):
                cell = summary_ws.cell(row=1, column=col_num, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment

            ouvrages_by_id = {
                item.ouvrage_id: item.ouvrage
                for item in queryset
                if getattr(item, 'ouvrage_id', None)
            }
            summary_row_num = 2
            for summary in sorted(
                modalite_commune_summary.values(),
                key=lambda item: (
                    item['region'].casefold(),
                    item['district'].casefold(),
                    item['commune'].casefold(),
                ),
            ):
                ages = []
                for ouvrage_id in summary['ouvrage_ids']:
                    ouvrage = ouvrages_by_id.get(ouvrage_id)
                    annee_realisation = getattr(ouvrage, 'annee_realisation', None)
                    if annee_realisation:
                        ages.append(max(timezone.localdate().year - annee_realisation, 0))

                point_counts = summary['point_counts']
                row_values = [
                    summary['region'],
                    summary['district'],
                    summary['commune'],
                    len(summary['ouvrage_ids']),
                    sum(point_counts.values()),
                ] + [
                    point_counts.get(str(point_type['type_point_eau_id']), 0)
                    for point_type in modalite_export_point_types
                ] + [
                    round(sum(ages) / len(ages), 1) if ages else '',
                ]
                for col_num, value in enumerate(row_values, 1):
                    summary_ws.cell(row=summary_row_num, column=col_num, value=value)
                summary_row_num += 1

            summary_ws.freeze_panes = 'A2'
            for column in summary_ws.columns:
                column_letter = get_column_letter(column[0].column)
                max_length = max(len(str(cell.value or '')) for cell in column)
                summary_ws.column_dimensions[column_letter].width = min(max_length + 2, 50)

            if summary_row_num > 2:
                summary_table = Table(
                    displayName='SyntheseModalitesParCommune',
                    ref=(
                        f'A1:{get_column_letter(len(summary_headers))}'
                        f'{summary_row_num - 1}'
                    ),
                )
                summary_table.tableStyleInfo = TableStyleInfo(
                    name='TableStyleMedium2',
                    showFirstColumn=False,
                    showLastColumn=False,
                    showRowStripes=True,
                    showColumnStripes=False,
                )
                summary_ws.add_table(summary_table)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'export: {str(e)}'}, status=500)

    # Préparer la réponse HTTP
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{config["filename"]}"'

    # Sauvegarder le workbook dans la réponse
    wb.save(response)
    return response


def _safe_excel_text(value):
    """Retourne un texte qui ne peut pas etre interprete comme formule Excel."""
    text = str(value or '')
    if text.startswith(('=', '+', '-', '@')):
        return "'" + text
    return text


def _build_tarifs_consolides_workbook(user):
    """Construit le classeur qui joint tarifsvolumetriques et leurs tranches."""
    allowed_ouvrage_ids = filter_queryset_by_permissions(
        Ouvrage.objects.all(),
        user,
    ).values_list('id', flat=True)

    tarifs = list(
        TarifVolumetrique.objects.filter(
            ouvrage_id__in=allowed_ouvrage_ids,
            actif=True,
            datedebuttarif__lte=timezone.localdate(),
        ).filter(
            Q(datefintarif__isnull=True) | Q(datefintarif__gte=timezone.localdate()),
        ).select_related(
            'ouvrage',
            'type_point_eau',
        ).prefetch_related(
            'tranches_volumetriques',
        ).order_by(
            'ouvrage__nom_ouvrage',
            'type_point_eau__nom_type',
            '-datedebuttarif',
        )
    )

    ouvrage_ids = {tarif.ouvrage_id for tarif in tarifs}
    points_eau = PointEau.objects.filter(
        ouvrage_id__in=ouvrage_ids,
        parcelle__isnull=False,
    ).values(
        'ouvrage_id',
        'type_point_eau_id',
        'parcelle__village__fokontany__commune__nom_commune',
        'parcelle__village__fokontany__commune__district__nom_district',
        'parcelle__village__fokontany__commune__district__region__nom_region',
    ).order_by('ouvrage_id', 'type_point_eau_id', 'id')

    geo_by_ouvrage_type = {}
    geo_by_ouvrage = {}
    for point_eau in points_eau:
        ouvrage_key = str(point_eau['ouvrage_id'])
        type_key = str(point_eau['type_point_eau_id'] or '')
        geography = (
            point_eau['parcelle__village__fokontany__commune__district__region__nom_region'] or '',
            point_eau['parcelle__village__fokontany__commune__district__nom_district'] or '',
            point_eau['parcelle__village__fokontany__commune__nom_commune'] or '',
        )
        geo_by_ouvrage.setdefault(ouvrage_key, geography)
        geo_by_ouvrage_type.setdefault((ouvrage_key, type_key), geography)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Tarifs consolides'
    ws.sheet_view.showGridLines = False

    headers = [
        'R\u00e9gion',
        'District',
        'Commune',
        'Ouvrage',
        "Type point d'eau",
        'Prix abonnement (Ar)',
        'Volume minimum facture (m3)',
        'Tarif actif',
        'Num\u00e9ro de tranche',
        'Tranche sup\u00e9rieure (m3)',
        'Tarif tranche (Ar/m3)',
    ]

    last_column = get_column_letter(len(headers))
    ws.merge_cells(f'A1:{last_column}1')
    title_cell = ws['A1']
    title_cell.value = 'Export consolid\u00e9 des tarifs et tranches tarifaires'
    title_cell.font = Font(bold=True, color='FFFFFF', size=14)
    title_cell.fill = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 26

    ws.merge_cells(f'A2:{last_column}2')
    subtitle_cell = ws['A2']
    subtitle_cell.value = f'G\u00e9n\u00e9r\u00e9 le {timezone.localdate().strftime("%d/%m/%Y")} - une ligne par tranche tarifaire'
    subtitle_cell.font = Font(italic=True, color='44546A', size=10)
    subtitle_cell.alignment = Alignment(horizontal='left', vertical='center')

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_num, value=header)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[4].height = 32

    row_num = 5
    for tarif in tarifs:
        ouvrage_key = str(tarif.ouvrage_id)
        type_key = str(tarif.type_point_eau_id or '')
        region_name, district_name, commune_name = geo_by_ouvrage_type.get(
            (ouvrage_key, type_key),
            geo_by_ouvrage.get(ouvrage_key, ('', '', '')),
        )

        tranches_reelles = list(tarif.tranches_volumetriques.all())
        tranches = tranches_reelles or [None]
        for tranche_index, tranche in enumerate(tranches, start=1):
            if not tranche:
                numero_tranche = 'Sans tranche'
            elif len(tranches_reelles) == 1:
                numero_tranche = 'Tranche unique'
            elif tranche_index == 1:
                numero_tranche = '1\u00e8re tranche'
            else:
                numero_tranche = f'{tranche_index}e tranche'

            row_values = [
                _safe_excel_text(region_name),
                _safe_excel_text(district_name),
                _safe_excel_text(commune_name),
                _safe_excel_text(getattr(tarif.ouvrage, 'nom_ouvrage', '')),
                _safe_excel_text(getattr(tarif.type_point_eau, 'nom_type', '')),
                tarif.prixabonnement,
                tarif.volume_minimum_facture,
                'Oui' if tarif.actif else 'Non',
                numero_tranche,
                tranche.tranchesuperieur if tranche else None,
                tranche.tarif if tranche else None,
            ]
            for col_num, value in enumerate(row_values, 1):
                ws.cell(row=row_num, column=col_num, value=value)
            row_num += 1

    last_row = max(row_num - 1, 4)
    if last_row >= 5:
        table = Table(displayName='TarifsConsolides', ref=f'A4:{last_column}{last_row}')
        table.tableStyleInfo = TableStyleInfo(
            name='TableStyleMedium2',
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)
    else:
        ws.auto_filter.ref = f'A4:{last_column}4'

    ws.freeze_panes = 'A5'
    ws.auto_filter.ref = f'A4:{last_column}{last_row}'
    ws.print_title_rows = '1:4'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    for row in ws.iter_rows(min_row=5, max_row=last_row):
        for cell in row:
            cell.alignment = Alignment(vertical='top')
    for column in ('F', 'J', 'K'):
        for cell in ws[column][4:]:
            cell.number_format = '#,##0'
    for cell in ws['G'][4:]:
        cell.number_format = '#,##0.00'

    column_widths = {
        'A': 18, 'B': 20, 'C': 22, 'D': 28, 'E': 22,
        'F': 20, 'G': 26, 'H': 12, 'I': 20, 'J': 24, 'K': 24,
    }
    for column_letter, width in column_widths.items():
        ws.column_dimensions[column_letter].width = width

    return wb, max(row_num - 5, 0)


@employe_required
def export_tarifs_consolides_excel(request):
    """Exporte les tarifs et leurs tranches dans un seul fichier Excel."""
    wb, _ = _build_tarifs_consolides_workbook(request.user)
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'tarifs_consolides_{timezone.localdate().strftime("%Y%m%d")}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@employe_required
def export_ouvrages_custom_excel(request):
    return _export_ouvrages_custom_excel(request, include_extended_columns=False)


@employe_required
def export_ouvrages_custom_excel_plus(request):
    return _export_ouvrages_custom_excel(request, include_extended_columns=True)


@employe_required
def export_ouvrages_responsable_excel(request):
    """Exporte les ouvrages actifs de l'employe choisi et de ses subordonnes."""
    return _export_ouvrages_custom_excel(
        request,
        include_extended_columns=False,
        responsible_export=True,
    )


def _export_ouvrages_custom_excel(
    request,
    include_extended_columns=False,
    responsible_export=False,
):
    organisation_id = (request.GET.get('organisation') or '').strip()
    region_id = (request.GET.get('region') or '').strip()
    district_id = (request.GET.get('district') or '').strip()
    commune_id = (request.GET.get('commune') or '').strip()
    responsible_employee_id = (request.GET.get('responsible_employee') or '').strip()
    annee_raw = (request.GET.get('annee') or '').strip()
    try:
        export_year = int(annee_raw) if annee_raw else (date.today().year if responsible_export else 2025)
    except (TypeError, ValueError):
        export_year = 2025

    today = timezone.now().date()
    reference_date = date(export_year, 12, 31)
    if reference_date > today:
        reference_date = today

    selected_employee = None
    if responsible_export:
        eligible_employee_ids = get_employe_ids_with_responsible_ouvrage_scope(today)
        try:
            selected_employee = Employe.objects.filter(
                pk=responsible_employee_id,
                date_debauchage__isnull=True,
                pk__in=eligible_employee_ids,
            ).first()
        except (TypeError, ValueError, ValidationError):
            selected_employee = None
        if not selected_employee:
            return JsonResponse(
                {'error': 'Veuillez choisir un employe actif valide.'},
                status=400,
            )

        # Cet export est volontairement defini uniquement par l'employe et sa
        # hierarchie. Ignorer aussi d'anciens parametres geographiques qui
        # pourraient rester dans une URL ou un formulaire mis en cache.
        region_id = 'all'
        district_id = 'all'
        commune_id = 'all'

        geography_checks = (
            (region_id, Region, 'region'),
            (district_id, District, 'district'),
            (commune_id, Commune, 'commune'),
        )
        for value, model, label in geography_checks:
            if not value or value == 'all':
                continue
            try:
                exists = model.objects.filter(pk=value).exists()
            except (TypeError, ValueError, ValidationError):
                exists = False
            if not exists:
                return JsonResponse(
                    {'error': f'Le filtre {label} est invalide.'},
                    status=400,
                )

    def _resolve_billing_period(releve_date):
        if not releve_date:
            return None, None
        if releve_date.month == 12:
            return releve_date.year + 1, 1
        return releve_date.year, releve_date.month + 1

    wb = Workbook()
    ws = wb.active
    ws.title = 'Ouvrages'

    headers = [
        'Annee',
        'Region',
        'District',
        'Commune',
        'Fokontany',
        'Ouvrage',
        "Type d'ouvrage",
    ]
    trailing_headers = [
        "Nombre d'habitants",
        'Organisation affectee',
    ]
    if include_extended_columns:
        trailing_headers.extend([
            'Modalite de paiement en vigueur',
            "Agent de recouvrement responsable de l'ouvrage",
            'Grading 2025',
            'Point grading',
            'Montant a collecter',
            'Montant collecte',
            "Nombre de points d'eau collecte",
        ])
    if responsible_export:
        trailing_headers.append('Perimetre du responsable choisi')

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")

    modalites_actives = ModaliteGestion.objects.filter(
        ouvrage=OuterRef('pk'),
        date_debut__lte=reference_date,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
    ).order_by('-date_debut', '-updated_at')

    modalite_active_nom_subquery = modalites_actives.values('gestionnaire__nom_organisation')[:1]
    modalite_active_id_subquery = modalites_actives.values('gestionnaire_id')[:1]
    modalite_active_paiement_subquery = modalites_actives.values('modalitepaiement')[:1]

    responsables_actifs = EmployeOuvrages.objects.filter(
        ouvrage=OuterRef('pk'),
        date_debut__lte=reference_date,
        employe__poste__nom_poste__in=[
            'Agent de recouvrement',
            'Agent de recouvrement Superviseur technique',
        ],
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
    ).filter(
        Q(employe__date_debauchage__isnull=True) | Q(employe__date_debauchage__gte=reference_date)
    ).order_by('-est_responsable_principal', '-date_debut', '-updated_at')

    responsable_nom_subquery = responsables_actifs.values('employe__surnom')[:1]
    responsable_nom_complet_subquery = responsables_actifs.values('employe__nom_employe')[:1]
    grading_2025_subquery = OuvrageGradingAnnuel.objects.filter(
        ouvrage=OuterRef('pk'),
        annee=2025,
    ).values('grade')[:1]

    ouvrages_base = Ouvrage.objects.all()
    # Pour ce rapport, la table EmployeOuvrages definit elle-meme le
    # perimetre. Un second filtre par organisation supprimait toutes les
    # lignes lorsque le responsable appartenait a une autre base/organisation.
    if not responsible_export and not (
        request.user.is_superuser or is_directeur_poste(request.user)
    ):
        ouvrages_base = filter_queryset_by_permissions(
            ouvrages_base,
            request.user,
        )
    # L'export par responsable porte sur les affectations actuelles et ne doit
    # pas perdre un ouvrage a cause de son annee de realisation. La contrainte
    # annuelle reste uniquement celle des exports historiques personnalises.
    if not responsible_export:
        ouvrages_base = ouvrages_base.filter(
            Q(annee_realisation__isnull=True) | Q(annee_realisation__lte=export_year),
            Q(annee_realisation_avant__isnull=True) | Q(annee_realisation_avant__lte=export_year),
        )
    ouvrages = ouvrages_base.select_related('type_ouvrage').annotate(
        organisation_affectee_nom=Subquery(modalite_active_nom_subquery),
        organisation_affectee_id=Subquery(modalite_active_id_subquery),
        modalite_paiement_active=Subquery(modalite_active_paiement_subquery),
        responsable_ouvrage_surnom=Subquery(responsable_nom_subquery),
        responsable_ouvrage_nom=Subquery(responsable_nom_complet_subquery),
        grading_2025=Subquery(grading_2025_subquery),
        nb_points_eau=Count(
            'pointeau',
            distinct=True,
        ),
    ).order_by('nom_ouvrage')

    if organisation_id and organisation_id != 'all':
        ouvrages = ouvrages.filter(
            modalites_gestion__statut='actif',
            modalites_gestion__gestionnaire_id=organisation_id,
        ).distinct()

    if region_id and region_id != 'all':
        ouvrages = ouvrages.filter(
            pointeau__parcelle__isnull=False,
            pointeau__parcelle__village__fokontany__commune__district__region_id=region_id,
        ).distinct()

    if district_id and district_id != 'all':
        ouvrages = ouvrages.filter(
            pointeau__parcelle__village__fokontany__commune__district_id=district_id,
        ).distinct()

    if commune_id and commune_id != 'all':
        ouvrages = ouvrages.filter(
            pointeau__parcelle__village__fokontany__commune_id=commune_id,
        ).distinct()

    if selected_employee:
        responsible_ouvrage_ids = get_active_employee_ouvrage_ids(
            selected_employee.pk,
            today,
        )
        ouvrages = ouvrages.filter(pk__in=responsible_ouvrage_ids)

    ouvrage_ids = list(ouvrages.values_list('id', flat=True))

    if responsible_export:
        employee_scope_ids = get_active_employee_scope_ids(selected_employee.pk, today)
        all_assignment_count = EmployeOuvrages.objects.filter(
            employe_id__in=employee_scope_ids,
        ).count()
        control_ws = wb.create_sheet('Controle export')
        control_rows = [
            ('Employe choisi', selected_employee.surnom or selected_employee.nom_employe),
            ('Date de reference', today.isoformat()),
            ('Employes inclus avec subordonnes', len(employee_scope_ids)),
            ('Affectations historiques trouvees', all_assignment_count),
            ('Ouvrages avec affectation active', len(responsible_ouvrage_ids)),
            ('Ouvrages finalement exportes', len(ouvrage_ids)),
            ('Filtre region', region_id or 'all'),
            ('Filtre district', district_id or 'all'),
            ('Filtre commune', commune_id or 'all'),
        ]
        for row_index, (label, value) in enumerate(control_rows, start=1):
            control_ws.cell(row=row_index, column=1, value=label).font = Font(bold=True)
            control_ws.cell(row=row_index, column=2, value=value)
        control_ws.column_dimensions['A'].width = 38
        control_ws.column_dimensions['B'].width = 45
    forfaitaire_totals_by_ouvrage = {}
    releve_totals_by_ouvrage = {}
    forfaitaire_collected_by_ouvrage = {}
    volume_collected_by_ouvrage = {}
    points_eau_collectes_by_ouvrage = {}

    if include_extended_columns and ouvrage_ids:
        ouvrage_ids_set = {str(obj_id) for obj_id in ouvrage_ids}
        forfaitaire_totals_by_ouvrage = {
            str(row['point_eau__ouvrage_id']): row['total_montant']
            for row in (
                PaiementForfaitaire.objects.filter(
                    point_eau__ouvrage_id__in=ouvrage_ids,
                    date_facture__year=export_year,
                )
                .values('point_eau__ouvrage_id')
                .annotate(total_montant=Sum('montant'))
            )
        }

        # Montants collectes forfaitaires depuis DiameX, en miroir du dashboard forfaitaire.
        diamex_forfaitaire = BaseDiameX.objects.filter(
            compte_code='748411',
            date_m__year=export_year,
        )
        for entry in diamex_forfaitaire:
            extraction = extraire_ouvrage_et_mois_generique(entry.description or '', '748411')
            ouvrage_obj = extraction.get('ouvrage_obj')
            if not ouvrage_obj:
                continue
            ouvrage_key = str(ouvrage_obj.id)
            if ouvrage_key not in ouvrage_ids_set:
                continue
            forfaitaire_collected_by_ouvrage[ouvrage_key] = (
                forfaitaire_collected_by_ouvrage.get(ouvrage_key, Decimal('0'))
                + Decimal(str(entry.montant_in or 0))
            )

        # Montants collectes volume depuis DiameX, en miroir du dashboard volume.
        diamex_volume = BaseDiameX.objects.filter(
            compte_code='707401',
        )
        for entry in diamex_volume:
            segments = []
            if entry.description and ';' in entry.description:
                segments = diviser_paiement_volume_multi(
                    entry.description,
                    entry.compte_code,
                    entry.montant_in if entry.montant_in else 0,
                )

            if segments:
                for segment in segments:
                    extraction = segment.get('extraction') or {}
                    ouvrage_obj = extraction.get('ouvrage_obj')
                    if not ouvrage_obj or extraction.get('annee') != export_year:
                        continue
                    ouvrage_key = str(ouvrage_obj.id)
                    if ouvrage_key not in ouvrage_ids_set:
                        continue
                    volume_collected_by_ouvrage[ouvrage_key] = (
                        volume_collected_by_ouvrage.get(ouvrage_key, Decimal('0'))
                        + Decimal(str(segment.get('montant') or 0))
                    )
            else:
                extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)
                ouvrage_obj = extraction.get('ouvrage_obj')
                if not ouvrage_obj or extraction.get('annee') != export_year:
                    continue
                ouvrage_key = str(ouvrage_obj.id)
                if ouvrage_key not in ouvrage_ids_set:
                    continue
                volume_collected_by_ouvrage[ouvrage_key] = (
                    volume_collected_by_ouvrage.get(ouvrage_key, Decimal('0'))
                    + Decimal(str(entry.montant_in or 0))
                )

        # Nombre de points d'eau collectes:
        # un point d'eau est compte si, sur l'annee choisie, il a au moins une facture
        # et que toutes ses factures pertinentes sont pointees payees.
        points_status = {}

        paiements_forfaitaires_points = PaiementForfaitaire.objects.filter(
            point_eau__ouvrage_id__in=ouvrage_ids,
            date_facture__year=export_year,
        ).values(
            'point_eau_id',
            'point_eau__ouvrage_id',
            'numeroDiameX',
            'baseDiameX',
        )
        for row in paiements_forfaitaires_points:
            point_id = str(row['point_eau_id'])
            ouvrage_key = str(row['point_eau__ouvrage_id'])
            status = points_status.setdefault(point_id, {
                'ouvrage_key': ouvrage_key,
                'has_invoice': False,
                'all_paid': True,
            })
            status['has_invoice'] = True
            is_paid = bool(
                str(row.get('numeroDiameX') or '').strip()
                and str(row.get('baseDiameX') or '').strip()
            )
            if not is_paid:
                status['all_paid'] = False

        releves_points = Releve.objects.filter(
            point_eau__ouvrage_id__in=ouvrage_ids,
            montant__isnull=False,
        ).values(
            'point_eau_id',
            'point_eau__ouvrage_id',
            'datereleve',
            'numeroDiameX',
            'baseDiameX',
        )
        for row in releves_points:
            annee_facture, _ = _resolve_billing_period(row.get('datereleve'))
            if annee_facture != export_year:
                continue
            point_id = str(row['point_eau_id'])
            ouvrage_key = str(row['point_eau__ouvrage_id'])
            status = points_status.setdefault(point_id, {
                'ouvrage_key': ouvrage_key,
                'has_invoice': False,
                'all_paid': True,
            })
            status['has_invoice'] = True
            is_paid = bool(
                str(row.get('numeroDiameX') or '').strip()
                and str(row.get('baseDiameX') or '').strip()
            )
            if not is_paid:
                status['all_paid'] = False

        for point_status in points_status.values():
            if point_status['has_invoice'] and point_status['all_paid']:
                ouvrage_key = point_status['ouvrage_key']
                points_eau_collectes_by_ouvrage[ouvrage_key] = (
                    points_eau_collectes_by_ouvrage.get(ouvrage_key, 0) + 1
                )
        releve_totals_by_ouvrage = {}
        releves_volume = Releve.objects.filter(
            point_eau__ouvrage_id__in=ouvrage_ids,
            montant__isnull=False,
        ).select_related('point_eau__ouvrage')
        for releve in releves_volume:
            annee_facture, _ = _resolve_billing_period(releve.datereleve)
            if annee_facture != export_year:
                continue
            ouvrage_id = getattr(getattr(releve, 'point_eau', None), 'ouvrage_id', None)
            if not ouvrage_id:
                continue
            ouvrage_key = str(ouvrage_id)
            releve_totals_by_ouvrage[ouvrage_key] = (
                releve_totals_by_ouvrage.get(ouvrage_key, Decimal('0'))
                + Decimal(str(releve.montant or 0))
            )

    points_eau = PointEau.objects.filter(
        ouvrage_id__in=ouvrage_ids,
        parcelle__isnull=False,
    ).select_related(
        'type_point_eau',
        'parcelle__village__fokontany__commune__district__region',
    )
    if region_id and region_id != 'all':
        points_eau = points_eau.filter(
            parcelle__village__fokontany__commune__district__region_id=region_id
        )
    points_eau = points_eau.order_by('ouvrage_id', 'id')

    geo_by_ouvrage = {}
    parcelles_by_ouvrage = {}
    points_count_by_ouvrage = {}
    points_count_by_ouvrage_and_type = {}
    point_type_labels = {}

    for point in points_eau:
        ouvrage_key = str(point.ouvrage_id)
        point_type_key = str(point.type_point_eau_id) if point.type_point_eau_id else '__undefined__'
        point_type_label = (
            point.type_point_eau.nom_type
            if point.type_point_eau and point.type_point_eau.nom_type
            else 'Non defini'
        )
        point_type_labels[point_type_key] = point_type_label
        parcelles_by_ouvrage.setdefault(ouvrage_key, set())
        points_count_by_ouvrage[ouvrage_key] = points_count_by_ouvrage.get(ouvrage_key, 0) + 1
        type_counts = points_count_by_ouvrage_and_type.setdefault(ouvrage_key, {})
        type_counts[point_type_key] = type_counts.get(point_type_key, 0) + 1
        if point.parcelle_id:
            parcelles_by_ouvrage[ouvrage_key].add(str(point.parcelle_id))

        if ouvrage_key in geo_by_ouvrage:
            continue

        region_name = ''
        district_name = ''
        commune_name = ''
        fokontany_name = ''

        parcelle = getattr(point, 'parcelle', None)
        village = getattr(parcelle, 'village', None) if parcelle else None
        fokontany = getattr(village, 'fokontany', None) if village else None
        commune = getattr(fokontany, 'commune', None) if fokontany else None
        district = getattr(commune, 'district', None) if commune else None
        region = getattr(district, 'region', None) if district else None

        if fokontany and fokontany.nom_fokontany:
            fokontany_name = fokontany.nom_fokontany
        if commune and commune.nom_commune:
            commune_name = commune.nom_commune
        if district and district.nom_district:
            district_name = district.nom_district
        if region and region.nom_region:
            region_name = region.nom_region

        geo_by_ouvrage[ouvrage_key] = (
            region_name,
            district_name,
            commune_name,
            fokontany_name,
        )

    point_type_keys = sorted(
        point_type_labels,
        key=lambda key: (point_type_labels[key].casefold(), key),
    )
    headers.extend([
        f"Nombre de points d'eau - {point_type_labels[key]}"
        for key in point_type_keys
    ])
    headers.extend(trailing_headers)
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    parcelle_ids = {
        parcelle_id
        for parcelles_ids in parcelles_by_ouvrage.values()
        for parcelle_id in parcelles_ids
    }
    habitants_by_parcelle = {
        str(row['id']): int(row['nombre_habitants'] or 0)
        for row in Parcelle.objects.filter(id__in=parcelle_ids).values('id', 'nombre_habitants')
    }

    parcelles_deja_comptees = set()
    modalite_labels = dict(ModaliteGestion._meta.get_field('modalitepaiement').choices)
    row_num = 2
    for ouvrage in ouvrages:
        ouvrage_key = str(ouvrage.id)
        region_name, district_name, commune_name, fokontany_name = geo_by_ouvrage.get(
            ouvrage_key, ('', '', '', '')
        )
        parcelles_ouvrage = parcelles_by_ouvrage.get(ouvrage_key, set())
        habitants = sum(
            habitants_by_parcelle.get(parcelle_id, 0)
            for parcelle_id in parcelles_ouvrage
            if parcelle_id not in parcelles_deja_comptees
        )
        parcelles_deja_comptees.update(parcelles_ouvrage)

        responsable_ouvrage = (
            ouvrage.responsable_ouvrage_surnom
            or ouvrage.responsable_ouvrage_nom
            or ''
        )
        modalite_paiement = modalite_labels.get(
            ouvrage.modalite_paiement_active,
            ouvrage.modalite_paiement_active or ''
        )

        total_forfaitaire = forfaitaire_totals_by_ouvrage.get(ouvrage_key) or 0
        total_volume = releve_totals_by_ouvrage.get(ouvrage_key) or 0
        montant_a_collecter = 0
        montant_collecte = Decimal('0')
        nb_points_eau_collectes = points_eau_collectes_by_ouvrage.get(ouvrage_key, 0)
        if ouvrage.modalite_paiement_active == 'forfaitaire':
            montant_a_collecter = total_forfaitaire
            montant_collecte = forfaitaire_collected_by_ouvrage.get(ouvrage_key, Decimal('0'))
        elif ouvrage.modalite_paiement_active == 'au_volume':
            montant_a_collecter = total_volume
            montant_collecte = volume_collected_by_ouvrage.get(ouvrage_key, Decimal('0'))
        elif ouvrage.modalite_paiement_active == 'mixte':
            montant_a_collecter = total_forfaitaire + total_volume
            montant_collecte = (
                forfaitaire_collected_by_ouvrage.get(ouvrage_key, Decimal('0'))
                + volume_collected_by_ouvrage.get(ouvrage_key, Decimal('0'))
            )

        nb_points_eau_total = points_count_by_ouvrage.get(ouvrage_key, 0)
        if Decimal(str(montant_collecte or 0)) <= Decimal('0'):
            nb_points_eau_collectes = 0
        elif (
            nb_points_eau_collectes < nb_points_eau_total
            and Decimal(str(montant_collecte or 0)) >= Decimal(str(montant_a_collecter or 0))
            and nb_points_eau_total > 0
        ):
            nb_points_eau_collectes = nb_points_eau_total

        row_values = [
            export_year,
            region_name,
            district_name,
            commune_name,
            fokontany_name,
            ouvrage.nom_ouvrage,
            getattr(getattr(ouvrage, 'type_ouvrage', None), 'nom_type_ouvrage', '') or '',
        ]
        row_values.extend([
            points_count_by_ouvrage_and_type.get(ouvrage_key, {}).get(point_type_key, 0)
            for point_type_key in point_type_keys
        ])
        row_values.extend([
            habitants,
            ouvrage.organisation_affectee_nom or '',
        ])
        if include_extended_columns:
            point_grading = 1 if (ouvrage.grading_2025 or '') == 'A' else 0
            row_values.extend([
                modalite_paiement,
                responsable_ouvrage,
                ouvrage.grading_2025 or '',
                point_grading,
                float(montant_a_collecter or 0),
                float(montant_collecte or 0),
                nb_points_eau_collectes,
            ])
        if responsible_export:
            row_values.append(selected_employee.surnom or selected_employee.nom_employe)

        for col_num, value in enumerate(row_values, 1):
            ws.cell(row=row_num, column=col_num, value=value)
        row_num += 1

    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                max_length = max(max_length, len(str(cell.value or '')))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 40)

    selected_org = ''
    selected_region = ''
    if organisation_id and organisation_id != 'all':
        selected_org = Organisation.objects.filter(pk=organisation_id).values_list('nom_organisation', flat=True).first() or ''
    if region_id and region_id != 'all':
        selected_region = Region.objects.filter(pk=region_id).values_list('nom_region', flat=True).first() or ''

    filename_parts = [
        'export_ouvrages_responsable'
        if responsible_export else (
            'export_ouvrages_personnalise_plus'
            if include_extended_columns else
            'export_ouvrages_personnalise'
        )
    ]
    filename_parts.append(str(export_year))
    if selected_org:
        filename_parts.append(selected_org.replace(' ', '_'))
    if selected_region:
        filename_parts.append(selected_region.replace(' ', '_'))
    if selected_employee:
        employee_export_name = selected_employee.surnom or selected_employee.nom_employe
        filename_parts.append(employee_export_name.replace(' ', '_'))

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{"_".join(filename_parts)}.xlsx"'
    wb.save(response)
    return response


def _iter_equipement_gps_import(ws, allowed_equipements):
    """Traite et vérifie en base chaque ligne GPS d'équipement."""
    rows = [
        (row_num, row)
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2)
        if row and row[0]
    ]
    yield {'event': 'start', 'total': len(rows)}
    updated_count = verified_count = unchanged_count = error_count = 0

    for position, (row_num, row) in enumerate(rows, start=1):
        equipement_id = str(row[0]).strip()
        excel_name = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ''
        base_event = {
            'event': 'row', 'position': position, 'total': len(rows),
            'row': row_num, 'id': equipement_id, 'excel_name': excel_name,
        }
        try:
            latitude = row[2] if len(row) > 2 else None
            longitude = row[3] if len(row) > 3 else None
            if latitude in (None, '') or longitude in (None, ''):
                raise ValueError('Latitude ou longitude manquante')

            lat = float(str(latitude).strip().replace(',', '.'))
            lon = float(str(longitude).strip().replace(',', '.'))
            if not -90 <= lat <= 90:
                raise ValueError('Latitude hors limites (-90 à 90)')
            if not -180 <= lon <= 180:
                raise ValueError('Longitude hors limites (-180 à 180)')

            equipement = allowed_equipements.get(pk=equipement_id)
            changed = (
                equipement.latitude is None
                or equipement.longitude is None
                or abs(float(equipement.latitude) - lat) >= 1e-8
                or abs(float(equipement.longitude) - lon) >= 1e-8
            )
            equipement.latitude = lat
            equipement.longitude = lon
            equipement.save(update_fields=['latitude', 'longitude'])

            stored = EquipementConstitutif.objects.filter(pk=equipement.pk).values('latitude', 'longitude').first()
            is_verified = (
                stored
                and stored['latitude'] is not None
                and stored['longitude'] is not None
                and abs(float(stored['latitude']) - lat) < 1e-8
                and abs(float(stored['longitude']) - lon) < 1e-8
            )
            if not is_verified:
                raise RuntimeError("Échec de la vérification après l'enregistrement")

            verified_count += 1
            if changed:
                updated_count += 1
            else:
                unchanged_count += 1
            yield {
                **base_event,
                'status': 'verified',
                'changed': changed,
                'name': equipement.nom or equipement.code_equipement or excel_name or equipement_id,
                'latitude': float(stored['latitude']),
                'longitude': float(stored['longitude']),
                'message': 'Mis à jour et vérifié' if changed else 'Déjà identique, vérifié',
            }
        except EquipementConstitutif.DoesNotExist:
            error_count += 1
            yield {**base_event, 'status': 'error', 'message': 'Équipement introuvable ou non autorisé'}
        except (TypeError, ValueError) as exc:
            error_count += 1
            yield {**base_event, 'status': 'error', 'message': str(exc)}
        except Exception as exc:
            error_count += 1
            yield {**base_event, 'status': 'error', 'message': f'Erreur : {exc}'}

    yield {
        'event': 'complete', 'total': len(rows), 'updated': updated_count,
        'verified': verified_count, 'unchanged': unchanged_count, 'errors': error_count,
    }


@employe_required
def import_excel_update_equipements_gps(request):
    """Import GPS des équipements avec progression et vérification en base."""
    if request.method != 'POST' or not request.FILES.get('excel_file'):
        return redirect('organization:ouvrage_list')

    try:
        wb = load_workbook(request.FILES['excel_file'], read_only=True, data_only=True)
        ws = wb.active
        allowed_ouvrage_ids = filter_queryset_by_permissions(
            Ouvrage.objects.all(), request.user
        ).values('pk')
        allowed_equipements = EquipementConstitutif.objects.filter(
            ouvrage_id__in=allowed_ouvrage_ids
        )
        events = _iter_equipement_gps_import(ws, allowed_equipements)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            def stream_events():
                try:
                    for event in events:
                        yield json.dumps(event, ensure_ascii=False) + '\n'
                finally:
                    wb.close()

            response = StreamingHttpResponse(
                stream_events(), content_type='application/x-ndjson; charset=utf-8'
            )
            response['Cache-Control'] = 'no-cache, no-transform'
            response['X-Accel-Buffering'] = 'no'
            return response

        results = list(events)
        wb.close()
        summary = results[-1]
        if summary['verified']:
            messages.success(
                request,
                f"{summary['verified']} équipement(s) vérifié(s) en base, "
                f"dont {summary['updated']} réellement modifié(s).",
            )
        if summary['errors']:
            messages.warning(request, f"{summary['errors']} ligne(s) en erreur.")
    except Exception as exc:
        messages.error(request, f"Erreur lors de l'import : {exc}")

    return redirect('organization:ouvrage_list')


def _iter_point_eau_gps_import(ws, allowed_points_eau):
    """Traite, relit et vérifie chaque ligne GPS avant de la déclarer réussie."""
    rows = [
        (row_num, row)
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2)
        if row and row[0]
    ]
    yield {'event': 'start', 'total': len(rows)}

    updated_count = 0
    verified_count = 0
    unchanged_count = 0
    error_count = 0

    for position, (row_num, row) in enumerate(rows, start=1):
        point_eau_id = str(row[0]).strip()
        excel_name = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ''
        base_event = {
            'event': 'row',
            'position': position,
            'total': len(rows),
            'row': row_num,
            'id': point_eau_id,
            'excel_name': excel_name,
        }
        try:
            latitude = row[2] if len(row) > 2 else None
            longitude = row[3] if len(row) > 3 else None
            if latitude in (None, '') or longitude in (None, ''):
                raise ValueError('Latitude ou longitude manquante')

            lat = float(str(latitude).strip().replace(',', '.'))
            lon = float(str(longitude).strip().replace(',', '.'))
            if not -90 <= lat <= 90:
                raise ValueError('Latitude hors limites (-90 à 90)')
            if not -180 <= lon <= 180:
                raise ValueError('Longitude hors limites (-180 à 180)')

            point_eau = allowed_points_eau.get(pk=point_eau_id)
            old_latitude = point_eau.latitude
            old_longitude = point_eau.longitude
            changed = old_latitude != lat or old_longitude != lon

            point_eau.latitude = lat
            point_eau.longitude = lon
            point_eau.save(update_fields=['latitude', 'longitude'])

            # Relecture indépendante : le succès n'est annoncé que si la base
            # contient effectivement les deux valeurs attendues.
            stored = PointEau.objects.filter(pk=point_eau.pk).values('latitude', 'longitude').first()
            is_verified = (
                stored
                and stored['latitude'] is not None
                and stored['longitude'] is not None
                and abs(stored['latitude'] - lat) < 1e-8
                and abs(stored['longitude'] - lon) < 1e-8
            )
            if not is_verified:
                raise RuntimeError("Échec de la vérification après l'enregistrement")

            verified_count += 1
            if changed:
                updated_count += 1
            else:
                unchanged_count += 1
            yield {
                **base_event,
                'status': 'verified',
                'changed': changed,
                'name': point_eau.nomabonne or point_eau.code_point_eau or excel_name or point_eau_id,
                'latitude': stored['latitude'],
                'longitude': stored['longitude'],
                'message': 'Mis à jour et vérifié' if changed else 'Déjà identique, vérifié',
            }
        except PointEau.DoesNotExist:
            error_count += 1
            yield {**base_event, 'status': 'error', 'message': "Point d'eau introuvable ou non autorisé"}
        except (TypeError, ValueError) as exc:
            error_count += 1
            yield {**base_event, 'status': 'error', 'message': str(exc)}
        except Exception as exc:
            error_count += 1
            yield {**base_event, 'status': 'error', 'message': f'Erreur : {exc}'}

    yield {
        'event': 'complete',
        'total': len(rows),
        'updated': updated_count,
        'verified': verified_count,
        'unchanged': unchanged_count,
        'errors': error_count,
    }


@employe_required
def import_excel_update_points_eau_gps(request):
    """Import GPS des points d'eau avec progression et vérification en base."""
    if request.method != 'POST' or not request.FILES.get('excel_file'):
        return redirect('organization:ouvrage_list')

    try:
        wb = load_workbook(request.FILES['excel_file'], read_only=True, data_only=True)
        ws = wb.active
        allowed_points_eau = filter_queryset_by_permissions(PointEau.objects.all(), request.user)
        events = _iter_point_eau_gps_import(ws, allowed_points_eau)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            def stream_events():
                try:
                    for event in events:
                        yield json.dumps(event, ensure_ascii=False) + '\n'
                finally:
                    wb.close()

            response = StreamingHttpResponse(
                stream_events(),
                content_type='application/x-ndjson; charset=utf-8',
            )
            response['Cache-Control'] = 'no-cache, no-transform'
            response['X-Accel-Buffering'] = 'no'
            return response

        results = list(events)
        wb.close()
        summary = results[-1]
        if summary['verified']:
            messages.success(
                request,
                f"{summary['verified']} point(s) d'eau vérifié(s) en base, "
                f"dont {summary['updated']} réellement modifié(s).",
            )
        if summary['errors']:
            messages.warning(request, f"{summary['errors']} ligne(s) en erreur.")
    except Exception as exc:
        messages.error(request, f"Erreur lors de l'import : {exc}")

    return redirect('organization:ouvrage_list')


def download_excel_template(request, model_name):
    """Téléchargement des templates Excel pour les organisations"""
    templates = {
        'organisations': {
            'fields': ['nom_organisation', 'telephone', 'mail', 'adresse1', 'adresse2', 'code_postal', 'localite', 'province', 'nif', 'stat', 'numero_cnaps', 'tarif_carte_sociale', 'tarif_demande', 'tarif_minimum_bp', 'salaire_minimum', 'deduction_irsa'],
            'examples': [
                ['JIRAMA', '020 22 123 45', 'contact@jirama.mg', 'BP 230', '', '101', 'Antananarivo', 'Analamanga', '1234567890', '0987654321', 'CNAPS123', '5000', '1000', '2500', '180000', '8000'],
                ['WASH', '020 22 678 90', 'info@wash.mg', 'Rue de la République', 'Lot II', '301', 'Fianarantsoa', 'Haute Matsiatra', '2345678901', '1098765432', 'CNAPS456', '4500', '800', '2000', '160000', '7500']
            ]
        },
        'bases': {
            'fields': ['nom_base', 'organisation', 'ouvrage', 'volet', 'base_diamex'],
            'examples': [
                ['Base Nord', 'JIRAMA', 'Forage Analakely', 'Production', 'BASE001'],
                ['Base Sud', 'WASH', 'Puits Central', 'Distribution', 'BASE002']
            ]
        },
        'magasins': {
            'fields': ['nom_magasin', 'base'],
            'examples': [
                ['Magasin Principal', 'Base Nord'],
                ['Magasin Secondaire', 'Base Sud']
            ]
        },
        'journaux': {
            'fields': ['nom_journal', 'base', 'compte', 'code'],
            'examples': [
                ['Journal Caisse', 'Base Nord', '570000', 'JCA'],
                ['Journal Banque', 'Base Sud', '512000', 'JBQ']
            ]
        },
        'comptes': {
            'fields': ['nom_compte', 'organisation', 'compte', 'detail', 'financement', 'a_recouper_hydria_diamex', 'achat'],
            'examples': [
                ['Caisse', 'JIRAMA', '570000', 'Compte de caisse principal', 'RL Activités', 'Non', 'Non'],
                ['Banque BNI', 'JIRAMA', '512000', 'Compte bancaire BNI', 'FAN', 'Oui', 'Non'],
                ['Achats fournitures', 'WASH', '601000', 'Compte d\'achat fournitures', 'MEB', 'Non', 'Oui']
            ]
        },
        'postes': {
            'fields': ['nom_poste', 'organisation', 'tarif_indemnite', 'prefixe', 'compte_salaire_nom', 'compte_irsa_nom', 'compte_cnaps_nom'],
            'examples': [
                ['Directeur', 'JIRAMA', '500000', 'DIR', 'Salaires personnel', 'IRSA', 'CNAPS'],
                ['Technicien', 'JIRAMA', '250000', 'TECH', 'Salaires personnel', 'IRSA', 'CNAPS'],
                ['Agent', 'WASH', '180000', 'AGT', 'Salaires personnel', 'IRSA', 'CNAPS']
            ]
        },
        'equipements': {
            'fields': [
                'nom', 'type_equipement', 'code_equipement', 'statut', 'ouvrage_nom',
                'nombre_nettoyages_annuels', 'temps_acces_heures', 'point_depart', 'longueur_perimetre',
                'haie_vive_cultivable', 'boite_a_vanne', 'boite_a_vanne_utile', 'vanne_flotteur',
                'duree_nettoyage', 'distance_materiaux_locaux'
            ],
            'examples': [
                ['Pompe principale', 'pompe', 'PMP001', 'actif', 'Forage Analakely',
                 '4', '2.5', 'Village Centre', '150', 'Oui', 'Oui', 'Oui', 'Non', '3.0', 'proche'],
                ['Vanne de contrôle', 'vanne', 'VAN001', 'actif', 'Puits Central',
                 '2', '1.0', 'Route Nationale', '80', 'Non', 'Non', 'Non', 'Oui', '1.5', 'moyen']
            ]
        },
        'compteurtetes': {
            'fields': ['numerocompteur', 'marque', 'modele', 'statut', 'ouvrage_nom'],
            'examples': [
                ['CTR001', 'Sensus', 'WP-Dynamic', 'actif', 'Forage Analakely'],
                ['CTR002', 'Itron', 'Aquadis+', 'actif', 'Puits Central']
            ]
        },
        'tarifs': {
            'fields': ['ouvrage_nom', 'type_point_eau', 'datedebuttarif', 'datefintarif', 'prixabonnement', 'volume_minimum_facture'],
            'examples': [
                ['2024-01-01', '2024-12-31', '5000', 'Forage Analakely'],
                ['2024-01-01', '', '4500', 'Puits Central']
            ]
        },
        'modalitegestion': {
            'fields': ['ouvrage_nom', 'type_gestion', 'gestionnaire_nom', 'employe_surnom', 'date_debut', 'date_fin', 'modalitepaiement'],
            'examples': [
                ['Forage Analakely', 'communautaire', 'Commune Analakely', 'Rakoto', '2024-01-01', '2024-12-31', 'especes'],
                ['Puits Central', 'deleguee', 'JIRAMA', 'Rasoa', '2024-01-01', '', 'virement']
            ]
        },
        'fournisseurs': {
            'fields': ['idxls', 'nom_fournisseur', 'type_fournisseur', 'telephone', 'email',
                      'nif_ou_isi', 'cin', 'date_cin', 'lieu_cin', 'code_postal', 'adresse', 'numero_nif', 'numero_stat',
                      'autre_information', 'tacheron', 'devis'],
            'examples': [
                ['1', 'Entreprise ABC', 'Equipement', '020 22 123 45', 'contact@abc.mg', 'NIF', '123456789012', '2020-01-15', 'Antananarivo', '101', 'Lot II Analakely', '1234567890', '12345678901234567', 'Fournisseur principal', 'oui', 'non'],
                ['2', 'Soci?t? XYZ', 'Maintenance', '020 22 678 90', 'info@xyz.mg', 'ISI', '987654321098', '2019-05-20', 'Fianarantsoa', '102', 'Ambohitrarahaba', '0987654321', '76543210987654321', '', 'non', 'oui']
            ]
        },
        'adresses': {
            'fields': ['nomadresse', 'type_adresse', 'adresse_complete', 'latitude', 'longitude', 'ouvrage_nom'],
            'examples': [
                ['Bureau principal', 'bureau', 'Lot II Analakely Antananarivo', '-18.8792', '47.5079', 'Forage Analakely'],
                ['Site technique', 'technique', 'Village Ambohimanga', '-18.7669', '47.5692', 'Puits Central']
            ]
        },
        'tarifs_tranches': {
            'fields': ['tarifvolumetrique_id', 'tranchesuperieur', 'tarif'],
            'examples': [
                ['<ID du tarif>', '5', '800'],
                ['<ID du tarif>', '10', '1000'],
                ['<ID du tarif>', '20', '1200']
            ]
        },
        'ouvrages': {
            'fields': ['idxlsx', 'nom_ouvrage', 'type_ouvrage', 'annee_realisation', 'annee_realisation_avant', 'intervenant', 'saisonnier', 'observation'],
            'examples': [
                ['1', 'Forage Analakely', 'AEPG', 'JIRAMA', '2023', '2020', 'Entreprise ABC', 'Non', 'Bon état'],
                ['2', 'Puits Central', 'PPMH', 'WASH', '2024', '', 'Société XYZ', 'Oui', 'Nécessite entretien']
            ]
        },
        'pointseaus': {
            'fields': ['code_point_eau', 'nomabonne', 'numeroteleph', 'contactabonne', 'ouvrage', 'type_point_eau', 'parcelle_id', 'typeabonne', 'institutionnel', 'datebranchement', 'datearretbranchement', 'tarifforfaitaire', 'compteur_tete', 'numerodiamexdemande', 'numerodiamexdevis', 'basediamexdemande', 'basediamexdevis', 'datepaiementdemande', 'datepaiementdevis', 'montantdemandepaye', 'montantdevispaye', 'nombre_consommateurs', 'nombre_menages_consommateurs', 'idxls', 'latitude', 'longitude'],
            'examples': [
                ['PE001', 'RAKOTO Jean', '032 12 345 67', 'jean.rakoto@email.com', 'Forage Analakely', 'Branchement particulier', '<ID Parcelle>', 'particulier', 'Non', '15/01/2024', '', '5000', 'CTR001', '15', '20', '1', '1', '10/01/2024', '12/01/2024', '50000', '75000', '5', '1', 'PE001', '-18.8792', '47.5079'],
                ['PE002', 'RASOANIRINA Marie', '033 23 456 78', '', 'Puits Central', 'Borne fontaine', '', 'institution', 'Oui', '20/02/2024', '', '', 'CTR002', '', '', '', '', '', '', '', '', '50', '10', 'PE002', '-18.7669', '47.5692']
            ]
        },
        'cartes_sociales': {
            'fields': ['numero_carte', 'nom_beneficiaire', 'point_eau_id', 'nombre_habitants', 'observations'],
            'examples': [
                ['CS001', 'RAKOTO Jean', '<ID Point Eau>', '5', 'Carte sociale familiale'],
                ['CS002', 'RASOANIRINA Marie', '<ID Point Eau>', '7', 'Famille nombreuse']
            ]
        }
    }

    if model_name not in templates:
        return JsonResponse({'error': 'Template non trouvé'}, status=404)

    template = templates[model_name]

    # Créer un workbook Excel
    wb = Workbook()
    ws = wb.active
    ws.title = f'Template {model_name.title()}'

    # Styliser les en-têtes
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="28A745", end_color="28A745", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")

    # Créer les en-têtes lisibles
    headers = []
    for field in template['fields']:
        headers.append(field.replace('_', ' ').title())

    # Ajouter les en-têtes
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    # Ajouter les exemples
    for row_num, example in enumerate(template['examples'], 2):
        for col_num, value in enumerate(example, 1):
            ws.cell(row=row_num, column=col_num, value=value)

    # Auto-ajuster la largeur des colonnes
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)  # Largeur max de 50
        ws.column_dimensions[column_letter].width = adjusted_width

    # Préparer la réponse HTTP
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="template_{model_name}.xlsx"'

    # Sauvegarder le workbook dans la réponse
    wb.save(response)
    return response


def import_excel_view(request, model_name):
    """Vue générique pour l'import Excel des organisations"""
    models = {
        'organisations': Organisation,
        'types_ouvrages': TypeOuvrage,
        'ouvrages': Ouvrage,
        'pointseaus': PointEau,
        'bases': Base,
        'magasins': Magasin,
        'journaux': Journal,
        'comptes': Compte,
        'postes': Poste,
        'equipements': EquipementConstitutif,
        'compteurtetes': CompteurTete,
        'tarifs': TarifVolumetrique,
        'modalitegestion': ModaliteGestion,
        'fournisseurs': Fournisseur,
        'adresses': Adresse,
        'cartes_sociales': CarteSociale,
        'tarifs_tranches': TarifVolumetriqueTranche
    }

    if model_name not in models:
        messages.error(request, f'Type de données non reconnu: {model_name}')
        return redirect('organization:list')

    model_class = models[model_name]

    if request.method == 'POST':
        if 'excel_file' not in request.FILES:
            messages.error(request, 'Aucun fichier sélectionné.')
            return redirect(request.META.get('HTTP_REFERER', 'organization:list'))

        excel_file = request.FILES['excel_file']

        if not (excel_file.name.endswith('.xlsx') or excel_file.name.endswith('.xls')):
            messages.error(request, 'Le fichier doit être un fichier Excel (.xlsx ou .xls).')
            return redirect(request.META.get('HTTP_REFERER', 'organization:list'))

        try:
            # Lire le fichier Excel
            wb = load_workbook(excel_file)
            ws = wb.active

            # Lire les en-têtes (première ligne)
            headers = []
            for cell in ws[1]:
                headers.append(cell.value.lower().replace(' ', '_') if cell.value else '')

            created_count = 0
            error_count = 0
            error_messages = []  # Liste pour stocker les messages d'erreur détaillés

            # Traiter chaque ligne à partir de la ligne 2
            for row_num in range(2, ws.max_row + 1):
                try:
                    # Créer un dictionnaire avec les données de la ligne
                    row_data = {}
                    for col_num, header in enumerate(headers, 1):
                        cell_value = ws.cell(row=row_num, column=col_num).value
                        row_data[header] = str(cell_value).strip() if cell_value is not None else ''

                    # Traiter selon le type de modèle (même logique que CSV)
                    if model_name == 'organisations':
                        Organisation.objects.get_or_create(
                            nom_organisation=row_data.get('nom_organisation', '').strip(),
                            defaults={
                                'telephone': row_data.get('telephone', '').strip(),
                                'mail': row_data.get('mail', '').strip(),
                                'adresse1': row_data.get('adresse1', '').strip(),
                                'adresse2': row_data.get('adresse2', '').strip(),
                                'code_postal': row_data.get('code_postal', '').strip(),
                                'localite': row_data.get('localite', '').strip(),
                                'province': row_data.get('province', '').strip(),
                                'nif': row_data.get('nif', '').strip(),
                                'stat': row_data.get('stat', '').strip(),
                                'numero_cnaps': row_data.get('numero_cnaps', '').strip(),
                                'tarif_carte_sociale': float(row_data.get('tarif_carte_sociale', 0)) if row_data.get('tarif_carte_sociale', '').strip() else None,
                                'tarif_demande': float(row_data.get('tarif_demande', 0)) if row_data.get('tarif_demande', '').strip() else None,
                                'tarif_minimum_bp': float(row_data.get('tarif_minimum_bp', 0)) if row_data.get('tarif_minimum_bp', '').strip() else None,
                                'salaire_minimum': float(row_data.get('salaire_minimum', 0)) if row_data.get('salaire_minimum', '').strip() else None,
                                'deduction_irsa': float(row_data.get('deduction_irsa', 0)) if row_data.get('deduction_irsa', '').strip() else None,
                            }
                        )
                    elif model_name == 'bases':
                        organisation = Organisation.objects.get(nom_organisation=row_data.get('organisation', '').strip())
                        ouvrage_nom = (
                            row_data.get('ouvrage', '') or
                            row_data.get('ouvrage_nom', '') or
                            row_data.get('ouvrage_-_nom_ouvrage', '')
                        ).strip()
                        ouvrage = Ouvrage.objects.get(nom_ouvrage=ouvrage_nom) if ouvrage_nom else None
                        Base.objects.get_or_create(
                            nom_base=row_data.get('nom_base', '').strip(),
                            defaults={
                                'organisation': organisation,
                                'ouvrage': ouvrage,
                                'volet': row_data.get('volet', '').strip(),
                                'base_diamex': row_data.get('base_diamex', '').strip()
                            }
                        )
                    elif model_name == 'magasins':
                        base = Base.objects.get(nom_base=row_data.get('base', '').strip())
                        Magasin.objects.get_or_create(
                            nom_magasin=row_data.get('nom_magasin', '').strip(),
                            defaults={'base': base}
                        )
                    elif model_name == 'journaux':
                        base = Base.objects.get(nom_base=row_data.get('base', '').strip())
                        Journal.objects.get_or_create(
                            nom_journal=row_data.get('nom_journal', '').strip(),
                            defaults={
                                'base': base,
                                'compte': row_data.get('compte', '').strip(),
                                'code': row_data.get('code', '').strip()
                            }
                        )
                    elif model_name == 'comptes':
                        organisation = Organisation.objects.get(nom_organisation=row_data.get('organisation', '').strip())
                        Compte.objects.get_or_create(
                            nom_compte=row_data.get('nom_compte', '').strip(),
                            defaults={
                                'organisation': organisation,
                                'compte': row_data.get('compte', '').strip(),
                                'detail': row_data.get('detail', '').strip(),
                                'financement': row_data.get('financement', '').strip(),
                                'a_recouper_hydria_diamex': row_data.get('a_recouper_hydria_diamex', '').lower() in ['true', '1', 'oui', 'yes'],
                                'achat': row_data.get('achat', '').lower() in ['true', '1', 'oui', 'yes']
                            }
                        )
                    elif model_name == 'postes':
                        organisation = Organisation.objects.get(nom_organisation=row_data.get('organisation', '').strip())

                        # Récupérer les comptes associés si spécifiés
                        compte_salaire = None
                        compte_irsa = None
                        compte_cnaps = None

                        if row_data.get('compte_salaire_nom', '').strip():
                            compte_salaire = Compte.objects.filter(
                                nom_compte=row_data.get('compte_salaire_nom', '').strip(),
                                organisation=organisation
                            ).first()

                        if row_data.get('compte_irsa_nom', '').strip():
                            compte_irsa = Compte.objects.filter(
                                nom_compte=row_data.get('compte_irsa_nom', '').strip(),
                                organisation=organisation
                            ).first()

                        if row_data.get('compte_cnaps_nom', '').strip():
                            compte_cnaps = Compte.objects.filter(
                                nom_compte=row_data.get('compte_cnaps_nom', '').strip(),
                                organisation=organisation
                            ).first()

                        Poste.objects.get_or_create(
                            nom_poste=row_data.get('nom_poste', '').strip(),
                            organisation=organisation,
                            defaults={
                                'tarif_indemnite': float(row_data.get('tarif_indemnite', 0)) if row_data.get('tarif_indemnite', '').strip() else None,
                                'prefixe': row_data.get('prefixe', '').strip(),
                                'compte_salaire': compte_salaire,
                                'compte_irsa': compte_irsa,
                                'compte_cnaps_fmfp_sante': compte_cnaps
                            }
                        )
                    elif model_name == 'ouvrages':
                        # Récupérer le type d'ouvrage depuis la table organization.TypeOuvrage
                        type_ouvrage_nom = row_data.get('type_ouvrage', '').strip()
                        type_ouvrage = TypeOuvrage.objects.get(nom_type_ouvrage=type_ouvrage_nom) if type_ouvrage_nom else None

                        # Saisonnier (accepter Oui/Non, Yes/No, True/False, 1/0)
                        saisonnier_val = row_data.get('saisonnier', '').lower()
                        saisonnier = saisonnier_val in ['true', '1', 'oui', 'yes']

                        # idxlsx
                        idxlsx_val = row_data.get('idxlsx', '').strip()
                        idxlsx = int(idxlsx_val) if idxlsx_val and idxlsx_val != 'None' else None

                        # Années de réalisation
                        annee_real = row_data.get('annee_realisation', '').strip()
                        annee_realisation = int(annee_real) if annee_real and annee_real != 'None' else None

                        annee_real_avant = row_data.get('annee_realisation_avant', '').strip()
                        annee_realisation_avant = int(annee_real_avant) if annee_real_avant and annee_real_avant != 'None' else None

                        Ouvrage.objects.get_or_create(
                            nom_ouvrage=row_data.get('nom_ouvrage', '').strip(),
                            defaults={
                                'idxlsx': idxlsx,
                                'type_ouvrage': type_ouvrage,
                                'annee_realisation': annee_realisation,
                                'annee_realisation_avant': annee_realisation_avant,
                                'intervenant': row_data.get('intervenant', '').strip(),
                                'saisonnier': saisonnier,
                                'observation': row_data.get('observation', '').strip()
                            }
                        )
                    elif model_name == 'pointseaus':
                        from apps.geography.models import Parcelle
                        from datetime import datetime

                        # Récupérer les données de base
                        nomabonne = row_data.get('nomabonne', '').strip()
                        code_point_eau = row_data.get('code_point_eau', '').strip() or None

                        # Récupérer l'ouvrage avec gestion d'erreur
                        ouvrage_nom = row_data.get('ouvrage', '').strip()
                        ouvrage = None
                        if ouvrage_nom:
                            try:
                                ouvrage = Ouvrage.objects.get(nom_ouvrage=ouvrage_nom)
                            except Ouvrage.DoesNotExist:
                                errors.append(f"Ligne {idx + 2}: Ouvrage '{ouvrage_nom}' non trouvé")

                        # Récupérer le type de point d'eau
                        type_point_eau_nom = row_data.get('type_point_eau', '').strip()
                        type_point_eau = TypePointEau.objects.filter(nom_type__icontains=type_point_eau_nom).first() if type_point_eau_nom else None

                        # Récupérer la parcelle avec gestion d'erreur
                        parcelle_id_str = row_data.get('parcelle_id', '').strip()
                        parcelle = None
                        if parcelle_id_str and parcelle_id_str != '<ID Parcelle>':
                            try:
                                parcelle = Parcelle.objects.get(pk=parcelle_id_str)
                            except Parcelle.DoesNotExist:
                                errors.append(f"Ligne {idx + 2}: Parcelle ID '{parcelle_id_str}' non trouvée")

                        # Récupérer le compteur tête
                        compteur_tete_num = row_data.get('compteur_tete', '').strip()
                        compteur_tete = CompteurTete.objects.filter(numerocompteur=compteur_tete_num).first() if compteur_tete_num else None

                        # Institutionnel (Oui/Non)
                        institutionnel_val = row_data.get('institutionnel', '').lower()
                        estbranchementinstitutionnel = institutionnel_val in ['oui', 'yes', 'true', '1']

                        # Fonction helper pour parser les dates
                        def parse_date(date_str):
                            if not date_str:
                                return None
                            try:
                                # Essayer format dd/mm/yyyy
                                return datetime.strptime(date_str, '%d/%m/%Y')
                            except:
                                try:
                                    # Essayer format ISO (yyyy-mm-dd)
                                    return datetime.fromisoformat(date_str)
                                except:
                                    return None

                        # Traiter les dates
                        datebranchement = parse_date(row_data.get('datebranchement', '').strip())
                        datearretbranchement = parse_date(row_data.get('datearretbranchement', '').strip())
                        datepaiementdemande = parse_date(row_data.get('datepaiementdemande', '').strip())
                        datepaiementdevis = parse_date(row_data.get('datepaiementdevis', '').strip())

                        # Traiter les montants avec gestion d'erreurs
                        try:
                            tarif_str = row_data.get('tarifforfaitaire', '').strip()
                            tarifforfaitaire = float(tarif_str) if tarif_str and tarif_str != 'None' else None
                        except ValueError:
                            tarifforfaitaire = None

                        try:
                            # Supporter les deux formats : "montantdemandepaye" et "montant_demande_paye"
                            montant_demande_str = row_data.get('montantdemandepaye', '') or row_data.get('montant_demande_paye', '')
                            montant_demande_str = montant_demande_str.strip() if montant_demande_str else ''
                            montantdemandepaye = float(montant_demande_str) if montant_demande_str and montant_demande_str != 'None' else None
                        except ValueError:
                            montantdemandepaye = None

                        try:
                            # Supporter les deux formats : "montantdevispaye" et "montant_devis_paye"
                            montant_devis_str = row_data.get('montantdevispaye', '') or row_data.get('montant_devis_paye', '')
                            montant_devis_str = montant_devis_str.strip() if montant_devis_str else ''
                            montantdevispaye = float(montant_devis_str) if montant_devis_str and montant_devis_str != 'None' else None
                        except ValueError:
                            montantdevispaye = None

                        # Traiter les numéros DiameX avec gestion d'erreurs
                        try:
                            numdemande_str = row_data.get('numerodiamexdemande', '').strip()
                            numerodiamexdemande = int(numdemande_str) if numdemande_str and numdemande_str != 'None' else None
                        except ValueError:
                            numerodiamexdemande = None

                        try:
                            numdevis_str = row_data.get('numerodiamexdevis', '').strip()
                            numerodiamexdevis = int(numdevis_str) if numdevis_str and numdevis_str != 'None' else None
                        except ValueError:
                            numerodiamexdevis = None

                        # Traiter les bases DiameX (chaînes de caractères)
                        basediamexdemande = row_data.get('basediamexdemande', '').strip() or None
                        basediamexdevis = row_data.get('basediamexdevis', '').strip() or None

                        # Traiter les nombres avec gestion d'erreurs
                        try:
                            nb_conso_str = row_data.get('nombre_consommateurs', '').strip()
                            nombre_consommateurs = int(nb_conso_str) if nb_conso_str and nb_conso_str != 'None' else None
                        except ValueError:
                            nombre_consommateurs = None

                        try:
                            nb_menages_str = row_data.get('nombre_menages_consommateurs', '').strip()
                            nombre_menages_consommateurs = int(nb_menages_str) if nb_menages_str and nb_menages_str != 'None' else None
                        except ValueError:
                            nombre_menages_consommateurs = None

                        # Traiter latitude et longitude avec gestion d'erreurs
                        try:
                            lat_str = row_data.get('latitude', '').strip()
                            latitude = float(lat_str) if lat_str and lat_str != 'None' else None
                        except ValueError:
                            latitude = None

                        try:
                            lon_str = row_data.get('longitude', '').strip()
                            longitude = float(lon_str) if lon_str and lon_str != 'None' else None
                        except ValueError:
                            longitude = None

                        # ✅ VALIDATION : Vérifier qu'il y a AU MOINS UN attribut significatif
                        # Un point d'eau doit avoir soit un nom, soit un ouvrage, soit une parcelle, soit des coordonnées GPS
                        has_significant_data = any([
                            nomabonne,
                            code_point_eau,
                            ouvrage is not None,
                            parcelle is not None,
                            type_point_eau is not None,
                            (latitude is not None and longitude is not None),
                            compteur_tete is not None,
                            tarifforfaitaire is not None,
                            nombre_consommateurs is not None
                        ])

                        if not has_significant_data:
                            errors.append(f"Ligne {idx + 2}: Point d'eau vide (aucun attribut significatif) - ligne ignorée")
                            continue

                        # ✅ Préparer les données pour création/mise à jour
                        defaults_data = {
                            'nomabonne': nomabonne or '',  # Utiliser chaîne vide si None
                            'numeroteleph': row_data.get('numeroteleph', '').strip(),
                            'contactabonne': row_data.get('contactabonne', '').strip(),
                            'ouvrage': ouvrage,
                            'type_point_eau': type_point_eau,
                            'parcelle': parcelle,
                            'compteur_tete': compteur_tete,
                            'typeabonne': row_data.get('typeabonne', '').strip(),
                            'estbranchementinstitutionnel': estbranchementinstitutionnel,
                            'datebranchement': datebranchement,
                            'datearretbranchement': datearretbranchement,
                            'tarifforfaitaire': tarifforfaitaire,
                            'numerodiamexdemande': numerodiamexdemande,
                            'numerodiamexdevis': numerodiamexdevis,
                            'basediamexdemande': basediamexdemande,
                            'basediamexdevis': basediamexdevis,
                            'datepaiementdemande': datepaiementdemande,
                            'datepaiementdevis': datepaiementdevis,
                            'montantdemandepaye': montantdemandepaye,
                            'montantdevispaye': montantdevispaye,
                            'nombre_consommateurs': nombre_consommateurs,
                            'nombre_menages_consommateurs': nombre_menages_consommateurs,
                            'idxls': row_data.get('idxls', '').strip(),
                            'latitude': latitude,
                            'longitude': longitude
                        }

                        # ✅ Utiliser get_or_create si code_point_eau existe pour éviter doublons
                        if code_point_eau:
                            point_eau, created = PointEau.objects.get_or_create(
                                code_point_eau=code_point_eau,
                                defaults=defaults_data
                            )
                            if not created:
                                # Mettre à jour si existe déjà
                                for key, value in defaults_data.items():
                                    setattr(point_eau, key, value)
                                point_eau.save()
                        else:
                            # ✅ Pas de code unique : créer directement
                            defaults_data['code_point_eau'] = None
                            PointEau.objects.create(**defaults_data)
                    elif model_name == 'cartes_sociales':
                        # Récupérer le point d'eau depuis l'ID
                        point_eau_id = row_data.get('point_eau_id', '').strip()
                        point_eau = None
                        ouvrage = None

                        if point_eau_id:
                            try:
                                point_eau = PointEau.objects.select_related('ouvrage').get(pk=point_eau_id)
                                # Déduire l'ouvrage depuis le point d'eau (organization.Ouvrage)
                                if point_eau.ouvrage:
                                    ouvrage = point_eau.ouvrage
                            except PointEau.DoesNotExist:
                                pass

                        # Si pas d'ouvrage via point d'eau, chercher dans les colonnes ouvrage
                        if not ouvrage:
                            # Essayer plusieurs variantes de noms de colonnes
                            ouvrage_nom = (
                                row_data.get('ouvrage__nom_ouvrage', '') or
                                row_data.get('ouvrage_-_nom_ouvrage', '') or
                                row_data.get('ouvrage', '') or
                                row_data.get('nom_ouvrage', '')
                            ).strip()
                            if ouvrage_nom:
                                try:
                                    ouvrage = Ouvrage.objects.get(nom_ouvrage=ouvrage_nom)
                                except Ouvrage.DoesNotExist:
                                    # Essayer une recherche insensible à la casse
                                    ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()

                        # Si toujours pas d'ouvrage, ignorer cette ligne avec un warning
                        if not ouvrage:
                            messages.warning(request, f"Ligne ignorée : carte {row_data.get('numero_carte', '?')} - aucun ouvrage trouvé")
                            continue

                        # Récupérer nombre_habitants
                        nombre_habitants = row_data.get('nombre_habitants', '').strip()
                        nombre_habitants = int(nombre_habitants) if nombre_habitants and nombre_habitants.isdigit() else None

                        # Récupérer le numéro de carte (peut être vide/null)
                        numero_carte = row_data.get('numero_carte', '').strip()
                        numero_carte = numero_carte if numero_carte else None

                        # Créer directement (pas get_or_create car doublons autorisés)
                        CarteSociale.objects.create(
                            numero_carte=numero_carte,
                            nom_beneficiaire=row_data.get('nom_beneficiaire', '').strip(),
                            ouvrage=ouvrage,
                            point_eau=point_eau,
                            nombre_habitants=nombre_habitants,
                            statut='active',
                            observations=row_data.get('observations', '').strip()
                        )
                    elif model_name == 'equipements':
                        from apps.infrastructure.models import TypeEquipement
                        from apps.organization.models import Ouvrage as OrgOuvrage

                        # Récupérer l'ouvrage depuis organization.Ouvrage (la vraie table avec 1233 ouvrages)
                        ouvrage_nom = row_data.get('ouvrage_nom', '').strip()
                        ouvrage = None
                        if ouvrage_nom:
                            # Recherche exacte d'abord
                            ouvrage = OrgOuvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()

                            # Si pas trouvé, recherche approximative
                            if not ouvrage:
                                ouvrage = OrgOuvrage.objects.filter(nom_ouvrage__icontains=ouvrage_nom).first()

                        # Si toujours pas d'ouvrage, lever une erreur explicite
                        if not ouvrage:
                            raise ValueError(f"Impossible de trouver l'ouvrage '{ouvrage_nom}' dans la table ouvrages")

                        # Récupérer le type d'équipement
                        type_equipement_nom = row_data.get('type_equipement', '').strip()
                        type_equipement = TypeEquipement.objects.filter(nom_type__iexact=type_equipement_nom).first() if type_equipement_nom else None

                        # Si le type n'existe pas, le créer
                        if not type_equipement and type_equipement_nom:
                            type_equipement = TypeEquipement.objects.create(nom_type=type_equipement_nom)

                        # Traiter les champs numériques
                        nombre_nettoyages = row_data.get('nombre_nettoyages_annuels', '').strip()
                        nombre_nettoyages_annuels = int(nombre_nettoyages) if nombre_nettoyages and nombre_nettoyages not in ['None', ''] else None

                        temps_acces = row_data.get('temps_acces_heures', '').strip()
                        temps_acces_heures = float(temps_acces) if temps_acces and temps_acces not in ['None', ''] else None

                        longueur = row_data.get('longueur_perimetre', '').strip()
                        longueur_perimetre = int(longueur) if longueur and longueur not in ['None', ''] else None

                        duree = row_data.get('duree_nettoyage', '').strip()
                        duree_nettoyage = float(duree) if duree and duree not in ['None', ''] else None

                        # Traiter les champs booléens (accepter Oui/Non, Yes/No, True/False, 1/0)
                        haie_val = str(row_data.get('haie_vive_cultivable', '')).lower().strip()
                        haie_vive_cultivable = haie_val in ['oui', 'yes', 'true', '1']

                        boite_val = str(row_data.get('boite_a_vanne', '')).lower().strip()
                        boite_a_vanne = boite_val in ['oui', 'yes', 'true', '1']

                        boite_utile_val = str(row_data.get('boite_a_vanne_utile', '')).lower().strip()
                        boite_a_vanne_utile = boite_utile_val in ['oui', 'yes', 'true', '1']

                        vanne_val = str(row_data.get('vanne_flotteur', '')).lower().strip()
                        vanne_flotteur = vanne_val in ['oui', 'yes', 'true', '1']

                        # Traiter code_equipement (None si vide pour éviter les doublons)
                        code_equipement_val = row_data.get('code_equipement', '').strip()
                        code_equipement = code_equipement_val if code_equipement_val else None

                        # Créer ou mettre à jour l'équipement
                        EquipementConstitutif.objects.update_or_create(
                            nom=row_data.get('nom', '').strip(),
                            ouvrage=ouvrage,
                            defaults={
                                'type_equipement': type_equipement,
                                'code_equipement': code_equipement,
                                'statut': row_data.get('statut', 'operationnel').strip() or 'operationnel',
                                'nombre_nettoyages_annuels': nombre_nettoyages_annuels,
                                'temps_acces_heures': temps_acces_heures,
                                'point_depart': row_data.get('point_depart', '').strip(),
                                'longueur_perimetre': longueur_perimetre,
                                'haie_vive_cultivable': haie_vive_cultivable,
                                'boite_a_vanne': boite_a_vanne,
                                'boite_a_vanne_utile': boite_a_vanne_utile,
                                'vanne_flotteur': vanne_flotteur,
                                'duree_nettoyage': duree_nettoyage,
                                'distance_materiaux_locaux': row_data.get('distance_materiaux_locaux', '').strip() or None,
                            }
                        )
                    elif model_name == 'compteurtetes':
                        # Debug : afficher tous les headers disponibles (première ligne seulement)
                        if row_num == 2:
                            print(f"Headers disponibles: {list(row_data.keys())}")
                            print(f"Valeurs ligne 2: {row_data}")

                        # Récupérer l'ouvrage depuis organization.Ouvrage
                        # Essayer plusieurs noms de colonnes possibles
                        ouvrage_nom = (
                            row_data.get('ouvrage', '') or
                            row_data.get('ouvrage_-_nom', '') or
                            row_data.get('ouvrage_nom', '') or
                            ''
                        ).strip()

                        ouvrage = None
                        if ouvrage_nom:
                            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()

                        # Traiter la date d'installation
                        date_installation = None
                        date_installation_str = row_data.get('date_installation', '').strip()
                        if date_installation_str and date_installation_str != 'None':
                            try:
                                from datetime import datetime
                                date_installation = datetime.strptime(date_installation_str, '%Y-%m-%d').date()
                            except:
                                pass

                        # Traiter l'index initial
                        index_initial_str = row_data.get('index_initial', '').strip()
                        index_initial = float(index_initial_str) if index_initial_str and index_initial_str != 'None' else 0

                        # Récupérer ou créer le compteur
                        numerocompteur = row_data.get('numerocompteur', '').strip() or None

                        # Debug : afficher les informations
                        print(f"Ligne {row_num}: numerocompteur={numerocompteur}, ouvrage_nom='{ouvrage_nom}', ouvrage_trouvé={ouvrage is not None}")

                        if not numerocompteur:
                            raise ValueError(f"Numéro de compteur manquant")

                        if not ouvrage:
                            raise ValueError(f"Ouvrage '{ouvrage_nom}' introuvable pour le compteur {numerocompteur}")

                        compteur, created = CompteurTete.objects.get_or_create(
                            numerocompteur=numerocompteur,
                            ouvrage=ouvrage,
                            defaults={
                                'marque': row_data.get('marque', '').strip() or None,
                                'modele': row_data.get('modele', '').strip() or None,
                                'date_installation': date_installation,
                                'index_initial': index_initial,
                                'statut': row_data.get('statut', '').strip() or None
                            }
                        )
                        print(f"  -> Compteur {numerocompteur}: {'créé' if created else 'existant'}")
                    elif model_name == 'tarifs':
                        # Debug : afficher tous les headers disponibles (première ligne seulement)
                        if row_num == 2:
                            print(f"Headers disponibles pour tarifs: {list(row_data.keys())}")
                            print(f"Valeurs ligne 2: {row_data}")

                        # Récupérer l'ouvrage depuis organization.Ouvrage
                        # Essayer plusieurs noms de colonnes possibles
                        ouvrage_nom = (
                            row_data.get('ouvrage_-_nom_ouvrage', '') or
                            row_data.get('ouvrage', '') or
                            row_data.get('ouvrage_nom', '') or
                            row_data.get('nom_ouvrage', '') or
                            ''
                        ).strip()

                        ouvrage = None
                        if ouvrage_nom:
                            ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()

                        if not ouvrage:
                            raise ValueError(f"Ouvrage '{ouvrage_nom}' introuvable pour le tarif")

                        # Récupérer le type de point d'eau par son nom
                        type_point_eau_nom = row_data.get('type_point_eau', '').strip()
                        type_point_eau = None
                        if type_point_eau_nom and type_point_eau_nom.lower() not in ['none', '']:
                            type_point_eau = TypePointEau.objects.filter(nom_type__iexact=type_point_eau_nom).first()

                        # Traiter les dates
                        from datetime import datetime
                        datedebuttarif = None
                        datedebuttarif_str = row_data.get('datedebuttarif', '').strip()
                        if datedebuttarif_str and datedebuttarif_str != 'None':
                            try:
                                # Essayer format datetime complet d'abord
                                datedebuttarif = datetime.strptime(datedebuttarif_str, '%Y-%m-%d %H:%M:%S').date()
                            except:
                                try:
                                    # Puis format date simple
                                    datedebuttarif = datetime.strptime(datedebuttarif_str, '%Y-%m-%d').date()
                                except:
                                    pass

                        datefintarif = None
                        datefintarif_str = row_data.get('datefintarif', '').strip()
                        if datefintarif_str and datefintarif_str != 'None':
                            try:
                                # Essayer format datetime complet d'abord
                                datefintarif = datetime.strptime(datefintarif_str, '%Y-%m-%d %H:%M:%S').date()
                            except:
                                try:
                                    # Puis format date simple
                                    datefintarif = datetime.strptime(datefintarif_str, '%Y-%m-%d').date()
                                except:
                                    pass

                        # Traiter le prix d'abonnement et le volume minimal
                        prixabonnement_str = row_data.get('prixabonnement', '').strip()
                        prixabonnement = int(prixabonnement_str) if prixabonnement_str and prixabonnement_str != 'None' else 0

                        volume_minimum_facture_str = row_data.get('volume_minimum_facture', '').strip()
                        volume_minimum_facture = float(volume_minimum_facture_str) if volume_minimum_facture_str and volume_minimum_facture_str not in ['None', ''] else None

                        # Traiter le statut actif
                        actif_str = row_data.get('actif', '').strip().lower()
                        actif = actif_str in ['true', '1', 'oui', 'yes', 'vrai']

                        # Colonne optionnelle : tarif des branchements institutionnels (distinct du tarif ordinaire)
                        institutionnel_str = (row_data.get('institutionnel') or '').strip().lower()
                        institutionnel = institutionnel_str in ['true', '1', 'oui', 'yes', 'vrai']

                        # Créer ou mettre à jour le tarif
                        tarif, created = TarifVolumetrique.objects.get_or_create(
                            ouvrage=ouvrage,
                            type_point_eau=type_point_eau,
                            datedebuttarif=datedebuttarif or '2024-01-01',
                            institutionnel=institutionnel,
                            defaults={
                                'datefintarif': datefintarif,
                                'prixabonnement': prixabonnement,
                                'volume_minimum_facture': volume_minimum_facture,
                                'actif': actif
                            }
                        )
                        print(f"  -> Tarif pour {ouvrage_nom} ({type_point_eau_nom or 'tous types'}): {'créé' if created else 'existant'}")
                    elif model_name == 'modalitegestion':
                        from datetime import datetime
                        from apps.employees.models import Employe

                        # Récupérer l'ouvrage
                        ouvrage_nom = row_data.get('ouvrage_nom', '').strip()
                        if not ouvrage_nom:
                            raise ValueError("Le nom de l'ouvrage est obligatoire")

                        ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
                        if not ouvrage:
                            raise ValueError(f"Ouvrage '{ouvrage_nom}' introuvable")

                        # Récupérer le gestionnaire (organisation)
                        gestionnaire_nom = row_data.get('gestionnaire_nom', '').strip()
                        gestionnaire = None
                        if gestionnaire_nom:
                            gestionnaire = Organisation.objects.filter(nom_organisation__iexact=gestionnaire_nom).first()

                        # Récupérer l'employé
                        employe_surnom = row_data.get('employe_surnom', '').strip()
                        employe = None
                        if employe_surnom:
                            employe = Employe.objects.filter(surnom__iexact=employe_surnom).first()

                        # Traiter les dates
                        date_debut_str = row_data.get('date_debut', '').strip()
                        date_debut = None
                        if date_debut_str:
                            try:
                                date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d %H:%M:%S').date()
                            except:
                                try:
                                    date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                                except:
                                    pass

                        date_fin_str = row_data.get('date_fin', '').strip()
                        date_fin = None
                        if date_fin_str:
                            try:
                                date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d %H:%M:%S').date()
                            except:
                                try:
                                    date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                                except:
                                    pass

                        # Type de gestion - convertir le label en clé
                        type_gestion_str = row_data.get('type_gestion', '').strip().lower()
                        type_gestion_map = {
                            'privée': 'privee',
                            'privee': 'privee',
                            'comité eau': 'comite_eau',
                            'comite eau': 'comite_eau',
                            'comite_eau': 'comite_eau',
                            'pas de gestion': 'pas_de_gestion',
                            'pas_de_gestion': 'pas_de_gestion',
                        }
                        type_gestion = type_gestion_map.get(type_gestion_str, type_gestion_str)

                        # Modalité de paiement - convertir le label en clé
                        modalitepaiement_str = row_data.get('modalitepaiement', '').strip().lower()
                        modalitepaiement_map = {
                            'forfaitaire': 'forfaitaire',
                            'au volume': 'au_volume',
                            'au_volume': 'au_volume',
                            'cotisation annuelle': 'cotisation_annuelle',
                            'cotisation_annuelle': 'cotisation_annuelle',
                            'mixte': 'mixte',
                        }
                        modalitepaiement = modalitepaiement_map.get(modalitepaiement_str, modalitepaiement_str) if modalitepaiement_str else None

                        # Créer ou récupérer la modalité de gestion
                        ModaliteGestion.objects.create(
                            ouvrage=ouvrage,
                            type_gestion=type_gestion,
                            gestionnaire=gestionnaire,
                            employe=employe,
                            date_debut=date_debut,
                            date_fin=date_fin,
                            modalitepaiement=modalitepaiement
                        )
                        print(f"  -> Modalité de gestion pour {ouvrage_nom}: créée")
                    elif model_name == 'adresses':
                        from datetime import datetime

                        # Récupérer le nom de l'adresse (obligatoire)
                        nom_adresse = row_data.get('nomadresse', '').strip()
                        if not nom_adresse:
                            raise ValueError("Le nom de l'adresse est obligatoire")

                        # Récupérer l'ouvrage (obligatoire) - utiliser organization.Ouvrage
                        ouvrage_nom = row_data.get('ouvrage_nom', '').strip()
                        if not ouvrage_nom:
                            raise ValueError("Le nom de l'ouvrage est obligatoire")

                        # Chercher dans organization.Ouvrage
                        ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom).first()
                        if not ouvrage:
                            raise ValueError(f"Ouvrage '{ouvrage_nom}' introuvable")

                        # Champs optionnels
                        type_adresse = row_data.get('type_adresse', '').strip().lower() or 'principale'
                        adresse_complete = row_data.get('adresse_complete', '').strip() or None

                        latitude_str = row_data.get('latitude', '').strip()
                        latitude = float(latitude_str) if latitude_str and latitude_str != 'None' else None

                        longitude_str = row_data.get('longitude', '').strip()
                        longitude = float(longitude_str) if longitude_str and longitude_str != 'None' else None

                        # Créer l'adresse
                        Adresse.objects.create(
                            ouvrage=ouvrage,
                            nomadresse=nom_adresse,
                            type_adresse=type_adresse,
                            adresse_complete=adresse_complete,
                            latitude=latitude,
                            longitude=longitude
                        )
                        print(f"  -> Adresse '{nom_adresse}' pour {ouvrage_nom}: créée")
                    elif model_name == 'fournisseurs':
                        from datetime import datetime

                        # Récupérer le nom du fournisseur (obligatoire)
                        nom_fournisseur = row_data.get('nom_fournisseur', '').strip()
                        if not nom_fournisseur:
                            raise ValueError("Le nom du fournisseur est obligatoire")

                        # Champ IDxls (optionnel)
                        idxls_str = row_data.get('idxls', '').strip()
                        idxls = int(idxls_str) if idxls_str and idxls_str not in ['None', ''] else None

                        # Champs optionnels
                        type_fournisseur = row_data.get('type_fournisseur', '').strip() or None
                        telephone = row_data.get('telephone', '').strip() or None
                        email = row_data.get('email', '').strip() or None
                        adresse = row_data.get('adresse', '').strip() or None

                        # Champs CIN, date CIN et lieu CIN (optionnels)
                        cin = row_data.get('cin', '').strip() or None
                        date_cin_str = (
                            row_data.get('date_cin', '')
                            or row_data.get('datecin', '')
                            or row_data.get('date cin', '')
                            or row_data.get('date_delivrance_cin', '')
                        ).strip()
                        lieu_cin = (
                            row_data.get('lieu_cin', '')
                            or row_data.get('lieucin', '')
                            or row_data.get('lieu cin', '')
                            or row_data.get('lieu_delivrance_cin', '')
                        ).strip() or None
                        date_cin = None
                        if date_cin_str and date_cin_str not in ['None', '']:
                            try:
                                date_cin = datetime.strptime(date_cin_str, '%Y-%m-%d %H:%M:%S').date()
                            except:
                                try:
                                    date_cin = datetime.strptime(date_cin_str, '%Y-%m-%d').date()
                                except:
                                    try:
                                        date_cin = datetime.strptime(date_cin_str, '%d/%m/%Y').date()
                                    except:
                                        pass

                        # Champs NIF/ISI, numéros, code postal (optionnels)
                        nif_ou_isi = row_data.get('nifouisi', '').strip()
                        if nif_ou_isi and nif_ou_isi.upper() in ['ISI', 'NIF']:
                            nif_ou_isi = nif_ou_isi.upper()
                        else:
                            nif_ou_isi = ''  # Vide par défaut

                        numero_nif = row_data.get('numero_nif', '').strip() or None
                        numero_stat = row_data.get('numero_stat', '').strip() or None
                        code_postal = row_data.get('code_postal', '').strip() or None

                        # Champ autre information (optionnel)
                        autre_information = row_data.get('autre_information', '').strip() or None

                        # Champs booléens (tacheron et devis)
                        tacheron_str = row_data.get('tacheron', '').strip().lower()
                        tacheron = tacheron_str in ['true', '1', 'oui', 'yes', 'vrai']

                        devis_str = row_data.get('devis', '').strip().lower()
                        devis = devis_str in ['true', '1', 'oui', 'yes', 'vrai']

                        # Champ actif
                        actif_str = row_data.get('actif', '').strip().lower()
                        actif = actif_str not in ['false', '0', 'non', 'no', 'faux']  # Actif par défaut sauf si explicitement False

                        # Gestion de la relation avec Adresse (optionnelle)
                        adresse_relation = None
                        adresse_id_str = row_data.get('adresse_relation_id', '').strip()
                        if adresse_id_str and adresse_id_str not in ['None', '']:
                            try:
                                adresse_relation = Adresse.objects.get(pk=adresse_id_str)
                            except Adresse.DoesNotExist:
                                pass  # Ignorer si l'adresse n'existe pas

                        # Créer ou mettre à jour le fournisseur
                        fournisseur, created = Fournisseur.objects.get_or_create(
                            nom_fournisseur=nom_fournisseur,
                            defaults={
                                'idxls': idxls,
                                'type_fournisseur': type_fournisseur,
                                'telephone': telephone,
                                'email': email,
                                'adresse': adresse,
                                'nif_ou_isi': nif_ou_isi,
                                'cin': cin,
                                'date_cin': date_cin,
                                'lieu_cin': lieu_cin,
                                'numero_nif': numero_nif,
                                'numero_stat': numero_stat,
                                'code_postal': code_postal,
                                'autre_information': autre_information,
                                'tacheron': tacheron,
                                'devis': devis,
                                'actif': actif,
                                'adresse_relation': adresse_relation
                            }
                        )
                        if not created:
                            # Si le fournisseur existe déjà, mettre à jour les champs
                            fournisseur.idxls = idxls
                            fournisseur.type_fournisseur = type_fournisseur
                            fournisseur.telephone = telephone
                            fournisseur.email = email
                            fournisseur.adresse = adresse
                            fournisseur.nif_ou_isi = nif_ou_isi
                            fournisseur.cin = cin
                            fournisseur.date_cin = date_cin
                            fournisseur.lieu_cin = lieu_cin
                            fournisseur.numero_nif = numero_nif
                            fournisseur.numero_stat = numero_stat
                            fournisseur.code_postal = code_postal
                            fournisseur.autre_information = autre_information
                            fournisseur.tacheron = tacheron
                            fournisseur.devis = devis
                            fournisseur.actif = actif
                            fournisseur.adresse_relation = adresse_relation
                            fournisseur.save()

                        print(f"  -> Fournisseur '{nom_fournisseur}': {'créé' if created else 'mis à jour'}")
                    elif model_name == 'tarifs_tranches':
                        # Essayer plusieurs variantes du nom de colonne
                        tarif_id = (row_data.get('tarifvolumetrique_id', '') or
                                   row_data.get('tarifvolumetrique_(id)', '') or
                                   row_data.get('tarif_id', '')).strip()

                        if not tarif_id:
                            raise ValueError("Le champ tarifvolumetrique_id est obligatoire")

                        try:
                            tarif = TarifVolumetrique.objects.get(pk=tarif_id)
                        except TarifVolumetrique.DoesNotExist:
                            raise ValueError(f"Tarif ID '{tarif_id}' introuvable")

                        tranche_sup = row_data.get('tranchesuperieur', '')
                        tarif_val = row_data.get('tarif', '')

                        if not tranche_sup or not tarif_val:
                            raise ValueError("Les champs tranchesuperieur et tarif sont obligatoires")

                        obj, created = TarifVolumetriqueTranche.objects.get_or_create(
                            tarifvolumetrique=tarif,
                            tranchesuperieur=int(tranche_sup),
                            defaults={
                                'tarif': int(float(tarif_val))
                            }
                        )
                        print(f"  -> Tranche {tranche_sup}m³: {tarif_val} Ar/m³ ({'créée' if created else 'existante'})")

                    created_count += 1

                except Exception as e:
                    error_count += 1
                    # Stocker le message d'erreur avec la ligne concernée et le nom de l'ouvrage si disponible
                    nom_ouvrage = row_data.get('nom_ouvrage', 'N/A')
                    error_msg = f"Ligne {row_num} ({nom_ouvrage}): {str(e)}"
                    error_messages.append(error_msg)
                    print(f"Erreur ligne {row_num}: {row_data}, erreur: {e}")

            if created_count > 0:
                messages.success(request, f'{created_count} enregistrement(s) importé(s) avec succès depuis Excel.')
            if error_count > 0:
                # Afficher les 10 premières erreurs
                error_summary = f'{error_count} erreur(s) rencontrée(s) lors de l\'import Excel.'
                if error_messages:
                    # Créer un fichier de log avec toutes les erreurs
                    import os
                    from datetime import datetime
                    log_dir = os.path.join('logs', 'import_errors')
                    os.makedirs(log_dir, exist_ok=True)
                    log_filename = f'import_errors_{model_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
                    log_path = os.path.join(log_dir, log_filename)

                    with open(log_path, 'w', encoding='utf-8') as log_file:
                        log_file.write(f'Erreurs d\'import pour {model_name}\n')
                        log_file.write(f'Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
                        log_file.write(f'Total erreurs: {error_count}\n')
                        log_file.write('='*80 + '\n\n')
                        for error_msg in error_messages:
                            log_file.write(error_msg + '\n')

                    # Afficher les 10 premières erreurs à l'utilisateur
                    first_errors = error_messages[:10]
                    error_list = '\n'.join(f'• {err}' for err in first_errors)
                    if error_count > 10:
                        error_list += f'\n• ... et {error_count - 10} autres erreurs.'

                    messages.error(
                        request,
                        f'{error_summary}\n\n'
                        f'Premières erreurs :\n{error_list}\n\n'
                        f'📄 Fichier de log détaillé : {log_path}'
                    )
                else:
                    messages.warning(request, error_summary)

        except Exception as e:
            messages.error(request, f'Erreur lors de la lecture du fichier Excel: {str(e)}')

    return redirect(request.META.get('HTTP_REFERER', 'organization:list'))

def import_update_fournisseur_idxls(request):
    """Import Excel spécifique pour mettre à jour uniquement l'IDxls des fournisseurs existants"""
    if request.method == 'POST':
        if 'excel_file' not in request.FILES:
            messages.error(request, 'Aucun fichier sélectionné.')
            return redirect(request.META.get('HTTP_REFERER', 'organization:fournisseurs_list'))

        excel_file = request.FILES['excel_file']

        if not (excel_file.name.endswith('.xlsx') or excel_file.name.endswith('.xls')):
            messages.error(request, 'Le fichier doit être un fichier Excel (.xlsx ou .xls).')
            return redirect(request.META.get('HTTP_REFERER', 'organization:fournisseurs_list'))

        try:
            # Lire le fichier Excel
            wb = load_workbook(excel_file)
            ws = wb.active

            # Lire les en-têtes (première ligne)
            headers = []
            for cell in ws[1]:
                headers.append(cell.value.lower().replace(' ', '_') if cell.value else '')

            # Vérifier que les colonnes nécessaires sont présentes
            if 'id' not in headers or 'idxls' not in headers:
                messages.error(request, 'Le fichier Excel doit contenir les colonnes "ID" et "IDxls".')
                return redirect(request.META.get('HTTP_REFERER', 'organization:fournisseurs_list'))

            updated_count = 0
            not_found_count = 0
            error_count = 0
            error_messages_list = []

            # Traiter chaque ligne à partir de la ligne 2
            for row_num in range(2, ws.max_row + 1):
                try:
                    # Créer un dictionnaire avec les données de la ligne
                    row_data = {}
                    for col_num, header in enumerate(headers, 1):
                        cell_value = ws.cell(row=row_num, column=col_num).value
                        row_data[header] = str(cell_value).strip() if cell_value is not None else ''

                    # Récupérer l'ID (UUID) du fournisseur
                    fournisseur_id = row_data.get('id', '').strip()
                    if not fournisseur_id or fournisseur_id == 'None':
                        continue  # Ignorer les lignes sans ID

                    # Récupérer l'IDxls
                    idxls_str = row_data.get('idxls', '').strip()
                    idxls = int(idxls_str) if idxls_str and idxls_str not in ['None', '', '-'] else None

                    # Chercher le fournisseur par ID
                    try:
                        fournisseur = Fournisseur.objects.get(pk=fournisseur_id)
                        # Mettre à jour seulement l'IDxls
                        fournisseur.idxls = idxls
                        fournisseur.save(update_fields=['idxls'])
                        updated_count += 1
                        print(f"  -> Fournisseur '{fournisseur.nom_fournisseur}' (ID: {fournisseur_id[:8]}...): IDxls mis à jour → {idxls}")
                    except Fournisseur.DoesNotExist:
                        not_found_count += 1
                        error_messages_list.append(f"Ligne {row_num}: Fournisseur ID '{fournisseur_id[:8]}...' introuvable")
                        continue

                except Exception as e:
                    error_count += 1
                    error_messages_list.append(f"Ligne {row_num}: {str(e)}")
                    continue

            # Messages de résultat
            if updated_count > 0:
                messages.success(request, f'✅ {updated_count} fournisseur(s) mis à jour avec succès.')

            if not_found_count > 0:
                messages.warning(request, f'⚠️ {not_found_count} fournisseur(s) introuvable(s) (IDs invalides ou inexistants).')

            if error_count > 0:
                first_errors = error_messages_list[:10]
                error_list = '\n'.join(f'• {err}' for err in first_errors)
                if error_count > 10:
                    error_list += f'\n• ... et {error_count - 10} autres erreurs.'
                messages.error(request, f'❌ {error_count} erreur(s) lors de l\'import:\n{error_list}')

        except Exception as e:
            messages.error(request, f'Erreur lors de la lecture du fichier Excel: {str(e)}')

    return redirect(request.META.get('HTTP_REFERER', 'organization:fournisseurs_list'))
