"""
Vues pour la vérification de conformité des autres comptes
Vérifie les comptes qui ne sont ni des paiements employés ni des fournisseurs
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from apps.accounting.models import BaseDiameX
from apps.organization.models import Compte
from apps.accounting.charte_verification import verifier_charte_compte
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
from apps.employees.models import EmployeBaseDiameX
import re
from datetime import datetime


def _is_access_driver_unavailable(error):
    text = str(error or '').lower()
    return "can't open lib" in text and 'microsoft access driver' in text


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _filter_comptes_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()
    return queryset.filter(organisation_id=organisation_id)


def _get_scoped_diamex_queryset(user):
    qs = BaseDiameX.objects.all()
    if getattr(user, 'is_superuser', False):
        return qs

    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return qs.none()

    from apps.organization.models import Base

    allowed_progs = list(
        Base.objects.filter(organisation_id=organisation_id)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )
    if not allowed_progs:
        return qs.none()
    return qs.filter(prog__in=allowed_progs)


def _build_access_update_payload_for_entry(user, entry, updates):
    if not entry.fichier_source or not updates:
        return None

    base_diamex = None
    user_employe = getattr(user, 'employe', None)
    if user_employe:
        base_diamex = EmployeBaseDiameX.objects.filter(
            employe=user_employe,
            base_diamex=entry.fichier_source
        ).first()

    if not base_diamex and entry.imported_by:
        base_diamex = EmployeBaseDiameX.objects.filter(
            employe=entry.imported_by,
            base_diamex=entry.fichier_source
        ).first()

    if not base_diamex:
        prog_value = (entry.prog or '').strip()
        if prog_value:
            base_diamex = EmployeBaseDiameX.objects.filter(base_diamex__icontains=prog_value).first()
    if not base_diamex:
        base_diamex = EmployeBaseDiameX.objects.filter(base_diamex=entry.fichier_source).first()
    if not base_diamex:
        return None

    return {
        'file_path': base_diamex.chemin_complet,
        'id_access': entry.id_access,
        'updates': updates,
    }


@login_required
def verification_autres_comptes(request):
    """Page de vérification des autres comptes (ni employés, ni fournisseurs)"""

    # Filtrer les comptes par organisation de l'utilisateur (si applicable)
    autres_comptes_qs = Compte.objects.exclude(
        Q(employe_obligatoire=True) |
        Q(fournisseur_obligatoire=True)
    ).exclude(compte__in=['748201', '707401', '748411', '748415'])

    # Filtrer par organisation si l'utilisateur en a une
    if hasattr(request.user, 'employe') and request.user.employe and request.user.employe.base:
        organisation = request.user.employe.base.organisation
        autres_comptes_qs = autres_comptes_qs.filter(organisation=organisation)

    autres_comptes = autres_comptes_qs.select_related('organisation')

    # Compter les comptes employés et fournisseurs pour les stats
    codes_employes_count = Compte.objects.filter(employe_obligatoire=True).count()
    codes_fournisseurs_count = Compte.objects.filter(fournisseur_obligatoire=True).count()

    context = {
        'title': 'Vérification Autres Comptes',
        'autres_comptes': autres_comptes,
        'autres_comptes_count': autres_comptes.count(),
        'codes_employes_count': codes_employes_count,
        'codes_fournisseurs_count': codes_fournisseurs_count,
    }

    return render(request, 'accounting/verification_autres.html', context)


@login_required
@require_http_methods(["GET"])
def api_verification_autres_comptes(request):
    """
    API pour r?cup?rer les entr?es DiameX des autres comptes
    """
    try:
        search = request.GET.get('search', '').strip()
        prog_filter = request.GET.get('prog', '').strip()
        compte_filter = request.GET.get('compte', '').strip()
        source_filter = request.GET.get('source', '').strip()
        type_filter = request.GET.get('type', '').strip()
        conformite_filter = request.GET.get('conformite', '').strip()
        mois_filter = request.GET.get('mois', '').strip()  # 'AAAA-MM' ou vide

        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 50))

        comptes_exclus_qs = _filter_comptes_by_scope(
            Compte.objects.filter(
                Q(employe_obligatoire=True) | Q(fournisseur_obligatoire=True)
            ),
            request.user
        )
        codes_exclus = set(comptes_exclus_qs.values_list('compte', flat=True))
        codes_exclus.update(['748201', '707401', '748411', '748415'])

        entries_qs = _get_scoped_diamex_queryset(request.user).exclude(
            compte_code__in=codes_exclus
        ).exclude(
            Q(compte_code__istartswith='00BOOK') |
            Q(compte_code__istartswith='00PERS') |
            Q(compte_code__istartswith='00SPLITBOOK') |
            Q(compte_code__istartswith='00FND1')
        ).select_related('imported_by')

        if prog_filter and prog_filter != 'all':
            entries_qs = entries_qs.filter(prog=prog_filter)

        if compte_filter and compte_filter != 'all':
            entries_qs = entries_qs.filter(compte_code=compte_filter)

        if source_filter and source_filter != 'all':
            entries_qs = entries_qs.filter(fichier_source=source_filter)

        if type_filter and type_filter != 'all':
            if type_filter == 'entree':
                entries_qs = entries_qs.filter(Q(montant_in__isnull=False) | Q(montant_in__gt=0))
            elif type_filter == 'sortie':
                entries_qs = entries_qs.filter(Q(montant_out__isnull=False) | Q(montant_out__gt=0))

        if mois_filter:
            try:
                annee_m, mois_m = mois_filter.split('-')
                entries_qs = entries_qs.filter(
                    date_rec__year=int(annee_m), date_rec__month=int(mois_m)
                )
            except ValueError:
                pass  # format invalide : filtre ignoré

        if search:
            entries_qs = entries_qs.filter(
                Q(description__icontains=search) |
                Q(pers__icontains=search) |
                Q(detail__icontains=search) |
                Q(compte_code__icontains=search)
            )

        all_entries = entries_qs.order_by('-date_m', '-id')
        compte_map = {
            (compte.compte or '').strip(): compte
            for compte in _filter_comptes_by_scope(Compte.objects.all(), request.user)
        }

        entries_analysees = []
        total_entrees = 0
        total_sorties = 0
        montant_total_entrees = 0
        montant_total_sorties = 0

        for entry in all_entries:
            try:
                is_entree = bool(entry.montant_in and entry.montant_in > 0)
                is_sortie = bool(entry.montant_out and entry.montant_out > 0)
                entry_type = 'Entr?e' if is_entree else 'Sortie' if is_sortie else 'Inconnu'

                if is_entree:
                    total_entrees += 1
                    montant_total_entrees += float(entry.montant_in)
                if is_sortie:
                    total_sorties += 1
                    montant_total_sorties += float(entry.montant_out)

                compte_code = (entry.compte_code or '').strip()
                compte_obj = compte_map.get(compte_code)
                if not compte_obj and compte_code:
                    compte_obj = _filter_comptes_by_scope(
                        Compte.objects.filter(compte=compte_code),
                        request.user
                    ).first()
                charte_result = None
                if compte_obj and compte_obj.charte_verification:
                    charte_result = verifier_charte_compte(
                        description=entry.description or '',
                        charte_type=compte_obj.charte_verification,
                        compte_code=compte_code
                    )

                fichier_nom = ''
                if entry.fichier_source:
                    import os
                    fichier_nom = os.path.basename(entry.fichier_source)

                extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)

                entry_data = {
                    'id': entry.id,
                    'rec': entry.rec,
                    'date_m': entry.date_rec.strftime('%Y-%m-%d') if entry.date_rec else None,
                    'prog': entry.prog or '',
                    'description': entry.description or '',
                    'cat': compte_code,
                    'cat_libelle': compte_obj.nom_compte if compte_obj else '',
                    'pers': entry.pers or '',
                    'detail': entry.detail or '',
                    'inn': float(entry.montant_in) if entry.montant_in else 0,
                    'out': float(entry.montant_out) if entry.montant_out else 0,
                    'type': entry_type,
                    'fichier_source': entry.fichier_source or '',
                    'fichier_nom': fichier_nom,
                    'charte_type': compte_obj.get_charte_verification_display() if compte_obj and compte_obj.charte_verification else None,
                    'charte_conforme': charte_result['conforme'] if charte_result else None,
                    'charte_erreurs': charte_result['erreurs'] if charte_result else [],
                    'charte_details': charte_result['details'] if charte_result else {},
                    'ouvrage_extrait_nom': extraction['ouvrage_nom'],
                    'ouvrage_extrait_id': str(extraction['ouvrage_obj'].id) if extraction['ouvrage_obj'] else None,
                    'ouvrage_extrait_libelle': extraction['ouvrage_obj'].nom_ouvrage if extraction['ouvrage_obj'] else None,
                    'mois_extrait': extraction['mois'],
                    'annee_extrait': extraction['annee'],
                    'date_extrait': extraction['date_str'],
                    'point_eau_extrait_idxls': extraction.get('point_eau_idxls'),
                    'point_eau_extrait_id': str(extraction['point_eau_obj'].id) if extraction.get('point_eau_obj') else None,
                    'point_eau_extrait_nom': extraction['point_eau_obj'].code_point_eau if extraction.get('point_eau_obj') else None,
                }

                if conformite_filter and conformite_filter != 'all':
                    if conformite_filter == 'conforme' and charte_result and not charte_result.get('conforme'):
                        continue
                    if conformite_filter == 'non_conforme' and (not charte_result or charte_result.get('conforme')):
                        continue

                entries_analysees.append(entry_data)
            except Exception as entry_error:
                entries_analysees.append({
                    'id': entry.id,
                    'rec': entry.rec,
                    'date_m': entry.date_rec.strftime('%Y-%m-%d') if entry.date_rec else None,
                    'prog': entry.prog or '',
                    'description': entry.description or '',
                    'cat': entry.compte_code or '',
                    'cat_libelle': '',
                    'pers': entry.pers or '',
                    'detail': entry.detail or '',
                    'inn': float(entry.montant_in) if entry.montant_in else 0,
                    'out': float(entry.montant_out) if entry.montant_out else 0,
                    'type': 'Erreur',
                    'fichier_source': entry.fichier_source or '',
                    'fichier_nom': entry.fichier_source or '',
                    'charte_type': None,
                    'charte_conforme': False,
                    'charte_erreurs': [f'Erreur analyse transaction: {entry_error}'],
                    'charte_details': {},
                    'ouvrage_extrait_nom': None,
                    'ouvrage_extrait_id': None,
                    'ouvrage_extrait_libelle': None,
                    'mois_extrait': None,
                    'annee_extrait': None,
                    'date_extrait': None,
                    'point_eau_extrait_idxls': None,
                    'point_eau_extrait_id': None,
                    'point_eau_extrait_nom': None,
                })

        total = len(entries_analysees)
        total_conformes = sum(1 for e in entries_analysees if e.get('charte_conforme') is True)
        total_non_conformes = sum(1 for e in entries_analysees if e.get('charte_conforme') is False)
        taux_conformite = int((total_conformes / total * 100) if total > 0 else 0)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        entries_page = entries_analysees[start_idx:end_idx]
        total_pages = (total + per_page - 1) // per_page

        return JsonResponse({
            'entries': entries_page,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            'stats': {
                'total': total,
                'total_entrees': total_entrees,
                'total_sorties': total_sorties,
                'montant_total_entrees': montant_total_entrees,
                'montant_total_sorties': montant_total_sorties,
                'total_conformes': total_conformes,
                'total_non_conformes': total_non_conformes,
                'taux_conformite': taux_conformite,
            }
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return JsonResponse({
            'error': str(e),
            'trace': error_trace
        }, status=500)




def trouver_base_access_par_prog(prog):
    """
    Trouve la base Access correspondant au mieux à un prog donné
    Utilise un algorithme de scoring basé sur les mots-clés
    """
    from apps.employees.models import EmployeBaseDiameX

    # Chercher correspondance exacte d'abord
    base_diamex = EmployeBaseDiameX.objects.filter(
        base_diamex__icontains=prog
    ).first()

    if base_diamex:
        return base_diamex

    # Essayer par mots-clés avec scoring
    prog_keywords = prog.split('-')
    keywords_clean = []
    for kw in prog_keywords:
        kw = kw.strip()
        if len(kw) > 3 and kw.upper() not in ['EHA', 'SKJ']:
            sub_words = kw.split()
            if len(sub_words) > 1:
                for sub in sub_words:
                    if len(sub) > 3:
                        keywords_clean.append(sub)
            else:
                keywords_clean.append(kw)

    if keywords_clean:
        bases = EmployeBaseDiameX.objects.all()
        best_match = None
        best_score = 0

        for base in bases:
            score = 0
            base_name = base.base_diamex.lower()
            for kw in keywords_clean:
                if kw.lower() in base_name:
                    score += 1
            if score > best_score:
                best_score = score
                best_match = base

        if best_match:
            return best_match

    return None

@login_required
@require_http_methods(["POST"])
def api_modifier_entry_autre(request):
    """API pour modifier une entrée DiameX d'un autre compte"""
    import json
    import pyodbc
    import os

    try:
        data = json.loads(request.body)
        entry_id = data.get('entry_id')
        champ = data.get('champ')  # 'description', 'pers', 'detail', 'cat'
        nouvelle_valeur = data.get('nouvelle_valeur', '').strip()

        if not entry_id or not champ:
            return JsonResponse({
                'success': False,
                'message': 'Données manquantes'
            }, status=400)

        # Vérifier que le champ est autorisé
        champs_autorises = ['description', 'pers', 'detail', 'cat']
        if champ not in champs_autorises:
            return JsonResponse({
                'success': False,
                'message': f'Champ non autorisé: {champ}'
            }, status=400)

        # Récupérer l'entrée
        entry = BaseDiameX.objects.get(id=entry_id)

        # Mapper les noms de champs Django vers les noms Access
        champ_mapping = {
            'description': 'Description',
            'pers': 'PERS',  # En majuscules dans Access
            'detail': 'Detail',
            'cat': 'Cat'
        }
        champ_access = champ_mapping.get(champ, champ)

        # 1. Mettre à jour Django (PostgreSQL)
        setattr(entry, champ, nouvelle_valeur)
        entry.save(update_fields=[champ])

        django_success = True
        access_success = False
        access_message = ''
        access_status = 'not_attempted'
        access_payload = _build_access_update_payload_for_entry(
            request.user,
            entry,
            {champ_access: nouvelle_valeur}
        )

        # 2. Mettre ? jour Access
        if entry.prog:
            try:
                # Trouver la base Access correspondante
                base_diamex = trouver_base_access_par_prog(entry.prog)

                if base_diamex and base_diamex.chemin_base_diamex:
                    # Chemin complet vers la base Access (dossier + nom fichier)
                    chemin_dossier = base_diamex.chemin_base_diamex
                    nom_fichier = base_diamex.base_diamex
                    chemin_access = os.path.join(chemin_dossier, nom_fichier)

                    # Connexion ? la base Access
                    conn_str = (
                        r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                        f'DBQ={chemin_access};'
                    )
                    conn = pyodbc.connect(conn_str)
                    cursor = conn.cursor()

                    # Pr?parer la requ?te SQL
                    # On utilise DateRec, Prog, In et Out comme identifiants uniques
                    # Note: DateM est calcul?e automatiquement (1er du mois de DateRec)
                    sql = f"""
                        UPDATE DATA
                        SET {champ_access} = ?
                        WHERE DateRec = ? AND Prog = ? AND [In] = ? AND [Out] = ?
                    """

                    cursor.execute(sql, (
                        nouvelle_valeur,
                        entry.date_rec,
                        entry.prog,
                        entry.montant_in if entry.montant_in else 0,
                        entry.montant_out if entry.montant_out else 0
                    ))

                    conn.commit()
                    rows_affected = cursor.rowcount
                    cursor.close()
                    conn.close()

                    if rows_affected > 0:
                        access_success = True
                        access_status = 'updated'
                        access_message = f'{rows_affected} ligne(s) mise(s) ? jour dans Access'
                    else:
                        access_status = 'not_found'
                        access_message = 'Aucune ligne trouv?e dans Access (peut-?tre d?j? ? jour)'
                else:
                    access_status = 'missing_file'
                    access_message = f'Base Access non trouvee pour le prog: {entry.prog}'

            except pyodbc.Error as e:
                if _is_access_driver_unavailable(e):
                    access_status = 'driver_unavailable'
                    access_message = 'Synchronisation Access non disponible sur ce serveur'
                else:
                    access_status = 'error'
                    access_message = f'Erreur Access: {str(e)}'
            except Exception as e:
                access_status = 'error'
                access_message = f'Erreur lors de la mise a jour Access: {str(e)}'
        else:
            access_status = 'missing_prog'
            access_message = 'Pas de prog defini pour cette entree'

        if django_success and access_success:
            return JsonResponse({
                'success': True,
                'message': f'{champ.capitalize()} mis à jour avec succès',
                'django_success': True,
                'access_success': True,
                'access_status': access_status,
                'access_message': access_message,
                'access_payload': None,
                'fichier_source': entry.fichier_source
            })
        elif django_success and not access_success:
            message = f'{champ.capitalize()} mis ? jour dans Django mais pas dans Access'
            if access_status == 'driver_unavailable':
                message = f'{champ.capitalize()} mis ? jour dans Django (synchronisation Access indisponible sur ce serveur)'
            return JsonResponse({
                'success': True,
                'partial': True,
                'message': message,
                'django_success': True,
                'access_success': False,
                'access_status': access_status,
                'access_message': access_message,
                'access_payload': access_payload,
                'fichier_source': entry.fichier_source
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Erreur lors de la mise à jour',
                'django_success': False,
                'access_success': False
            }, status=500)

    except BaseDiameX.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Entrée introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }, status=500)
