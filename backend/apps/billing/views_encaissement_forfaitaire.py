"""
Encaissement des paiements forfaitaires par la caissière.

Étape 1 du circuit (rapide) : la caissière encaisse -> `date_encaissement` est posée
sur le PaiementForfaitaire et une ligne DiameXTemporaire (compte 748411) part vers
la compta. Les dashboards peuvent ainsi afficher « encaissé, en attente de pointage ».

Étape 2 du circuit (confirmation) : la compta saisit dans DiameX puis le pointage
renseigne numeroDiameX + baseDiameX. Le pointage reste seul juge du « payé »
(`PaiementForfaitaire.est_paye`) ; l'encaissement ne le remplace pas.
"""

import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounting.models import DiameXTemporaire
from apps.billing.models import PaiementForfaitaire
from apps.organization.models import Ouvrage
from apps.organization.scoping import (
    get_gestionnaire_organisations_queryset,
    get_user_accessible_gestionnaire_ids,
)

COMPTE_FORFAIT = '748411'  # Vente d'eau au forfait

# Non pointé = le couple numeroDiameX + baseDiameX n'est pas complet
# (même règle que PaiementForfaitaire.est_pointe_complet).
NON_POINTE_Q = (
    Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
    | Q(baseDiameX__isnull=True) | Q(baseDiameX='')
)


def api_login_required(view):
    """Comme login_required, mais répond en JSON (401) au lieu de rediriger."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'error': 'Authentification requise'}, status=401)
        return view(request, *args, **kwargs)
    return wrapper


def _employe(user):
    return getattr(user, 'employe', None)


def _paiements_accessibles(user):
    """PaiementForfaitaire visibles par l'utilisateur (cloisonnement par organisation)."""
    qs = PaiementForfaitaire.objects.select_related(
        'point_eau', 'point_eau__ouvrage', 'point_eau__ouvrage__type_ouvrage'
    )
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if gestionnaire_ids is None:
        return qs
    if not gestionnaire_ids:
        return qs.none()
    return qs.filter(
        point_eau__ouvrage__modalites_gestion__gestionnaire_id__in=gestionnaire_ids,
        point_eau__ouvrage__modalites_gestion__date_fin__isnull=True,
    ).distinct()


def _idxls_suffix(paiements):
    valeurs = []
    for paiement in paiements:
        idxls = str(getattr(paiement.point_eau, 'idxls', '') or '').strip()
        if idxls and idxls not in valeurs:
            valeurs.append(idxls)
    return f" ({';'.join(valeurs)})" if valeurs else ''


def _volet_ouvrage(ouvrage):
    """Ouvrage -> ModaliteGestion active -> Employe -> Base -> volet."""
    if not ouvrage:
        return None
    modalite = ouvrage.modalites_gestion.filter(date_fin__isnull=True).first()
    if modalite and modalite.employe and modalite.employe.base:
        return modalite.employe.base.volet
    return None


def _tronquer(valeur, taille=50):
    return valeur[:taille] if valeur and len(str(valeur)) > taille else valeur


def _creer_ligne_diamex(paiements, date_enc, journal_code, employe, groupe):
    """Crée la ligne DiameXTemporaire d'un encaissement (un paiement ou un groupe)."""
    premier = paiements[0]
    ouvrage = premier.point_eau.ouvrage if premier.point_eau else None
    ouvrage_nom = ouvrage.nom_ouvrage if ouvrage else 'Sans ouvrage'
    montant_total = sum((p.montant or Decimal('0') for p in paiements), Decimal('0'))
    quantite_totale = sum(int(p.quantite or 0) for p in paiements)
    tarif = int(montant_total / quantite_totale) if quantite_totale > 0 else 0

    # Pattern : Paiement forfaitaire_U_[Quantité]_[Tarif]_[Ouvrage] (+ IDXLS entre parenthèses)
    description = (
        f"Paiement forfaitaire_U_{quantite_totale}_{tarif}_{ouvrage_nom}{_idxls_suffix(paiements)}"
    )[:255]

    base = employe.base if employe and employe.base else None
    activ = _volet_ouvrage(ouvrage) or (base.volet if base else None)
    prog = (base.prog_diamex or base.nom_base) if base else None
    pers = employe.nom if employe and journal_code == '00PERS' else None

    return DiameXTemporaire.objects.create(
        paiement_forfaitaire=premier,
        paiements_forfaitaires_ids=[str(p.id) for p in paiements] if groupe else None,
        type_transaction='recette',
        journal_code=_tronquer(journal_code),
        date_m=date_enc,
        date_rec=date_enc,
        description=description,
        montant_in=float(montant_total),
        montant_out=0.0,
        compte_code=COMPTE_FORFAIT,
        pers=_tronquer(pers),
        activ=_tronquer(activ),
        prog=_tronquer(prog),
        fin='RL Activités',
        info=(f'Hydria - Paiement forfaitaire groupé - {len(paiements)} factures'
              if groupe else 'Hydria - Paiement forfaitaire'),
        statut='en_attente',
        created_by=employe,
    )


