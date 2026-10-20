"""
Signaux Django pour créer automatiquement des posts dans le fil d'actualité
lors de changements dans les paiements forfaitaires et réparations.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal

from apps.planning.models import Planning, PlanningDetail
from apps.feed.models import Post
from apps.employees.models import Employe


def get_system_user():
    """Retourne None pour les posts automatiques (affichera 'Système')"""
    return None


def calculate_paiement_stats():
    """Calcule les statistiques globales des paiements forfaitaires"""
    from django.db.models import Sum, Count, Q
    from apps.billing.models import PointEau, ModaliteGestion
    from apps.planning.models import Designation, PlanningDetail

    # Filtrer les modalités forfaitaires ET mixtes actives (comme le dashboard)
    modalites_forfait = ModaliteGestion.objects.filter(
        modalitepaiement__in=['forfaitaire', 'mixte'],  # Inclure mixte aussi
        date_fin__isnull=True
    )

    # Stats globales
    total_modalites = modalites_forfait.count()

    # Compter les points d'eau avec tarif forfaitaire (modalité forfaitaire OU mixte)
    points_eau_forfait = PointEau.objects.filter(
        ouvrage__modalites_gestion__modalitepaiement__in=['forfaitaire', 'mixte'],
        ouvrage__modalites_gestion__date_fin__isnull=True,
        tarifforfaitaire__isnull=False
    ).distinct()

    nb_points_eau = points_eau_forfait.count()

    # Calculer montant prévu (tarif * 4 trimestres)
    montant_prevu = sum([
        Decimal(str(pe.tarifforfaitaire)) * 4
        for pe in points_eau_forfait
        if pe.tarifforfaitaire
    ]) or Decimal('0')

    # Calculer montant payé via les plannings (année courante + réellement payés)
    try:
        import pytz
        from datetime import datetime

        designation_forfait = Designation.objects.filter(
            nom__icontains='forfait'  # Corrigé: nom au lieu de nom_designation
        ).first()

        if designation_forfait:
            # Filtrer par année courante et numeroDiameX non null (réellement payé)
            annee_courante = timezone.now().year
            tz_madagascar = pytz.timezone('Indian/Antananarivo')

            details_paiement = PlanningDetail.objects.filter(
                designation=designation_forfait,
                numeroDiameX__isnull=False  # Seulement les paiements réellement payés
            ).select_related('planning')

            # Filtrer par année en Python (conversion timezone)
            montant_paye = Decimal('0')
            for detail in details_paiement:
                if detail.planning and detail.planning.date:
                    date_aware = detail.planning.date
                    if date_aware.tzinfo:
                        date_madagascar = date_aware.astimezone(tz_madagascar)
                    else:
                        date_madagascar = tz_madagascar.localize(date_aware)

                    if date_madagascar.date().year == annee_courante:
                        montant_paye += detail.montant if detail.montant else Decimal('0')
        else:
            montant_paye = Decimal('0')
    except:
        montant_paye = Decimal('0')

    # Taux de recouvrement
    taux_recouvrement = 0
    if montant_prevu > 0:
        taux_recouvrement = int(round((float(montant_paye) / float(montant_prevu)) * 100))

    return {
        'total_modalites': total_modalites,
        'nb_points_eau': nb_points_eau,
        'montant_prevu': montant_prevu,
        'montant_paye': montant_paye,
        'taux_recouvrement': taux_recouvrement,
    }


def calculate_reparation_stats():
    """Calcule les statistiques globales des réparations"""
    from django.db.models import Count, Q
    from apps.planning.models import TypeActivite, Activite

    # Récupérer l'année en cours
    current_year = timezone.now().year

    # Compter les réparations/réhabilitations via les plannings
    # Types d'activités de réparation
    try:
        type_reparation = TypeActivite.objects.filter(nom__icontains='réparation').first()
        type_rehabilitation = TypeActivite.objects.filter(nom__icontains='réhabilitation').first()

        nb_reparations = 0
        nb_rehabilitations = 0
        nb_pannes = 0

        if type_reparation:
            # Activités de réparation
            activites_reparation = Activite.objects.filter(type_activite=type_reparation)
            nb_reparations = Planning.objects.filter(
                activite__in=activites_reparation,
                date__year=current_year
            ).count()

        if type_rehabilitation:
            # Activités de réhabilitation
            activites_rehabilitation = Activite.objects.filter(type_activite=type_rehabilitation)
            nb_rehabilitations = Planning.objects.filter(
                activite__in=activites_rehabilitation,
                date__year=current_year
            ).count()

        # Compter les pannes
        activites_panne = Activite.objects.filter(nom__icontains='panne')
        nb_pannes = Planning.objects.filter(
            activite__in=activites_panne,
            date__year=current_year
        ).count()

        # Total d'interventions
        total_interventions = nb_reparations + nb_rehabilitations + nb_pannes

        # Compter les ouvrages uniques concernés
        ouvrages_concernes = Planning.objects.filter(
            Q(activite__in=activites_reparation) |
            Q(activite__in=activites_rehabilitation) |
            Q(activite__in=activites_panne),
            date__year=current_year,
            ouvrage__isnull=False
        ).values('ouvrage').distinct().count()

    except Exception as e:
        nb_reparations = 0
        nb_rehabilitations = 0
        nb_pannes = 0
        total_interventions = 0
        ouvrages_concernes = 0

    return {
        'nb_reparations': nb_reparations,
        'nb_rehabilitations': nb_rehabilitations,
        'nb_pannes': nb_pannes,
        'total_interventions': total_interventions,
        'ouvrages_concernes': ouvrages_concernes,
        'annee': current_year,
    }


def create_or_update_paiement_forfaitaire_post():
    """Crée ou met à jour le post quotidien des paiements forfaitaires"""
    stats = calculate_paiement_stats()

    # Chercher un post existant pour aujourd'hui
    today = timezone.now().date()
    existing_post = Post.objects.filter(
        type_post='paiement_forfaitaire',
        date_creation__date=today
    ).first()

    # Formatter le contenu
    titre = f"📊 Paiements Forfaitaires - {today.strftime('%d/%m/%Y')}"
    contenu = f"""
