"""
API mobile pour le workflow Volumetrique (app Android Hydria Terrain).

Ne reimplemente aucune regle metier : reutilise telles quelles les
fonctions du web (calculer_montant_releve, _get_allowed_ouvrage_ids,
_get_releve_facturation_period). Le pointage DiameX (3e onglet mobile)
n'est PAS couvert ici - c'est un chantier distinct (voir le dashboard
comptable /comptabilite/dashboard-paiements-volume/, qui fonctionne par
auto-pointage mensuel par ouvrage, pas par correspondance manuelle
facture <-> ligne DiameX comme l'onglet mobile le proposait). Le champ
"diamex" renvoye ici reste donc toujours vide : l'onglet Pointage de
l'appli restera visible mais non fonctionnel tant que ce chantier n'est
pas traite separement.
"""
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.views_mobile_auth import mobile_auth_required
from apps.billing.models import Releve
from apps.billing.views_facturation import _get_allowed_ouvrage_ids, calculer_montant_releve
from apps.billing.views_encaissement import _get_releve_facturation_period
from apps.organization.models import Journal, Ouvrage


def _version_of(releve):
    """
    Jeton de verrouillage optimiste utilise par la synchro mobile : si le
    releve a change cote serveur entre le telechargement et l'envoi d'une
    action, la version ne correspond plus et la synchro doit renvoyer un
    conflit (409) plutot que d'ecraser silencieusement une modification
    faite ailleurs entre-temps (web, autre telephone).
    """
    return releve.updated_at.isoformat() if releve.updated_at else '0'


def serialize_mobile_facture(releve, mois):
    """
    Forme exacte attendue par VolumeWorkflow/VolumeRepository/VolumeActivity
    cote Android (voir factures[] du pack, et recap() qui lit ouvrage_id/
    ouvrage/mois/type_pe/idxls/abonne/numero/montant sur chaque ligne).
    """
    return {
        'id': str(releve.id),
        'version': _version_of(releve),
        'numero': releve.numero_facture or '',
        'idxls': releve.point_eau.idxls if releve.point_eau else '',
        'abonne': releve.abonne or '',
        'mois': mois,
        'ouvrage_id': str(releve.point_eau.ouvrage_id) if releve.point_eau and releve.point_eau.ouvrage_id else '',
        'ouvrage': releve.point_eau.ouvrage.nom_ouvrage if releve.point_eau and releve.point_eau.ouvrage else '',
        'type_pe': releve.point_eau.type_point_eau.nom_type if releve.point_eau and releve.point_eau.type_point_eau else '',
        'montant': str(releve.montant) if releve.montant is not None else None,
        'erreur_calcul': '',
        'imprimee': bool(releve.facture_imprimee),
        'encaissee': releve.datepaiement is not None,
        'pointee': bool(releve.numeroDiameX),
        'validee': releve.montant is not None,
        'numero_diamex': releve.numeroDiameX or '',
        'base_diamex': releve.baseDiameX or '',
    }


@mobile_auth_required
@require_http_methods(["GET"])
def api_mobile_volume_bootstrap(request):
    """
    GET /facturation/api/mobile/volume/bootstrap/?ouvrage_id=&mois=

    - Ni ouvrage_id ni mois : liste des ouvrages autorises (alimente le
      selecteur d'ouvrage de l'onglet Facturation).
    - ouvrage_id + mois : lot de facturation d'un ouvrage pour ce mois de
      facture (recalcule a la volee les montants non encore enregistres,
      via calculer_montant_releve - identique au web).
    - mois seul (pas d'ouvrage_id) : factures a encaisser, tous ouvrages
      autorises confondus, pour ce mois de facture (equivalent du filtre
      "Tous les ouvrages" de la page web Encaissement).
    """
    try:
        ouvrage_id = (request.GET.get('ouvrage_id') or '').strip()
        mois = (request.GET.get('mois') or '').strip()
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        if not ouvrage_id and not mois:
            ouvrages = Ouvrage.objects.filter(id__in=allowed_ouvrage_ids).order_by('nom_ouvrage')
            return JsonResponse({
                'success': True,
                'ouvrages': [{'id': str(o.id), 'nom': o.nom_ouvrage} for o in ouvrages],
            })

        if not mois:
            return JsonResponse({'success': False, 'error': 'Mois requis (format AAAA-MM)'}, status=400)
        try:
            annee, m = (int(part) for part in mois.split('-'))
        except (ValueError, AttributeError):
            return JsonResponse({'success': False, 'error': 'Format de mois invalide (attendu AAAA-MM)'}, status=400)

        journaux = list(Journal.objects.all().order_by('code'))
        journaux_data = [
            {'code': j.code or '', 'nom': j.nom_journal, 'base': j.base.nom_base if j.base else ''}
            for j in journaux
        ]

        if ouvrage_id:
            if not Ouvrage.objects.filter(id=ouvrage_id, id__in=allowed_ouvrage_ids).exists():
                return JsonResponse({'success': False, 'error': 'Ouvrage non autorise'}, status=403)

            # Le mois de facture porte sur les releves du mois precedent
            # (meme regle que api_calculer_factures cote web).
            mois_releve = m - 1
            annee_releve = annee
            if mois_releve == 0:
                mois_releve = 12
                annee_releve -= 1

            releves = Releve.objects.filter(
                point_eau__ouvrage_id=ouvrage_id,
                datereleve__year=annee_releve,
                datereleve__month=mois_releve,
            ).select_related('point_eau', 'point_eau__type_point_eau', 'point_eau__ouvrage')

            factures = []
            for releve in releves:
                entry = serialize_mobile_facture(releve, mois)
                if releve.montant is None:
                    resultat = calculer_montant_releve(releve)
                    if resultat['success']:
                        entry['montant'] = str(resultat['montant_total'])
                    else:
                        entry['erreur_calcul'] = resultat['error']
                factures.append(entry)

            return JsonResponse({
                'success': True,
                'ouvrage_id': str(ouvrage_id),
                'mois': mois,
                'generated_at': timezone.now().isoformat(),
                'factures': factures,
                'journaux': journaux_data,
                'diamex': [],
            })

        # Pas d'ouvrage precise : encaissement tous ouvrages confondus.
        factures_qs = Releve.objects.filter(
            montant__isnull=False,
            datepaiement__isnull=True,
        ).filter(
            Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
        ).filter(
            point_eau__ouvrage_id__in=allowed_ouvrage_ids
        ).select_related('point_eau', 'point_eau__type_point_eau', 'point_eau__ouvrage')

        factures = []
        for releve in factures_qs:
            annee_f, mois_f = _get_releve_facturation_period(releve)
            if annee_f is None or f'{annee_f:04d}-{mois_f:02d}' != mois:
                continue
            factures.append(serialize_mobile_facture(releve, mois))

        return JsonResponse({
            'success': True,
            'ouvrage_id': '',
            'mois': mois,
            'generated_at': timezone.now().isoformat(),
            'factures': factures,
            'journaux': journaux_data,
            'diamex': [],
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
