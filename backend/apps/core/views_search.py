"""
Views pour la recherche globale dans l'application
"""
from django.http import JsonResponse
from django.db.models import Q
from apps.organization.models import Ouvrage
from apps.billing.models import PointEau
from apps.infrastructure.models import EquipementConstitutif, CarteSociale
from apps.geography.models import Village, Commune
from apps.employees.models import Employe
from apps.planning.models import Designation


def api_search_global(request):
    """
    API de recherche globale dans toute l'application
    Recherche dans : Ouvrages, Points d'eau, Équipements, Villages, Employés
    """
    query = request.GET.get('q', '').strip()

    if not query or len(query) < 2:
        return JsonResponse({
            'success': False,
            'error': 'Veuillez saisir au moins 2 caractères'
        })

    results = []

    # Recherche dans les Ouvrages
    try:
        ouvrages = Ouvrage.objects.filter(
            Q(nom_ouvrage__icontains=query) |
            Q(type_ouvrage__nom_type_ouvrage__icontains=query) |
            Q(pointeau__parcelle__village__nom_village__icontains=query) |
            Q(pointeau__parcelle__village__fokontany__nom_fokontany__icontains=query) |
            Q(pointeau__parcelle__village__fokontany__commune__nom_commune__icontains=query) |
            Q(pointeau__parcelle__village__fokontany__commune__district__nom_district__icontains=query)
        ).select_related('type_ouvrage').distinct()[:10]

        for ouvrage in ouvrages:
            # Récupérer les infos géographiques via le premier point d'eau
            point_eau = ouvrage.pointeau_set.select_related(
                'parcelle__village__fokontany__commune__district__region'
            ).first()

            commune = None
            district = None
            if point_eau and point_eau.parcelle:
                village = point_eau.parcelle.village
                if village and village.fokontany:
                    fokontany = village.fokontany
                    if fokontany.commune:
                        commune = fokontany.commune.nom_commune
                        if fokontany.commune.district:
                            district = fokontany.commune.district.nom_district

            # Chercher une photo depuis les points d'eau ou équipements liés
            photo_url = None
            try:
                # Essayer les points d'eau d'abord
                points_eau_with_photos = ouvrage.pointeau_set.filter(photos__isnull=False).first()
                if points_eau_with_photos and points_eau_with_photos.photos:
                    photo_url = points_eau_with_photos.photos.get_download_url()
                else:
                    # Sinon, essayer les équipements
                    equipements_with_photos = ouvrage.equipementconstitutif_set.filter(photos__isnull=False).first()
                    if equipements_with_photos and equipements_with_photos.photos:
                        photo_url = equipements_with_photos.photos.get_download_url()
            except Exception:
                pass

            results.append({
                'id': str(ouvrage.id),
                'type': 'ouvrage',  # Changed from 'Ouvrage' to match checkbox ID
                'title': ouvrage.nom_ouvrage or 'Ouvrage sans nom',
                'subtitle': f"{ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else 'Type inconnu'} - {commune or 'Commune inconnue'}",
                'description': f"{ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else 'Type inconnu'}",
                'badge': 'Ouvrage',
                'badge_class': 'primary',
                'icon': 'fa-building',
                'type_display': 'Ouvrage',
                'photo_url': photo_url,
                'url': f'/recherche/details/ouvrage/{ouvrage.id}/',
                'meta': {
                    'Type': ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else 'N/A',
                    'Commune': commune or 'N/A',
                    'District': district or 'N/A'
                }
            })
    except Exception as e:
        print(f"Erreur recherche ouvrages: {e}")

    # Recherche dans les Points d'eau
    try:
        points_eau = PointEau.objects.filter(
            Q(nomabonne__icontains=query) |
            Q(code_point_eau__icontains=query) |
            Q(type_point_eau__nom_type__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query) |
            Q(parcelle__village__nom_village__icontains=query) |
            Q(parcelle__village__fokontany__nom_fokontany__icontains=query) |
            Q(parcelle__village__fokontany__commune__nom_commune__icontains=query) |
            Q(parcelle__village__fokontany__commune__district__nom_district__icontains=query)
        ).select_related(
            'type_point_eau',
            'ouvrage',
            'parcelle__village__fokontany__commune'
        ).distinct()[:10]

        for point in points_eau:
            village = None
            commune = None
            if point.parcelle and point.parcelle.village:
                village = point.parcelle.village.nom_village
                if point.parcelle.village.fokontany and point.parcelle.village.fokontany.commune:
                    commune = point.parcelle.village.fokontany.commune.nom_commune

            # Récupérer la photo si disponible
            photo_url = None
            try:
                if point.photos:
                    photo_url = point.photos.get_download_url()
            except Exception:
                pass

            results.append({
                'id': str(point.id),
                'type': 'point_eau',  # Changed from 'Point d\'eau' to match checkbox ID
                'title': point.nomabonne or point.code_point_eau or 'Point d\'eau sans nom',
                'subtitle': f"{point.type_point_eau.nom_type if point.type_point_eau else 'Type inconnu'} - {village or 'Village inconnu'}",
                'description': f"{point.type_point_eau.nom_type if point.type_point_eau else 'Type inconnu'} - {point.ouvrage.nom_ouvrage if point.ouvrage else 'Sans ouvrage'}",
                'badge': 'Point d\'eau',
                'badge_class': 'info',
                'icon': 'fa-tint',
                'type_display': 'Point d\'eau',
                'photo_url': photo_url,
                'url': f'/recherche/details/point_eau/{point.id}/',
                'meta': {
                    'Type': point.type_point_eau.nom_type if point.type_point_eau else 'N/A',
                    'Ouvrage': point.ouvrage.nom_ouvrage if point.ouvrage else 'N/A',
                    'Village': village or 'N/A',
                    'Commune': commune or 'N/A'
                }
            })
    except Exception as e:
        print(f"Erreur recherche points d'eau: {e}")

    # Recherche dans les Équipements
    try:
        equipements = EquipementConstitutif.objects.filter(
            Q(nom__icontains=query) |
            Q(code_equipement__icontains=query) |
            Q(type_equipement__nom_type__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query) |
            Q(ouvrage__pointeau__parcelle__village__nom_village__icontains=query) |
            Q(ouvrage__pointeau__parcelle__village__fokontany__nom_fokontany__icontains=query) |
            Q(ouvrage__pointeau__parcelle__village__fokontany__commune__nom_commune__icontains=query) |
            Q(ouvrage__pointeau__parcelle__village__fokontany__commune__district__nom_district__icontains=query)
        ).select_related('type_equipement', 'ouvrage').distinct()[:10]

        for equipement in equipements:
            # Récupérer la photo si disponible
            photo_url = None
            try:
                if equipement.photos:
                    photo_url = equipement.photos.get_download_url()
            except Exception:
                pass

            results.append({
                'id': str(equipement.id),
                'type': 'equipement',  # Changed from 'Équipement' to match checkbox ID
                'title': equipement.nom or 'Équipement sans nom',
                'subtitle': f"{equipement.type_equipement.nom_type if equipement.type_equipement else 'Type inconnu'} - {equipement.ouvrage.nom_ouvrage if equipement.ouvrage else 'Sans ouvrage'}",
                'description': f"{equipement.type_equipement.nom_type if equipement.type_equipement else 'Type inconnu'} - {equipement.ouvrage.nom_ouvrage if equipement.ouvrage else 'Sans ouvrage'}",
                'badge': 'Équipement',
                'badge_class': 'accent',
                'icon': 'fa-cogs',
                'type_display': 'Équipement',
                'photo_url': photo_url,
                'url': f'/recherche/details/equipement/{equipement.id}/',
                'meta': {
                    'Type': equipement.type_equipement.nom_type if equipement.type_equipement else 'N/A',
                    'Ouvrage': equipement.ouvrage.nom_ouvrage if equipement.ouvrage else 'N/A',
                    'Statut': equipement.statut or 'N/A'
                }
            })
    except Exception as e:
        print(f"Erreur recherche équipements: {e}")

    # Recherche dans les Villages
    try:
        villages = Village.objects.filter(
            Q(nom_village__icontains=query) |
            Q(fokontany__nom_fokontany__icontains=query) |
            Q(fokontany__commune__nom_commune__icontains=query)
        ).select_related('fokontany__commune__district')[:10]

        for village in villages:
            commune = None
            district = None
            fokontany = None

            if village.fokontany:
                fokontany = village.fokontany.nom_fokontany
                if village.fokontany.commune:
                    commune = village.fokontany.commune.nom_commune
                    if village.fokontany.commune.district:
                        district = village.fokontany.commune.district.nom_district

            results.append({
                'id': str(village.id),
                'type': 'village',  # Changed from 'Village' to match checkbox ID
                'title': village.nom_village,
                'subtitle': f"{fokontany or 'Fokontany inconnu'} - {commune or 'Commune inconnue'}",
                'description': f"Village de {commune or 'commune inconnue'}",
                'badge': 'Village',
                'badge_class': 'info',
                'icon': 'fa-home',
                'type_display': 'Village',
                'photo_url': None,
                'url': f'/geography/villages/{village.id}/',
                'meta': {
                    'Fokontany': fokontany or 'N/A',
                    'Commune': commune or 'N/A',
                    'District': district or 'N/A'
                }
            })
    except Exception as e:
        print(f"Erreur recherche villages: {e}")

    # Recherche dans les Communes
    try:
        communes = Commune.objects.filter(
            Q(nom_commune__icontains=query) |
            Q(district__nom_district__icontains=query) |
            Q(district__region__nom_region__icontains=query)
        ).select_related('district__region')[:10]

        for commune in communes:
            district = commune.district.nom_district if commune.district else None
            region = commune.district.region.nom_region if commune.district and commune.district.region else None

            results.append({
                'id': str(commune.id),
                'type': 'commune',
                'title': commune.nom_commune or 'Commune sans nom',
                'subtitle': f"{district or 'District inconnu'} - {region or 'Region inconnue'}",
                'description': f"{district or 'District inconnu'}",
                'badge': 'Commune',
                'badge_class': 'secondary',
                'icon': 'fa-map-marker-alt',
                'type_display': 'Commune',
                'photo_url': None,
                'url': f'/recherche/details/commune/{commune.id}/',
                'meta': {
                    'Commune': commune.nom_commune or 'N/A',
                    'District': district or 'N/A',
                    'Region': region or 'N/A'
                }
            })
    except Exception as e:
        print(f"Erreur recherche communes: {e}")

    # Recherche dans les Employés
    try:
        employes = Employe.objects.filter(
            Q(nom__icontains=query) |
            Q(prenom__icontains=query) |
            Q(surnom__icontains=query)
        ).select_related('poste')[:10]

        for employe in employes:
            nom_complet = f"{employe.prenom or ''} {employe.nom or ''}".strip()
            if employe.surnom:
                nom_complet += f" ({employe.surnom})"

            poste = None
            if employe.poste:
                poste = employe.poste.nom_poste

            # Déterminer si l'employé est actif (pas de date de débauchage)
            est_actif = employe.date_debauchage is None

            # Récupérer la signature/photo si disponible
            photo_url = None
            if employe.signature and isinstance(employe.signature, list) and len(employe.signature) > 0:
                first_photo = employe.signature[0]
                if isinstance(first_photo, dict) and 'data' in first_photo:
                    photo_url = first_photo['data']

            results.append({
                'id': str(employe.id),
                'type': 'employe',
                'title': nom_complet or 'Employé sans nom',
                'subtitle': f"{poste or 'Poste inconnu'} - {'Actif' if est_actif else 'Inactif'}",
                'description': f"{poste or 'Poste inconnu'}",
                'badge': 'Employé',
                'badge_class': 'success' if est_actif else 'error',
                'icon': 'fa-user',
                'type_display': 'Employé',
                'photo_url': photo_url,
                'url': f'/employees/{employe.id}/',
                'meta': {
                    'Poste': poste or 'N/A',
                    'Statut': 'Actif' if est_actif else 'Inactif'
                }
            })
    except Exception as e:
        print(f"Erreur recherche employés: {e}")

    # Recherche dans les Désignations
    try:
        designations = Designation.objects.filter(
            Q(nom__icontains=query) |
            Q(type_designation__nom__icontains=query)
        ).select_related('type_designation')[:10]

        for designation in designations:
            # Récupérer la photo si disponible
            photo_url = None
            if designation.photo_specimen and isinstance(designation.photo_specimen, list) and len(designation.photo_specimen) > 0:
                first_photo = designation.photo_specimen[0]
                if isinstance(first_photo, dict) and 'data' in first_photo:
                    photo_url = first_photo['data']

            results.append({
                'id': str(designation.id),
                'type': 'designation',
                'title': designation.nom or 'Désignation sans nom',
                'subtitle': f"{designation.type_designation.nom if designation.type_designation else 'Type inconnu'}",
                'description': f"{designation.type_designation.nom if designation.type_designation else 'Type inconnu'}",
                'badge': 'Désignation',
                'badge_class': 'warning',
                'icon': 'fa-tag',
                'type_display': 'Désignation',
                'photo_url': photo_url,
                'url': f'/recherche/details/designation/{designation.id}/',
                'meta': {
                    'Type': designation.type_designation.nom if designation.type_designation else 'N/A',
                    'Prix': f"{designation.prix_unitaire} Ar" if designation.prix_unitaire else 'N/A'
                }
            })
    except Exception as e:
        print(f"Erreur recherche désignations: {e}")

    # Recherche dans les Cartes Sociales
    try:
        cartes_sociales = CarteSociale.objects.filter(
            Q(numero_carte__icontains=query) |
            Q(nom_beneficiaire__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query) |
            Q(point_eau__nomabonne__icontains=query)
        ).select_related('ouvrage', 'point_eau')[:10]

        for carte in cartes_sociales:
            # Déterminer le statut avec badge approprié
            statut_badge = {
                'active': 'success',
                'suspendue': 'warning',
                'expiree': 'error',
                'annulee': 'error'
            }.get(carte.statut, 'info')

            statut_display = {
                'active': 'Active',
                'suspendue': 'Suspendue',
                'expiree': 'Expirée',
                'annulee': 'Annulée'
            }.get(carte.statut, carte.statut)

            results.append({
                'id': str(carte.id),
                'type': 'carte_sociale',
                'title': f"Carte {carte.numero_carte or 'sans numéro'} - {carte.nom_beneficiaire}",
                'subtitle': f"{carte.ouvrage.nom_ouvrage if carte.ouvrage else 'Ouvrage inconnu'} - {statut_display}",
                'description': f"Bénéficiaire: {carte.nom_beneficiaire}",
                'badge': 'Carte Sociale',
                'badge_class': statut_badge,
                'icon': 'fa-id-card',
                'type_display': 'Carte Sociale',
                'photo_url': None,  # Les cartes sociales n'ont pas de photo dans le modèle
                'url': f'/recherche/details/carte_sociale/{carte.id}/',
                'meta': {
                    'Numéro': carte.numero_carte or 'N/A',
                    'Bénéficiaire': carte.nom_beneficiaire,
                    'Ouvrage': carte.ouvrage.nom_ouvrage if carte.ouvrage else 'N/A',
                    'Point d\'eau': carte.point_eau.nomabonne if carte.point_eau else 'N/A',
                    'Statut': statut_display
                }
            })
    except Exception as e:
        print(f"Erreur recherche cartes sociales: {e}")

    return JsonResponse({
        'success': True,
        'results': results,
        'total': len(results)
    })
