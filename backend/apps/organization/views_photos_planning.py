"""Import en lot de photos rattachees a des lignes de planning.

Arborescence attendue : [Base /] CR. Commune / Ouvrage / Activite / photos.
- L'ouvrage est retrouve par le resolveur existant (commune + nom approximatif).
- L'activite (= fiche de poste du planning) est retrouvee par le nom du dossier.
- Si une ligne de planning (ouvrage + activite + jour de la 1re photo) existe, les photos s'y
  rattachent ; sinon elle est creee : date = 1re photo, employe = premier responsable de
  l'ouvrage, statut « termine ».
"""
import base64
import json
import os
import uuid
from datetime import datetime, timedelta

import pytz
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.employees.models import EmployeOuvrages
from apps.employees.models_evaluation import FichePoste
from apps.employees.permissions import employe_required, filter_queryset_by_permissions
from apps.organization.models import Ouvrage
from apps.planning.models import Planning
from apps.planning.views_reparations_apis import _parse_planning_photo_payload

from .views import _construire_resolveur, _jetons_dossier, _score_ouvrage

TZ = pytz.timezone('Indian/Antananarivo')
NB_PLANNINGS_PAR_OUVRAGE = 40
TAILLE_MAX_PHOTO = 10 * 1024 * 1024


def _parse_date_locale(texte):
    """'YYYY-MM-DD HH:MM:SS' (ou 'YYYY-MM-DD') en heure de Madagascar -> datetime aware, ou None."""
    texte = str(texte or '').strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return TZ.localize(datetime.strptime(texte, fmt))
        except ValueError:
            continue
    return None


def _premier_responsable(ouvrage_id, quand):
    """Premier responsable de l'ouvrage a la date donnee (principal d'abord, puis le plus ancien)."""
    jour = quand.astimezone(TZ).date()
    from django.db.models import Q
    lien = (
        EmployeOuvrages.objects.filter(ouvrage_id=ouvrage_id, date_debut__lte=jour)
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour))
        .select_related('employe')
        .order_by('-est_responsable_principal', 'date_debut', 'created_at')
        .first()
    )
    if lien is None:  # aucun responsable a cette date : le premier connu pour cet ouvrage
        lien = (
            EmployeOuvrages.objects.filter(ouvrage_id=ouvrage_id).select_related('employe')
            .order_by('-est_responsable_principal', 'date_debut', 'created_at').first()
        )
    return lien.employe if lien else None


def _classer_activites(nom_dossier, fiches):
    """Fiches de poste classees par ressemblance avec le nom du dossier."""
    jetons = _jetons_dossier(nom_dossier)
    classees = []
    for fiche in fiches:
        score = _score_ouvrage(jetons, _jetons_dossier(fiche['tache']))
        if score >= 0.4:
            classees.append({'id': fiche['id'], 'nom': fiche['tache'], 'score': round(score, 2)})
    classees.sort(key=lambda c: -c['score'])
    return classees[:6]


@employe_required
@require_http_methods(['POST'])
def api_photos_planning_analyser(request):
    """Reçoit {"dossiers": [{"chemin": "...", "date_premiere_photo": "YYYY-MM-DD HH:MM:SS"}, ...]}.

    Pour chaque dossier : ouvrages candidats (avec leurs plannings recents) et activites candidates ;
    `activites` donne le catalogue complet pour le choix manuel.
    """
    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    resoudre = _construire_resolveur(request.user)
    fiches = [
        {'id': str(f.id), 'tache': f.tache, 'dans_planning': f.dans_planning}
        for f in FichePoste.objects.all().order_by('-dans_planning', 'tache')
    ]
    cache_plannings = {}
    resultats = []
    for entree in payload.get('dossiers', [])[:5000]:
        chemin = entree.get('chemin') if isinstance(entree, dict) else str(entree)
        date_photo = _parse_date_locale(entree.get('date_premiere_photo')) if isinstance(entree, dict) else None
        resultat, segments, idx_ouvrage, _meilleurs = resoudre(chemin)
        nom_activite = segments[idx_ouvrage + 1] if idx_ouvrage is not None and idx_ouvrage + 1 < len(segments) else None
        resultat['activite_dossier'] = nom_activite
        resultat['date_premiere_photo'] = date_photo.strftime('%Y-%m-%d %H:%M:%S') if date_photo else None
        resultat['activites_candidates'] = _classer_activites(nom_activite, fiches) if nom_activite else []
        activites = resultat['activites_candidates']
        ecart = activites[0]['score'] - activites[1]['score'] if len(activites) > 1 else 1
        resultat['activite_auto'] = (
            activites[0]['id'] if activites and (
                (activites[0]['score'] >= 0.85 and ecart >= 0.04) or (activites[0]['score'] >= 0.7 and ecart >= 0.1)
            ) else ''
        )
        for cand in resultat['candidats']:
            if cand['id'] not in cache_plannings:
                accessibles = filter_queryset_by_permissions(Ouvrage.objects.filter(pk=cand['id']), request.user)
                if not accessibles.exists():
                    cache_plannings[cand['id']] = []
                    continue
                lignes = (
                    Planning.objects.filter(ouvrage_id=cand['id'], fiche_poste__isnull=False)
                    .select_related('employe').order_by('-date')[:NB_PLANNINGS_PAR_OUVRAGE]
                )
                cache_plannings[cand['id']] = [
                    {
                        'id': str(p.id),
                        'fiche_id': str(p.fiche_poste_id),
                        'jour': p.date.astimezone(TZ).strftime('%Y-%m-%d'),
                        'date': p.date.astimezone(TZ).strftime('%d/%m/%Y'),
                        'statut': p.statut or '',
                        'employe': (p.employe.surnom or p.employe.nom) if p.employe else '',
                        'nb_photos': len(_parse_planning_photo_payload(p.photo)),
                    }
                    for p in lignes
                ]
            cand['plannings'] = cache_plannings[cand['id']]
        resultats.append(resultat)
    return JsonResponse({'success': True, 'resultats': resultats, 'activites': fiches})


