"""
Views pour l'encaissement des factures par la caissière
Workflow : Sélection multiple de factures → Regroupement → Export vers DiameXTemporaire
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Count, Q
from decimal import Decimal
import json
from datetime import datetime

from apps.billing.models import Releve, ModaliteGestion
from apps.accounting.models import DiameXTemporaire
from apps.organization.models import Base, Journal, Ouvrage
from apps.organization.scoping import get_user_accessible_gestionnaire_ids


def _build_facture_qr_payload(releve, annee_facture=None, mois_facture=None):
    releve_id = str(getattr(releve, 'id', '') or '')
    numero_facture = getattr(releve, 'numero_facture', '') or ''
    ouvrage_id = str(getattr(getattr(releve, 'point_eau', None), 'ouvrage_id', '') or '')

    if annee_facture is None or mois_facture is None:
        annee_facture, mois_facture = _get_releve_facturation_period(releve)

    annee_mois = ''
    if annee_facture and mois_facture:
        annee_mois = f'{annee_facture:04d}-{mois_facture:02d}'

    return f'HYDRIA|FACTURE|{releve_id}|{numero_facture}|{annee_mois}|{ouvrage_id}'


def _parse_facture_qr_payload(payload):
    raw_payload = (payload or '').strip()
    if not raw_payload:
        return {}

    parts = raw_payload.split('|')
    if len(parts) >= 6 and parts[0] == 'HYDRIA' and parts[1] == 'FACTURE':
        return {
            'releve_id': parts[2].strip(),
            'numero_facture': parts[3].strip(),
            'annee_mois': parts[4].strip(),
            'ouvrage_id': parts[5].strip(),
        }

    return {
        'numero_facture': raw_payload,
    }


def _is_directeur_user(user):
    if not user or not user.is_authenticated:
        return False
    employe = getattr(user, 'employe', None)
    if employe and hasattr(employe, 'is_directeur') and employe.is_directeur:
        return True
    return user.groups.filter(name='Directeur').exists()


def _get_user_organisation_id(user):
    employe = getattr(user, 'employe', None)
    base = getattr(employe, 'base', None)
    return getattr(base, 'organisation_id', None)


def _get_allowed_ouvrage_ids(user):
    """
    Ouvrages autorisés pour l'encaissement volumétrique:
    ModaliteGestion active (date_fin IS NULL), modalité volume/mixte,
    cloisonnée par organisation sauf directeur/superuser.
    """
    modalites = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['au_volume', 'mixte']
    )

    if not (getattr(user, 'is_superuser', False) or _is_directeur_user(user)):
        gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
        if gestionnaire_ids is None:
            pass
        elif not gestionnaire_ids:
            return modalites.none().values_list('ouvrage_id', flat=True)
        else:
            modalites = modalites.filter(gestionnaire_id__in=gestionnaire_ids)

    return modalites.exclude(ouvrage_id__isnull=True).values_list('ouvrage_id', flat=True).distinct()


def _get_releve_facturation_period(releve):
    date_releve = getattr(releve, 'datereleve', None)
    if not date_releve:
        return None, None

    mois_facture = date_releve.month + 1
    annee_facture = date_releve.year
    if mois_facture == 13:
        mois_facture = 1
        annee_facture += 1
    return annee_facture, mois_facture


@login_required
def encaissement_factures(request):
    """
    Vue principale pour l'encaissement des factures par la caissière
    Permet de sélectionner plusieurs factures et créer un regroupement
    """
    from datetime import datetime, timedelta
    from django.utils import timezone as dj_timezone
    import pytz

    # Récupérer les filtres
    annee_filter = request.GET.get('annee')
    ouvrage_filter = request.GET.get('ouvrage')

    # Générer liste des années (de 2020 à année courante + 1)
    annee_courante = datetime.now().year
    annees = range(2020, annee_courante + 2)

    # Si pas d'année spécifiée, utiliser l'année courante
    if not annee_filter:
        annee_filter = str(annee_courante)

    # Base queryset des relevés non payés avec montant
    # Un relevé est payé si numeroDiameX est renseigné OU si datepaiement est renseigné
    allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

    releves_qs = Releve.objects.filter(
        montant__isnull=False,
        datepaiement__isnull=True  # Exclure les factures déjà encaissées
    ).filter(
        Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
    ).filter(
        point_eau__ouvrage_id__in=allowed_ouvrage_ids
    )

    # Appliquer filtre année
    if ouvrage_filter and ouvrage_filter != 'all':
        releves_qs = releves_qs.filter(point_eau__ouvrage_id=ouvrage_filter)

    releves = list(releves_qs.select_related('point_eau__ouvrage'))
    if annee_filter:
        try:
            annee_filter_int = int(annee_filter)
            releves = [
                releve for releve in releves
                if _get_releve_facturation_period(releve)[0] == annee_filter_int
            ]
        except (ValueError, TypeError):
            pass

    # Calculer les dates de retard
    tz_madagascar = pytz.timezone('Indian/Antananarivo')
    now = dj_timezone.now().astimezone(tz_madagascar)
    date_limite_tres_retard = now - timedelta(days=60)  # Plus de 2 mois
    date_limite_retard = now - timedelta(days=30)  # Plus d'1 mois

    # Compter et calculer montants par statut de retard
    tres_en_retard = 0
    en_retard = 0
    en_attente = 0
    montant_tres_retard = Decimal('0')
    montant_retard = Decimal('0')
    montant_attente = Decimal('0')

    for releve in releves:
        if releve.datereleve:
            # datereleve est un date, pas un datetime - convertir en datetime pour comparaison
            date_releve = releve.datereleve
            if isinstance(date_releve, datetime):
                # C'est un datetime
                if dj_timezone.is_aware(date_releve):
                    date_releve = date_releve.astimezone(tz_madagascar)
                else:
                    date_releve = tz_madagascar.localize(date_releve)
            else:
                # C'est un date - convertir en datetime à minuit Madagascar
                date_releve = tz_madagascar.localize(datetime.combine(date_releve, datetime.min.time()))

            montant = releve.montant or Decimal('0')

            if date_releve <= date_limite_tres_retard:
                tres_en_retard += 1
                montant_tres_retard += montant
            elif date_releve <= date_limite_retard:
                en_retard += 1
                montant_retard += montant
            else:
                en_attente += 1
                montant_attente += montant

    stats = {
        'tres_en_retard': tres_en_retard,
        'en_retard': en_retard,
        'en_attente': en_attente,
        'montant_tres_retard': montant_tres_retard,
        'montant_retard': montant_retard,
        'montant_attente': montant_attente,
        'montant_total': montant_tres_retard + montant_retard + montant_attente,
    }

    # Derniers regroupements d'encaissement
    derniers_regroupements = DiameXTemporaire.objects.filter(
        type_transaction='recette',
        description__icontains='Paiement au volume'
    ).order_by('-date_rec')[:20]

    context = {
        'title': 'Encaissement des factures - Caissière',
        'stats': stats,
        'derniers_regroupements': derniers_regroupements,
        'annees': annees,
        'annee_courante': annee_courante,
        'annee_filter': annee_filter,
        'ouvrage_filter': ouvrage_filter or 'all',
        'today': timezone.now().date(),
    }

    return render(request, 'billing/encaissement_factures.html', context)


@require_http_methods(["GET"])
def api_factures_a_encaisser(request):
    """
    API pour lister les factures imprimées non payées
    Avec filtres par ouvrage, mois, recherche
    """
    try:
        # Récupérer les paramètres de filtre
        ouvrage_id = request.GET.get('ouvrage')
        mois = request.GET.get('mois')  # Format: YYYY-MM
        annee = request.GET.get('annee')  # Format: YYYY
        recherche = request.GET.get('recherche', '').strip()

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        # Base queryset : factures avec montant non payées
        # Un relevé est payé si numeroDiameX est renseigné OU si datepaiement est renseigné
        factures = Releve.objects.filter(
            montant__isnull=False,
            datepaiement__isnull=True  # Exclure les factures déjà encaissées
        ).filter(
            Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
        ).filter(
            point_eau__ouvrage_id__in=allowed_ouvrage_ids
        ).select_related(
            'point_eau',
            'point_eau__ouvrage',
            'point_eau__type_point_eau',
            'point_eau__parcelle',
            'point_eau__parcelle__village'
        ).order_by('-datereleve')

        # Filtre par année
        if annee:
            try:
                factures = factures
            except (ValueError, TypeError):
                pass

        # Filtre par ouvrage
        if ouvrage_id and ouvrage_id != 'all':
            if not Ouvrage.objects.filter(id=ouvrage_id, id__in=allowed_ouvrage_ids).exists():
                return JsonResponse({'success': False, 'error': 'Ouvrage non autorisé'}, status=403)
            factures = factures.filter(point_eau__ouvrage_id=ouvrage_id)

        # Filtre par mois
        if mois:
            try:
                year, month = mois.split('-')
                factures = factures
            except (ValueError, AttributeError):
                pass

        # Recherche par numéro de facture ou nom abonné
        if recherche:
            factures = factures.filter(
                Q(numero_facture__icontains=recherche) |
                Q(abonne__icontains=recherche)
            )

        # Limiter à 500 résultats (augmenté de 100 à 500)
        factures = list(factures)
        if annee:
            try:
                annee_int = int(annee)
                factures = [facture for facture in factures if _get_releve_facturation_period(facture)[0] == annee_int]
            except (ValueError, TypeError):
                pass
        if mois:
            try:
                year_str, month_str = mois.split('-')
                annee_mois_int = (int(year_str), int(month_str))
                factures = [facture for facture in factures if _get_releve_facturation_period(facture) == annee_mois_int]
            except (ValueError, AttributeError):
                pass
        factures = factures[:500]

        # Préparer les données
        factures_data = []
        for facture in factures:
            ouvrage_nom = facture.point_eau.ouvrage.nom_ouvrage if facture.point_eau and facture.point_eau.ouvrage else None

            # IDXls et type de point d'eau
            idxls = facture.point_eau.idxls if facture.point_eau else None
            type_pe = None
            type_pe_icone = 'fa-tint'
            type_pe_color = 'info'
            if facture.point_eau and facture.point_eau.type_point_eau:
                type_pe = facture.point_eau.type_point_eau.nom_type
                # Icônes selon le type
                if 'kiosque' in type_pe.lower():
                    type_pe_icone = 'fa-store'
                    type_pe_color = 'secondary'
                elif 'borne' in type_pe.lower() or 'bf' in type_pe.lower():
                    type_pe_icone = 'fa-faucet'
                    type_pe_color = 'primary'
                elif 'branchement' in type_pe.lower() or 'bp' in type_pe.lower() or 'bi' in type_pe.lower():
                    type_pe_icone = 'fa-home'
                    type_pe_color = 'success'
                elif 'reservoir' in type_pe.lower() or 'réservoir' in type_pe.lower():
                    type_pe_icone = 'fa-database'
                    type_pe_color = 'warning'
                elif 'pmh' in type_pe.lower() or 'puits' in type_pe.lower():
                    type_pe_icone = 'fa-water'
                    type_pe_color = 'info'

            # Parcelle et village
            parcelle_nom = None
            village_nom = None
            parcelle_id = None
            if facture.point_eau and facture.point_eau.parcelle:
                parcelle_nom = facture.point_eau.parcelle.reference_parcelle
                parcelle_id = str(facture.point_eau.parcelle.id)
                if facture.point_eau.parcelle.village:
                    village_nom = facture.point_eau.parcelle.village.nom_village

            # Extraire année et mois pour le regroupement
            annee_facture, mois_facture = _get_releve_facturation_period(facture)
            if annee_facture and mois_facture:
                date_facturation = datetime(annee_facture, mois_facture, 1)
                annee_mois = date_facturation.strftime('%Y-%m')
                mois_annee_display = date_facturation.strftime('%B %Y').capitalize()
            else:
                annee_mois = None
                mois_annee_display = None

            factures_data.append({
                'id': str(facture.id),
                'numero_facture': facture.numero_facture,
                'abonne': facture.abonne,
                'date_releve': facture.datereleve.strftime('%Y-%m-%d'),
                'date_releve_display': facture.datereleve.strftime('%d/%m/%Y'),
                'montant': float(facture.montant),
                'ouvrage': ouvrage_nom,
                'ouvrage_id': str(facture.point_eau.ouvrage_id) if facture.point_eau and facture.point_eau.ouvrage else None,
                'statut': facture.statut,
                'idxls': idxls,
                'type_pe': type_pe,
                'est_institutionnel': bool(facture.point_eau and facture.point_eau.estbranchementinstitutionnel),
                'type_pe_icone': type_pe_icone,
                'type_pe_color': type_pe_color,
                'parcelle': parcelle_nom,
                'parcelle_id': parcelle_id,
                'village': village_nom,
                'annee_mois': annee_mois,
                'mois_annee_display': mois_annee_display,
                'qr_payload': _build_facture_qr_payload(facture, annee_facture, mois_facture),
            })

        return JsonResponse({
            'success': True,
            'factures': factures_data,
            'count': len(factures_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_resoudre_facture_qr(request):
    try:
        data = json.loads(request.body or '{}')
        qr_payload = data.get('qr_payload', '')
        parsed = _parse_facture_qr_payload(qr_payload)
        releve_id = parsed.get('releve_id')
        numero_facture = parsed.get('numero_facture')
        annee_mois = parsed.get('annee_mois')
        ouvrage_id = parsed.get('ouvrage_id')

        if not releve_id and not numero_facture:
            return JsonResponse({
                'success': False,
                'error': 'QR code invalide'
            }, status=400)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        facture_qs = Releve.objects.filter(
            montant__isnull=False,
            datepaiement__isnull=True
        ).filter(
            Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
        ).filter(
            point_eau__ouvrage_id__in=allowed_ouvrage_ids
        ).select_related('point_eau__ouvrage')

        if releve_id:
            facture_qs = facture_qs.filter(id=releve_id)
        elif numero_facture:
            facture_qs = facture_qs.filter(numero_facture=numero_facture)

        facture = facture_qs.first()
        if not facture:
            return JsonResponse({
                'success': False,
                'error': 'Facture introuvable ou déjà encaissée'
            }, status=404)

        annee_facture, mois_facture = _get_releve_facturation_period(facture)
        resolved_annee_mois = f'{annee_facture:04d}-{mois_facture:02d}' if annee_facture and mois_facture else ''

        return JsonResponse({
            'success': True,
            'facture': {
                'id': str(facture.id),
                'numero_facture': facture.numero_facture,
                'abonne': facture.abonne,
                'ouvrage_id': str(facture.point_eau.ouvrage_id) if facture.point_eau and facture.point_eau.ouvrage_id else '',
                'ouvrage': facture.point_eau.ouvrage.nom_ouvrage if facture.point_eau and facture.point_eau.ouvrage else '',
                'annee_mois': resolved_annee_mois,
                'annee': str(annee_facture) if annee_facture else '',
                'mois': resolved_annee_mois,
                'qr_payload': _build_facture_qr_payload(facture, annee_facture, mois_facture),
            },
            'meta': {
                'qr_annee_mois': annee_mois,
                'qr_ouvrage_id': ouvrage_id,
                'qr_numero_facture': numero_facture,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_valider_encaissement_groupe(request):
    """
    API pour valider l'encaissement d'un groupe de factures
    Crée UNE ligne DiameXTemporaire avec regroupement selon les règles :
    - DateRec = date d'encaissement
    - Journal = 00PERS ou code de sa caisse
    - Description = "_Paiement au volume_[Nom ouvrage]_[Mois]_[Montant total]"
    - In = montant total
    - Out = 0
    - Cat = 707401
    - PERS = obligatoire si journal=00PERS, vide sinon
    - ACTIV = volet de la Base de l'employé
    - Prog = BaseDIameX de l'employé
    """
    try:
        data = json.loads(request.body)
        factures_ids = data.get('factures_ids', [])
        date_encaissement_str = data.get('date_encaissement')
        journal_code = data.get('journal_code', '00PERS')  # Par défaut 00PERS

        if not factures_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucune facture sélectionnée'
            }, status=400)

        if not date_encaissement_str:
            return JsonResponse({
                'success': False,
                'error': 'Date d\'encaissement requise'
            }, status=400)

        # Parser la date
        date_encaissement = datetime.strptime(date_encaissement_str, '%Y-%m-%d').date()
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        with transaction.atomic():
            # Récupérer les factures sélectionnées (non payées = sans numeroDiameX)
            factures = Releve.objects.filter(
                id__in=factures_ids,
                montant__isnull=False
            ).filter(
                Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
            ).filter(
                point_eau__ouvrage_id__in=allowed_ouvrage_ids
            ).select_related('point_eau', 'point_eau__ouvrage')

            if not factures.exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Aucune facture valide trouvée'
                }, status=400)

            # Grouper par ouvrage et mois
            regroupements = {}
            for facture in factures:
                if not facture.point_eau or not facture.point_eau.ouvrage:
                    continue

                ouvrage = facture.point_eau.ouvrage
                annee_facture, mois_facture = _get_releve_facturation_period(facture)
                if not annee_facture or not mois_facture:
                    continue
                mois = f"{annee_facture:04d}-{mois_facture:02d}"
                mois_display = datetime(annee_facture, mois_facture, 1).strftime('%B %Y').capitalize()

                cle = f"{ouvrage.id}_{mois}"

                if cle not in regroupements:
                    regroupements[cle] = {
                        'ouvrage': ouvrage,
                        'mois': mois,
                        'mois_display': mois_display,
                        'factures': [],
                        'montant_total': Decimal('0')
                    }

                regroupements[cle]['factures'].append(facture)
                regroupements[cle]['montant_total'] += facture.montant

            if not regroupements:
                return JsonResponse({
                    'success': False,
                    'error': 'Aucune facture exploitable trouvee pour cet encaissement'
                }, status=400)

            if len(regroupements) > 1:
                return JsonResponse({
                    'success': False,
                    'error': 'Un encaissement ne peut contenir que des factures d un seul ouvrage et d un seul mois'
                }, status=400)

            # Récupérer les informations de l'employé pour ACTIV et Prog
            employe = request.user.employe if hasattr(request.user, 'employe') else None
            volet = None
            prog = None

            if employe and employe.base:
                # Récupérer prog et activ depuis la Base de l'employé
                prog = employe.base.prog_diamex or employe.base.nom_base
                volet = employe.base.volet  # Colonne volet de la table Bases

            # Créer une ligne DiameXTemporaire par regroupement
            lignes_creees = []
            factures_ids_traites = []

            for cle, groupe in regroupements.items():
                ouvrage_nom = groupe['ouvrage'].nom_ouvrage
                montant_total = groupe['montant_total']
                factures_groupe = groupe['factures']
                idxls_values = []
                for facture in factures_groupe:
                    idxls_value = str(getattr(getattr(facture, 'point_eau', None), 'idxls', '') or '').strip()
                    if idxls_value and idxls_value not in idxls_values:
                        idxls_values.append(idxls_value)

                if len(idxls_values) <= 5 and idxls_values:
                    suffixe_pattern = ";".join(idxls_values)
                    detail_diamex = f"IDXLS:{suffixe_pattern}"
                else:
                    suffixe_pattern = f"{len(factures_groupe)} relevés"
                    detail_diamex = f"NB_RELEVES:{len(factures_groupe)}"

                description = f'Paiement au volume {ouvrage_nom} {date_encaissement.strftime("%d/%m/%Y")} ({suffixe_pattern})'

                # PERS = obligatoire si journal=00PERS, vide sinon
                pers = employe.nom if employe and journal_code == '00PERS' else None
                # Tronquer à 50 caractères pour respecter la limite du champ
                if pers and len(pers) > 50:
                    pers = pers[:50]

                # Tronquer activ et prog à 50 caractères
                activ_value = volet[:50] if volet and len(str(volet)) > 50 else volet
                prog_value = prog[:50] if prog and len(str(prog)) > 50 else prog

                # Créer la ligne DiameXTemporaire
                ligne = DiameXTemporaire.objects.create(
                    type_transaction='recette',
                    journal_code=journal_code[:50] if journal_code else None,  # Tronquer aussi
                    date_rec=date_encaissement,
                    description=description[:255],  # Limiter à 255 caractères
                    montant_in=float(montant_total),
                    montant_out=0,
                    compte_code='707401',  # Cat
                    pers=pers,
                    detail=detail_diamex[:50],
                    activ=activ_value,
                    prog=prog_value,
                    fin='RL Activités',
                    info='hydria paiement facture au volume',
                    statut='en_attente',
                    created_by=employe
                )

                lignes_creees.append({
                    'id': ligne.id,
                    'description': description,
                    'montant': float(montant_total),
                    'nb_factures': len(groupe['factures']),
                    'mois': groupe['mois'],
                    'mois_display': groupe['mois_display'],
                    'ouvrage': ouvrage_nom,
                })

                # Marquer les factures comme payées via numeroDiameX
                # Note: Le numeroDiameX sera renseigné dans une étape ultérieure
                # Pour l'instant, on marque juste le statut et la date de paiement
                for facture in groupe['factures']:
                    facture.statut = 'paye'
                    facture.datepaiement = date_encaissement
                    facture.montantpaye = facture.montant
                    # numeroDiameX sera renseigné lors de l'export vers DiameX
                    # facture.numeroDiameX sera mis à jour dans la suite du workflow
                    facture.save()
                    factures_ids_traites.append(str(facture.id))

            return JsonResponse({
                'success': True,
                'message': f'{len(lignes_creees)} ligne(s) DiameX créée(s)',
                'lignes': lignes_creees,
                'nb_factures_traitees': len(factures_ids_traites),
                'factures_ids': factures_ids_traites
            })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Format JSON invalide'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_liste_ouvrages(request):
    """
    API pour récupérer la liste des ouvrages (pour le filtre)
    """
    try:
        from apps.billing.models import PointEau

        # Récupérer les IDs des ouvrages ayant des relevés non payés
        # Un relevé est payé si numeroDiameX est renseigné OU si datepaiement est renseigné
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        ouvrages_ids = Releve.objects.filter(
            montant__isnull=False,
            datepaiement__isnull=True  # Exclure les factures déjà encaissées
        ).filter(
            Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
        ).filter(
            point_eau__ouvrage_id__in=allowed_ouvrage_ids
        ).values_list('point_eau__ouvrage_id', flat=True).distinct()

        # Récupérer les ouvrages correspondants (exclure les None)
        ouvrages = Ouvrage.objects.filter(
            id__in=[oid for oid in ouvrages_ids if oid is not None]
        ).filter(
            id__in=allowed_ouvrage_ids
        ).order_by('nom_ouvrage')[:100]

        ouvrages_data = []
        for ouvrage in ouvrages:
            ouvrages_data.append({
                'id': str(ouvrage.id),
                'nom': ouvrage.nom_ouvrage
            })

        return JsonResponse({
            'success': True,
            'ouvrages': ouvrages_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_liste_journaux(request):
    """
    API pour récupérer la liste des codes journaux depuis la table journaux
    """
    try:
        journaux = Journal.objects.all().order_by('code')

        journaux_data = []
        for journal in journaux:
            journaux_data.append({
                'code': journal.code or '',
                'nom': journal.nom_journal,
                'base': journal.base.nom_base if journal.base else ''
            })

        return JsonResponse({
            'success': True,
            'journaux': journaux_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_derniers_encaissements(request):
    """
    API pour récupérer les derniers encaissements (lignes DiameXTemporaire de type recette)
    Avec les factures associées groupées par date d'encaissement
    """
    try:
        from collections import defaultdict
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        page = max(int(request.GET.get('page', 1) or 1), 1)
        page_size = 5

        # Récupérer les lignes DiameX de type recette des 7 derniers jours
        date_limite = timezone.now() - timezone.timedelta(days=7)

        lignes_diamex = DiameXTemporaire.objects.filter(
            type_transaction='recette',
            created_at__gte=date_limite
        ).order_by('-date_rec', '-created_at')[:50]

        # Regrouper par date d'encaissement et description
        encaissements = defaultdict(lambda: {
            'lignes': [],
            'factures': [],
            'montant_total': 0.0,  # Utiliser float au lieu de Decimal
            'date_encaissement': None
        })

        for ligne in lignes_diamex:
            # Récupérer les factures associées à cette date d'encaissement
            if ligne.date_rec:
                # Chercher les factures avec cette date de paiement
                factures = Releve.objects.filter(
                    datepaiement=ligne.date_rec
                ).filter(
                    point_eau__ouvrage_id__in=allowed_ouvrage_ids
                ).select_related('point_eau', 'point_eau__ouvrage')

                if not factures.exists():
                    continue

                cle = f"{ligne.date_rec}_{ligne.description}"

                encaissements[cle]['date_encaissement'] = ligne.date_rec
                encaissements[cle]['lignes'].append({
                    'id': ligne.id,
                    'description': ligne.description,
                    'montant': float(ligne.montant_in or 0),
                    'journal': ligne.journal_code,
                    'created_at': ligne.created_at.strftime('%Y-%m-%d %H:%M') if ligne.created_at else None
                })
                # Additionner en float
                encaissements[cle]['montant_total'] += float(ligne.montant_in or 0)

                # Ajouter les factures
                for facture in factures:
                    encaissements[cle]['factures'].append({
                        'id': str(facture.id),
                        'numero_facture': facture.numero_facture,
                        'point_eau_nom': facture.point_eau.nomabonne if facture.point_eau else None,
                        'point_eau_idxls': facture.point_eau.idxls if facture.point_eau else None,
                        'ouvrage': facture.point_eau.ouvrage.nom_ouvrage if facture.point_eau and facture.point_eau.ouvrage else None,
                        'parcelle': facture.point_eau.parcelle.reference_parcelle if facture.point_eau and facture.point_eau.parcelle else None,
                        'montant': float(facture.montant or 0),
                        'mois_facture_display': (
                            datetime(*_get_releve_facturation_period(facture), 1).strftime('%B %Y').capitalize()
                            if all(_get_releve_facturation_period(facture)) else None
                        ),
                    })

        # Convertir en liste
        encaissements_list = []
        for cle, data in encaissements.items():
            encaissements_list.append({
                'date_encaissement': data['date_encaissement'].strftime('%Y-%m-%d') if data['date_encaissement'] else None,
                'date_encaissement_display': data['date_encaissement'].strftime('%d/%m/%Y') if data['date_encaissement'] else None,
                'lignes': data['lignes'],
                'factures': data['factures'],
                'nb_factures': len(data['factures']),
                'montant_total': data['montant_total']  # Déjà en float
            })

        # Trier par date décroissante
        encaissements_list.sort(key=lambda x: x['date_encaissement'] or '', reverse=True)
        total_items = len(encaissements_list)
        total_pages = max((total_items + page_size - 1) // page_size, 1)
        if page > total_pages:
            page = total_pages
        start = (page - 1) * page_size
        end = start + page_size
        encaissements_page = encaissements_list[start:end]

        return JsonResponse({
            'success': True,
            'encaissements': encaissements_page,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_items': total_items,
                'total_pages': total_pages,
                'has_previous': page > 1,
                'has_next': page < total_pages,
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_idxls_deja_pointes(request):
    """
    API pour recuperer les IDXLS des factures deja pointees DiameX
    (numeroDiameX renseigne) pour un ouvrage et un mois de facturation donnes.
    Utilisee pour construire la grille de pointage imprimee avec le recap
    d'encaissement (chiffres en gris = deja pointes DiameX).
    """
    try:
        ouvrage_id = request.GET.get('ouvrage_id')
        annee_mois = request.GET.get('annee_mois')  # Format YYYY-MM
        exclude_ids = request.GET.get('exclude_ids', '')
        exclude_ids_list = [v for v in exclude_ids.split(',') if v]

        if not ouvrage_id or not annee_mois:
            return JsonResponse({
                'success': False,
                'error': 'Parametres ouvrage_id et annee_mois requis'
            }, status=400)

        try:
            annee_str, mois_str = annee_mois.split('-')
            annee_int = int(annee_str)
            mois_int = int(mois_str)
        except (ValueError, AttributeError):
            return JsonResponse({
                'success': False,
                'error': 'Format annee_mois invalide (attendu YYYY-MM)'
            }, status=400)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if not Ouvrage.objects.filter(id=ouvrage_id, id__in=allowed_ouvrage_ids).exists():
            return JsonResponse({'success': False, 'error': 'Ouvrage non autorise'}, status=403)

        factures_payees = Releve.objects.filter(
            point_eau__ouvrage_id=ouvrage_id,
            montant__isnull=False
        ).exclude(
            Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
        ).exclude(
            id__in=exclude_ids_list
        ).select_related('point_eau')

        idxls_pointes = []
        for facture in factures_payees:
            annee_facture, mois_facture = _get_releve_facturation_period(facture)
            if annee_facture == annee_int and mois_facture == mois_int:
                idxls = getattr(getattr(facture, 'point_eau', None), 'idxls', None)
                if idxls:
                    idxls_pointes.append(str(idxls).strip())

        return JsonResponse({
            'success': True,
            'idxls_pointes': sorted(set(idxls_pointes))
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_annuler_encaissement(request):
    """
    API pour annuler un encaissement
    - Supprime les lignes DiameXTemporaire
    - Réinitialise datepaiement et montantpaye des factures
    """
    try:
        data = json.loads(request.body)
        date_encaissement = data.get('date_encaissement')

        if not date_encaissement:
            return JsonResponse({
                'success': False,
                'error': 'Date d\'encaissement requise'
            }, status=400)

        # Convertir la date
        date_obj = datetime.strptime(date_encaissement, '%Y-%m-%d').date()
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        with transaction.atomic():
            # Récupérer les factures encaissées à cette date
            factures = Releve.objects.filter(
                datepaiement=date_obj
            ).filter(
                point_eau__ouvrage_id__in=allowed_ouvrage_ids
            )

            nb_factures = factures.count()

            # Réinitialiser les factures
            factures.update(
                datepaiement=None,
                montantpaye=None,
                statut='impaye'
            )

            # Supprimer les lignes DiameXTemporaire de cette date
            lignes_diamex = DiameXTemporaire.objects.filter(
                type_transaction='recette',
                date_rec=date_obj
            )
            if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
                organisation_id = _get_user_organisation_id(request.user)
                if organisation_id:
                    lignes_diamex = lignes_diamex.filter(created_by__base__organisation_id=organisation_id)
                else:
                    lignes_diamex = lignes_diamex.none()

            nb_lignes = lignes_diamex.count()
            lignes_diamex.delete()

            return JsonResponse({
                'success': True,
                'message': f'Encaissement annulé : {nb_lignes} ligne(s) DiameX supprimée(s), {nb_factures} facture(s) réinitialisée(s)',
                'nb_lignes': nb_lignes,
                'nb_factures': nb_factures
            })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Format JSON invalide'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