**Statistiques des Paiements Forfaitaires**

📌 **Vue d'ensemble**
- Total modalités forfaitaires actives : **{stats['total_modalites']:,}**
- Points d'eau avec tarif forfaitaire : **{stats['nb_points_eau']:,}**

💰 **Montants**
- Montant prévu total : **{stats['montant_prevu']:,.0f} Ar**
- Montant payé total : **{stats['montant_paye']:,.0f} Ar**
- Taux de recouvrement : **{stats['taux_recouvrement']}%**

🔗 [Voir le dashboard détaillé](/dashboard/paiements-forfaitaires/)
"""

    resume = f"Taux de recouvrement : {stats['taux_recouvrement']}% | {stats['nb_points_eau']} points d'eau"

    tags = f"paiement_forfaitaire,stats,montant:{stats['montant_paye']},taux:{stats['taux_recouvrement']}"

    if existing_post:
        # Mettre à jour le post existant
        existing_post.titre = titre
        existing_post.contenu = contenu
        existing_post.resume = resume
        existing_post.tags = tags
        existing_post.save()
    else:
        # Créer un nouveau post
        Post.objects.create(
            type_post='paiement_forfaitaire',
            statut='actif',
            titre=titre,
            contenu=contenu,
            resume=resume,
            auteur_employe=None,  # Post automatique, pas d'auteur
            auteur_user=None,
            tags=tags,
            priorite=False,
        )


def create_or_update_reparation_post():
    """Crée ou met à jour le post quotidien des réparations"""
    stats = calculate_reparation_stats()

    # Chercher un post existant pour aujourd'hui
    today = timezone.now().date()
    existing_post = Post.objects.filter(
        type_post='planning',
        tags__contains='reparations',
        date_creation__date=today
    ).first()

    # Formatter le contenu
    titre = f"🔧 Suivi Réparations & Réhabilitations - {today.strftime('%d/%m/%Y')}"

    contenu = f"""
**Suivi des Réparations - Année {stats['annee']}**

🔧 **Interventions réalisées**
- Réparations : **{stats['nb_reparations']}**
- Réhabilitations : **{stats['nb_rehabilitations']}**
- Réparations de pannes : **{stats['nb_pannes']}**
- **Total interventions : {stats['total_interventions']}**

🏗️ **Ouvrages concernés**
- Ouvrages ayant bénéficié d'interventions : **{stats['ouvrages_concernes']}**

