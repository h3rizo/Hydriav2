"""
Vues pour la gestion des paiements CNaPS et FMFP trimestriels
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from django.db.models import Sum, Q
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
import json
import os
from datetime import datetime, date
from calendar import monthrange
import openpyxl
from openpyxl.cell.cell import MergedCell

from .models import Employe, Salaire, GrilleSalaire, PaiementCNaPSFMFP, PaiementCNaPSFMFPDetail
from .salary_consistency import sync_salaire_with_grille
from apps.organization.models import Organisation


@login_required
def paiements_cnaps_fmfp_list(request):
    """Page de liste des paiements CNaPS/FMFP"""
    # Récupérer l'organisation de l'utilisateur
    organisation = None
    if hasattr(request.user, 'employe') and request.user.employe:
        if request.user.employe.base and request.user.employe.base.organisation:
            organisation = request.user.employe.base.organisation

    # Récupérer toutes les organisations si admin
    organisations = Organisation.objects.all()

    context = {
        'organisation_user': organisation,
        'organisations': organisations,
    }

    return render(request, 'employees/paiements_cnaps_fmfp_list.html', context)


@login_required
@require_http_methods(["GET"])
def api_paiements_cnaps_fmfp_list(request):
    """API pour lister les paiements CNaPS/FMFP"""
    try:
        # Récupérer l'organisation de l'utilisateur
        organisation_user = None
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                organisation_user = request.user.employe.base.organisation

        # Filtres
        organisation_id = request.GET.get('organisation_id')
        annee = request.GET.get('annee')
        trimestre = request.GET.get('trimestre')
        statut = request.GET.get('statut')

        # Query de base
        paiements_qs = PaiementCNaPSFMFP.objects.all()

        # Filtrer par organisation de l'utilisateur (sécurité)
        if organisation_user:
            paiements_qs = paiements_qs.filter(organisation=organisation_user)

        # Filtres additionnels
        if organisation_id and organisation_id != 'all':
            paiements_qs = paiements_qs.filter(organisation_id=organisation_id)

        if annee:
            paiements_qs = paiements_qs.filter(annee=int(annee))

        if trimestre:
            paiements_qs = paiements_qs.filter(trimestre=int(trimestre))

        if statut and statut != 'all':
            paiements_qs = paiements_qs.filter(statut=statut)

        # Ajouter les relations après les filtres
        paiements_qs = paiements_qs.select_related(
            'organisation',
            'created_by'
        ).prefetch_related('details').order_by('-annee', '-trimestre')

        # Construire la réponse
        paiements_data = []
        for paiement in paiements_qs:
            nb_employes = paiement.details.count()

            paiements_data.append({
                'id': str(paiement.id),
                'organisation': paiement.organisation.nom_organisation,
                'organisation_id': str(paiement.organisation.id),
                'trimestre': paiement.trimestre,
                'annee': paiement.annee,
                'periode': paiement.periode_label,
                'date_paiement': paiement.date_paiement.strftime('%Y-%m-%d'),
                'nb_employes': nb_employes,
                'montant_total_cnaps': float(paiement.montant_total_cnaps),
                'montant_total_fmfp': float(paiement.montant_total_fmfp),
                'statut': paiement.statut,
                'statut_display': paiement.get_statut_display(),
                'facture_generee': paiement.facture_generee,
                'date_generation': paiement.date_generation.strftime('%Y-%m-%d %H:%M') if paiement.date_generation else None,
                'facture_imprimee': paiement.facture_imprimee,
                'date_impression': paiement.date_impression.strftime('%Y-%m-%d %H:%M') if paiement.date_impression else None,
                'created_by': paiement.created_by.get_full_name() if paiement.created_by else None,
                'created_at': paiement.created_at.strftime('%Y-%m-%d %H:%M'),
            })

        return JsonResponse({
            'success': True,
            'paiements': paiements_data,
            'total': len(paiements_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_employes_cnaps_fmfp(request):
    """API pour récupérer la liste des employés avec leurs montants CNaPS/FMFP à payer pour un trimestre"""
    try:
        # Récupérer l'organisation de l'utilisateur
        organisation_user = None
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                organisation_user = request.user.employe.base.organisation

        if not organisation_user:
            return JsonResponse({
                'success': False,
                'error': 'Aucune organisation associée à votre compte'
            }, status=403)

        # Paramètres
        trimestre = int(request.GET.get('trimestre', 1))
        annee = int(request.GET.get('annee', datetime.now().year))

        # Récupérer les mois du trimestre
        mois_par_trimestre = {
            1: [1, 2, 3],    # Janvier, Février, Mars
            2: [4, 5, 6],    # Avril, Mai, Juin
            3: [7, 8, 9],    # Juillet, Août, Septembre
            4: [10, 11, 12]  # Octobre, Novembre, Décembre
        }
        mois_trimestre = mois_par_trimestre.get(trimestre, [])

        # Récupérer tous les salaires payés pour ce trimestre et cette organisation
        employes_data_map = {}  # Dictionnaire pour grouper par employé

        for mois in mois_trimestre:
            premier_jour = date(annee, mois, 1)
            dernier_jour = date(annee, mois, monthrange(annee, mois)[1])

            salaires = Salaire.objects.filter(
                grille_salaire__contrat__employe__base__organisation=organisation_user,
                date_paiement__gte=premier_jour,
                date_paiement__lte=dernier_jour
            ).select_related(
                'grille_salaire__contrat__employe',
                'grille_salaire__contrat__employe__poste'
            )

            for salaire in salaires:
                sync_salaire_with_grille(salaire)
                employe = salaire.grille_salaire.contrat.employe
                employe_id = str(employe.id)

                # Initialiser l'entrée si nouveau employé
                if employe_id not in employes_data_map:
                    employes_data_map[employe_id] = {
                        'employe_id': employe_id,
                        'employe_nom_complet': employe.nom_complet,
                        'employe_fonction': employe.poste.nom_poste if employe.poste else 'Non défini',
                        'numero_cnaps': employe.numero_cnaps if hasattr(employe, 'numero_cnaps') else '',
                        'mois_1_cnaps': Decimal('0'),
                        'mois_1_fmfp': Decimal('0'),
                        'mois_2_cnaps': Decimal('0'),
                        'mois_2_fmfp': Decimal('0'),
                        'mois_3_cnaps': Decimal('0'),
                        'mois_3_fmfp': Decimal('0'),
                    }

                # Déterminer l'index du mois dans le trimestre (0, 1, 2)
                mois_index = mois_trimestre.index(mois)

                # Récupérer les montants CNaPS et FMFP
                cnaps = salaire.cnaps_paye if salaire.cnaps_paye else Decimal('0')
                fmfp = salaire.fmfp_paye if salaire.fmfp_paye else Decimal('0')

                # Ajouter aux bons champs (mois_1, mois_2, mois_3)
                if mois_index == 0:
                    employes_data_map[employe_id]['mois_1_cnaps'] = cnaps
                    employes_data_map[employe_id]['mois_1_fmfp'] = fmfp
                elif mois_index == 1:
                    employes_data_map[employe_id]['mois_2_cnaps'] = cnaps
                    employes_data_map[employe_id]['mois_2_fmfp'] = fmfp
                elif mois_index == 2:
                    employes_data_map[employe_id]['mois_3_cnaps'] = cnaps
                    employes_data_map[employe_id]['mois_3_fmfp'] = fmfp

        # Convertir en liste et calculer les totaux
        employes_data = []
        for emp_data in employes_data_map.values():
            total_cnaps = (
                emp_data['mois_1_cnaps'] +
                emp_data['mois_2_cnaps'] +
                emp_data['mois_3_cnaps']
            )
            total_fmfp = (
                emp_data['mois_1_fmfp'] +
                emp_data['mois_2_fmfp'] +
                emp_data['mois_3_fmfp']
            )

            emp_data['total_cnaps'] = float(total_cnaps)
            emp_data['total_fmfp'] = float(total_fmfp)

            # Convertir les montants en float pour JSON
            emp_data['mois_1_cnaps'] = float(emp_data['mois_1_cnaps'])
            emp_data['mois_1_fmfp'] = float(emp_data['mois_1_fmfp'])
            emp_data['mois_2_cnaps'] = float(emp_data['mois_2_cnaps'])
            emp_data['mois_2_fmfp'] = float(emp_data['mois_2_fmfp'])
            emp_data['mois_3_cnaps'] = float(emp_data['mois_3_cnaps'])
            emp_data['mois_3_fmfp'] = float(emp_data['mois_3_fmfp'])

            employes_data.append(emp_data)

        # Trier par fonction puis nom
        employes_data.sort(key=lambda x: (x['employe_fonction'], x['employe_nom_complet']))

        return JsonResponse({
            'success': True,
            'employes': employes_data,
            'total': len(employes_data),
            'trimestre': trimestre,
            'annee': annee
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_creer_paiement_cnaps_fmfp(request):
    """API pour créer un paiement CNaPS/FMFP"""
    try:
        data = json.loads(request.body)

        # Récupérer l'organisation de l'utilisateur
        organisation_user = None
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                organisation_user = request.user.employe.base.organisation

        if not organisation_user:
            return JsonResponse({
                'success': False,
                'error': 'Aucune organisation associée à votre compte'
            }, status=403)

        trimestre = int(data.get('trimestre'))
        annee = int(data.get('annee'))
        date_paiement_str = data.get('date_paiement')
        employes_data = data.get('employes', [])

        # Vérifier si un paiement existe déjà
        paiement_existant = PaiementCNaPSFMFP.objects.filter(
            organisation=organisation_user,
            trimestre=trimestre,
            annee=annee
        ).first()

        if paiement_existant:
            trimestre_labels = {1: '1er', 2: '2e', 3: '3e', 4: '4e'}
            return JsonResponse({
                'success': False,
                'error': f'Un paiement CNaPS/FMFP existe déjà pour le {trimestre_labels[trimestre]} trimestre {annee}'
            }, status=400)

        # Parser la date de paiement
        date_paiement = datetime.strptime(date_paiement_str, '%Y-%m-%d').date()

        # Créer le paiement CNaPS/FMFP
        paiement = PaiementCNaPSFMFP.objects.create(
            organisation=organisation_user,
            trimestre=trimestre,
            annee=annee,
            date_paiement=date_paiement,
            created_by=request.user,
            statut='brouillon'
        )

        # Créer les détails
        montant_total_cnaps = Decimal('0')
        montant_total_fmfp = Decimal('0')

        for emp_data in employes_data:
            detail = PaiementCNaPSFMFPDetail.objects.create(
                paiement=paiement,
                employe_id=emp_data['employe_id'],
                employe_nom_complet=emp_data['employe_nom_complet'],
                employe_fonction=emp_data['employe_fonction'],
                numero_cnaps=emp_data.get('numero_cnaps', ''),
                mois_1_cnaps=Decimal(str(emp_data['mois_1_cnaps'])),
                mois_1_fmfp=Decimal(str(emp_data['mois_1_fmfp'])),
                mois_2_cnaps=Decimal(str(emp_data['mois_2_cnaps'])),
                mois_2_fmfp=Decimal(str(emp_data['mois_2_fmfp'])),
                mois_3_cnaps=Decimal(str(emp_data['mois_3_cnaps'])),
                mois_3_fmfp=Decimal(str(emp_data['mois_3_fmfp'])),
                total_cnaps=Decimal(str(emp_data['total_cnaps'])),
                total_fmfp=Decimal(str(emp_data['total_fmfp']))
            )

            montant_total_cnaps += detail.total_cnaps
            montant_total_fmfp += detail.total_fmfp

        # Mettre à jour les totaux
        paiement.montant_total_cnaps = montant_total_cnaps
        paiement.montant_total_fmfp = montant_total_fmfp
        paiement.save()

        return JsonResponse({
            'success': True,
            'message': 'Paiement CNaPS/FMFP créé avec succès',
            'paiement_id': str(paiement.id)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_valider_paiement_cnaps_fmfp(request, paiement_id):
    """API pour valider un paiement CNaPS/FMFP"""
    try:
        paiement = PaiementCNaPSFMFP.objects.get(id=paiement_id)

        # Vérifier que l'utilisateur a le droit de valider
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                if paiement.organisation != request.user.employe.base.organisation:
                    return JsonResponse({
                        'success': False,
                        'error': 'Vous n\'avez pas le droit de valider ce paiement'
                    }, status=403)

        paiement.statut = 'valide'
        paiement.save()

        return JsonResponse({
            'success': True,
            'message': 'Paiement CNaPS/FMFP validé avec succès'
        })

    except PaiementCNaPSFMFP.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement CNaPS/FMFP introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["DELETE"])
def api_supprimer_paiement_cnaps_fmfp(request, paiement_id):
    """API pour supprimer un paiement CNaPS/FMFP (si statut = brouillon)"""
    try:
        paiement = PaiementCNaPSFMFP.objects.get(id=paiement_id)

        # Vérifier que l'utilisateur a le droit de supprimer
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                if paiement.organisation != request.user.employe.base.organisation:
                    return JsonResponse({
                        'success': False,
                        'error': 'Vous n\'avez pas le droit de supprimer ce paiement'
                    }, status=403)

        if paiement.statut != 'brouillon':
            return JsonResponse({
                'success': False,
                'error': 'Seuls les paiements en brouillon peuvent être supprimés'
            }, status=400)

        paiement.delete()

        return JsonResponse({
            'success': True,
            'message': 'Paiement CNaPS/FMFP supprimé avec succès'
        })

    except PaiementCNaPSFMFP.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement CNaPS/FMFP introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_detail_paiement_cnaps_fmfp(request, paiement_id):
    """API pour récupérer les détails d'un paiement CNaPS/FMFP"""
    try:
        paiement = PaiementCNaPSFMFP.objects.select_related(
            'organisation',
            'created_by'
        ).get(id=paiement_id)

        # Vérifier les droits
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                if paiement.organisation != request.user.employe.base.organisation:
                    return JsonResponse({
                        'success': False,
                        'error': 'Vous n\'avez pas accès à ce paiement'
                    }, status=403)

        details = paiement.details.all()

        details_data = []
        for detail in details:
            details_data.append({
                'id': str(detail.id),
                'employe_nom_complet': detail.employe_nom_complet,
                'employe_fonction': detail.employe_fonction,
                'numero_cnaps': detail.numero_cnaps,
                'mois_1_cnaps': float(detail.mois_1_cnaps),
                'mois_1_fmfp': float(detail.mois_1_fmfp),
                'mois_2_cnaps': float(detail.mois_2_cnaps),
                'mois_2_fmfp': float(detail.mois_2_fmfp),
                'mois_3_cnaps': float(detail.mois_3_cnaps),
                'mois_3_fmfp': float(detail.mois_3_fmfp),
                'total_cnaps': float(detail.total_cnaps),
                'total_fmfp': float(detail.total_fmfp),
            })

        return JsonResponse({
            'success': True,
            'paiement': {
                'id': str(paiement.id),
                'organisation': paiement.organisation.nom_organisation,
                'trimestre': paiement.trimestre,
                'annee': paiement.annee,
                'periode_label': paiement.periode_label,
                'date_paiement': paiement.date_paiement.strftime('%Y-%m-%d'),
                'montant_total_cnaps': float(paiement.montant_total_cnaps),
                'montant_total_fmfp': float(paiement.montant_total_fmfp),
                'statut': paiement.statut,
                'facture_generee': paiement.facture_generee,
                'details': details_data
            }
        })

    except PaiementCNaPSFMFP.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement CNaPS/FMFP introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def generer_facture_cnaps_fmfp(request, paiement_id):
    """Génère la facture Excel CNaPS/FMFP selon le modèle"""
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import Font, Alignment, Border, Side
        from django.conf import settings

        # DEBUG
        print(f"[DEBUG generer_facture] paiement_id recu: {paiement_id} (type: {type(paiement_id)})")
        
        paiement = PaiementCNaPSFMFP.objects.select_related('organisation').get(id=paiement_id)
        print(f"[DEBUG generer_facture] Paiement trouve: {paiement}")

        # Vérifier les droits
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                if paiement.organisation != request.user.employe.base.organisation:
                    return JsonResponse({
                        'success': False,
                        'error': 'Vous n\'avez pas accès à ce paiement'
                    }, status=403)

        # Charger le modèle
        modele_path = os.path.join(settings.BASE_DIR, 'Modèle Facture CNaPS FMFP.xlsx')
        wb = load_workbook(modele_path)

        # Récupérer le salaire minimum depuis ConfigSalaire
        from apps.employees.models import ConfigSalaire, Contrat, Salaire
        try:
            config_salaire = ConfigSalaire.objects.first()
            SALAIRE_MINIMUM = float(config_salaire.salaire_minimum) if config_salaire else 262680
        except:
            SALAIRE_MINIMUM = 262680  # Valeur par défaut si table vide

        # Récupérer les détails triés avec relations vers Employe et Contrat
        details = paiement.details.select_related(
            'employe',
            'employe__poste'
        ).prefetch_related('employe__contrats').order_by('employe_fonction', 'employe_nom_complet')

        # Préparer un dictionnaire pour récupérer les salaires bruts par employé et par mois
        # Format: {employe_id: {mois: salaire_brut}}
        salaires_bruts_map = {}

        # Récupérer les mois du trimestre
        mois_trimestre = paiement.mois_trimestre  # [1,2,3] ou [4,5,6] etc.

        # Récupérer les salaires pour tous les employés et tous les mois du trimestre
        for detail in details:
            employe_id = str(detail.employe.id)
            salaires_bruts_map[employe_id] = {}

            for idx, mois in enumerate(mois_trimestre, 1):
                # Chercher le salaire pour cet employé et ce mois
                # La période est définie par la date de paiement réelle
                salaire = Salaire.objects.filter(
                    grille_salaire__contrat__employe=detail.employe,
                    date_paiement__year=paiement.annee,
                    date_paiement__month=mois
                ).select_related('grille_salaire').first()

                if salaire and salaire.grille_salaire:
                    # Utiliser salaire_brut_total depuis la grille de salaire
                    salaires_bruts_map[employe_id][idx] = float(salaire.grille_salaire.salaire_brut_total)
                else:
                    # Si pas de salaire trouvé, utiliser 0
                    salaires_bruts_map[employe_id][idx] = 0

        # Noms des mois en français
        mois_noms = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                     'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']

        # Déterminer les mois du trimestre
        mois_trimestre = paiement.mois_trimestre  # [1,2,3] ou [4,5,6] etc.
        mois_1_nom = mois_noms[mois_trimestre[0]]
        mois_2_nom = mois_noms[mois_trimestre[1]]
        mois_3_nom = mois_noms[mois_trimestre[2]]

        # Période (date du premier jour du trimestre)
        premier_mois = mois_trimestre[0]
        date_periode = date(paiement.annee, premier_mois, 1)

        # Définir le style de bordure pour les tableaux
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # ========================================
        # ONGLET 1 : Annexe DNS (REMPLIR EN PREMIER - SOURCE DE DONNÉES)
        # ========================================
        ws_annexe = wb['Annexe DNS']

        # Fusionner les cellules d'en-tête pour les mois
        # Mois 1 (colonnes I, J, K, L)
        ws_annexe.merge_cells('I1:L1')
        cell_i1 = ws_annexe['I1']
        cell_i1.border = thin_border
        cell_i1.alignment = Alignment(horizontal='center', vertical='center')

        # Mois 2 (colonnes M, N, O, P)
        ws_annexe.merge_cells('M1:P1')
        cell_m1 = ws_annexe['M1']
        cell_m1.border = thin_border
        cell_m1.alignment = Alignment(horizontal='center', vertical='center')

        # Mois 3 (colonnes Q, R, S, T)
        ws_annexe.merge_cells('Q1:T1')
        cell_q1 = ws_annexe['Q1']
        cell_q1.border = thin_border
        cell_q1.alignment = Alignment(horizontal='center', vertical='center')

        # En-têtes pour les colonnes Charges CNAPS (X, Y, Z)
        # Colonne X : Charges CNAPS Mois 1
        cell_x1 = ws_annexe['X1']
        cell_x1.value = f"Charges CNAPS {mois_1_nom}"
        cell_x1.font = Font(name='Arial Narrow', size=11, bold=True)
        cell_x1.alignment = Alignment(horizontal='center', vertical='center')
        cell_x1.border = thin_border

        # Colonne Y : Charges CNAPS Mois 2
        cell_y1 = ws_annexe['Y1']
        cell_y1.value = f"Charges CNAPS {mois_2_nom}"
        cell_y1.font = Font(name='Arial Narrow', size=11, bold=True)
        cell_y1.alignment = Alignment(horizontal='center', vertical='center')
        cell_y1.border = thin_border

        # Colonne Z : Charges CNAPS Mois 3
        cell_z1 = ws_annexe['Z1']
        cell_z1.value = f"Charges CNAPS {mois_3_nom}"
        cell_z1.font = Font(name='Arial Narrow', size=11, bold=True)
        cell_z1.alignment = Alignment(horizontal='center', vertical='center')
        cell_z1.border = thin_border

        # En-têtes pour les colonnes Salaires Plafonnés (AA, AB, AC)
        # Colonne AA : Salaire plafonné Mois 1
        cell_aa1 = ws_annexe['AA1']
        cell_aa1.value = f"Salaire plafonné {mois_1_nom}"
        cell_aa1.font = Font(name='Arial Narrow', size=11, bold=True)
        cell_aa1.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell_aa1.border = thin_border

        # Colonne AB : Salaire plafonné Mois 2
        cell_ab1 = ws_annexe['AB1']
        cell_ab1.value = f"Salaire plafonné {mois_2_nom}"
        cell_ab1.font = Font(name='Arial Narrow', size=11, bold=True)
        cell_ab1.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell_ab1.border = thin_border

        # Colonne AC : Salaire plafonné Mois 3
        cell_ac1 = ws_annexe['AC1']
        cell_ac1.value = f"Salaire plafonné {mois_3_nom}"
        cell_ac1.font = Font(name='Arial Narrow', size=11, bold=True)
        cell_ac1.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell_ac1.border = thin_border

        # Fonction helper : Calculer la valeur des colonnes K, O, S selon le type de contrat
        def calculer_valeur_colonne_kos(employe, salaire_brut, nombre_jours_travailles=None):
            """
            Calcule la valeur pour les colonnes K, O, S selon les règles :
            - Si salaire = 0 : retourner 0
            - Temps plein : 243
            - Mi-temps : 121.5
            - Journalier : nombre_jours × 8
            - Fonction "Femme de ménage" : 40
            """
            # Si salaire est 0, retourner 0
            if float(salaire_brut) == 0:
                return 0

            # Récupérer le contrat actif
            contrat_actif = None
            for contrat in employe.contrats.all():
                if contrat.fin_contrat is None or contrat.fin_contrat >= date.today():
                    contrat_actif = contrat
                    break

            # Si pas de contrat, utiliser la fonction pour détecter "Femme de ménage"
            fonction = employe.poste.nom_poste if employe.poste else ''

            # Cas spécial : Femme de ménage
            if 'femme de ménage' in fonction.lower() or 'femme de menage' in fonction.lower():
                return 40

            # Si contrat trouvé, utiliser le type
            if contrat_actif and contrat_actif.type_contrat:
                type_contrat = contrat_actif.type_contrat

                if type_contrat == 'temps_plein':
                    return 243
                elif type_contrat in ['temps_partiel', 'Mi-temps']:  # Mi-temps peut être écrit différemment
                    return 121.5
                elif type_contrat == 'journalier':
                    # Pour journalier, utiliser nombre de jours travaillés
                    if nombre_jours_travailles is not None and nombre_jours_travailles > 0:
                        return nombre_jours_travailles * 8
                    else:
                        return 0  # Si pas de jours, retourner 0

            # Par défaut (si type inconnu), retourner 0
            return 0

        # IMPORTANT: Effacer le contenu des lignes existantes (au lieu de delete_rows)
        # delete_rows() peut casser des structures Excel complexes
        from openpyxl.cell.cell import MergedCell
        max_row_to_clear = min(ws_annexe.max_row, 500)  # Limiter à 500 lignes
        for row in range(3, max_row_to_clear + 1):
            for col in range(1, 30):  # Colonnes A-AC (1 à 29)
                cell = ws_annexe.cell(row=row, column=col)
                # Ignorer les cellules fusionnées (MergedCell est en lecture seule)
                if not isinstance(cell, MergedCell):
                    cell.value = None
                    cell.border = None

        # Remplir les employés (à partir de la ligne 3)
        current_row_annexe = 3
        for detail in details:
            try:
                employe = detail.employe

                # Colonne A : Numéro employé
                cell_a = ws_annexe.cell(row=current_row_annexe, column=1, value=employe.numero_employe if hasattr(employe, 'numero_employe') else '')

                # Colonne B : Matricule CNaPS (depuis employe.numero_cnaps)
                cell_b = ws_annexe.cell(row=current_row_annexe, column=2, value=employe.numero_cnaps if hasattr(employe, 'numero_cnaps') else '')

                # Colonne C : Numéro CIN (depuis employe.numero_cin)
                cell_c = ws_annexe.cell(row=current_row_annexe, column=3, value=employe.numero_cin if hasattr(employe, 'numero_cin') else '')

                # Colonne D : Nom (depuis employe.nom)
                cell_d = ws_annexe.cell(row=current_row_annexe, column=4, value=employe.nom if hasattr(employe, 'nom') else '')

                # Colonne E : Prénom (depuis employe.prenom) - FACULTATIF
                prenom_value = ''
                if hasattr(employe, 'prenom') and employe.prenom:
                    prenom_value = employe.prenom
                cell_e = ws_annexe.cell(row=current_row_annexe, column=5, value=prenom_value)

                # Colonne F : Réf. Employeur (Code du poste)
                cell_f = ws_annexe.cell(row=current_row_annexe, column=6, value=employe.poste.code_poste if employe.poste and hasattr(employe.poste, 'code_poste') else '')

                # Colonne G : Date embauche (format DD/MM/YYYY)
                cell_g = ws_annexe.cell(row=current_row_annexe, column=7)
                if hasattr(employe, 'date_embauche') and employe.date_embauche:
                    cell_g.value = employe.date_embauche
                    cell_g.number_format = 'DD/MM/YYYY'
                else:
                    cell_g.value = ''

                # Colonne H : Date débauchage (format DD/MM/YYYY)
                cell_h = ws_annexe.cell(row=current_row_annexe, column=8)
                if hasattr(employe, 'date_debauchage') and employe.date_debauchage:
                    cell_h.value = employe.date_debauchage
                    cell_h.number_format = 'DD/MM/YYYY'
                else:
                    cell_h.value = '/'

                # Récupérer les salaires bruts pour cet employé
                employe_id = str(employe.id)
                salaire_brut_m1 = salaires_bruts_map.get(employe_id, {}).get(1, 0)
                salaire_brut_m2 = salaires_bruts_map.get(employe_id, {}).get(2, 0)
                salaire_brut_m3 = salaires_bruts_map.get(employe_id, {}).get(3, 0)

                # MOIS 1
                # Colonne I : Salaire brut total Mois 1 (depuis Salaire)
                cell_i = ws_annexe.cell(row=current_row_annexe, column=9, value=float(salaire_brut_m1))
                cell_i.number_format = '#,##0.00'

                # Colonne J : 0 (toujours 0)
                cell_j = ws_annexe.cell(row=current_row_annexe, column=10, value=0)
                cell_j.number_format = '#,##0.00'

                # Colonne K : Calculée selon type de contrat
                valeur_k_mois1 = calculer_valeur_colonne_kos(employe, salaire_brut_m1)
                cell_k = ws_annexe.cell(row=current_row_annexe, column=11, value=float(valeur_k_mois1))
                cell_k.number_format = '#,##0.00'

                # Colonne L : Salaire minimum x 8
                cell_l = ws_annexe.cell(row=current_row_annexe, column=12, value=float(SALAIRE_MINIMUM * 8))
                cell_l.number_format = '#,##0.00'

                # MOIS 2
                # Colonne M : Salaire brut total Mois 2 (depuis Salaire)
                cell_m = ws_annexe.cell(row=current_row_annexe, column=13, value=float(salaire_brut_m2))
                cell_m.number_format = '#,##0.00'

                # Colonne N : 0 (toujours 0)
                cell_n = ws_annexe.cell(row=current_row_annexe, column=14, value=0)
                cell_n.number_format = '#,##0.00'

                # Colonne O : Calculée selon type de contrat
                valeur_o_mois2 = calculer_valeur_colonne_kos(employe, salaire_brut_m2)
                cell_o = ws_annexe.cell(row=current_row_annexe, column=15, value=float(valeur_o_mois2))
                cell_o.number_format = '#,##0.00'

                # Colonne P : Salaire minimum x 8
                cell_p = ws_annexe.cell(row=current_row_annexe, column=16, value=float(SALAIRE_MINIMUM * 8))
                cell_p.number_format = '#,##0.00'

                # MOIS 3
                # Colonne Q : Salaire brut total Mois 3 (depuis Salaire)
                cell_q = ws_annexe.cell(row=current_row_annexe, column=17, value=float(salaire_brut_m3))
                cell_q.number_format = '#,##0.00'

                # Colonne R : 0 (toujours 0)
                cell_r = ws_annexe.cell(row=current_row_annexe, column=18, value=0)
                cell_r.number_format = '#,##0.00'

                # Colonne S : Calculée selon type de contrat
                valeur_s_mois3 = calculer_valeur_colonne_kos(employe, salaire_brut_m3)
                cell_s = ws_annexe.cell(row=current_row_annexe, column=19, value=float(valeur_s_mois3))
                cell_s.number_format = '#,##0.00'

                # Colonne T : Salaire minimum x 8
                cell_t = ws_annexe.cell(row=current_row_annexe, column=20, value=float(SALAIRE_MINIMUM * 8))
                cell_t.number_format = '#,##0.00'

                # Colonne U : "N"
                cell_u = ws_annexe.cell(row=current_row_annexe, column=21, value='N')

                # Colonne V : Téléphone
                cell_v = ws_annexe.cell(row=current_row_annexe, column=22, value=employe.telephone if hasattr(employe, 'telephone') else '')

                # Colonne W : Email
                cell_w = ws_annexe.cell(row=current_row_annexe, column=23, value=employe.email if hasattr(employe, 'email') else '')

                # Colonnes X, Y, Z : Charges CNAPS par mois (depuis PaiementCNaPSFMFPDetail)
                # Colonne X : Charges CNAPS Mois 1
                cell_x = ws_annexe.cell(row=current_row_annexe, column=24, value=float(detail.mois_1_cnaps))
                cell_x.number_format = '#,##0.00'

                # Colonne Y : Charges CNAPS Mois 2
                cell_y = ws_annexe.cell(row=current_row_annexe, column=25, value=float(detail.mois_2_cnaps))
                cell_y.number_format = '#,##0.00'

                # Colonne Z : Charges CNAPS Mois 3
                cell_z = ws_annexe.cell(row=current_row_annexe, column=26, value=float(detail.mois_3_cnaps))
                cell_z.number_format = '#,##0.00'

                # Colonnes AA, AB, AC : Salaires plafonnés par mois (MIN entre salaire brut et plafond)
                # Colonne AA : Salaire plafonné Mois 1 = MIN(I, L)
                salaire_plafonne_m1 = min(salaire_brut_m1, SALAIRE_MINIMUM * 8)
                cell_aa = ws_annexe.cell(row=current_row_annexe, column=27, value=float(salaire_plafonne_m1))
                cell_aa.number_format = '#,##0.00'

                # Colonne AB : Salaire plafonné Mois 2 = MIN(M, P)
                salaire_plafonne_m2 = min(salaire_brut_m2, SALAIRE_MINIMUM * 8)
                cell_ab = ws_annexe.cell(row=current_row_annexe, column=28, value=float(salaire_plafonne_m2))
                cell_ab.number_format = '#,##0.00'

                # Colonne AC : Salaire plafonné Mois 3 = MIN(Q, T)
                salaire_plafonne_m3 = min(salaire_brut_m3, SALAIRE_MINIMUM * 8)
                cell_ac = ws_annexe.cell(row=current_row_annexe, column=29, value=float(salaire_plafonne_m3))
                cell_ac.number_format = '#,##0.00'

                # Appliquer la police Arial Narrow taille 9 ET bordures à TOUTES les cellules
                arial_narrow_9 = Font(name='Arial Narrow', size=9)
                for col in range(1, 30):  # Colonnes A-AC (1 à 29)
                    cell = ws_annexe.cell(row=current_row_annexe, column=col)
                    cell.font = arial_narrow_9
                    cell.border = thin_border  # Ajouter bordures intérieures

                current_row_annexe += 1
            except Exception as e:
                # Continuer même en cas d'erreur sur un employé
                print(f"[ERROR] Erreur pour employé {detail.employe_nom_complet}: {e}")
                current_row_annexe += 1

        # Sauvegarder le nombre de lignes dans Annexe DNS
        annexe_first_row = 3
        annexe_last_row = current_row_annexe - 1

        # ========================================
        # ONGLET 2 : DIAME CNAPS (UTILISE ANNEXE DNS COMME SOURCE)
        # ========================================
        ws_diame = wb['DIAME CNAPS']

        # Helper function: Écrire une valeur en évitant les cellules fusionnées
        def safe_write(ws, row, col, value):
            """Écrit une valeur dans une cellule si elle n'est pas fusionnée"""
            cell = ws.cell(row=row, column=col)
            if not isinstance(cell, MergedCell):
                cell.value = value
                return cell
            return None

        # En-têtes (lignes 1-2)
        safe_write(ws_diame, 1, 3, mois_1_nom)  # C1
        safe_write(ws_diame, 1, 5, mois_2_nom)  # E1
        safe_write(ws_diame, 1, 7, mois_3_nom)  # G1

        # IMPORTANT: Effacer le contenu des lignes existantes (au lieu de delete_rows)
        max_row_to_clear = min(ws_diame.max_row, 500)
        for row in range(3, max_row_to_clear + 1):
            for col in range(1, 11):  # Colonnes A-J
                cell = ws_diame.cell(row=row, column=col)
                # Ignorer les cellules fusionnées
                if not isinstance(cell, MergedCell):
                    cell.value = None
                    cell.border = None

        # Remplir les employés avec formules référençant Annexe DNS (à partir de la ligne 3)
        current_row_diame = 3
        for row_idx in range(annexe_first_row, annexe_last_row + 1):
            # Nom (référence Annexe DNS colonne D)
            cell = ws_diame.cell(row=current_row_diame, column=1)
            if not isinstance(cell, MergedCell):
                cell.value = f"='Annexe DNS'!D{row_idx}"

            # Prénoms (référence Annexe DNS colonne E)
            cell = ws_diame.cell(row=current_row_diame, column=2)
            if not isinstance(cell, MergedCell):
                cell.value = f"='Annexe DNS'!E{row_idx}"

            # Mois 1 CNaPS et FMFP
            # Colonne C: Charge CNaPS M1 = Annexe DNS colonne X
            cell = ws_diame.cell(row=current_row_diame, column=3)
            if not isinstance(cell, MergedCell):
                cell.value = f"='Annexe DNS'!X{row_idx}"

            # Colonne D: Charge FMFP M1 = Annexe DNS colonne X/14
            cell = ws_diame.cell(row=current_row_diame, column=4)
            if not isinstance(cell, MergedCell):
                cell.value = f"='Annexe DNS'!X{row_idx}/14"

            # Mois 2 CNaPS et FMFP
            # Colonne E: Charge CNaPS M2 = Annexe DNS colonne Y
            cell = ws_diame.cell(row=current_row_diame, column=5)
            if not isinstance(cell, MergedCell):
                cell.value = f"='Annexe DNS'!Y{row_idx}"

            # Colonne F: Charge FMFP M2 = Annexe DNS colonne Y
            cell = ws_diame.cell(row=current_row_diame, column=6)
            if not isinstance(cell, MergedCell):
                cell.value = f"='Annexe DNS'!Y{row_idx}/14"

            # Mois 3 CNaPS et FMFP
            # Colonne G: Charge CNaPS M3 = Annexe DNS colonne Z
            cell = ws_diame.cell(row=current_row_diame, column=7)
            if not isinstance(cell, MergedCell):
                cell.value = f"='Annexe DNS'!Z{row_idx}"

            # Colonne H: Charge FMFP M3 = Annexe DNS colonne Z
            cell = ws_diame.cell(row=current_row_diame, column=8)
            if not isinstance(cell, MergedCell):
                cell.value = f"='Annexe DNS'!Z{row_idx}/14"

            # Totaux - Formules
            # Colonne I (Total CNaPS) = C + E + G
            cell = ws_diame.cell(row=current_row_diame, column=9)
            if not isinstance(cell, MergedCell):
                cell.value = f'=C{current_row_diame}+E{current_row_diame}+G{current_row_diame}'

            # Colonne J (Total FMFP) = D + F + H
            cell = ws_diame.cell(row=current_row_diame, column=10)
            if not isinstance(cell, MergedCell):
                cell.value = f'=D{current_row_diame}+F{current_row_diame}+H{current_row_diame}'

            # Appliquer format nombre avec séparateurs de milliers ET bordures
            for col in range(1, 11):  # Colonnes A à J (1 à 10)
                cell = ws_diame.cell(row=current_row_diame, column=col)
                if col >= 3:  # Colonnes avec nombres (C à J)
                    cell.number_format = '#,##0.00'
                cell.border = thin_border  # Ajouter bordures

            current_row_diame += 1

        # Ajouter ligne TOTAL GÉNÉRAL
        total_row_diame = current_row_diame
        cell_total = safe_write(ws_diame, total_row_diame, 1, 'TOTAL GÉNÉRAL')
        if cell_total:
            cell_total.font = Font(bold=True, size=12)
        safe_write(ws_diame, total_row_diame, 2, '')

        # Formules pour totaux (somme de toutes les lignes employés)
        diame_first_row = 3
        diame_last_row = current_row_diame - 1

        # Totaux par mois
        safe_write(ws_diame, total_row_diame, 3, f'=SUM(C{diame_first_row}:C{diame_last_row})')  # M1 CNaPS
        safe_write(ws_diame, total_row_diame, 4, f'=SUM(D{diame_first_row}:D{diame_last_row})')  # M1 FMFP
        safe_write(ws_diame, total_row_diame, 5, f'=SUM(E{diame_first_row}:E{diame_last_row})')  # M2 CNaPS
        safe_write(ws_diame, total_row_diame, 6, f'=SUM(F{diame_first_row}:F{diame_last_row})')  # M2 FMFP
        safe_write(ws_diame, total_row_diame, 7, f'=SUM(G{diame_first_row}:G{diame_last_row})')  # M3 CNaPS
        safe_write(ws_diame, total_row_diame, 8, f'=SUM(H{diame_first_row}:H{diame_last_row})')  # M3 FMFP
        safe_write(ws_diame, total_row_diame, 9, f'=SUM(I{diame_first_row}:I{diame_last_row})')  # Total CNaPS
        safe_write(ws_diame, total_row_diame, 10, f'=SUM(J{diame_first_row}:J{diame_last_row})') # Total FMFP

        # Appliquer format, style et bordures à la ligne total
        for col in range(1, 11):  # Colonnes A à J
            cell = ws_diame.cell(row=total_row_diame, column=col)
            if col >= 3:  # Colonnes avec nombres
                cell.font = Font(bold=True, size=11)
                cell.number_format = '#,##0.00'
            else:  # Colonnes nom/prénoms
                cell.font = Font(bold=True, size=11)
            cell.border = thin_border  # Ajouter bordures

        # ========================================
        # ONGLET 3 : EMPLOYEUR (UTILISE ANNEXE DNS COMME SOURCE)
        # ========================================
        ws_employeur = wb['EMPLOYEUR']

        # Informations organisation
        safe_write(ws_employeur, 4, 3, paiement.organisation.numero_cnaps if hasattr(paiement.organisation, 'numero_cnaps') else '')  # C4
        safe_write(ws_employeur, 5, 3, paiement.organisation.nom_organisation)  # C5
        safe_write(ws_employeur, 6, 3, paiement.organisation.nif if hasattr(paiement.organisation, 'nif') else '')  # C6
        safe_write(ws_employeur, 8, 3, paiement.organisation.stat if hasattr(paiement.organisation, 'stat') else '')  # C8
        safe_write(ws_employeur, 9, 3, paiement.organisation.adresse if hasattr(paiement.organisation, 'adresse') else '')  # C9
        safe_write(ws_employeur, 10, 3, paiement.organisation.telephone if hasattr(paiement.organisation, 'telephone') else '')  # C10
        safe_write(ws_employeur, 11, 3, paiement.organisation.email if hasattr(paiement.organisation, 'email') else '')  # C11

        # Période (date du premier jour du trimestre)
        safe_write(ws_employeur, 14, 3, date_periode)  # C14

        # Ligne 31: Période de déclaration (format MM-YYYY)
        cell_c31 = safe_write(ws_employeur, 31, 3, "=C14")  # C31
        if cell_c31:
            cell_c31.number_format = 'MM-YYYY'

        # Corriger les formules pour utiliser l'onglet 'Annexe DNS' comme source
        # Section DÉCLARATION (lignes 24-27)
        # Ligne 24: Nombre d'employés par mois (compte uniquement ceux avec salaire positif)
        # Mois 1: compte les lignes où colonne I (salaire brut M1) > 0
        safe_write(ws_employeur, 24, 3, f"=COUNTIF('Annexe DNS'!I{annexe_first_row}:I{annexe_last_row},\">0\")")  # C24
        # Mois 2: compte les lignes où colonne M (salaire brut M2) > 0
        safe_write(ws_employeur, 24, 4, f"=COUNTIF('Annexe DNS'!M{annexe_first_row}:M{annexe_last_row},\">0\")")  # D24
        # Mois 3: compte les lignes où colonne Q (salaire brut M3) > 0
        safe_write(ws_employeur, 24, 5, f"=COUNTIF('Annexe DNS'!Q{annexe_first_row}:Q{annexe_last_row},\">0\")")  # E24

        # Ligne 25: Total salaires plafonnés par mois (depuis colonnes AA, AB, AC)
        # C25: Total salaires plafonnés Mois 1 (colonne AA)
        safe_write(ws_employeur, 25, 3, f"=SUM('Annexe DNS'!AA{annexe_first_row}:AA{annexe_last_row})")  # C25 - Mois 1
        # D25: Total salaires plafonnés Mois 2 (colonne AB)
        safe_write(ws_employeur, 25, 4, f"=SUM('Annexe DNS'!AB{annexe_first_row}:AB{annexe_last_row})")  # D25 - Mois 2
        # E25: Total salaires plafonnés Mois 3 (colonne AC)
        safe_write(ws_employeur, 25, 5, f"=SUM('Annexe DNS'!AC{annexe_first_row}:AC{annexe_last_row})")  # E25 - Mois 3
        safe_write(ws_employeur, 25, 6, "=SUM(C25:E25)")  # F25

        # Ligne 26: Cotisations CNaPS × 13% des charges (depuis colonnes X, Y, Z)
        # C26: 13% × Total charges CNAPS Mois 1 (colonne X)
        safe_write(ws_employeur, 26, 3, f"=SUM('Annexe DNS'!X{annexe_first_row}:X{annexe_last_row})*13/14")  # C26
        # D26: 13% × Total charges CNAPS Mois 2 (colonne Y)
        safe_write(ws_employeur, 26, 4, f"=SUM('Annexe DNS'!Y{annexe_first_row}:Y{annexe_last_row})*13/14")  # D26
        # E26: 13% × Total charges CNAPS Mois 3 (colonne Z)
        safe_write(ws_employeur, 26, 5, f"=SUM('Annexe DNS'!Z{annexe_first_row}:Z{annexe_last_row})*13/14")  # E26
        safe_write(ws_employeur, 26, 6, "=SUM(C26:E26)")  # F26

        # Ligne 27: Total CNaPS par mois (depuis colonnes X, Y, Z)
        # C27: Total charges CNAPS Mois 1 (colonne X)
        safe_write(ws_employeur, 27, 3, f"=SUM('Annexe DNS'!X{annexe_first_row}:X{annexe_last_row})/14")  # C27
        # D27: Total charges CNAPS Mois 2 (colonne Y)
        safe_write(ws_employeur, 27, 4, f"=SUM('Annexe DNS'!Y{annexe_first_row}:Y{annexe_last_row})/14")  # D27
        # E27: Total charges CNAPS Mois 3 (colonne Z)
        safe_write(ws_employeur, 27, 5, f"=SUM('Annexe DNS'!Z{annexe_first_row}:Z{annexe_last_row})/14")  # E27
        safe_write(ws_employeur, 27, 6, "=SUM(C27:E27)")  # F27

        # Section FMFP (lignes 36-38)
        # Ligne 36: Nombre d'employés (même que ligne 24)
        safe_write(ws_employeur, 36, 3, "=C24")  # C36
        safe_write(ws_employeur, 36, 4, "=D24")  # D36
        safe_write(ws_employeur, 36, 5, "=E24")  # E36

        # Ligne 37: Total salaires plafonnés (depuis colonnes AA, AB, AC)
        # C37: Total salaires plafonnés Mois 1 (colonne AA)
        safe_write(ws_employeur, 37, 3, f"=SUM('Annexe DNS'!AA{annexe_first_row}:AA{annexe_last_row})")  # C37
        # D37: Total salaires plafonnés Mois 2 (colonne AB)
        safe_write(ws_employeur, 37, 4, f"=SUM('Annexe DNS'!AB{annexe_first_row}:AB{annexe_last_row})")  # D37
        # E37: Total salaires plafonnés Mois 3 (colonne AC)
        safe_write(ws_employeur, 37, 5, f"=SUM('Annexe DNS'!AC{annexe_first_row}:AC{annexe_last_row})")  # E37
        safe_write(ws_employeur, 37, 6, "=SUM(C37:E37)")  # F37

        # Ligne 38: Total charges CNAPS par mois (depuis colonnes X, Y, Z)
        # C38: Total charges CNAPS Mois 1 (colonne X)
        safe_write(ws_employeur, 38, 3, f"=SUM('Annexe DNS'!X{annexe_first_row}:X{annexe_last_row})/14")  # C38
        # D38: Total charges CNAPS Mois 2 (colonne Y)
        safe_write(ws_employeur, 38, 4, f"=SUM('Annexe DNS'!Y{annexe_first_row}:Y{annexe_last_row})/14")  # D38
        # E38: Total charges CNAPS Mois 3 (colonne Z)
        safe_write(ws_employeur, 38, 5, f"=SUM('Annexe DNS'!Z{annexe_first_row}:Z{annexe_last_row})/14")  # E38
        safe_write(ws_employeur, 38, 6, "=SUM(C38:E38)")  # F38

        # ========================================
        # ONGLET 4 : Talon DNS - RECOPIE DU MODÈLE
        # ========================================
        # Le Talon DNS est un formulaire pré-formaté, pas une liste d'employés
        # Il doit être copié depuis le modèle avec ses formules intactes

        # Charger le modèle pour copier l'onglet Talon DNS
        model_path = os.path.join(settings.BASE_DIR, 'Modèle Facture CNaPS FMFP.xlsx')
        wb_model = load_workbook(model_path)
        ws_talon_model = wb_model['Talon DNS']
        ws_talon = wb['Talon DNS']

        # Copier TOUT le contenu du Talon DNS du modèle (structure, formules, formats)
        # Méthode : copier chaque cellule avec son format, formule et valeur
        for row in range(1, ws_talon_model.max_row + 1):
            for col in range(1, ws_talon_model.max_column + 1):
                source_cell = ws_talon_model.cell(row=row, column=col)
                target_cell = ws_talon.cell(row=row, column=col)

                # Copier la valeur/formule
                if source_cell.value is not None:
                    target_cell.value = source_cell.value

                # Copier le format de nombre
                if source_cell.number_format:
                    target_cell.number_format = source_cell.number_format

                # Copier les styles
                if source_cell.font:
                    target_cell.font = source_cell.font.copy()
                if source_cell.border:
                    target_cell.border = source_cell.border.copy()
                if source_cell.fill:
                    target_cell.fill = source_cell.fill.copy()
                if source_cell.alignment:
                    target_cell.alignment = source_cell.alignment.copy()

        # Copier les fusions de cellules
        # D'abord, supprimer toutes les fusions existantes
        merged_cells_to_remove = list(ws_talon.merged_cells.ranges)
        for merged_range in merged_cells_to_remove:
            ws_talon.unmerge_cells(str(merged_range))

        # Ensuite, copier les fusions du modèle
        for merged_range in ws_talon_model.merged_cells.ranges:
            ws_talon.merge_cells(str(merged_range))

        # Copier les largeurs de colonnes
        for col_letter in ws_talon_model.column_dimensions:
            if col_letter in ws_talon.column_dimensions:
                ws_talon.column_dimensions[col_letter].width = ws_talon_model.column_dimensions[col_letter].width

        # Copier les hauteurs de lignes
        for row_num in ws_talon_model.row_dimensions:
            if row_num in ws_talon.row_dimensions:
                ws_talon.row_dimensions[row_num].height = ws_talon_model.row_dimensions[row_num].height

        # Maintenant, mettre à jour UNIQUEMENT les cellules personnalisées :

        # 0. Effacer L1 et M1 (servaient aux formules Excel)
        safe_write(ws_talon, 1, 12, None)  # L1
        safe_write(ws_talon, 1, 13, None)  # M1

        # 2. Période et date limite (A11, A12)
        # A11: "Période : [Rang] trimestre [Année]"
        rangs_trimestre = {1: '1er', 2: '2e', 3: '3e', 4: '4e'}
        rang = rangs_trimestre.get(paiement.trimestre, str(paiement.trimestre))
        texte_periode = f"Période : {rang} trimestre {paiement.annee}"
        safe_write(ws_talon, 11, 1, texte_periode)  # A11

        # A12: "Date impérative de retour de paiement avant le : [Dernier jour du mois suivant le trimestre]"
        # Dernier mois du trimestre: T1=Mars(3), T2=Juin(6), T3=Sept(9), T4=Déc(12)
        # Mois suivant: T1=Avril(4), T2=Juillet(7), T3=Oct(10), T4=Jan(1)+1
        dernier_mois_trimestre = paiement.trimestre * 3
        mois_suivant = dernier_mois_trimestre + 1
        annee_date_limite = paiement.annee
        if mois_suivant > 12:
            mois_suivant = 1
            annee_date_limite += 1

        # Dernier jour du mois suivant
        dernier_jour = monthrange(annee_date_limite, mois_suivant)[1]

        # Formatter la date (ex: "31 Juillet 2025")
        mois_noms = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril', 5: 'Mai', 6: 'Juin',
            7: 'Juillet', 8: 'Août', 9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
        }
        texte_date_limite = f"Date impérative de retour de paiement avant le : {dernier_jour} {mois_noms[mois_suivant]} {annee_date_limite}"
        safe_write(ws_talon, 12, 1, texte_date_limite)  # A12

        # 3. Informations employeur (ligne 13)
        numero_cnaps = paiement.organisation.numero_cnaps if hasattr(paiement.organisation, 'numero_cnaps') else ''
        safe_write(ws_talon, 13, 2, numero_cnaps)  # B13
        safe_write(ws_talon, 13, 3, paiement.organisation.nom_organisation)  # C13

        # 4. Adresse employeur (ligne 14)
        adresse_complete = paiement.organisation.adresse if hasattr(paiement.organisation, 'adresse') else ''
        safe_write(ws_talon, 14, 1, f'Adresse: {adresse_complete}')

        # 5. Date de versement (D36) - Date d'export (aujourd'hui)
        date_export = timezone.now().date()
        safe_write(ws_talon, 36, 4, date_export)  # D36

        # 6. Totaux salaires et cotisations
        # C30 et I30 : Total des salaires non plafonnés (Total colonnes I, M, Q de Annexe DNS)
        safe_write(ws_talon, 30, 3, f"=SUM('Annexe DNS'!I{annexe_first_row}:I{annexe_last_row})+"
                                    f"SUM('Annexe DNS'!M{annexe_first_row}:M{annexe_last_row})+"
                                    f"SUM('Annexe DNS'!Q{annexe_first_row}:Q{annexe_last_row})")  # C30
        safe_write(ws_talon, 30, 9, f"=SUM('Annexe DNS'!I{annexe_first_row}:I{annexe_last_row})+"
                                    f"SUM('Annexe DNS'!M{annexe_first_row}:M{annexe_last_row})+"
                                    f"SUM('Annexe DNS'!Q{annexe_first_row}:Q{annexe_last_row})")  # I30

        # C31 et I31 : Valeur de EMPLOYEUR!F25
        safe_write(ws_talon, 31, 3, "=EMPLOYEUR!F25")  # C31
        safe_write(ws_talon, 31, 9, "=EMPLOYEUR!F25")  # I31

        # C32 : EMPLOYEUR!F26
        safe_write(ws_talon, 32, 3, "=EMPLOYEUR!F26")  # C32

        # C33, I32, I35 : EMPLOYEUR!F27
        safe_write(ws_talon, 33, 3, "=EMPLOYEUR!F27")  # C33
        safe_write(ws_talon, 32, 9, "=EMPLOYEUR!F27")  # I32
        safe_write(ws_talon, 35, 9, "=EMPLOYEUR!F27")  # I35

        # C35 : C32 + C33
        safe_write(ws_talon, 35, 3, "=C32+C33")  # C35

        # I36 : Date d'export (même que D36)
        safe_write(ws_talon, 36, 9, date_export)  # I36

        # D37 et I37 : MAX(EMPLOYEUR!C24, D24, E24)
        safe_write(ws_talon, 37, 4, "=MAX(EMPLOYEUR!C24,EMPLOYEUR!D24,EMPLOYEUR!E24)")  # D37
        safe_write(ws_talon, 37, 9, "=MAX(EMPLOYEUR!C24,EMPLOYEUR!D24,EMPLOYEUR!E24)")  # I37

        # 7. Certification (A50)
        # Format: "[Localité de l'organisation], le [Date de l'export]"
        # Puis: "Certifié sincère et véritable - (Cachet et signature)"
        localite = paiement.organisation.ville if hasattr(paiement.organisation, 'ville') and paiement.organisation.ville else 'Antananarivo'
        jour_export = date_export.day
        mois_export_nom = mois_noms[date_export.month]
        annee_export = date_export.year
        texte_certification = (f"{localite}, le {jour_export} {mois_export_nom} {annee_export} "
                              f"Certifié sincère et véritable - (Cachet et signature)")
        safe_write(ws_talon, 50, 1, texte_certification)  # A50

        # Les autres cellules du Talon DNS utilisent des formules
        # qui référencent soit l'Annexe DNS, soit EMPLOYEUR, soit font des calculs internes.
        # Ces formules ont été copiées du modèle et fonctionneront automatiquement.

        # Sauvegarder le fichier
        filename = f"Facture_CNaPS_FMFP_{paiement.organisation.nom_organisation}_T{paiement.trimestre}_{paiement.annee}.xlsx"
        output_path = os.path.join(settings.MEDIA_ROOT, 'factures_cnaps_fmfp', filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        wb.save(output_path)

        # Mettre à jour le paiement
        paiement.facture_generee = True
        paiement.date_generation = timezone.now()
        paiement.fichier_facture = filename
        paiement.save()

        # Retourner le fichier
        response = FileResponse(open(output_path, 'rb'), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    except PaiementCNaPSFMFP.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement CNaPS/FMFP introuvable'
        }, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
