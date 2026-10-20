from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from .models import Post, Comment, Like, Dislike, PostImage
from apps.employees.models import Employe
from apps.organization.models import Ouvrage
from apps.inspections.models import Inspection
from apps.planning.models import Planning
import json

def feed_home(request):
    if not request.user.is_authenticated:
        return render(request, 'feed/feed_cta.html')

    employe = Employe.objects.filter(date_debauchage__isnull=True).first()
    # Exclure les posts de type planning sans ouvrage
    posts = Post.objects.select_related('auteur_employe','auteur_user','ouvrage').prefetch_related('images','commentaires__auteur_employe','commentaires__auteur_user','likes','dislikes').exclude(
        Q(type_post='planning') & Q(ouvrage__isnull=True)
    ).order_by('-date_creation')

    search = request.GET.get('search','')
    if search:
        posts = posts.filter(Q(titre__icontains=search)|Q(contenu__icontains=search))

    # Filtre par commune avec cascade simple vers ouvrages
    from apps.geography.models import Commune
    from apps.billing.models import PointEau

    commune_filter = request.GET.get('commune','')
    ouvrages_filtered = Ouvrage.objects.all().order_by('nom_ouvrage')

    if commune_filter:
        # Cascade simple: commune → ouvrage (via points d'eau)
        # Note: le champ est ouvrage_id (avec underscore) dans PointEau
        ouvrages_ids = PointEau.objects.filter(
            parcelle__village__fokontany__commune_id=commune_filter
        ).values_list('ouvrage_id', flat=True).distinct()

        # Filtrer les posts ET les ouvrages pour affichage
        posts = posts.filter(ouvrage_id__in=ouvrages_ids)
        ouvrages_filtered = ouvrages_filtered.filter(id__in=ouvrages_ids)

    ouvrage_filter = request.GET.get('ouvrage','')
    if ouvrage_filter:
        posts = posts.filter(ouvrage__nom_ouvrage__icontains=ouvrage_filter)

    employe_filter = request.GET.get('employe','')
    if employe_filter:
        posts = posts.filter(Q(auteur_employe_id=employe_filter)|Q(employe_concerne_id=employe_filter))

    type_filter = request.GET.get('type','')
    if type_filter:
        posts = posts.filter(type_post=type_filter)

    priorite_filter = request.GET.get('priorite','')
    if priorite_filter == 'true':
        posts = posts.filter(priorite=True)
    elif priorite_filter == 'false':
        posts = posts.filter(priorite=False)

    # Filtre Commune non assignée
    commune_non_assignee = request.GET.get('commune_non_assignee', '')
    if commune_non_assignee == 'true':
        posts = posts.filter(ouvrage__isnull=True)

    # Filtre Désignation (pour posts de type paiement_forfaitaire, coupure_eau, remise_eau)
    designation_filter = request.GET.get('designation', '')
    if designation_filter:
        # Récupérer les posts liés à des PlanningDetail avec cette désignation
        from apps.planning.models import PlanningDetail
        detail_ids = PlanningDetail.objects.filter(
            designation__nom__icontains=designation_filter
        ).values_list('id', flat=True)

        planningdetail_ct = ContentType.objects.get_for_model(PlanningDetail)
        posts = posts.filter(
            content_type=planningdetail_ct,
            object_id__in=detail_ids
        )

    # Filtre Statut
    statut_filter = request.GET.get('statut', '')
    if statut_filter:
        posts = posts.filter(statut=statut_filter)

    # Charger uniquement les communes liées à des ouvrages (via points d'eau)
    communes_ids = PointEau.objects.filter(
        ouvrage_id__isnull=False
    ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()
    communes = Commune.objects.filter(id__in=communes_ids).order_by('nom_commune')

    # Ajouter les informations de like/dislike pour l'utilisateur connecté
    posts_list = list(posts[:50])
    if hasattr(request.user, 'employe') and request.user.employe:
        for post in posts_list:
            post.user_liked = post.user_has_liked(request.user)
            post.user_disliked = post.user_has_disliked(request.user)
    else:
        for post in posts_list:
            post.user_liked = False
            post.user_disliked = False

    # Récupérer les désignations pour le filtre
    from apps.planning.models import Designation
    from datetime import datetime
    designations = Designation.objects.all().order_by('nom')

    # Mois en cours pour bouton "Mes plannings du mois"
    current_month = datetime.now().strftime('%Y-%m')

    context = {
        'posts': posts_list,
        'ouvrages': ouvrages_filtered,
        'employes': Employe.objects.filter(date_debauchage__isnull=True).order_by('nom_employe'),
        'communes': communes,
        'designations': designations,
        'employe_actuel': employe,
        'search': search,
        'commune_filter': commune_filter,
        'ouvrage_filter': ouvrage_filter,
        'employe_filter': employe_filter,
        'type_filter': type_filter,
        'priorite_filter': priorite_filter,
        'commune_non_assignee': commune_non_assignee,
        'designation_filter': designation_filter,
        'statut_filter': statut_filter,
        'current_month': current_month,
    }
    return render(request, 'feed/feed_home.html', context)

@csrf_exempt
def post_create(request):
    if request.method == 'POST':
        # Utiliser l'utilisateur connecté au lieu d'un employé aléatoire
        auteur_nom = request.user.username if request.user.is_authenticated else 'Anonyme'
        employe = None
        if hasattr(request.user, 'employe') and request.user.employe:
            employe = request.user.employe
            # Priorité au surnom, sinon nom complet
            auteur_nom = employe.surnom or employe.nom_employe

        priorite = request.POST.get('priorite') == 'on'  # Checkbox value
        post = Post.objects.create(
            type_post='manuel',
            titre=request.POST.get('titre'),
            contenu=request.POST.get('contenu'),
            auteur_user=request.user if request.user.is_authenticated else None,
            auteur_employe=employe,
            auteur_nom=auteur_nom,
            ouvrage_id=request.POST.get('ouvrage') if request.POST.get('ouvrage') else None,
            employe_concerne_id=request.POST.get('employe_concerne') if request.POST.get('employe_concerne') else None,
            priorite=priorite
        )
        for f in request.FILES.getlist('images'):
            PostImage.objects.create(post=post,image=f)
        return JsonResponse({'success':True,'post_id':str(post.id)})
    return JsonResponse({'error':'Méthode non autorisée'},status=405)

def comment_create(request, post_id):
    print(f"[DEBUG] comment_create appelé - Method: {request.method}, Post ID: {post_id}")
    if request.method == 'POST':
        post = get_object_or_404(Post, id=post_id)
        print(f"[DEBUG] Post trouvé: {post.titre}")

        # Récupérer l'employé de l'utilisateur connecté
        if not hasattr(request.user, 'employe') or not request.user.employe:
            print(f"[DEBUG] Utilisateur non autorisé: {request.user}")
            return JsonResponse({'error': 'Utilisateur non autorisé'}, status=403)

        employe = request.user.employe
        print(f"[DEBUG] Employé: {employe.nom_employe}")
        contenu = request.POST.get('contenu')
        print(f"[DEBUG] Contenu: {contenu}")

        comment = Comment.objects.create(
            post=post,
            auteur_user=request.user if request.user.is_authenticated else None,
            auteur_employe=employe,
            # Priorité au surnom, sinon nom complet
            auteur_nom=(employe.surnom or employe.nom_employe) if employe else "Anonyme",
            contenu=contenu
        )
        print(f"[DEBUG] Commentaire créé: {comment.id}")
        return JsonResponse({
            'success': True,
            'auteur': comment.auteur_nom,
            'date': comment.date_creation.strftime('%d/%m/%Y %H:%M'),
            'contenu': comment.contenu
        })
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

def like_toggle(request, post_id):
    print(f"[DEBUG] like_toggle appelé - Method: {request.method}, Post ID: {post_id}")
    if request.method == 'POST':
        post = get_object_or_404(Post, id=post_id)
        print(f"[DEBUG] Post trouvé: {post.titre}")

        # Récupérer l'employé de l'utilisateur connecté
        if not hasattr(request.user, 'employe') or not request.user.employe:
            print(f"[DEBUG] Utilisateur non autorisé: {request.user}")
            return JsonResponse({'error': 'Utilisateur non autorisé'}, status=403)

        employe = request.user.employe
        action_type = request.POST.get('action', 'like')  # 'like' ou 'dislike'
        print(f"[DEBUG] Action: {action_type}, Employé: {employe.nom_employe}")

        if action_type == 'like':
            # Gérer les likes
            like, created = Like.objects.get_or_create(
                post=post,
                auteur_user=request.user if request.user.is_authenticated else None,
                auteur_employe=employe
            )
            if not created:
                like.delete()
                return JsonResponse({
                    'success': True,
                    'action': 'unlike',
                    'count_likes': post.nombre_likes,
                    'count_dislikes': post.nombre_dislikes
                })
            # Si on like, retirer le dislike s'il existe
            Dislike.objects.filter(post=post, auteur_employe=employe).delete()
            return JsonResponse({
                'success': True,
                'action': 'like',
                'count_likes': post.nombre_likes,
                'count_dislikes': post.nombre_dislikes
            })
        elif action_type == 'dislike':
            # Gérer les dislikes
            dislike, created = Dislike.objects.get_or_create(
                post=post,
                auteur_user=request.user if request.user.is_authenticated else None,
                auteur_employe=employe
            )
            if not created:
                dislike.delete()
                return JsonResponse({
                    'success': True,
                    'action': 'undislike',
                    'count_likes': post.nombre_likes,
                    'count_dislikes': post.nombre_dislikes
                })
            # Si on dislike, retirer le like s'il existe
            Like.objects.filter(post=post, auteur_employe=employe).delete()
            return JsonResponse({
                'success': True,
                'action': 'dislike',
                'count_likes': post.nombre_likes,
                'count_dislikes': post.nombre_dislikes
            })

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

def sync_feed(request):
    """Synchronise le fil d'actualité avec les activités récentes et à venir"""
    from datetime import timedelta
    from apps.inspections.models import Visite, ResultatControle
    from apps.planning.models import Planning

    count = 0

    # 1. Synchroniser les visites récentes (7 derniers jours)
    date_limite_passe = timezone.now() - timedelta(days=7)
    visites = Visite.objects.filter(date_visite__gte=date_limite_passe).select_related('ouvrage','agent')
    visite_ct = ContentType.objects.get_for_model(Visite)
    posts_existants_visites = Post.objects.filter(content_type=visite_ct).values_list('object_id',flat=True)

    for visite in visites:
        if visite.id not in posts_existants_visites:
            # Récupérer la commune
            commune = None
            if visite.ouvrage:
                try:
                    from apps.billing.models import PointEau
                    pe = PointEau.objects.filter(ouvrage=visite.ouvrage).select_related(
                        'parcelle__village__fokontany__commune'
                    ).first()
                    if pe and pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
                        commune = pe.parcelle.village.fokontany.commune
                except:
                    pass

            resultats = ResultatControle.objects.filter(visite=visite)
            total = resultats.count()
            anomalies = resultats.filter(necessite_action=True).count()

            if total > 0:
                contenu = f"Visite {visite.get_type_visite_display()} - {total} points contrôlés"
                if anomalies > 0:
                    contenu += f", {anomalies} anomalie(s) détectée(s)"
                else:
                    contenu += ", aucune anomalie"
                if visite.commentaires_generaux:
                    contenu += f"\n\n{visite.commentaires_generaux}"
            else:
                contenu = visite.commentaires_generaux or "Visite en cours"

            # Ajouter ouvrage et commune dans le contenu
            if visite.ouvrage:
                contenu += f"\n\nOuvrage : {visite.ouvrage.nom_ouvrage}"
            if commune:
                contenu += f"\nCommune : {commune.nom_commune}"

            # Tags avec commune et ouvrage
            tags = f"visite,{visite.type_visite},{visite.statut}"
            if commune:
                tags += f",commune:{commune.id}"
            if visite.ouvrage:
                tags += f",ouvrage:{visite.ouvrage.id}"

            Post.objects.create(
                type_post='inspection',
                titre=f"Visite {visite.ouvrage.nom_ouvrage if visite.ouvrage else 'terrain'}",
                contenu=contenu,
                content_type=visite_ct,
                object_id=visite.id,
                auteur_employe=visite.agent, auteur_nom=(visite.agent.surnom or visite.agent.nom_employe) if visite.agent else "Système",
                ouvrage=visite.ouvrage,
                employe_concerne=visite.agent,
                tags=tags
            )
            count += 1

    # 2. Synchroniser les activités de planning récemment réalisées (7 derniers jours)
    plannings_recents = Planning.objects.filter(
        date__gte=date_limite_passe,
        date__lte=timezone.now(),
        ouvrage__isnull=False  # Exclure les plannings sans ouvrage
    ).select_related('employe', 'type_activite', 'ouvrage')

    planning_ct = ContentType.objects.get_for_model(Planning)
    posts_existants_plannings = Post.objects.filter(content_type=planning_ct).values_list('object_id',flat=True)

    for planning in plannings_recents:
        if planning.id not in posts_existants_plannings:
            # Récupérer la commune via ouvrage → point d'eau → parcelle → village → fokontany → commune
            commune = None
            if planning.ouvrage:
                try:
                    from apps.billing.models import PointEau
                    pe = PointEau.objects.filter(ouvrage=planning.ouvrage).select_related(
                        'parcelle__village__fokontany__commune'
                    ).first()
                    if pe and pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
                        commune = pe.parcelle.village.fokontany.commune
                except:
                    pass

            contenu = f"Activité : {planning.type_activite.nomtype if planning.type_activite else 'Non spécifiée'}"
            if planning.ouvrage:
                contenu += f"\nOuvrage : {planning.ouvrage.nom_ouvrage}"
            if commune:
                contenu += f"\nCommune : {commune.nom_commune}"
            if planning.bilan:
                contenu += f"\n\nBilan : {planning.bilan}"
            if planning.remarque:
                contenu += f"\n\nRemarque : {planning.remarque}"

            # Tags avec commune et ouvrage
            tags = f"planning,realise,{planning.statut if planning.statut else 'termine'}"
            if commune:
                tags += f",commune:{commune.id}"
            if planning.ouvrage:
                tags += f",ouvrage:{planning.ouvrage.id}"

            Post.objects.create(
                type_post='planning',
                titre=f"Activité réalisée - {planning.type_activite.nomtype if planning.type_activite else 'Planning'}",
                contenu=contenu,
                content_type=planning_ct,
                object_id=planning.id,
                auteur_employe=planning.employe, auteur_nom=(planning.employe.surnom or planning.employe.nom_employe) if planning.employe else "Système",
                ouvrage=planning.ouvrage,
                employe_concerne=planning.employe,
                tags=tags
            )
            count += 1

    # 3. Synchroniser les activités à venir (7 prochains jours)
    date_limite_futur = timezone.now() + timedelta(days=7)
    plannings_a_venir = Planning.objects.filter(
        date__gt=timezone.now(),
        date__lte=date_limite_futur,
        ouvrage__isnull=False  # Exclure les plannings sans ouvrage
    ).select_related('employe', 'type_activite', 'ouvrage')

    for planning in plannings_a_venir:
        if planning.id not in posts_existants_plannings:
            # Récupérer la commune
            commune = None
            if planning.ouvrage:
                try:
                    from apps.billing.models import PointEau
                    pe = PointEau.objects.filter(ouvrage=planning.ouvrage).select_related(
                        'parcelle__village__fokontany__commune'
                    ).first()
                    if pe and pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
                        commune = pe.parcelle.village.fokontany.commune
                except:
                    pass

            contenu = f"Activité prévue : {planning.type_activite.nomtype if planning.type_activite else 'Non spécifiée'}"
            contenu += f"\n\nDate : {planning.date.strftime('%d/%m/%Y à %H:%M')}"
            if planning.ouvrage:
                contenu += f"\nOuvrage : {planning.ouvrage.nom_ouvrage}"
            if commune:
                contenu += f"\nCommune : {commune.nom_commune}"
            if planning.remarque:
                contenu += f"\n\nRemarque : {planning.remarque}"

            # Tags avec commune et ouvrage
            tags = f"planning,a_venir,{planning.statut if planning.statut else 'en_cours'}"
            if commune:
                tags += f",commune:{commune.id}"
            if planning.ouvrage:
                tags += f",ouvrage:{planning.ouvrage.id}"

            # Détecter automatiquement la priorité
            titre = f"Activité à venir - {planning.type_activite.nomtype if planning.type_activite else 'Planning'}"
            priority_keywords = ['RÉPARATION', 'PAIEMENT', 'URGENT', 'PANNE', 'URGENCE', 'CRITIQUE']
            is_priority = any(keyword in titre.upper() or keyword in contenu.upper() for keyword in priority_keywords)

            Post.objects.create(
                type_post='planning',
                titre=titre,
                contenu=contenu,
                content_type=planning_ct,
                object_id=planning.id,
                auteur_employe=planning.employe, auteur_nom=(planning.employe.surnom or planning.employe.nom_employe) if planning.employe else "Système",
                ouvrage=planning.ouvrage,
                employe_concerne=planning.employe,
                tags=tags,
                epingle=True,
                priorite=is_priority
            )
            count += 1

    # 4. Synchroniser les dépenses/recettes récentes (7 derniers jours)
    from apps.planning.models import PlanningDetail

    details_recents = PlanningDetail.objects.filter(
        created_at__gte=date_limite_passe
    ).select_related('planning__employe', 'planning__ouvrage', 'designation')[:50]

    planningdetail_ct = ContentType.objects.get_for_model(PlanningDetail)
    posts_existants_details = Post.objects.filter(content_type=planningdetail_ct).values_list('object_id',flat=True)

    for detail in details_recents:
        if detail.id not in posts_existants_details and detail.planning and detail.planning.employe:
            # Récupérer la commune
            commune = None
            if detail.planning.ouvrage:
                try:
                    from apps.billing.models import PointEau
                    pe = PointEau.objects.filter(ouvrage=detail.planning.ouvrage).select_related(
                        'parcelle__village__fokontany__commune'
                    ).first()
                    if pe and pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
                        commune = pe.parcelle.village.fokontany.commune
                except:
                    pass

            # Déterminer si c'est une dépense ou recette
            type_transaction = "Dépense"
            if detail.designation and hasattr(detail.designation, 'concerne_livraison'):
                if detail.designation.concerne_livraison:
                    type_transaction = "Recette (Livraison)"
                elif hasattr(detail.designation, 'concerne_avance') and detail.designation.concerne_avance:
                    type_transaction = "Recette (Avance)"

            contenu = f"{type_transaction} : {detail.designation.nom_designation if detail.designation else 'N/A'}"
            contenu += f"\nQuantité : {detail.quantity}"
            contenu += f"\nMontant : {detail.montant} Ar"
            if detail.magasin:
                contenu += f"\nMagasin : {detail.magasin}"
            if detail.acheteur:
                contenu += f"\nAcheteur : {detail.acheteur}"
            if detail.planning.ouvrage:
                contenu += f"\nOuvrage : {detail.planning.ouvrage.nom_ouvrage}"
            if commune:
                contenu += f"\nCommune : {commune.nom_commune}"

            # Tags
            tags = f"depense,planning,{type_transaction.lower().replace(' ', '_')}"
            if commune:
                tags += f",commune:{commune.id}"
            if detail.planning.ouvrage:
                tags += f",ouvrage:{detail.planning.ouvrage.id}"

            employe_nom = detail.planning.employe.surnom if detail.planning.employe.surnom else detail.planning.employe.nom_employe

            Post.objects.create(
                type_post='planning',
                titre=f"{type_transaction} - {employe_nom}",
                contenu=contenu,
                content_type=planningdetail_ct,
                object_id=detail.id,
                auteur_employe=detail.planning.employe, auteur_nom=(detail.planning.employe.surnom or detail.planning.employe.nom_employe) if detail.planning.employe else "Système",
                ouvrage=detail.planning.ouvrage,
                employe_concerne=detail.planning.employe,
                tags=tags
            )
            count += 1

    # 5. Générer les posts pour paiements forfaitaires, coupures et remises en eau
    from apps.planning.models import PlanningDetail
    from datetime import timedelta as td

    today = timezone.now().date()
    date_limite_futur = today + td(days=7)

    # Paiements forfaitaires
    details_paiements = PlanningDetail.objects.filter(
        designation__nom='Paiement forfaitaire',
        planning__date__gte=today,
        planning__date__lte=date_limite_futur,
        point_eau__isnull=False
    ).select_related(
        'planning__ouvrage',
        'point_eau',
        'point_eau__parcelle__village__fokontany__commune'
    )

    for detail in details_paiements:
        existe = Post.objects.filter(
            content_type=planningdetail_ct,
            object_id=detail.id,
            type_post='paiement_forfaitaire'
        ).exists()

        if not existe:
            point_eau = detail.point_eau
            contact = getattr(point_eau, 'contact', None) or 'Non renseigné'
            commune = 'Non liée'
            if point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany and point_eau.parcelle.village.fokontany.commune:
                commune = point_eau.parcelle.village.fokontany.commune.nom_commune

            jours_restants = (detail.planning.date - today).days if hasattr(detail.planning.date, 'date') else (detail.planning.date.date() - today).days if hasattr(detail.planning.date, 'date') else 0
            titre = f"💰 Paiement forfaitaire à venir - {point_eau.nomabonne}"

            contenu = f"""<div class="bg-success bg-opacity-10 border-l-4 border-success p-4 rounded">
    <h4 class="font-bold text-success mb-2">🔔 Paiement forfaitaire imminent</h4>
    <p><strong>Point d'eau:</strong> {point_eau.nomabonne}</p>
    <p><strong>Ouvrage:</strong> {detail.planning.ouvrage.nom_ouvrage if detail.planning.ouvrage else 'N/A'}</p>
    <p><strong>Commune:</strong> {commune}</p>
    <p><strong>Contact:</strong> <span class="badge badge-info">{contact}</span></p>
    <p><strong>Date prévue:</strong> {detail.planning.date.strftime('%d/%m/%Y')}</p>
    <p><strong>Montant:</strong> {detail.montant:,.0f} Ar</p>
    <p><strong>Échéance:</strong> Dans <span class="badge badge-warning">{jours_restants} jour{'s' if jours_restants > 1 else ''}</span></p>
</div>
<div class="alert alert-info mt-4">
    <i class="fas fa-phone-alt mr-2"></i>
    <div>
        <p class="font-semibold">Action requise (Caissière):</p>
        <ul class="list-disc ml-6">
            <li>Appeler le responsable du point d'eau</li>
            <li>Confirmer la date de paiement</li>
            <li>Vérifier les coordonnées bancaires si nécessaire</li>
        </ul>
    </div>
</div>"""

            employe_systeme = Employe.objects.filter(date_debauchage__isnull=True).first()
            Post.objects.create(
                type_post='paiement_forfaitaire',
                titre=titre,
                contenu=contenu,
                auteur_employe=None, auteur_nom="Système" or detail.planning.employe,
                ouvrage=detail.planning.ouvrage,
                priorite=True,
                content_type=planningdetail_ct,
                object_id=detail.id,
                tags=f"paiement,forfaitaire,urgent,contact:{contact}"
            )
            count += 1

    # Coupures d'eau
    details_coupures = PlanningDetail.objects.filter(
        designation__nom='Coupure d\'eau',
        planning__date__gte=today,
        planning__date__lte=date_limite_futur,
        point_eau__isnull=False
    ).select_related(
        'planning__ouvrage',
        'point_eau',
        'point_eau__parcelle__village__fokontany__commune'
    )

    for detail in details_coupures:
        existe = Post.objects.filter(
            content_type=planningdetail_ct,
            object_id=detail.id,
            type_post='coupure_eau'
        ).exists()

        if not existe:
            point_eau = detail.point_eau
            contact = getattr(point_eau, 'contact', None) or 'Non renseigné'
            commune = 'Non liée'
            if point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany and point_eau.parcelle.village.fokontany.commune:
                commune = point_eau.parcelle.village.fokontany.commune.nom_commune

            jours_restants = (detail.planning.date - today).days if hasattr(detail.planning.date, 'date') else (detail.planning.date.date() - today).days if hasattr(detail.planning.date, 'date') else 0
            titre = f"🚫 Coupure d'eau programmée - {point_eau.nomabonne}"

            contenu = f"""<div class="bg-error bg-opacity-10 border-l-4 border-error p-4 rounded">
    <h4 class="font-bold text-error mb-2">⚠️ Coupure d'eau prévue</h4>
    <p><strong>Point d'eau:</strong> {point_eau.nomabonne}</p>
    <p><strong>Ouvrage:</strong> {detail.planning.ouvrage.nom_ouvrage if detail.planning.ouvrage else 'N/A'}</p>
    <p><strong>Commune:</strong> {commune}</p>
    <p><strong>Contact:</strong> <span class="badge badge-info">{contact}</span></p>
    <p><strong>Date prévue:</strong> {detail.planning.date.strftime('%d/%m/%Y')}</p>
    <p><strong>Échéance:</strong> Dans <span class="badge badge-error">{jours_restants} jour{'s' if jours_restants > 1 else ''}</span></p>
</div>
<div class="alert alert-warning mt-4">
    <i class="fas fa-exclamation-triangle mr-2"></i>
    <div>
        <p class="font-semibold">Action requise :</p>
        <ul class="list-disc ml-6">
            <li>Prévenir le responsable du point d'eau</li>
            <li>Confirmer la date de la coupure</li>
            <li>Vérifier le motif de la coupure (impayés, maintenance, etc.)</li>
        </ul>
    </div>
</div>"""

            employe_systeme = Employe.objects.filter(date_debauchage__isnull=True).first()
            Post.objects.create(
                type_post='coupure_eau',
                titre=titre,
                contenu=contenu,
                auteur_employe=None, auteur_nom="Système" or detail.planning.employe,
                ouvrage=detail.planning.ouvrage,
                priorite=True,
                content_type=planningdetail_ct,
                object_id=detail.id,
                tags=f"coupure,eau,urgent,contact:{contact}"
            )
            count += 1

    # Remises en eau
    details_remises = PlanningDetail.objects.filter(
        designation__nom='Remise en eau',
        planning__date__gte=today,
        planning__date__lte=date_limite_futur,
        point_eau__isnull=False
    ).select_related(
        'planning__ouvrage',
        'point_eau',
        'point_eau__parcelle__village__fokontany__commune'
    )

    for detail in details_remises:
        existe = Post.objects.filter(
            content_type=planningdetail_ct,
            object_id=detail.id,
            type_post='remise_eau'
        ).exists()

        if not existe:
            point_eau = detail.point_eau
            contact = getattr(point_eau, 'contact', None) or 'Non renseigné'
            commune = 'Non liée'
            if point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany and point_eau.parcelle.village.fokontany.commune:
                commune = point_eau.parcelle.village.fokontany.commune.nom_commune

            jours_restants = (detail.planning.date - today).days if hasattr(detail.planning.date, 'date') else (detail.planning.date.date() - today).days if hasattr(detail.planning.date, 'date') else 0
            titre = f"✅ Remise en eau programmée - {point_eau.nomabonne}"

            contenu = f"""<div class="bg-accent bg-opacity-10 border-l-4 border-accent p-4 rounded">
    <h4 class="font-bold text-accent mb-2">💧 Remise en eau prévue</h4>
    <p><strong>Point d'eau:</strong> {point_eau.nomabonne}</p>
    <p><strong>Ouvrage:</strong> {detail.planning.ouvrage.nom_ouvrage if detail.planning.ouvrage else 'N/A'}</p>
    <p><strong>Commune:</strong> {commune}</p>
    <p><strong>Contact:</strong> <span class="badge badge-info">{contact}</span></p>
    <p><strong>Date prévue:</strong> {detail.planning.date.strftime('%d/%m/%Y')}</p>
    <p><strong>Échéance:</strong> Dans <span class="badge badge-accent">{jours_restants} jour{'s' if jours_restants > 1 else ''}</span></p>
</div>
<div class="alert alert-success mt-4">
    <i class="fas fa-check-circle mr-2"></i>
    <div>
        <p class="font-semibold">Action requise :</p>
        <ul class="list-disc ml-6">
            <li>Prévenir le responsable du point d'eau</li>
            <li>Confirmer la date de la remise en eau</li>
            <li>Vérifier que les conditions de remise en service sont remplies</li>
        </ul>
    </div>
</div>"""

            employe_systeme = Employe.objects.filter(date_debauchage__isnull=True).first()
            Post.objects.create(
                type_post='remise_eau',
                titre=titre,
                contenu=contenu,
                auteur_employe=None, auteur_nom="Système" or detail.planning.employe,
                ouvrage=detail.planning.ouvrage,
                priorite=False,
                content_type=planningdetail_ct,
                object_id=detail.id,
                tags=f"remise,eau,contact:{contact}"
            )
            count += 1

    return JsonResponse({'success':True,'count':count})

def sync_priority(request):
    """Synchronise automatiquement la priorité des posts basée sur des mots-clés"""
    from django.contrib import messages
    from django.shortcuts import redirect

    priority_keywords = ['RÉPARATION', 'PAIEMENT', 'URGENT', 'PANNE', 'URGENCE', 'CRITIQUE',
                         'Réparation', 'réparation', 'REPARATION', 'reparation']

    # Récupérer tous les posts
    posts = Post.objects.all()
    count_updated = 0

    for post in posts:
        titre_upper = post.titre.upper()
        contenu_upper = post.contenu.upper()

        # Vérifier si le titre ou contenu contient un mot-clé prioritaire
        is_priority = any(keyword.upper() in titre_upper or keyword.upper() in contenu_upper
                         for keyword in priority_keywords)

        # Mettre à jour uniquement si la valeur a changé
        if is_priority and not post.priorite:
            post.priorite = True
            post.save()
            count_updated += 1

    # Si requête AJAX, retourner JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'count_updated': count_updated})

    # Sinon rediriger avec message
    messages.success(request, f'✅ {count_updated} post(s) marqué(s) comme prioritaire(s)')
    return redirect('feed:home')


@csrf_exempt
def post_change_status(request, post_id):
    """Change le statut d'un post (actif, terminé, annulé)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    try:
        data = json.loads(request.body)
        statut = data.get('statut')

        if statut not in ['actif', 'termine', 'annule']:
            return JsonResponse({'success': False, 'error': 'Statut invalide'}, status=400)

        post = get_object_or_404(Post, id=post_id)
        post.statut = statut
        post.save()

        return JsonResponse({
            'success': True,
            'message': f'Post marqué comme {post.get_statut_display()}'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def post_delete(request, post_id):
    """Supprime un post"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    try:
        post = get_object_or_404(Post, id=post_id)
        post.delete()

        return JsonResponse({
            'success': True,
            'message': 'Post supprimé avec succès'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def post_toggle_priority(request, post_id):
    """Bascule manuellement la priorité d'un post"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    try:
        post = get_object_or_404(Post, id=post_id)
        post.priorite = not post.priorite
        post.save()

        return JsonResponse({
            'success': True,
            'priorite': post.priorite,
            'message': f'Post {"marqué comme prioritaire" if post.priorite else "priorité retirée"}'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def generer_posts_paiements_forfaitaires(request):
    """Génère automatiquement les posts pour les paiements forfaitaires à venir"""
    from apps.planning.models import PlanningDetail
    from apps.billing.models import PointEau
    from datetime import timedelta

    # Employé par défaut pour créer les posts
    employe_systeme = Employe.objects.filter(date_debauchage__isnull=True).first()
    if not employe_systeme:
        return JsonResponse({'success': False, 'error': 'Aucun employé trouvé'}, status=500)

    # Trouver les détails de paiements forfaitaires à venir (7 prochains jours)
    today = timezone.now().date()
    date_limite = today + timedelta(days=7)

    details = PlanningDetail.objects.filter(
        designation__nom='Paiement forfaitaire',
        planning__date__gte=today,
        planning__date__lte=date_limite,
        point_eau__isnull=False
    ).select_related(
        'planning__ouvrage',
        'point_eau',
        'point_eau__parcelle__village__fokontany__commune'
    )

    posts_crees = 0

    for detail in details:
        # Vérifier si un post existe déjà pour ce détail
        content_type = ContentType.objects.get_for_model(PlanningDetail)
        existe = Post.objects.filter(
            content_type=content_type,
            object_id=detail.id,
            type_post='paiement_forfaitaire'
        ).exists()

        if existe:
            continue

        # Créer le contenu avec les informations du contact
        point_eau = detail.point_eau
        contact = point_eau.contact if hasattr(point_eau, 'contact') and point_eau.contact else 'Non renseigné'
        commune = 'Non liée'
        if point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany and point_eau.parcelle.village.fokontany.commune:
            commune = point_eau.parcelle.village.fokontany.commune.nom_commune

        jours_restants = (detail.planning.date - today).days
        titre = f"💰 Paiement forfaitaire à venir - {point_eau.nomabonne}"

        contenu = f"""
<div class="bg-success bg-opacity-10 border-l-4 border-success p-4 rounded">
    <h4 class="font-bold text-success mb-2">🔔 Paiement forfaitaire imminent</h4>
    <p><strong>Point d'eau:</strong> {point_eau.nomabonne}</p>
    <p><strong>Ouvrage:</strong> {detail.planning.ouvrage.nom_ouvrage if detail.planning.ouvrage else 'N/A'}</p>
    <p><strong>Commune:</strong> {commune}</p>
    <p><strong>Contact:</strong> <span class="badge badge-info">{contact}</span></p>
    <p><strong>Date prévue:</strong> {detail.planning.date.strftime('%d/%m/%Y')}</p>
    <p><strong>Montant:</strong> {detail.montant:,.0f} Ar</p>
    <p><strong>Échéance:</strong> Dans <span class="badge badge-warning">{jours_restants} jour{'s' if jours_restants > 1 else ''}</span></p>
</div>

<div class="alert alert-info mt-4">
    <i class="fas fa-phone-alt mr-2"></i>
    <div>
        <p class="font-semibold">Action requise (Caissière):</p>
        <ul class="list-disc ml-6">
            <li>Appeler le responsable du point d'eau</li>
            <li>Confirmer la date de paiement</li>
            <li>Vérifier les coordonnées bancaires si nécessaire</li>
        </ul>
    </div>
</div>
"""

        # Créer le post avec priorité "paiement"
        post = Post.objects.create(
            type_post='paiement_forfaitaire',
            titre=titre,
            contenu=contenu,
            auteur_employe=None, auteur_nom="Système",
            ouvrage=detail.planning.ouvrage,
            priorite=True,  # Priorité haute pour l'attention de la caissière
            content_type=content_type,
            object_id=detail.id,
            tags=f"paiement,forfaitaire,urgent,contact:{contact}"
        )

        posts_crees += 1

    return JsonResponse({
        'success': True,
        'message': f'{posts_crees} post(s) de paiements forfaitaires créé(s)',
        'count': posts_crees
    })


def generer_posts_coupures_eau(request):
    """Génère automatiquement les posts pour les coupures d'eau à venir"""
    from apps.planning.models import PlanningDetail
    from apps.billing.models import PointEau
    from datetime import timedelta

    employe_systeme = Employe.objects.filter(date_debauchage__isnull=True).first()
    if not employe_systeme:
        return JsonResponse({'success': False, 'error': 'Aucun employé trouvé'}, status=500)

    today = timezone.now().date()
    date_limite = today + timedelta(days=7)

    # Trouver les détails de coupures d'eau à venir
    details = PlanningDetail.objects.filter(
        designation__nom='Coupure d\'eau',
        planning__date__gte=today,
        planning__date__lte=date_limite,
        point_eau__isnull=False
    ).select_related(
        'planning__ouvrage',
        'point_eau',
        'point_eau__parcelle__village__fokontany__commune'
    )

    posts_crees = 0

    for detail in details:
        content_type = ContentType.objects.get_for_model(PlanningDetail)
        existe = Post.objects.filter(
            content_type=content_type,
            object_id=detail.id,
            type_post='coupure_eau'
        ).exists()

        if existe:
            continue

        point_eau = detail.point_eau
        contact = point_eau.contact if hasattr(point_eau, 'contact') and point_eau.contact else 'Non renseigné'
        commune = 'Non liée'
        if point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany and point_eau.parcelle.village.fokontany.commune:
            commune = point_eau.parcelle.village.fokontany.commune.nom_commune

        jours_restants = (detail.planning.date - today).days
        titre = f"🚫 Coupure d'eau programmée - {point_eau.nomabonne}"

        contenu = f"""
<div class="bg-error bg-opacity-10 border-l-4 border-error p-4 rounded">
    <h4 class="font-bold text-error mb-2">⚠️ Coupure d'eau prévue</h4>
    <p><strong>Point d'eau:</strong> {point_eau.nomabonne}</p>
    <p><strong>Ouvrage:</strong> {detail.planning.ouvrage.nom_ouvrage if detail.planning.ouvrage else 'N/A'}</p>
    <p><strong>Commune:</strong> {commune}</p>
    <p><strong>Contact:</strong> <span class="badge badge-info">{contact}</span></p>
    <p><strong>Date prévue:</strong> {detail.planning.date.strftime('%d/%m/%Y')}</p>
    <p><strong>Échéance:</strong> Dans <span class="badge badge-error">{jours_restants} jour{'s' if jours_restants > 1 else ''}</span></p>
</div>

<div class="alert alert-warning mt-4">
    <i class="fas fa-exclamation-triangle mr-2"></i>
    <div>
        <p class="font-semibold">Action requise :</p>
        <ul class="list-disc ml-6">
            <li>Prévenir le responsable du point d'eau</li>
            <li>Confirmer la date de la coupure</li>
            <li>Vérifier le motif de la coupure (impayés, maintenance, etc.)</li>
        </ul>
    </div>
</div>
"""

        Post.objects.create(
            type_post='coupure_eau',
            titre=titre,
            contenu=contenu,
            auteur_employe=None, auteur_nom="Système",
            ouvrage=detail.planning.ouvrage,
            priorite=True,
            content_type=content_type,
            object_id=detail.id,
            tags=f"coupure,eau,urgent,contact:{contact}"
        )

        posts_crees += 1

    return JsonResponse({
        'success': True,
        'message': f'{posts_crees} post(s) de coupures d\'eau créé(s)',
        'count': posts_crees
    })


def generer_posts_remises_eau(request):
    """Génère automatiquement les posts pour les remises en eau à venir"""
    from apps.planning.models import PlanningDetail
    from apps.billing.models import PointEau
    from datetime import timedelta

    employe_systeme = Employe.objects.filter(date_debauchage__isnull=True).first()
    if not employe_systeme:
        return JsonResponse({'success': False, 'error': 'Aucun employé trouvé'}, status=500)

    today = timezone.now().date()
    date_limite = today + timedelta(days=7)

    # Trouver les détails de remises en eau à venir
    details = PlanningDetail.objects.filter(
        designation__nom='Remise en eau',
        planning__date__gte=today,
        planning__date__lte=date_limite,
        point_eau__isnull=False
    ).select_related(
        'planning__ouvrage',
        'point_eau',
        'point_eau__parcelle__village__fokontany__commune'
    )

    posts_crees = 0

    for detail in details:
        content_type = ContentType.objects.get_for_model(PlanningDetail)
        existe = Post.objects.filter(
            content_type=content_type,
            object_id=detail.id,
            type_post='remise_eau'
        ).exists()

        if existe:
            continue

        point_eau = detail.point_eau
        contact = point_eau.contact if hasattr(point_eau, 'contact') and point_eau.contact else 'Non renseigné'
        commune = 'Non liée'
        if point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany and point_eau.parcelle.village.fokontany.commune:
            commune = point_eau.parcelle.village.fokontany.commune.nom_commune

        jours_restants = (detail.planning.date - today).days
        titre = f"✅ Remise en eau programmée - {point_eau.nomabonne}"

        contenu = f"""
<div class="bg-accent bg-opacity-10 border-l-4 border-accent p-4 rounded">
    <h4 class="font-bold text-accent mb-2">💧 Remise en eau prévue</h4>
    <p><strong>Point d'eau:</strong> {point_eau.nomabonne}</p>
    <p><strong>Ouvrage:</strong> {detail.planning.ouvrage.nom_ouvrage if detail.planning.ouvrage else 'N/A'}</p>
    <p><strong>Commune:</strong> {commune}</p>
    <p><strong>Contact:</strong> <span class="badge badge-info">{contact}</span></p>
    <p><strong>Date prévue:</strong> {detail.planning.date.strftime('%d/%m/%Y')}</p>
    <p><strong>Échéance:</strong> Dans <span class="badge badge-accent">{jours_restants} jour{'s' if jours_restants > 1 else ''}</span></p>
</div>

<div class="alert alert-success mt-4">
    <i class="fas fa-check-circle mr-2"></i>
    <div>
        <p class="font-semibold">Action requise :</p>
        <ul class="list-disc ml-6">
            <li>Prévenir le responsable du point d'eau</li>
            <li>Confirmer la date de la remise en eau</li>
            <li>Vérifier que les conditions de remise en service sont remplies</li>
        </ul>
    </div>
</div>
"""

        Post.objects.create(
            type_post='remise_eau',
            titre=titre,
            contenu=contenu,
            auteur_employe=None, auteur_nom="Système",
            ouvrage=detail.planning.ouvrage,
            priorite=False,
            content_type=content_type,
            object_id=detail.id,
            tags=f"remise,eau,contact:{contact}"
        )

        posts_crees += 1

    return JsonResponse({
        'success': True,
        'message': f'{posts_crees} post(s) de remises en eau créé(s)',
        'count': posts_crees
    })
