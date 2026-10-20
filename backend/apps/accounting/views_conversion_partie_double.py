"""
Vues pour la conversion de DiameX en comptabilité partie double
"""
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db import transaction, models
from decimal import Decimal
from .models import BaseDiameX
from .models_partie_double import EcriturePartieDouble
from apps.organization.models import Journal, Compte
from apps.organization.scoping import get_user_accessible_gestionnaire_ids
from apps.employees.models import Employe
from apps.billing.models import Fournisseur
from .views_controle_conversion import _get_scoped_diamex_queryset, _get_user_organisation_id, api_controle_conversion
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import os
import shutil
import zipfile
from io import BytesIO
from datetime import datetime


def _get_user_scope_organisation_ids(user):
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if gestionnaire_ids is None:
        return None
    return [str(_id) for _id in gestionnaire_ids]


@login_required
def conversion_partie_double_page(request):
    """Page de conversion en partie double"""
    return render(request, 'accounting/conversion_partie_double.html', {
        'title': 'Conversion Partie Double'
    })


@login_required
@require_http_methods(["GET"])
def api_stats_conversion(request):
    """
    API pour obtenir les statistiques de conversion
    """
    try:
        # Total d'entrées DiameX
        diamex_scope = _get_scoped_diamex_queryset(request.user)
        total_diamex = diamex_scope.count()

        # Entrées déjÃ  converties
        deja_converties = diamex_scope.filter(
            ecritures_partie_double__isnull=False
        ).distinct().count()

        # Entrées Cat=00BOOK (déjÃ  en partie double)
        cat_00book = diamex_scope.filter(compte_code='00BOOK').count()

        # Entrées convertibles (celles qui sont valides selon le controle de conversion)
        # On récupère les mÃªmes données que la page de controle
        controle_result = api_controle_conversion(request)

        if controle_result.status_code == 200:
            import json
            controle_data = json.loads(controle_result.content)
            convertibles = controle_data.get('stats', {}).get('convertibles', 0)
            non_convertibles = controle_data.get('stats', {}).get('non_convertibles', 0)
        else:
            convertibles = 0
            non_convertibles = 0

        return JsonResponse({
            'success': True,
            'stats': {
                'total_diamex': total_diamex,
                'deja_converties': deja_converties,
                'cat_00book': cat_00book,
                'convertibles': convertibles,
                'non_convertibles': non_convertibles,
                'a_convertir': total_diamex - deja_converties
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_convertir_entrees(request):
    """
    API pour convertir les entrees DiameX en partie double.

    Parametres:
    - ids: Liste des IDs d'entrees DiameX a convertir (optionnel).
    - force: Boolean pour forcer la reconversion des entrees deja converties.
    - cursor: UUID de reprise pour pagination serveur.
    - batch_size: Taille du lot par requete.
    """
    try:
        import json
        import uuid

        data = json.loads(request.body) if request.body else {}
        ids = data.get('ids', []) or []
        force = bool(data.get('force', False))
        cursor = data.get('cursor')

        try:
            batch_size = int(data.get('batch_size', 300))
        except (TypeError, ValueError):
            batch_size = 300
        batch_size = max(25, min(batch_size, 1000))

        # Donnees de reference (meme logique que controle conversion)
        journaux_qs = Journal.objects.exclude(code__isnull=True).exclude(code='')
        employes_qs = Employe.objects.exclude(surnom__isnull=True).exclude(surnom='').exclude(code_tiers__isnull=True).exclude(code_tiers='')

        organisation_ids = _get_user_scope_organisation_ids(request.user)
        if organisation_ids is not None:
            if organisation_ids:
                journaux_qs = journaux_qs.filter(base__organisation_id__in=organisation_ids)
                employes_qs = employes_qs.filter(base__organisation_id__in=organisation_ids)
            else:
                journaux_qs = journaux_qs.none()
                employes_qs = employes_qs.none()

        journaux = {code: compte for code, compte in journaux_qs.values_list('code', 'compte')}
        employes_surnom = {
            surnom.lower(): code_tiers
            for surnom, code_tiers in employes_qs.values_list('surnom', 'code_tiers')
        }
        fournisseurs_idxls = {
            str(idxls).lower(): code_tiers
            for idxls, code_tiers in Fournisseur.objects
            .exclude(idxls__isnull=True)
            .exclude(code_tiers__isnull=True)
            .exclude(code_tiers='')
            .values_list('idxls', 'code_tiers')
        }

        # Scope des entrees + pagination serveur
        entrees_qs = _get_scoped_diamex_queryset(request.user)
        if ids:
            entrees_qs = entrees_qs.filter(id__in=ids)
        if not force:
            entrees_qs = entrees_qs.filter(ecritures_partie_double__isnull=True)

        if cursor not in (None, ''):
            try:
                cursor_id = int(cursor)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'error': 'Cursor invalide'}, status=400)
            entrees_qs = entrees_qs.filter(id__gt=cursor_id)

        entrees_qs = entrees_qs.only(
            'id', 'journal_code', 'compte_code', 'pers', 'rec', 'date_m', 'date_rec', 'description',
            'montant_out', 'montant_in', 'fournisseur', 'detail', 'activ', 'fin', 'info', 'scan'
        ).order_by('id')

        entrees_batch = list(entrees_qs[:batch_size])

        stats = {
            'total': 0,
            'converties': 0,
            'erreurs': 0,
            'cat_00book': 0,
            'conversions_standard': 0,
            'details_erreurs': [],
            'details_erreurs_omises': 0,
        }

        if not entrees_batch:
            return JsonResponse({
                'success': True,
                'message': 'Aucune entree a traiter',
                'stats': stats,
                'has_more': False,
                'next_cursor': None,
            })

        max_error_details = 200
        ecritures_to_create = []

        def add_error(entree_id, message):
            stats['erreurs'] += 1
            if len(stats['details_erreurs']) < max_error_details:
                stats['details_erreurs'].append({'id': entree_id, 'erreur': message})
            else:
                stats['details_erreurs_omises'] += 1

        def to_decimal(value):
            if value is None or value == '':
                return Decimal('0')
            return Decimal(str(value))

        for entree in entrees_batch:
            stats['total'] += 1
            try:
                journal_val = entree.journal_code or ''
                compte_val = entree.compte_code or ''
                pers_val = entree.pers or ''

                code_journal = None
                if journal_val == '00PERS':
                    pers_lower = pers_val.lower()
                    if pers_val == '00SPLIT':
                        code_journal = '401000'
                    elif pers_lower in employes_surnom:
                        code_journal = employes_surnom[pers_lower]
                    elif pers_lower in fournisseurs_idxls:
                        code_journal = fournisseurs_idxls[pers_lower]
                elif journal_val in journaux:
                    code_journal = journaux[journal_val]

                if not code_journal:
                    if journal_val == '00PERS':
                        add_error(entree.id, f'Code journal introuvable - Journal=00PERS, PERS={pers_val}')
                    else:
                        add_error(entree.id, f'Code journal introuvable pour {journal_val}')
                    continue

                code_cat = None
                if compte_val and len(compte_val) == 6 and compte_val.isdigit():
                    code_cat = compte_val
                elif compte_val == '00BOOK':
                    code_cat = code_journal
                elif compte_val == '00FND1':
                    code_cat = '742200'
                elif compte_val == '00FND2':
                    code_cat = '742210'
                elif compte_val == '00PERS':
                    pers_lower = pers_val.lower()
                    if pers_val == '00SPLIT':
                        code_cat = '401000'
                    elif pers_lower in employes_surnom:
                        code_cat = employes_surnom[pers_lower]
                    elif pers_lower in fournisseurs_idxls:
                        code_cat = fournisseurs_idxls[pers_lower]

                if not code_cat:
                    if compte_val == '00PERS':
                        add_error(entree.id, f'Code Cat introuvable - Cat=00PERS, PERS={pers_val}')
                    else:
                        add_error(entree.id, f'Code Cat introuvable pour {compte_val}')
                    continue

                id_lien = str(uuid.uuid4())

                if compte_val == '00BOOK':
                    ecritures_to_create.append(EcriturePartieDouble(
                        entree_diamex_id=entree.id,
                        numero_ligne=1,
                        rec=entree.rec,
                        date=entree.date_rec or entree.date_m,
                        compte=code_journal,
                        libelle=entree.description,
                        debit=to_decimal(entree.montant_out),
                        credit=to_decimal(entree.montant_in),
                        fournisseur=entree.fournisseur,
                        detail=entree.detail,
                        activ=entree.activ,
                        financement=entree.fin,
                        info=entree.info,
                        id_lien=id_lien,
                        scan=entree.scan,
                        type_conversion='00BOOK',
                    ))
                    stats['cat_00book'] += 1
                else:
                    ecritures_to_create.append(EcriturePartieDouble(
                        entree_diamex_id=entree.id,
                        numero_ligne=1,
                        rec=entree.rec,
                        date=entree.date_rec or entree.date_m,
                        compte=code_journal,
                        libelle=entree.description,
                        debit=to_decimal(entree.montant_out),
                        credit=to_decimal(entree.montant_in),
                        fournisseur=entree.fournisseur,
                        detail=entree.detail,
                        activ=entree.activ,
                        financement=entree.fin,
                        info=entree.info,
                        id_lien=id_lien,
                        scan=entree.scan,
                        type_conversion='standard',
                    ))
                    ecritures_to_create.append(EcriturePartieDouble(
                        entree_diamex_id=entree.id,
                        numero_ligne=2,
                        rec=entree.rec,
                        date=entree.date_rec or entree.date_m,
                        compte=code_cat,
                        libelle=entree.description,
                        debit=to_decimal(entree.montant_in),
                        credit=to_decimal(entree.montant_out),
                        fournisseur=entree.fournisseur,
                        detail=entree.detail,
                        activ=entree.activ,
                        financement=entree.fin,
                        info=entree.info,
                        id_lien=id_lien,
                        scan=entree.scan,
                        type_conversion='standard',
                    ))
                    stats['conversions_standard'] += 1

                stats['converties'] += 1
            except Exception as e:
                add_error(entree.id, str(e))

        batch_ids = [entree.id for entree in entrees_batch]
        with transaction.atomic():
            if force and batch_ids:
                EcriturePartieDouble.objects.filter(entree_diamex_id__in=batch_ids).delete()
            if ecritures_to_create:
                EcriturePartieDouble.objects.bulk_create(ecritures_to_create, batch_size=1000)

        next_cursor = entrees_batch[-1].id

        has_more_qs = _get_scoped_diamex_queryset(request.user)
        if ids:
            has_more_qs = has_more_qs.filter(id__in=ids)
        if not force:
            has_more_qs = has_more_qs.filter(ecritures_partie_double__isnull=True)
        has_more = has_more_qs.filter(id__gt=entrees_batch[-1].id).exists()

        return JsonResponse({
            'success': True,
            'message': (
                f"{stats['converties']} entree(s) convertie(s) "
                f"({stats['cat_00book']} Cat 00BOOK, {stats['conversions_standard']} conversions standard)"
            ),
            'stats': stats,
            'has_more': has_more,
            'next_cursor': next_cursor if has_more else None,
            'batch_size': batch_size,
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
@login_required
@require_http_methods(["GET"])
def api_analyser_erreurs_pers(request):
    """
    API pour analyser les erreurs PERS et les grouper
    """
    try:
        from django.db.models import Count

        # Récupérer les données de référence
        employes_qs = Employe.objects.all()
        organisation_ids = _get_user_scope_organisation_ids(request.user)
        if organisation_ids is not None:
            if organisation_ids:
                employes_qs = employes_qs.filter(base__organisation_id__in=organisation_ids)
            else:
                employes_qs = employes_qs.none()
        employes_surnom = {e.surnom.lower(): e.code_tiers for e in employes_qs.exclude(surnom__isnull=True).exclude(surnom='')}
        fournisseurs_idxls = {str(f.idxls).lower(): f.code_tiers for f in Fournisseur.objects.exclude(idxls__isnull=True).exclude(code_tiers__isnull=True).exclude(code_tiers='')}

        # Récupérer toutes les entrées avec Journal=00PERS ou Cat=00PERS
        entrees_pers = _get_scoped_diamex_queryset(request.user).filter(
            models.Q(journal_code='00PERS') | models.Q(compte_code='00PERS')
        )

        # Grouper par valeur PERS
        pers_stats = {}
        for entree in entrees_pers:
            pers_val = entree.pers or ''
            pers_lower = pers_val.lower()

            # Vérifier si trouvable
            est_employe = pers_lower in employes_surnom
            est_fournisseur = pers_lower in fournisseurs_idxls
            est_split = pers_val == '00SPLIT'
            est_trouvable = est_employe or est_fournisseur or est_split

            if pers_val not in pers_stats:
                pers_stats[pers_val] = {
                    'pers': pers_val,
                    'count': 0,
                    'est_trouvable': est_trouvable,
                    'type': 'Employé' if est_employe else ('Fournisseur' if est_fournisseur else ('Split' if est_split else 'Introuvable'))
                }

            pers_stats[pers_val]['count'] += 1

        # Trier par nombre d'occurrences
        pers_list = sorted(pers_stats.values(), key=lambda x: x['count'], reverse=True)

        # Statistiques
        total_pers = len(pers_list)
        trouvables = sum(1 for p in pers_list if p['est_trouvable'])
        introuvables = total_pers - trouvables
        total_entrees_probleme = sum(p['count'] for p in pers_list if not p['est_trouvable'])

        return JsonResponse({
            'success': True,
            'stats': {
                'total_valeurs_pers': total_pers,
                'trouvables': trouvables,
                'introuvables': introuvables,
                'total_entrees_probleme': total_entrees_probleme
            },
            'pers_list': pers_list[:50]  # Limiter aux 50 premières
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_ecritures_partie_double_list(request):
    """
    API pour lister les écritures partie double avec filtres
    """
    try:
        # Filtres
        date_debut = request.GET.get('date_debut')
        date_fin = request.GET.get('date_fin')
        compte = request.GET.get('compte')
        type_conversion = request.GET.get('type_conversion')
        search = request.GET.get('search')

        # RequÃªte de base
        diamex_scope = _get_scoped_diamex_queryset(request.user)
        ecritures_qs = EcriturePartieDouble.objects.select_related('entree_diamex').filter(
            entree_diamex__in=diamex_scope
        )

        # Appliquer les filtres
        if date_debut:
            ecritures_qs = ecritures_qs.filter(date__gte=date_debut)
        if date_fin:
            ecritures_qs = ecritures_qs.filter(date__lte=date_fin)
        if compte:
            ecritures_qs = ecritures_qs.filter(compte=compte)
        if type_conversion:
            ecritures_qs = ecritures_qs.filter(type_conversion=type_conversion)
        if search:
            from django.db.models import Q
            ecritures_qs = ecritures_qs.filter(
                Q(libelle__icontains=search) |
                Q(compte__icontains=search) |
                Q(fournisseur__icontains=search) |
                Q(detail__icontains=search)
            )

        # Limiter Ã  1000 résultats
        ecritures_qs = ecritures_qs[:1000]

        # Préparer les données
        ecritures_data = []
        for ecriture in ecritures_qs:
            # Récupérer le chemin de base depuis l'employé qui a importé
            chemin_base = ''
            scan_absolu = ecriture.scan

            if ecriture.entree_diamex.imported_by:
                employe = ecriture.entree_diamex.imported_by
                # Récupérer le chemin de base depuis EmployeBaseDiameX
                employe_base = employe.bases_diamex.filter(
                    base_diamex=ecriture.entree_diamex.fichier_source
                ).first()

                if employe_base:
                    chemin_base = employe_base.chemin_base_diamex

                    # Reconstruire le chemin absolu du scan
                    if ecriture.scan:
                        scan_relatif = ecriture.scan
                        # Nettoyer le chemin relatif (enlever .\ ou ./ au début)
                        scan_clean = scan_relatif.lstrip('.')

                        # Vérifier si le chemin n'est pas déjÃ  absolu
                        if scan_relatif.startswith(chemin_base):
                            # DéjÃ  absolu
                            scan_absolu = scan_relatif
                        else:
                            # Concaténer chemin_base + scan_clean
                            scan_absolu = chemin_base + scan_clean

            # Récupérer le nom du compte (Compte, Fournisseur ou Employé)
            nom_compte = None
            if ecriture.compte:
                try:
                    # 1. Essayer dans la table des comptes
                    compte_obj = Compte.objects.filter(compte=ecriture.compte).first()
                    if compte_obj:
                        nom_compte = compte_obj.nom_compte
                    else:
                        # 2. Essayer dans les fournisseurs (comptes de tiers)
                        fournisseur_obj = Fournisseur.objects.filter(code_tiers=ecriture.compte).first()
                        if fournisseur_obj:
                            nom_compte = fournisseur_obj.nom_fournisseur
                        else:
                            # 3. Essayer dans les employés (comptes de tiers)
                            employe_obj = Employe.objects.filter(code_tiers=ecriture.compte).first()
                            if employe_obj:
                                nom_compte = employe_obj.nom_affichage
                except Exception:
                    pass

            # Récupérer le nom du fournisseur (Fournisseur ou Employé)
            nom_fournisseur = None
            if ecriture.fournisseur:
                try:
                    # 1. Essayer dans les fournisseurs
                    f_obj = Fournisseur.objects.filter(
                        models.Q(code_tiers=ecriture.fournisseur) |
                        models.Q(nom_fournisseur__icontains=ecriture.fournisseur)
                    ).first()
                    if f_obj:
                        nom_fournisseur = f_obj.nom_fournisseur
                    else:
                        # 2. Essayer dans les employés
                        e_obj = Employe.objects.filter(
                            models.Q(code_tiers=ecriture.fournisseur) |
                            models.Q(nom_affichage__icontains=ecriture.fournisseur)
                        ).first()
                        if e_obj:
                            nom_fournisseur = e_obj.nom_affichage
                except Exception:
                    pass

            ecritures_data.append({
                'id': str(ecriture.id),
                'id_diamex': ecriture.entree_diamex.id,
                'numero_ligne': ecriture.numero_ligne,
                'rec': ecriture.rec,
                'date': str(ecriture.date) if ecriture.date else None,
                'compte': ecriture.compte,
                'nom_compte': nom_compte,
                'libelle': ecriture.libelle,
                'debit': float(ecriture.debit),
                'credit': float(ecriture.credit),
                'fournisseur': ecriture.fournisseur,
                'nom_fournisseur': nom_fournisseur,
                'detail': ecriture.detail,
                'activ': ecriture.activ,
                'financement': ecriture.financement,
                'info': ecriture.info,
                'id_lien': ecriture.id_lien,
                'scan': scan_absolu,  # Chemin absolu reconstruit
                'type_conversion': ecriture.type_conversion,
                'est_equilibree': ecriture.est_equilibree
            })

        return JsonResponse({
            'success': True,
            'ecritures': ecritures_data,
            'total': len(ecritures_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