@employe_required
@require_http_methods(['POST'])
def api_photos_planning_preparer(request):
    """Cree (ou retrouve) la ligne de planning d'un dossier : {ouvrage_id, fiche_poste_id, date}.

    Idempotent : relancer l'import ne cree pas de doublon (meme ouvrage + activite + jour).
    """
    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    ouvrage = filter_queryset_by_permissions(Ouvrage.objects.filter(pk=payload.get('ouvrage_id')), request.user).first()
    if not ouvrage:
        return JsonResponse({'success': False, 'error': 'Ouvrage introuvable ou accès refusé'}, status=403)
    fiche = FichePoste.objects.filter(pk=payload.get('fiche_poste_id')).select_related('type_activites').first()
    if not fiche:
        return JsonResponse({'success': False, 'error': 'Activité introuvable'}, status=400)
    quand = _parse_date_locale(payload.get('date'))
    if not quand:
        return JsonResponse({'success': False, 'error': 'Date de la première photo invalide'}, status=400)

    debut = TZ.localize(datetime.combine(quand.astimezone(TZ).date(), datetime.min.time()))
    with transaction.atomic():
        existant = Planning.objects.filter(
            ouvrage=ouvrage, fiche_poste=fiche, date__gte=debut, date__lt=debut + timedelta(days=1),
        ).order_by('date').first()
        if existant:
            return JsonResponse({'success': True, 'planning_id': str(existant.id), 'cree': False})
        employe = _premier_responsable(ouvrage.id, quand)
        planning = Planning.objects.create(
            date=quand,
            ouvrage=ouvrage,
            fiche_poste=fiche,
            type_activite=fiche.type_activites,
            employe=employe,
            statut='termine',
            remarque="Créé par import de photos en lot",
        )
    return JsonResponse({
        'success': True, 'planning_id': str(planning.id), 'cree': True,
        'employe': (employe.surnom or employe.nom) if employe else None,
    })


@employe_required
@require_http_methods(['POST'])
def api_photos_planning_importer(request):
    """Ajoute UNE photo a un planning : champs planning_id, fichier, taille_origine."""
    planning = Planning.objects.filter(pk=request.POST.get('planning_id')).first()
    fichier = request.FILES.get('fichier')
    if not planning or not fichier:
        return JsonResponse({'success': False, 'error': 'Planning ou fichier manquant'}, status=400)
    if not planning.ouvrage_id or not filter_queryset_by_permissions(
        Ouvrage.objects.filter(pk=planning.ouvrage_id), request.user
    ).exists():
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)

    extension = os.path.splitext(fichier.name or '')[1].lower()
    if not ((fichier.content_type or '').startswith('image/') or extension in {
            '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}):
        return JsonResponse({'success': False, 'error': "Ce n'est pas une image"}, status=400)
    if fichier.size > TAILLE_MAX_PHOTO:
        return JsonResponse({'success': False, 'error': 'Image trop lourde (10 Mo max)'}, status=413)

    taille_origine = int(request.POST.get('taille_origine') or fichier.size)
    contenu = fichier.read()
    type_mime = fichier.content_type if (fichier.content_type or '').startswith('image/') else 'image/jpeg'
    with transaction.atomic():
        planning = Planning.objects.select_for_update().get(pk=planning.pk)
        photos = _parse_planning_photo_payload(planning.photo)
        if any(p.get('name') == fichier.name and int(p.get('originalSize') or 0) == taille_origine for p in photos):
            return JsonResponse({'success': True, 'ignore': True})
        photos.append({
            'id': uuid.uuid4().hex,
            'name': (fichier.name or 'photo.jpg')[:180],
            'data': f'data:{type_mime};base64,{base64.b64encode(contenu).decode("ascii")}',
            'size': len(contenu),
            'originalSize': taille_origine,
            'type': type_mime,
            'date': datetime.now(TZ).isoformat(),
        })
        planning.photo = json.dumps(photos, ensure_ascii=True)
        planning.save(update_fields=['photo', 'updated_at'])
    return JsonResponse({'success': True, 'ignore': False, 'total_photos': len(photos)})