🔗 [Voir le suivi détaillé](/plannings/reparations/)
"""

    resume = f"{stats['total_interventions']} interventions | {stats['ouvrages_concernes']} ouvrages concernés"

    tags = f"reparations,stats,annee:{stats['annee']},interventions:{stats['total_interventions']}"

    if existing_post:
        # Mettre à jour le post existant
        existing_post.titre = titre
        existing_post.contenu = contenu
        existing_post.resume = resume
        existing_post.tags = tags
        existing_post.save()
    else:
        # Créer un nouveau post
        Post.objects.create(
            type_post='planning',
            statut='actif',
            titre=titre,
            contenu=contenu,
            resume=resume,
            auteur_employe=None,  # Post automatique, pas d'auteur
            auteur_user=None,
            tags=tags,
            priorite=stats['total_interventions'] > 10,  # Prioritaire si beaucoup d'interventions
        )


def calculate_releves_stats(today):
    """Calcule les statistiques des relevés terrain saisis aujourd'hui"""
    from apps.billing.models import Releve

    releves_du_jour = Releve.objects.filter(terrain_captured_at__date=today)
    total = releves_du_jour.count()
    avec_photo = releves_du_jour.exclude(photo_releve='').filter(photo_releve__isnull=False).count()
    points_concernes = releves_du_jour.values('point_eau').distinct().count()

    return {
        'total': total,
        'avec_photo': avec_photo,
        'points_concernes': points_concernes,
    }


def create_or_update_releves_post():
    """Crée ou met à jour le résumé quotidien des relevés terrain"""
    today = timezone.now().date()
    stats = calculate_releves_stats(today)
    if stats['total'] == 0:
        return

    existing_post = Post.objects.filter(type_post='releve_terrain', date_creation__date=today).first()

    titre = f"💧 Relevés du jour - {today.strftime('%d/%m/%Y')}"
    contenu = f"""
**Relevés terrain saisis aujourd'hui**

- Relevés saisis : **{stats['total']}**
- Dont avec photo : **{stats['avec_photo']}**
- Points d'eau concernés : **{stats['points_concernes']}**
"""
    resume = f"{stats['total']} relevé(s) | {stats['points_concernes']} point(s) d'eau"
    tags = f"releve_terrain,stats,total:{stats['total']}"

    if existing_post:
        existing_post.titre = titre
        existing_post.contenu = contenu
        existing_post.resume = resume
        existing_post.tags = tags
        existing_post.save()
    else:
        Post.objects.create(
            type_post='releve_terrain',
            statut='actif',
            titre=titre,
            contenu=contenu,
            resume=resume,
            auteur_employe=None,
            auteur_user=None,
            tags=tags,
            priorite=False,
        )


def calculate_gps_terrain_stats(today):
    """Calcule les statistiques des positions GPS mises à jour aujourd'hui"""
    from apps.navigation_terrain.models import GeoPositionAudit

    audits_du_jour = GeoPositionAudit.objects.filter(received_at__date=today)
    total = audits_du_jour.count()
    entites_concernees = audits_du_jour.values('entity_kind', 'entity_uuid').distinct().count()

    return {
        'total': total,
        'entites_concernees': entites_concernees,
    }


def create_or_update_gps_terrain_post():
    """Crée ou met à jour le résumé quotidien des positions GPS terrain"""
    today = timezone.now().date()
    stats = calculate_gps_terrain_stats(today)
    if stats['total'] == 0:
        return

    existing_post = Post.objects.filter(type_post='gps_terrain', date_creation__date=today).first()

    titre = f"📍 Positions GPS mises à jour - {today.strftime('%d/%m/%Y')}"
    contenu = f"""
**Positions GPS mises à jour aujourd'hui**

- Mises à jour de position : **{stats['total']}**
- Entités concernées : **{stats['entites_concernees']}**
"""
    resume = f"{stats['total']} mise(s) à jour | {stats['entites_concernees']} entité(s)"
    tags = f"gps_terrain,stats,total:{stats['total']}"

    if existing_post:
        existing_post.titre = titre
        existing_post.contenu = contenu
        existing_post.resume = resume
        existing_post.tags = tags
        existing_post.save()
    else:
        Post.objects.create(
            type_post='gps_terrain',
            statut='actif',
            titre=titre,
            contenu=contenu,
            resume=resume,
            auteur_employe=None,
            auteur_user=None,
            tags=tags,
            priorite=False,
        )