@api_login_required
@require_http_methods(["POST"])
def api_encaisser_paiements(request):
    """
    Encaisse des paiements forfaitaires.

    POST JSON :
      paiement_ids      : liste d'UUID (obligatoire)
      groupe            : true -> UNE ligne DiameX pour tous (même ouvrage obligatoire)
      date_encaissement : YYYY-MM-DD (défaut aujourd'hui, pas dans le futur)
      journal_code      : défaut '00PERS'
    """
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Format JSON invalide'}, status=400)

    paiement_ids = data.get('paiement_ids') or []
    groupe = bool(data.get('groupe', False))
    journal_code = data.get('journal_code') or '00PERS'

    if not paiement_ids:
        return JsonResponse({'success': False, 'error': 'Aucun paiement à encaisser'}, status=400)

    aujourd_hui = timezone.localdate()
    try:
        date_enc = date.fromisoformat(data['date_encaissement']) if data.get('date_encaissement') else aujourd_hui
    except ValueError:
        return JsonResponse({'success': False, 'error': "Date d'encaissement invalide"}, status=400)
    if date_enc > aujourd_hui:
        return JsonResponse({'success': False, 'error': "La date d'encaissement ne peut pas être dans le futur"}, status=400)

    employe = _employe(request.user)

    try:
        with transaction.atomic():
            # select_for_update : deux caissières ne peuvent pas encaisser le même paiement
            ids_valides = list(
                _paiements_accessibles(request.user)
                .filter(id__in=paiement_ids, date_encaissement__isnull=True)
                .filter(NON_POINTE_Q)
                .values_list('id', flat=True)
            )
            paiements = list(
                PaiementForfaitaire.objects.select_for_update(of=('self',))
                .select_related('point_eau', 'point_eau__ouvrage')
                .filter(id__in=ids_valides, date_encaissement__isnull=True)
                .order_by('point_eau__ouvrage__nom_ouvrage', 'date_facture')
            )

            trouves = {str(p.id) for p in paiements}
            erreurs = [
                f"Paiement {pid} ignoré (introuvable, déjà encaissé ou déjà pointé)"
                for pid in paiement_ids if str(pid) not in trouves
            ]
            if not paiements:
                return JsonResponse(
                    {'success': False, 'error': 'Aucun paiement encaissable dans la sélection', 'erreurs': erreurs},
                    status=400,
                )

            if groupe:
                ouvrages = {p.point_eau.ouvrage_id for p in paiements}
                if len(ouvrages) > 1:
                    return JsonResponse({
                        'success': False,
                        'error': "Un encaissement groupé ne peut contenir que des factures d'un seul ouvrage",
                    }, status=400)

            for paiement in paiements:
                paiement.date_encaissement = date_enc
                paiement.encaisse_par = employe
                paiement.paye = True
                if not paiement.date_paiement:
                    paiement.date_paiement = date_enc
                paiement.save(update_fields=[
                    'date_encaissement', 'encaisse_par', 'paye', 'date_paiement', 'updated_at'
                ])

            if groupe:
                lignes = [_creer_ligne_diamex(paiements, date_enc, journal_code, employe, True)]
            else:
                lignes = [_creer_ligne_diamex([p], date_enc, journal_code, employe, False) for p in paiements]

        montant_total = sum((p.montant or Decimal('0') for p in paiements), Decimal('0'))
        message = f'{len(paiements)} paiement(s) encaissé(s) - {float(montant_total):,.0f} Ar'
        if erreurs:
            message += f' - {len(erreurs)} ignoré(s)'
        return JsonResponse({
            'success': True,
            'message': message,
            'nb_encaisses': len(paiements),
            'nb_lignes_diamex': len(lignes),
            'montant_total': float(montant_total),
            'erreurs': erreurs,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_login_required
@require_http_methods(["POST"])
def api_annuler_encaissement(request):
    """
    Annule un encaissement forfaitaire (une ligne DiameXTemporaire).

    Refusé si la compta a déjà validé/exporté la ligne, ou si un des paiements
    est déjà pointé : il faudrait alors annuler le pointage d'abord.
    POST JSON : { "ligne_id": 123 }
    """
    try:
        data = json.loads(request.body or '{}')
        ligne_id = data.get('ligne_id')
        if not ligne_id:
            return JsonResponse({'success': False, 'error': 'ligne_id requis'}, status=400)

        with transaction.atomic():
            ligne = DiameXTemporaire.objects.select_for_update().filter(
                id=ligne_id, compte_code=COMPTE_FORFAIT, type_transaction='recette'
            ).first()
            if not ligne:
                return JsonResponse({'success': False, 'error': 'Ligne introuvable'}, status=404)
            if ligne.statut != 'en_attente':
                return JsonResponse({
                    'success': False,
                    'error': f'Cette ligne est déjà « {ligne.get_statut_display()} » côté compta : annulation impossible ici',
                }, status=400)

            ids = ligne.paiements_forfaitaires_ids or [str(ligne.paiement_forfaitaire_id)]
            paiements = list(_paiements_accessibles(request.user).filter(id__in=ids))
            if len(paiements) != len(ids):
                return JsonResponse({'success': False, 'error': 'Accès refusé sur ces paiements'}, status=403)
            if any(p.est_pointe_complet for p in paiements):
                return JsonResponse({
                    'success': False,
                    'error': 'Un paiement est déjà pointé : annulez d\'abord le pointage',
                }, status=400)

            for paiement in paiements:
                if paiement.date_paiement == paiement.date_encaissement:
                    paiement.date_paiement = None
                paiement.date_encaissement = None
                paiement.encaisse_par = None
                paiement.paye = False
                paiement.save(update_fields=[
                    'date_encaissement', 'encaisse_par', 'paye', 'date_paiement', 'updated_at'
                ])
            ligne.delete()

        return JsonResponse({
            'success': True,
            'message': f'Encaissement annulé : {len(paiements)} paiement(s) remis à encaisser',
            'nb_paiements': len(paiements),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@api_login_required
@require_http_methods(["GET"])
def api_derniers_encaissements(request):
    """Encaissements forfaitaires des 30 derniers jours (une entrée par ligne DiameX)."""
    try:
        depuis = timezone.now() - timedelta(days=30)
        lignes = DiameXTemporaire.objects.filter(
            compte_code=COMPTE_FORFAIT, type_transaction='recette', created_at__gte=depuis
        ).order_by('-created_at')[:60]

        accessibles = _paiements_accessibles(request.user)
        resultats = []
        for ligne in lignes:
            ids = ligne.paiements_forfaitaires_ids or (
                [str(ligne.paiement_forfaitaire_id)] if ligne.paiement_forfaitaire_id else []
            )
            paiements = list(accessibles.filter(id__in=ids))
            if not paiements:
                continue
            nb_pointes = sum(1 for p in paiements if p.est_pointe_complet)
            resultats.append({
                'ligne_id': ligne.id,
                'date_encaissement': ligne.date_rec.strftime('%d/%m/%Y') if ligne.date_rec else None,
                'description': ligne.description,
                'montant': float(ligne.montant_in or 0),
                'nb_paiements': len(paiements),
                'nb_pointes': nb_pointes,
                'statut_compta': ligne.get_statut_display(),
                'annulable': ligne.statut == 'en_attente' and nb_pointes == 0,
            })
        return JsonResponse({'success': True, 'encaissements': resultats[:25]})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def encaissement_groupe(request):
    """Page d'encaissement des paiements forfaitaires (individuel ou groupé par ouvrage)."""
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
    organisations = get_gestionnaire_organisations_queryset()
    ouvrages = Ouvrage.objects.filter(
        modalites_gestion__modalitepaiement__in=['forfaitaire', 'mixte'],
        modalites_gestion__date_fin__isnull=True,
    )
    if gestionnaire_ids is not None:
        if gestionnaire_ids:
            organisations = organisations.filter(id__in=gestionnaire_ids)
            ouvrages = ouvrages.filter(modalites_gestion__gestionnaire_id__in=gestionnaire_ids)
        else:
            organisations = organisations.none()
            ouvrages = ouvrages.none()

    return render(request, 'billing/encaissement_groupe.html', {
        'title': 'Encaissement - Paiements Forfaitaires',
        'organisations': organisations,
        'ouvrages': ouvrages.distinct().order_by('nom_ouvrage'),
        'today': timezone.localdate(),
    })


@api_login_required
@require_http_methods(["GET"])
def api_liste_paiements_forfaitaires(request):
    """
    Liste des paiements forfaitaires.

    GET : organisation_id, ouvrage_id, search, statut
      statut = a_encaisser (défaut) | encaisse (encaissé, pas encore pointé) | tous
    """
    try:
        organisation_id = request.GET.get('organisation_id')
        ouvrage_id = request.GET.get('ouvrage_id')
        search = request.GET.get('search', '').strip()
        statut = request.GET.get('statut', 'a_encaisser')

        queryset = _paiements_accessibles(request.user)

        if organisation_id and organisation_id != 'all':
            queryset = queryset.filter(
                point_eau__ouvrage__modalites_gestion__gestionnaire_id=organisation_id,
                point_eau__ouvrage__modalites_gestion__date_fin__isnull=True,
            )
        if ouvrage_id and ouvrage_id != 'all':
            queryset = queryset.filter(point_eau__ouvrage_id=ouvrage_id)

        if statut == 'a_encaisser':
            queryset = queryset.filter(date_encaissement__isnull=True).filter(NON_POINTE_Q)
        elif statut == 'encaisse':
            queryset = queryset.filter(date_encaissement__isnull=False).filter(NON_POINTE_Q)

        if search:
            queryset = queryset.filter(
                Q(point_eau__nomabonne__icontains=search) | Q(point_eau__code_point_eau__icontains=search)
                | Q(point_eau__idxls__icontains=search)
            )

        today = date.today()
        actifs, expires = [], []
        for p in queryset.distinct():
            item = {
                'id': str(p.id),
                'point_eau_nom': p.point_eau.nomabonne or p.point_eau.code_point_eau or 'Sans nom',
                'point_eau_id': str(p.point_eau.id),
                'idxls': p.point_eau.idxls or '',
                'ouvrage_nom': p.point_eau.ouvrage.nom_ouvrage if p.point_eau.ouvrage else 'Sans ouvrage',
                'ouvrage_id': str(p.point_eau.ouvrage.id) if p.point_eau.ouvrage else None,
                'date_facture': p.date_facture.strftime('%Y-%m-%d') if p.date_facture else None,
                'quantite': p.quantite or 0,
                'prix_unitaire': float(p.prix_unitaire or 0),
                'montant': float(p.montant or 0),
                'duree_mois': p.duree_mois or 0,
                'date_fin_validite': p.date_fin_validite.strftime('%Y-%m-%d') if p.date_fin_validite else None,
                'date_encaissement': p.date_encaissement.strftime('%Y-%m-%d') if p.date_encaissement else None,
                'est_pointe': p.est_pointe_complet,
                # Ancien encaissement (avant date_encaissement) : à vérifier avant de ré-encaisser
                'deja_marque_paye': bool(p.paye and not p.date_encaissement and not p.est_pointe_complet),
                'numeroDiameX': p.numeroDiameX or '',
            }
            (expires if p.date_fin_validite and p.date_fin_validite < today else actifs).append(
                (p.date_fin_validite, item)
            )

        actifs.sort(key=lambda t: t[0] or date.max)
        expires.sort(key=lambda t: t[0] or date.min, reverse=True)
        actifs = [i for _, i in actifs]
        expires = [i for _, i in expires]

        def grouper(liste):
            groupes = defaultdict(list)
            for i in liste:
                groupes[i['ouvrage_id'] or 'sans_ouvrage'].append(i)
            return dict(groupes)

        return JsonResponse({
            'success': True,
            'paiements_actifs': actifs,
            'paiements_expires': expires,
            'groupes_actifs': grouper(actifs),
            'groupes_expires': grouper(expires),
            'total': len(actifs) + len(expires),
            'total_actifs': len(actifs),
            'total_expires': len(expires),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
