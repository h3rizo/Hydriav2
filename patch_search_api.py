import re

def patch_views():
    with open('backend/apps/core/views.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Define the new search_api function
    new_search_api = '''def search_api(request):
    """API de recherche globale evoluee pour supporter la pagination et le filtrage par types"""
    import json
    from django.db.models import Q
    from apps.planning.models import Planning, Designation
    from apps.employees.models import Employe
    from apps.usagers.models import RepresentantUsager, Autorite, TiersParticipant
    from apps.billing.models import Fournisseur, PointEau, ModaliteGestion
    from apps.geography.models import Village, Commune
    from apps.organization.models import Ouvrage
    from apps.infrastructure.models import EquipementConstitutif, CarteSociale

    query = request.GET.get('q', '').strip()
    
    # Types filtering
    types_param = request.GET.get('types', '')
    requested_types = [t.strip() for t in types_param.split(',')] if types_param else []
    
    # Pagination
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
    except ValueError:
        page = 1
        page_size = 20

    if not query or len(query) < 2:
        return JsonResponse({
            'results': [],
            'total': 0,
            'message': 'Veuillez saisir au moins 2 caracteres',
            'has_next': False,
            'page': page
        })

    # Dictionnaires pour stocker les querysets et les fonctions de serialisation
    all_querysets = {}
    
    if not requested_types or 'planning' in requested_types:
        all_querysets['planning'] = Planning.objects.select_related(
            'employe', 'ouvrage', 'type_activite', 'fiche_poste'
        ).filter(
            Q(remarque__icontains=query) |
            Q(employe__nom__icontains=query) |
            Q(employe__prenom__icontains=query) |
            Q(employe__surnom__icontains=query) |
            Q(ouvrage__nom_ouvrage__icontains=query) |
            Q(type_activite__nomtype__icontains=query) |
            Q(fiche_poste__tache__icontains=query)
        )
        
    if not requested_types or 'employe' in requested_types:
        all_querysets['employe'] = Employe.objects.filter(
            Q(nom__icontains=query) |
            Q(prenom__icontains=query) |
            Q(surnom__icontains=query) |
            Q(mail__icontains=query) |
            Q(telephone__icontains=query)
        )
        
    if not requested_types or 'representant' in requested_types:
        all_querysets['representant'] = RepresentantUsager.objects.select_related(
            'village__fokontany__commune'
        ).filter(
            Q(nom__icontains=query) |
            Q(contact__icontains=query) |
            Q(village__nom_village__icontains=query)
        )
        
    if not requested_types or 'autorite' in requested_types:
        all_querysets['autorite'] = Autorite.objects.select_related(
            'fokontany', 'commune', 'district', 'region'
        ).filter(
            Q(nom__icontains=query) |
            Q(fonction__icontains=query) |
            Q(contact__icontains=query) |
            Q(email__icontains=query)
        )
        
    if not requested_types or 'tiers' in requested_types:
        all_querysets['tiers'] = TiersParticipant.objects.filter(
            Q(nom__icontains=query) |
            Q(organisme__icontains=query) |
            Q(fonction__icontains=query) |
            Q(contact__icontains=query) |
            Q(email__icontains=query)
        )
        
    if not requested_types or 'fournisseur' in requested_types:
        all_querysets['fournisseur'] = Fournisseur.objects.filter(
            Q(nom_fournisseur__icontains=query) |
            Q(telephone__icontains=query) |
            Q(email__icontains=query) |
            Q(numero_nif__icontains=query) |
            Q(code_tiers__icontains=query)
        )
        
    if not requested_types or 'village' in requested_types:
        all_querysets['village'] = Village.objects.select_related(
            'fokontany__commune__district__region'
        ).filter(
            Q(nom_village__icontains=query) |
            Q(fokontany__nom_fokontany__icontains=query) |
            Q(fokontany__commune__nom_commune__icontains=query)
        )
        
    if not requested_types or 'commune' in requested_types:
        all_querysets['commune'] = Commune.objects.select_related('district__region').filter(
            Q(nom_commune__icontains=query) |
            Q(district__nom_district__icontains=query)
        )

    # Note: On peut ajouter ouvrage, point_eau, equipement, designation, modalite, carte_sociale 
    # en suivant le meme pattern. 
    # Pour ne pas faire exploser la taille du code, on compte et on pagine globalement ou sequentiellement.
    
    totals_by_type = {}
    total_general = 0
    
    for t, qs in all_querysets.items():
        count = qs.count()
        totals_by_type[t] = count
        total_general += count

    # Logique de pagination sequentielle
    results = []
    offset = (page - 1) * page_size
    limit = page_size
    
    current_offset = 0
    
    for type_name, qs in all_querysets.items():
        type_count = totals_by_type[type_name]
        
        # Si on n'a pas encore atteint l'offset avec ce type
        if current_offset + type_count <= offset:
            current_offset += type_count
            continue
            
        # On doit piocher dans ce type
        start_idx = max(0, offset - current_offset)
        end_idx = start_idx + limit
        
        items = qs[start_idx:end_idx]
        
        # Serialisation basee sur le type
        for item in items:
            results.append(_serialize_search_item(item, type_name))
            
        limit -= len(items)
        current_offset += type_count
        
        if limit <= 0:
            break

    has_next = (page * page_size) < total_general

    return JsonResponse({
        'success': True,
        'results': results,
        'total': total_general,
        'totals_by_type': totals_by_type,
        'page': page,
        'page_size': page_size,
        'has_next': has_next
    })

def _serialize_search_item(item, type_name):
    # Logique de serialisation minimale
    if type_name == 'planning':
        return {
            'type': 'planning',
            'type_display': 'Planning',
            'id': str(item.id),
            'title': f"Planning {item.date.strftime('%d/%m/%Y') if item.date else 'Sans date'}",
            'subtitle': f"{item.employe.nom_affichage if item.employe else 'Sans employe'}",
            'badge': 'Valide' if getattr(item, 'estvalide', False) else 'En attente',
            'badge_class': 'success' if getattr(item, 'estvalide', False) else 'warning',
        }
    elif type_name == 'employe':
        est_actif = item.date_debauchage is None
        return {
            'type': 'employe',
            'type_display': 'Employe',
            'id': str(item.id),
            'title': item.nom_affichage,
            'subtitle': item.mail or item.telephone or '-',
            'badge': 'Actif' if est_actif else 'Inactif',
            'badge_class': 'success' if est_actif else 'error',
        }
    # ... autres types de maniere simplifiee pour retrocompatibilite ...
    return {
        'type': type_name,
        'type_display': type_name.capitalize(),
        'id': str(item.id),
        'title': str(item),
        'subtitle': '-'
    }
'''

    # On utilise regex pour remplacer de 'def search_api(request):' jusqu'au 'return JsonResponse(' 
    # de cette fonction
    pattern = re.compile(r'def search_api\(request\):.*?(?=def [a-zA-Z_]+\()', re.DOTALL)
    
    # We might have issues matching because of the end condition. Let's just do a manual replace or 
    # inject a new file.

    # Alternative: we can put this in a separate file and route to it.
    pass

if __name__ == "__main__":
    patch_views()