def calculate_photos_terrain_stats(today):
    """Calcule les statistiques des photos de repères ajoutées aujourd'hui"""
    from apps.navigation_terrain.models import ReperePhoto

    photos_du_jour = ReperePhoto.objects.filter(created_at__date=today)
    total = photos_du_jour.count()
    reperes_concernes = photos_du_jour.values('repere').distinct().count()

    return {
        'total': total,
        'reperes_concernes': reperes_concernes,
    }


def create_or_update_photos_terrain_post():
    """Crée ou met à jour le résumé quotidien des photos terrain"""
    today = timezone.now().date()
    stats = calculate_photos_terrain_stats(today)
    if stats['total'] == 0:
        return

    existing_post = Post.objects.filter(type_post='photo_terrain', date_creation__date=today).first()

    titre = f"📷 Nouvelles photos terrain - {today.strftime('%d/%m/%Y')}"
    contenu = f"""
**Photos terrain ajoutées aujourd'hui**

- Photos ajoutées : **{stats['total']}**
- Repères concernés : **{stats['reperes_concernes']}**
"""
    resume = f"{stats['total']} photo(s) | {stats['reperes_concernes']} repère(s)"
    tags = f"photo_terrain,stats,total:{stats['total']}"

    if existing_post:
        existing_post.titre = titre
        existing_post.contenu = contenu
        existing_post.resume = resume
        existing_post.tags = tags
        existing_post.save()
    else:
        Post.objects.create(
            type_post='photo_terrain',
            statut='actif',
            titre=titre,
            contenu=contenu,
            resume=resume,
            auteur_employe=None,
            auteur_user=None,
            tags=tags,
            priorite=False,
        )


# Signal pour détecter les nouveaux relevés terrain
@receiver(post_save, sender='billing.Releve')
def on_releve_save(sender, instance, created, **kwargs):
    """Déclenché quand un relevé est créé — met à jour le résumé du jour"""
    if created:
        create_or_update_releves_post()


# Signal pour détecter les changements de position GPS terrain
@receiver(post_save, sender='navigation_terrain.GeoPositionAudit')
def on_geo_position_audit_save(sender, instance, created, **kwargs):
    """Déclenché à chaque changement de position GPS — met à jour le résumé du jour"""
    if created:
        create_or_update_gps_terrain_post()


# Signal pour détecter les nouvelles photos de repères terrain
@receiver(post_save, sender='navigation_terrain.ReperePhoto')
def on_repere_photo_save(sender, instance, created, **kwargs):
    """Déclenché quand une photo de repère est ajoutée — met à jour le résumé du jour"""
    if created:
        create_or_update_photos_terrain_post()


# Signal pour détecter les changements dans les modalités de gestion
@receiver(post_save, sender='billing.ModaliteGestion')
def on_modalite_gestion_save(sender, instance, created, **kwargs):
    """Déclenché quand une modalité de gestion est créée ou modifiée"""
    # Ne créer/mettre à jour le post que pour les modalités forfaitaires
    if instance.modalitepaiement == 'forfaitaire':
        # Vérifier si le montant_paye a changé
        if not created:
            # Créer ou mettre à jour le post quotidien
            create_or_update_paiement_forfaitaire_post()


# Signal pour détecter les changements dans les inspections
@receiver(post_save, sender='inspections.Inspection')
def on_inspection_save(sender, instance, created, **kwargs):
    """Déclenché quand une inspection est créée ou modifiée"""
    # Créer ou mettre à jour le post quotidien des réparations
    create_or_update_reparation_post()


# Signal pour détecter les changements dans les plannings de réparation
@receiver(post_save, sender=Planning)
def on_planning_save(sender, instance, created, **kwargs):
    """Déclenché quand un planning est créé ou modifié"""
    # Vérifier si c'est une activité de réparation ou réhabilitation
    type_obj = None
    if instance.activite:
        type_obj = getattr(instance.activite, 'type_activite', None) or getattr(instance.activite, 'type_activites', None)
    if type_obj and getattr(type_obj, 'nomtype', None):
        import unicodedata
        type_nom = type_obj.nomtype.lower()
        type_nom_ascii = unicodedata.normalize("NFKD", type_nom).encode("ascii", "ignore").decode("ascii")
        if 'reparation' in type_nom_ascii or 'rehabilitation' in type_nom_ascii:
            # Creer ou mettre a jour le post quotidien des reparations
            create_or_update_reparation_post()
