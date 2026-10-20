"""
Vues pour la vérification de conformité des dépenses aux fournisseurs
Vérifie que les descriptions DiameX respectent la charte fournisseur
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Q, Count
from apps.accounting.models import BaseDiameX
from apps.organization.models import Compte, Base
from apps.employees.models import EmployeBaseDiameX
from apps.inventory.models_vehicles import Vehicule
import re
from datetime import datetime
import os


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_scoped_diamex_queryset(user):
    qs = BaseDiameX.objects.all()
    if getattr(user, 'is_superuser', False):
        return qs

    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return qs.none()

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


def _filter_comptes_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()
    return queryset.filter(organisation_id=organisation_id)


def _get_scoped_bases_queryset(user):
    qs = EmployeBaseDiameX.objects.all()
    if getattr(user, 'is_superuser', False):
        return qs
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return qs.none()
    return qs.filter(employe__base__organisation_id=organisation_id)


def _normalize_matricule(value):
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())


def _extract_matricule_candidate(value):
    text = str(value or '').upper()
    if not text:
        return ''

    patterns = [
        r'pour\s+(?:moto|voiture)\s+([A-Z0-9][A-Z0-9\s-]{2,}[A-Z0-9])',
        r'(?:moto|voiture)\s+([A-Z0-9][A-Z0-9\s-]{2,}[A-Z0-9])',
        r'\b([0-9]{3,5}\s*[A-Z]{2,4})\b',
        r'\b([A-Z]{1,3}\s*[0-9]{3,5}\s*[A-Z]{1,3})\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = _normalize_matricule(match.group(1))
            if len(candidate) >= 4:
                return candidate

    return ''


def extraire_fournisseur_depuis_description(description):
    """
    Extrait l'IDxls du fournisseur depuis la description DiameX
    Format attendu: [NIF/ISI...]_[Nom Fournisseur]_Libellé...
    """
    if not description:
        return None

    # Extraire la partie entre le premier et le deuxième underscore
    parts = description.split('_')
    if len(parts) >= 2:
        # Le nom du fournisseur est la deuxième partie
        nom_fournisseur = parts[1].strip()
        return nom_fournisseur

    return None


def extraire_infos_carburant(description, detail=''):
    """
    Extrait quantite carburant et matricule vehicule
    depuis un libelle de carburant.
    """
    raw_description = str(description or '').strip()
    raw_detail = str(detail or '').strip()
    full_text = f"{raw_description} {raw_detail}".strip()
    result = {
        'quantite_litres': None,
        'matricule_vehicule': '',
        'type_carburant': '',
    }
    if not full_text:
        return result

    fuel_match = re.search(r'_(Essence|Gasoil|Gazole|Diesel)_', raw_description, flags=re.IGNORECASE)
    if fuel_match:
        result['type_carburant'] = fuel_match.group(1)

    qty_match = None
    parts = [part.strip() for part in raw_description.split('_')]
    quantity_chunks = []
    if len(parts) >= 6:
        quantity_chunks.append(parts[5])
    if len(parts) >= 7:
        quantity_chunks.append(parts[6])

    for quantity_chunk in quantity_chunks:
        qty_match = re.search(r'\bx\s*([0-9]+(?:[.,][0-9]+)?)', quantity_chunk, flags=re.IGNORECASE)
        if qty_match:
            break

    if not qty_match:
        qty_match = re.search(r'\bx\s*([0-9]+(?:[.,][0-9]+)?)', full_text, flags=re.IGNORECASE)
    if not qty_match:
        qty_match = re.search(r'([0-9]+(?:[.,][0-9]+)?)\s*(?:l|litre|litres)\b', full_text, flags=re.IGNORECASE)
    if qty_match:
        try:
            result['quantite_litres'] = float(qty_match.group(1).replace(',', '.'))
        except Exception:
            result['quantite_litres'] = None

    # Extract license plate from description first to avoid capturing duplicated text.
    result['matricule_vehicule'] = _extract_matricule_candidate(raw_description)

    # Fallback: try detail field separately if nothing found
    if not result['matricule_vehicule'] and raw_detail:
        detail_clean = _extract_matricule_candidate(raw_detail)
        if len(detail_clean) >= 4:
            result['matricule_vehicule'] = detail_clean

    # Last fallback for detail values containing only the plate itself.
    if not result['matricule_vehicule'] and raw_detail:
        detail_clean = _normalize_matricule(raw_detail)
        if len(detail_clean) >= 4:
            result['matricule_vehicule'] = detail_clean

    return result


def _build_vehicules_map():
    """Return a plate lookup without letting vehicle lookup errors break the API."""
    try:
        return {
            _normalize_matricule(v.immatriculation): v.immatriculation
            for v in Vehicule.objects.all().only('immatriculation')
            if v.immatriculation
        }
    except Exception:
        return {}


def _is_access_driver_unavailable(error):
    text = str(error or '').lower()
    return "can't open lib" in text and 'microsoft access driver' in text


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


def verifier_format_charte_fournisseur(description, fournisseur_idxls=None, compte_code=None, detail=''):
    """
    Vérifie si la description respecte la charte fournisseur

    Format attendu standard:
    [NIF si NIF existe, NIF PREST si NIF+prestation, ISI si pas NIF, ISI PREST si pas NIF+prestation]_
    [Nom du fournisseur (IDxls dans colonne Fournisseur)]_
    Libellé de la transaction_
    [Unité]_
    [PU]_
    reste du libellé

    Format spécial Indemnité (compte 621101):
    Indemnité RBF_U_[Quantité]_[Prix unitaire]_[Nom de l'ouvrage]

    Returns:
        dict avec 'conforme' (bool), 'erreurs' (list), 'details' (dict)
    """
    from apps.billing.models import Fournisseur

    if not description:
        return {
            'conforme': False,
            'erreurs': ['Description vide'],
            'details': {}
        }

    erreurs = []
    details = {}

    if compte_code in ['606100', '606107']:
        carburant_info = extraire_infos_carburant(description, detail)
        details['type'] = 'carburant'
        details['type_compte_carburant'] = 'moto' if compte_code == '606100' else 'voiture'
        details['quantite_litres'] = carburant_info['quantite_litres']
        details['matricule_vehicule'] = carburant_info['matricule_vehicule']
        details['type_carburant'] = carburant_info['type_carburant']
        if carburant_info['quantite_litres'] in [None, 0]:
            erreurs.append('Quantité carburant non extraite du libellé')
        if not carburant_info['matricule_vehicule']:
            erreurs.append('Matricule véhicule non extrait du libellé / détail')

    # CAS SPÉCIAL : Indemnité pour compte 621101
    if compte_code == '621101' and description.upper().startswith('INDEMNITÉ'):
        # Format attendu : Indemnité RBF_U_[Quantité]_[Prix unitaire]_[Nom de l'ouvrage]
        parts = description.split('_')

        if len(parts) < 5:
            erreurs.append('Format Indemnité incomplet : attendu "Indemnité RBF_U_[Quantité]_[Prix unitaire]_[Nom ouvrage]"')
            return {'conforme': False, 'erreurs': erreurs, 'details': details}

        details['type'] = 'indemnite'
        details['prefix'] = parts[0].strip()  # "Indemnité RBF"
        details['unite'] = parts[1].strip()   # "U"
        details['quantite'] = parts[2].strip()
        details['prix_unitaire'] = parts[3].strip()
        details['ouvrage'] = '_'.join(parts[4:])  # Reste = nom ouvrage

        # Vérifications
        if not parts[0].strip().upper().startswith('INDEMNITÉ'):
            erreurs.append('Doit commencer par "Indemnité"')

        if parts[1].strip().upper() != 'U':
            erreurs.append(f'Unité doit être "U", trouvé "{parts[1].strip()}"')

        try:
            float(parts[2].strip())
        except:
            erreurs.append(f'Quantité "{parts[2].strip()}" doit être un nombre')

        try:
            float(parts[3].strip())
        except:
            erreurs.append(f'Prix unitaire "{parts[3].strip()}" doit être un nombre')

        if not parts[4:]:
            erreurs.append('Nom de l\'ouvrage manquant')

        conforme = len(erreurs) == 0
        return {'conforme': conforme, 'erreurs': erreurs, 'details': details}

    # FORMAT STANDARD (code existant continue)

    # Découper la description par underscore
    parts = description.split('_')

    # Vérifier qu'il y a au moins 2 parties (NIF/ISI + Nom fournisseur)
    if len(parts) < 2:
        erreurs.append('Format incomplet : doit contenir au moins [NIF/ISI]_[Nom Fournisseur]')
        return {'conforme': False, 'erreurs': erreurs, 'details': details}

    # 1. Vérifier la première partie (NIF ou ISI)
    prefix = parts[0].strip().upper()
    details['prefix'] = prefix

    if not (prefix.startswith('NIF') or prefix.startswith('ISI')):
        erreurs.append(f'Préfixe invalide "{prefix}" : doit commencer par NIF ou ISI')

    # Vérifier si c'est une prestation
    is_prestation = 'PREST' in prefix
    details['is_prestation'] = is_prestation

    # 2. Vérifier la deuxième partie (Nom fournisseur)
    nom_fournisseur_description = parts[1].strip() if len(parts) > 1 else ''
    details['nom_fournisseur'] = nom_fournisseur_description

    if not nom_fournisseur_description:
        erreurs.append('Nom du fournisseur manquant (2ème partie)')

    # 3. Vérifier correspondance avec colonne Fournisseur si fournie
    if fournisseur_idxls:
        # Convertir l'IDxls en nom de fournisseur
        fournisseur_obj = Fournisseur.objects.filter(idxls=str(fournisseur_idxls)).first()
        if fournisseur_obj:
            nom_attendu = fournisseur_obj.nom_fournisseur
            details['nom_fournisseur_attendu'] = nom_attendu
            details['idxls'] = fournisseur_idxls

            # Comparer le nom dans la description avec le nom du fournisseur
            if nom_fournisseur_description != nom_attendu:
                erreurs.append(f'Nom fournisseur "{nom_fournisseur_description}" ne correspond pas au nom attendu "{nom_attendu}" (IDxls: {fournisseur_idxls})')
        else:
            details['idxls'] = fournisseur_idxls
            erreurs.append(f'Fournisseur avec IDxls "{fournisseur_idxls}" introuvable dans la base')

    # 4. Vérifier qu'il y a un libellé (3ème partie minimum)
    if len(parts) < 3:
        erreurs.append('Libellé de transaction manquant (3ème partie)')
    else:
        details['libelle'] = parts[2].strip()

    # 5. Format complet attendu : au moins 5 parties pour avoir Unité et PU
    if len(parts) >= 5:
        details['unite'] = parts[3].strip()
        details['pu'] = parts[4].strip()
        details['reste'] = '_'.join(parts[5:]) if len(parts) > 5 else ''
    elif len(parts) >= 3:
        # Format minimal acceptable (sans unité/PU détaillés)
        details['reste'] = '_'.join(parts[3:])

    conforme = len(erreurs) == 0

    return {
        'conforme': conforme,
        'erreurs': erreurs,
        'details': details
    }


@login_required
@login_required
@ensure_csrf_cookie
def verification_depenses_fournisseurs(request):
    """Page de vérification des dépenses fournisseurs"""

    # Récupérer les comptes marqués comme fournisseurs
    comptes_fournisseurs = _filter_comptes_by_scope(
        Compte.objects.filter(fournisseur_obligatoire=True),
        request.user
    )
    comptes_fournisseurs_codes = list(comptes_fournisseurs.values_list('compte', flat=True))
    comptes_fournisseurs_map = {
        (compte.compte or '').strip(): compte.nom_compte or ''
        for compte in comptes_fournisseurs
    }

    context = {
        'title': 'Vérification Dépenses Fournisseurs',
        'comptes_fournisseurs': comptes_fournisseurs,
        'comptes_fournisseurs_count': len(comptes_fournisseurs_codes),
    }

    return render(request, 'accounting/verification_fournisseurs.html', context)


@login_required
@require_http_methods(["GET"])
def api_verification_depenses_fournisseurs(request):
    """
    API pour récupérer les entrées DiameX des comptes fournisseurs avec vérification
    """
    try:
        # Paramètres de filtrage
        search = request.GET.get('search', '').strip()
        prog_filter = request.GET.get('prog', '').strip()
        compte_filter = request.GET.get('compte', '').strip()
        source_filter = request.GET.get('source', '').strip()
        conformite_filter = request.GET.get('conformite', '').strip()  # 'conforme', 'non_conforme', 'all'
        mois_filter = request.GET.get('mois', '').strip()  # 'AAAA-MM' ou vide

        # Pagination
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 50))

        # Récupérer les comptes fournisseurs
        comptes_fournisseurs = _filter_comptes_by_scope(
            Compte.objects.filter(fournisseur_obligatoire=True),
            request.user
        )
        comptes_fournisseurs_codes = list(comptes_fournisseurs.values_list('compte', flat=True))
        comptes_fournisseurs_map = {
            (compte.compte or '').strip(): compte.nom_compte or ''
            for compte in comptes_fournisseurs
        }

        if not comptes_fournisseurs_codes:
            return JsonResponse({
                'entries': [],
                'total': 0,
                'page': page,
                'per_page': per_page,
                'total_pages': 0,
                'stats': {
                    'total': 0,
                    'conformes': 0,
                    'non_conformes': 0,
                    'taux_conformite': 0
                }
            })

        # Construire la requête
        entries_qs = _get_scoped_diamex_queryset(request.user).filter(
            compte_code__in=comptes_fournisseurs_codes
        ).select_related('imported_by')

        # Appliquer les filtres
        if prog_filter and prog_filter != 'all':
            entries_qs = entries_qs.filter(prog=prog_filter)

        if compte_filter and compte_filter != 'all':
            entries_qs = entries_qs.filter(compte_code=compte_filter)

        if source_filter and source_filter != 'all':
            entries_qs = entries_qs.filter(fichier_source=source_filter)

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
                Q(compte_code__icontains=search)
            )

        # Récupérer toutes les entrées pour calculer les stats
        all_entries = entries_qs.order_by('-date_rec', '-id')

        # Créer un dictionnaire fichier_source -> chemin_base
        bases_dict = {}
        for base in _get_scoped_bases_queryset(request.user):
            if base.base_diamex:
                bases_dict[base.base_diamex] = base.chemin_base_diamex or ''

        # Analyser chaque entrée
        entries_analysees = []
        nb_conformes = 0
        nb_non_conformes = 0
        vehicules_map = _build_vehicules_map()

        for entry in all_entries:
            try:
                verification = verifier_format_charte_fournisseur(
                    entry.description,
                    entry.fournisseur,
                    entry.compte_code,
                    entry.detail or ''
                )

                scan_path = ''
                if entry.scan and entry.fichier_source:
                    chemin_base = bases_dict.get(entry.fichier_source, '')
                    if chemin_base:
                        scan_relatif = entry.scan
                        if scan_relatif.startswith('.'):
                            scan_relatif = scan_relatif[1:]
                        if scan_relatif.startswith(chemin_base):
                            scan_path = scan_relatif
                        else:
                            scan_path = chemin_base + scan_relatif
                    else:
                        scan_path = entry.scan

                entry_data = {
                    'id': entry.id,
                    'rec': entry.rec,
                    'date_m': entry.date_rec.strftime('%Y-%m-%d') if entry.date_rec else None,
                    'prog': entry.prog or '',
                    'description': entry.description or '',
                    'cat': entry.compte_code or '',
                    'cat_label': (
                        '606100 - Carburant motos' if entry.compte_code == '606100'
                        else '606107 - Carburant voitures' if entry.compte_code == '606107'
                        else comptes_fournisseurs_map.get((entry.compte_code or '').strip(), '')
                    ),
                    'fournisseur': entry.fournisseur or '',
                    'out': float(entry.montant_out) if entry.montant_out else 0,
                    'fichier_source': entry.fichier_source or '',
                    'scan': scan_path,
                    'conforme': verification['conforme'],
                    'erreurs': verification['erreurs'],
                    'details': verification['details'],
                    'detail_col': entry.detail or '',
                    'is_carburant': entry.compte_code in ['606100', '606107'],
                }
                if entry_data['is_carburant']:
                    matricule_extrait = (verification.get('details') or {}).get('matricule_vehicule') or ''
                    matricule_norm = _normalize_matricule(matricule_extrait)
                    entry_data['vehicule_match'] = bool(matricule_norm and matricule_norm in vehicules_map)
                    entry_data['vehicule_match_label'] = vehicules_map.get(matricule_norm, '')
                else:
                    entry_data['vehicule_match'] = False
                    entry_data['vehicule_match_label'] = ''

                if verification['conforme']:
                    nb_conformes += 1
                else:
                    nb_non_conformes += 1

                entries_analysees.append(entry_data)
            except Exception as entry_error:
                nb_non_conformes += 1
                entries_analysees.append({
                    'id': entry.id,
                    'rec': entry.rec,
                    'date_m': entry.date_rec.strftime('%Y-%m-%d') if entry.date_rec else None,
                    'prog': entry.prog or '',
                    'description': entry.description or '',
                    'cat': entry.compte_code or '',
                    'cat_label': comptes_fournisseurs_map.get((entry.compte_code or '').strip(), ''),
                    'fournisseur': entry.fournisseur or '',
                    'out': float(entry.montant_out) if entry.montant_out else 0,
                    'fichier_source': entry.fichier_source or '',
                    'scan': entry.scan or '',
                    'conforme': False,
                    'erreurs': [f'Erreur analyse transaction: {entry_error}'],
                    'details': {},
                    'detail_col': entry.detail or '',
                    'is_carburant': entry.compte_code in ['606100', '606107'],
                    'vehicule_match': False,
                    'vehicule_match_label': '',
                })

        # Filtrer par conformité si nécessaire
        if conformite_filter == 'conforme':
            entries_analysees = [e for e in entries_analysees if e['conforme']]
        elif conformite_filter == 'non_conforme':
            entries_analysees = [e for e in entries_analysees if not e['conforme']]

        # Pagination manuelle
        total = len(entries_analysees)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        entries_page = entries_analysees[start_idx:end_idx]

        total_pages = (total + per_page - 1) // per_page

        # Calculer les statistiques
        conformes_filtres = sum(1 for e in entries_analysees if e['conforme'])
        non_conformes_filtres = sum(1 for e in entries_analysees if not e['conforme'])
        taux_conformite = int((conformes_filtres / total * 100)) if total > 0 else 0

        return JsonResponse({
            'entries': entries_page,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            'stats': {
                'total': total,
                'conformes': conformes_filtres,
                'non_conformes': non_conformes_filtres,
                'taux_conformite': taux_conformite
            }
        })

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Erreur dans api_verification_depenses_fournisseurs: {error_trace}")
        return JsonResponse({
            'error': str(e),
            'trace': error_trace
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_modifier_description_fournisseur(request):
    """API pour modifier la description DiameX d'une entrée fournisseur (PostgreSQL + Access)"""
    import json
    import pyodbc

    try:
        data = json.loads(request.body)
        entry_id = data.get('entry_id')
        nouvelle_description = data.get('nouvelle_description', '').strip()
        # Fournisseur (IDxls) : facultatif, vide = inchangé
        nouveau_fournisseur = (data.get('nouveau_fournisseur') or '').strip()

        if not entry_id or not nouvelle_description:
            return JsonResponse({
                'success': False,
                'message': 'Données manquantes'
            }, status=400)

        # Récupérer l'entrée
        entry = _get_scoped_diamex_queryset(request.user).get(id=entry_id)

        access_updates = {'Description': nouvelle_description}
        champs_pg = ['description']
        entry.description = nouvelle_description
        if nouveau_fournisseur and nouveau_fournisseur != (entry.fournisseur or ''):
            entry.fournisseur = nouveau_fournisseur
            champs_pg.append('fournisseur')
            access_updates['Fournisseur'] = nouveau_fournisseur

        # 1. Mettre à jour PostgreSQL
        entry.save(update_fields=champs_pg)

        # 2. Mettre à jour Access si fichier source disponible
        access_updated = False
        access_error = None
        access_status = 'not_attempted'
        access_payload = _build_access_update_payload_for_entry(
            request.user,
            entry,
            access_updates
        )

        if entry.fichier_source:
            try:
                # Construire le chemin complet vers le fichier Access
                from django.conf import settings
                access_path = os.path.join(settings.DIAMEX_BASE_PATH or '', entry.fichier_source)

                if os.path.exists(access_path):
                    conn_str = f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={access_path}"
                    conn = pyodbc.connect(conn_str)
                    cursor = conn.cursor()

                    # Mettre à jour la description dans la table DATA
                    set_clause = ', '.join(f"{col} = ?" for col in access_updates)
                    cursor.execute(
                        f"UPDATE DATA SET {set_clause} WHERE ID = ?",
                        (*access_updates.values(), entry.id_access)
                    )

                    conn.commit()
                    cursor.close()
                    conn.close()

                    access_updated = True
                    access_status = 'updated'
                else:
                    access_status = 'missing_file'
                    access_error = f"Fichier Access introuvable: {access_path}"

            except Exception as e:
                if _is_access_driver_unavailable(e):
                    access_status = 'driver_unavailable'
                    access_error = 'Synchronisation Access non disponible sur ce serveur'
                else:
                    access_status = 'error'
                    access_error = f"Erreur Access: {str(e)}"

        # Vérifier la nouvelle conformité
        verification = verifier_format_charte_fournisseur(
            nouvelle_description,
            entry.fournisseur,
            entry.compte_code,  # Ajout du compte pour format Indemnité
            entry.detail or ''
        )

        message = 'Description mise à jour avec succès'
        if access_updated:
            message += ' (PostgreSQL + Access)'
        elif access_error:
            message += f' (PostgreSQL uniquement - {access_error})'
        else:
            access_status = 'missing_source'
            message += ' (PostgreSQL uniquement - pas de fichier source)'

        return JsonResponse({
            'success': True,
            'message': message,
            'access_updated': access_updated,
            'access_status': access_status,
            'access_error': access_error,
            'access_payload': None if access_updated else access_payload,
            'conforme': verification['conforme'],
            'erreurs': verification['erreurs'],
            'details': verification['details']
        })

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


@login_required
@require_http_methods(["POST"])
def api_modifier_fournisseur_lot(request):
    """Modifie la colonne Fournisseur (IDxls) de plusieurs entrées en une fois.

    PostgreSQL est mis à jour ici ; pour Access, on renvoie un payload par ligne
    (le navigateur les transmet à l'agent local, comme pour la modification unitaire).
    La description n'est pas touchée.
    """
    import json

    try:
        data = json.loads(request.body)
        entry_ids = data.get('entry_ids') or []
        nouveau_fournisseur = (data.get('nouveau_fournisseur') or '').strip()

        if not isinstance(entry_ids, list) or not entry_ids or not nouveau_fournisseur:
            return JsonResponse({'success': False, 'message': 'Données manquantes'}, status=400)
        if len(entry_ids) > 500:
            return JsonResponse({'success': False, 'message': 'Maximum 500 lignes par lot'}, status=400)

        try:
            entry_ids = [int(i) for i in entry_ids]
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'Identifiants invalides'}, status=400)

        entries = list(_get_scoped_diamex_queryset(request.user).filter(id__in=entry_ids))
        trouves = {e.id for e in entries}
        introuvables = [i for i in entry_ids if i not in trouves]

        modifiees = 0
        inchangees = 0
        payloads = []
        sans_source = 0
        for entry in entries:
            if (entry.fournisseur or '') == nouveau_fournisseur:
                inchangees += 1
                continue
            entry.fournisseur = nouveau_fournisseur
            entry.save(update_fields=['fournisseur'])
            modifiees += 1

            payload = _build_access_update_payload_for_entry(
                request.user, entry, {'Fournisseur': nouveau_fournisseur}
            )
            if payload:
                payloads.append(payload)
            else:
                sans_source += 1

        return JsonResponse({
            'success': True,
            'message': f'{modifiees} ligne(s) modifiée(s) dans PostgreSQL',
            'modifiees': modifiees,
            'inchangees': inchangees,
            'introuvables': introuvables,
            'sans_source_access': sans_source,
            'access_payloads': payloads,
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'}, status=500)


@login_required
@require_http_methods(["POST"])
@login_required
@require_http_methods(["POST"])
def api_ajouter_fournisseur(request):
    """API pour ajouter un nouveau fournisseur dans la base"""
    import json
    from apps.billing.models import Fournisseur

    try:
        data = json.loads(request.body)

        idxls = data.get('idxls', '').strip()
        nom_fournisseur = data.get('nom_fournisseur', '').strip()

        if not idxls or not nom_fournisseur:
            return JsonResponse({
                'success': False,
                'message': 'IDxls et nom du fournisseur sont obligatoires'
            }, status=400)

        # Vérifier si le fournisseur existe déjà
        if Fournisseur.objects.filter(idxls=idxls).exists():
            return JsonResponse({
                'success': False,
                'message': f'Un fournisseur avec l\'IDxls "{idxls}" existe déjà'
            }, status=400)

        # Déterminer si c'est NIF ou ISI
        nif_value = data.get('nif', '').strip()
        cin_value = data.get('cin', '').strip()
        date_cin_value = data.get('date_cin', '').strip()
        lieu_cin_value = data.get('lieu_cin', '').strip()

        nif_ou_isi = ''
        numero_nif = None

        if nif_value:
            nif_ou_isi = 'NIF'
            numero_nif = nif_value

        parsed_date_cin = None
        if date_cin_value:
            try:
                parsed_date_cin = datetime.strptime(date_cin_value, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'message': 'Date CIN invalide. Format attendu: YYYY-MM-DD'
                }, status=400)

        autre_info_parts = []
        remarque = data.get('remarque', '').strip()
        if remarque:
            autre_info_parts.append(remarque)
        autre_information = '\n'.join(autre_info_parts) if autre_info_parts else None

        # Créer le fournisseur avec les bons noms de champs
        fournisseur = Fournisseur.objects.create(
            idxls=idxls,
            nom_fournisseur=nom_fournisseur,
            nif_ou_isi=nif_ou_isi,
            numero_nif=numero_nif,
            cin=cin_value or None,
            date_cin=parsed_date_cin,
            lieu_cin=lieu_cin_value or None,
            adresse=data.get('adresse', '').strip() or None,
            telephone=data.get('telephone', '').strip() or None,
            email=data.get('email', '').strip() or None,
            autre_information=autre_information
        )

        return JsonResponse({
            'success': True,
            'message': f'Fournisseur "{nom_fournisseur}" ajouté avec succès',
            'fournisseur_id': str(fournisseur.id)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur lors de l\'ajout: {str(e)}'
        }, status=500)
