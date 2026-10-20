"""
Vues pour la gestion des paiements IRSA
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from django.db.models import Sum, Q
from django.utils import timezone
from decimal import Decimal
import json
import os
from datetime import datetime, date
from calendar import monthrange

from .models import Employe, Salaire, GrilleSalaire, PaiementIRSA, PaiementIRSADetail
from .salary_consistency import sync_salaire_with_grille
from apps.organization.models import Organisation


@login_required
def paiements_irsa_list(request):
    """Page de liste des paiements IRSA"""
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

    return render(request, 'employees/paiements_irsa_list.html', context)


@login_required
@require_http_methods(["GET"])
def api_paiements_irsa_list(request):
    """API pour lister les paiements IRSA"""
    try:
        # Récupérer l'organisation de l'utilisateur
        organisation_user = None
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                organisation_user = request.user.employe.base.organisation

        # Filtres
        organisation_id = request.GET.get('organisation_id')
        annee = request.GET.get('annee')
        mois = request.GET.get('mois')
        statut = request.GET.get('statut')

        # Query de base
        paiements_qs = PaiementIRSA.objects.all()

        # Filtrer par organisation de l'utilisateur (sécurité)
        if organisation_user:
            paiements_qs = paiements_qs.filter(organisation=organisation_user)

        # Filtres additionnels
        if organisation_id and organisation_id != 'all':
            paiements_qs = paiements_qs.filter(organisation_id=organisation_id)

        if annee:
            paiements_qs = paiements_qs.filter(annee=int(annee))

        if mois:
            paiements_qs = paiements_qs.filter(mois=int(mois))

        if statut and statut != 'all':
            paiements_qs = paiements_qs.filter(statut=statut)

        # Ajouter les relations après les filtres
        paiements_qs = paiements_qs.select_related(
            'organisation',
            'created_by'
        ).prefetch_related('details').order_by('-annee', '-mois')

        # Construire la réponse
        paiements_data = []
        for paiement in paiements_qs:
            nb_employes = paiement.details.count()

            paiements_data.append({
                'id': str(paiement.id),
                'organisation': paiement.organisation.nom_organisation,
                'organisation_id': str(paiement.organisation.id),
                'mois': paiement.mois,
                'annee': paiement.annee,
                'periode': f"{paiement.mois:02d}/{paiement.annee}",
                'date_paiement': paiement.date_paiement.strftime('%Y-%m-%d'),
                'nb_employes': nb_employes,
                'montant_total_brut': float(paiement.montant_total_brut),
                'montant_total_base_imposable': float(paiement.montant_total_base_imposable),
                'montant_total_irsa': float(paiement.montant_total_irsa),
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
def api_employes_irsa(request):
    """API pour récupérer la liste des employés avec leurs montants IRSA à payer"""
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
        mois = int(request.GET.get('mois', datetime.now().month))
        annee = int(request.GET.get('annee', datetime.now().year))

        # Créer les dates de début et fin du mois
        premier_jour = date(annee, mois, 1)
        dernier_jour = date(annee, mois, monthrange(annee, mois)[1])

        # Récupérer tous les salaires payés pour ce mois et cette organisation.
        # La source de vérité doit être la date de paiement réelle, pas la date de la grille.
        salaires = Salaire.objects.filter(
            grille_salaire__contrat__employe__base__organisation=organisation_user,
            date_paiement__gte=premier_jour,
            date_paiement__lte=dernier_jour
        ).select_related(
            'grille_salaire__contrat__employe',
            'grille_salaire__contrat__employe__poste'
        ).order_by(
            'grille_salaire__contrat__employe__poste__nom_poste',
            'grille_salaire__contrat__employe__nom',
            'grille_salaire__contrat__employe__prenom'
        )

        employes_data = []
        for salaire in salaires:
            sync_salaire_with_grille(salaire)
            employe = salaire.grille_salaire.contrat.employe
            grille = salaire.grille_salaire

            # Récupérer les valeurs déjà calculées dans la grille et le salaire
            salaire_brut = grille.salaire_brut_total if grille.salaire_brut_total else Decimal('0')
            base_imposable = grille.base_imposable if grille.base_imposable else Decimal('0')
            montant_irsa = salaire.irsa_paye if salaire.irsa_paye else Decimal('0')

            employes_data.append({
                'salaire_id': str(salaire.id),
                'employe_id': str(employe.id),
                'employe_nom_complet': employe.nom_complet,
                'employe_fonction': employe.poste.nom_poste if employe.poste else 'Non défini',
                'salaire_brut': float(salaire_brut),
                'base_imposable': float(base_imposable),
                'montant_irsa': float(montant_irsa),
            })

        return JsonResponse({
            'success': True,
            'employes': employes_data,
            'total': len(employes_data),
            'mois': mois,
            'annee': annee
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_creer_paiement_irsa(request):
    """API pour créer un paiement IRSA"""
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

        mois = int(data.get('mois'))
        annee = int(data.get('annee'))
        date_paiement_str = data.get('date_paiement')
        employes_data = data.get('employes', [])

        # Vérifier si un paiement existe déjà
        paiement_existant = PaiementIRSA.objects.filter(
            organisation=organisation_user,
            mois=mois,
            annee=annee
        ).first()

        if paiement_existant:
            return JsonResponse({
                'success': False,
                'error': f'Un paiement IRSA existe déjà pour {mois:02d}/{annee}'
            }, status=400)

        # Parser la date de paiement
        date_paiement = datetime.strptime(date_paiement_str, '%Y-%m-%d').date()

        # Créer le paiement IRSA
        paiement = PaiementIRSA.objects.create(
            organisation=organisation_user,
            mois=mois,
            annee=annee,
            date_paiement=date_paiement,
            created_by=request.user,
            statut='brouillon'
        )

        # Créer les détails
        montant_total_brut = Decimal('0')
        montant_total_base_imposable = Decimal('0')
        montant_total_irsa = Decimal('0')

        for emp_data in employes_data:
            salaire = Salaire.objects.get(id=emp_data['salaire_id'])

            detail = PaiementIRSADetail.objects.create(
                paiement_irsa=paiement,
                salaire=salaire,
                employe_nom_complet=emp_data['employe_nom_complet'],
                employe_fonction=emp_data['employe_fonction'],
                salaire_brut=Decimal(str(emp_data['salaire_brut'])),
                base_imposable=Decimal(str(emp_data['base_imposable'])),
                montant_irsa=Decimal(str(emp_data['montant_irsa']))
            )

            montant_total_brut += detail.salaire_brut
            montant_total_base_imposable += detail.base_imposable
            montant_total_irsa += detail.montant_irsa

        # Mettre à jour les totaux
        paiement.montant_total_brut = montant_total_brut
        paiement.montant_total_base_imposable = montant_total_base_imposable
        paiement.montant_total_irsa = montant_total_irsa
        paiement.save()

        return JsonResponse({
            'success': True,
            'message': 'Paiement IRSA créé avec succès',
            'paiement_id': str(paiement.id)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_valider_paiement_irsa(request, paiement_id):
    """API pour valider un paiement IRSA"""
    try:
        paiement = PaiementIRSA.objects.get(id=paiement_id)

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
            'message': 'Paiement IRSA validé avec succès'
        })

    except PaiementIRSA.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement IRSA introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["DELETE"])
def api_supprimer_paiement_irsa(request, paiement_id):
    """API pour supprimer un paiement IRSA (si statut = brouillon)"""
    try:
        paiement = PaiementIRSA.objects.get(id=paiement_id)

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
            'message': 'Paiement IRSA supprimé avec succès'
        })

    except PaiementIRSA.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement IRSA introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_detail_paiement_irsa(request, paiement_id):
    """API pour récupérer les détails d'un paiement IRSA"""
    try:
        paiement = PaiementIRSA.objects.select_related(
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
                'salaire_brut': float(detail.salaire_brut),
                'base_imposable': float(detail.base_imposable),
                'montant_irsa': float(detail.montant_irsa),
            })

        return JsonResponse({
            'success': True,
            'paiement': {
                'id': str(paiement.id),
                'organisation': paiement.organisation.nom_organisation,
                'mois': paiement.mois,
                'annee': paiement.annee,
                'date_paiement': paiement.date_paiement.strftime('%Y-%m-%d'),
                'montant_total_brut': float(paiement.montant_total_brut),
                'montant_total_base_imposable': float(paiement.montant_total_base_imposable),
                'montant_total_irsa': float(paiement.montant_total_irsa),
                'statut': paiement.statut,
                'facture_generee': paiement.facture_generee,
                'details': details_data
            }
        })

    except PaiementIRSA.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement IRSA introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def generer_facture_irsa(request, paiement_id):
    """Génère la facture Excel IRSA selon le modèle"""
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import Font, Alignment, Border, Side
        from django.conf import settings

        paiement = PaiementIRSA.objects.select_related('organisation').get(id=paiement_id)

        # Vérifier les droits
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                if paiement.organisation != request.user.employe.base.organisation:
                    return JsonResponse({
                        'success': False,
                        'error': 'Vous n\'avez pas accès à ce paiement'
                    }, status=403)

        # Charger le nouveau modèle propre
        modele_path = os.path.join(settings.BASE_DIR, 'modèle facture IRSA PROPRE.xlsx')
        wb = load_workbook(modele_path)

        # Récupérer les détails triés (avec relations optionnelles pour dates)
        details = paiement.details.select_related('salaire__grille_salaire__contrat').order_by('employe_fonction', 'employe_nom_complet')

        # Nom du mois en français
        mois_noms = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                     'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        mois_annee = f"{mois_noms[paiement.mois]} {paiement.annee}"

        # ========================================
        # ONGLET 1 : DIAME IRSA
        # ========================================
        ws1 = wb['DIAME IRSA']

        # Remplacer les placeholders dans les en-têtes
        ws1['B1'] = paiement.organisation.nom_organisation
        ws1['D1'] = paiement.date_paiement.strftime('%d/%m/%Y')
        ws1['B2'] = f"Concernant les salaires du mois : {mois_annee}"

        # Styles pour le tableau
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
        thin_border = Border(
            left=Side(style='thin', color='000000'),
            right=Side(style='thin', color='000000'),
            top=Side(style='thin', color='000000'),
            bottom=Side(style='thin', color='000000')
        )

        bold_font = Font(bold=True)
        normal_font = Font(bold=False)
        header_fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
        number_format = '#,##0.00'  # Format avec séparateurs de milliers

        # Remplir les lignes des employés (à partir de la ligne 5)
        current_row = 5
        current_fonction = None

        for detail in details:
            # Si changement de fonction, ajouter la ligne de regroupement
            if detail.employe_fonction != current_fonction:
                # Ligne de fonction en gras
                fonction_cell = ws1.cell(row=current_row, column=1, value=detail.employe_fonction or 'Non spécifié')
                fonction_cell.font = bold_font
                fonction_cell.border = thin_border

                # Fusionner les cellules pour la fonction (colonnes A à D)
                ws1.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=4)

                current_fonction = detail.employe_fonction
                current_row += 1

            # Ajouter l'employé (4 colonnes : nom, salaire brut, base imposable, IRSA)
            nom_cell = ws1.cell(row=current_row, column=1, value=detail.employe_nom_complet)
            brut_cell = ws1.cell(row=current_row, column=2, value=float(detail.salaire_brut))
            base_cell = ws1.cell(row=current_row, column=3, value=float(detail.base_imposable))
            irsa_cell = ws1.cell(row=current_row, column=4, value=float(detail.montant_irsa))

            # Appliquer les bordures
            for cell in [nom_cell, brut_cell, base_cell, irsa_cell]:
                cell.border = thin_border

            # Appliquer le format nombre avec séparateurs de milliers
            brut_cell.number_format = number_format
            base_cell.number_format = number_format
            irsa_cell.number_format = number_format

            # Alignement
            nom_cell.alignment = Alignment(horizontal='left', vertical='center')
            brut_cell.alignment = Alignment(horizontal='right', vertical='center')
            base_cell.alignment = Alignment(horizontal='right', vertical='center')
            irsa_cell.alignment = Alignment(horizontal='right', vertical='center')

            current_row += 1

        # Ajouter la ligne "Total général" en gras avec fond gris (avec formules Excel)
        current_row += 1  # Ligne vide
        total_row = current_row
        total_label = ws1.cell(row=total_row, column=1, value='Total général')

        # Utiliser des formules Excel pour calculer les totaux automatiquement
        # Les données vont de la ligne 5 à (total_row - 2) en excluant les lignes de fonction
        # On utilise SUMIF pour sommer uniquement les cellules numériques
        first_data_row = 5
        last_data_row = total_row - 2

        total_brut = ws1.cell(row=total_row, column=2)
        total_brut.value = f'=SUM(B{first_data_row}:B{last_data_row})'

        total_base = ws1.cell(row=total_row, column=3)
        total_base.value = f'=SUM(C{first_data_row}:C{last_data_row})'

        total_irsa = ws1.cell(row=total_row, column=4)
        total_irsa.value = f'=SUM(D{first_data_row}:D{last_data_row})'

        # Style de la ligne Total (fond gris comme l'en-tête)
        for cell in [total_label, total_brut, total_base, total_irsa]:
            cell.font = bold_font
            cell.border = thin_border
            cell.fill = header_fill  # Même fond gris que l'en-tête

        total_brut.number_format = number_format
        total_base.number_format = number_format
        total_irsa.number_format = number_format

        total_label.alignment = Alignment(horizontal='left', vertical='center')
        total_brut.alignment = Alignment(horizontal='right', vertical='center')
        total_base.alignment = Alignment(horizontal='right', vertical='center')
        total_irsa.alignment = Alignment(horizontal='right', vertical='center')

        # ========================================
        # ONGLET 2 : D.N IRSA
        # ========================================
        ws2 = wb['D.N IRSA']

        # Les lignes 2 sont vidées (pas de placeholders)
        # Les en-têtes sont en ligne 3 (ligne 4 supprimée)

        # Remplir les lignes des employés (à partir de la ligne 4 maintenant)
        current_row = 4

        for detail in details:
            # Essayer de récupérer les données depuis l'employé et le contrat
            date_embauche = ''
            date_debauche = ''
            progr = ''  # Base de l'employé
            categorie = ''  # Catégorie professionnelle du contrat

            try:
                if detail.salaire and detail.salaire.grille_salaire and detail.salaire.grille_salaire.contrat:
                    contrat = detail.salaire.grille_salaire.contrat
                    employe = contrat.employe

                    # Date d'embauche depuis le modèle Employe (format DD/MM/YYYY)
                    date_embauche = employe.date_embauche.strftime('%d/%m/%Y') if employe.date_embauche else ''

                    # Date de débauchage depuis le modèle Employe (format DD/MM/YYYY)
                    date_debauche = employe.date_debauchage.strftime('%d/%m/%Y') if employe.date_debauchage else ''

                    # Progr. = Base de l'employé
                    progr = employe.base.nom_base if employe.base else ''

                    # Classif. Prof. = Catégorie du contrat
                    categorie = contrat.categorie_professionnel if contrat.categorie_professionnel else ''
            except:
                pass

            # Créer les cellules avec bordures
            nom_cell = ws2.cell(row=current_row, column=1, value=detail.employe_nom_complet)
            embauche_cell = ws2.cell(row=current_row, column=2, value=date_embauche)
            debauche_cell = ws2.cell(row=current_row, column=3, value=date_debauche)
            fonction_cell = ws2.cell(row=current_row, column=4, value=detail.employe_fonction or 'Non spécifié')
            progr_cell = ws2.cell(row=current_row, column=5, value=progr)
            categ_cell = ws2.cell(row=current_row, column=6, value=categorie)
            brut_cell = ws2.cell(row=current_row, column=7, value=float(detail.salaire_brut))
            base_cell = ws2.cell(row=current_row, column=8, value=float(detail.base_imposable))
            irsa_cell = ws2.cell(row=current_row, column=9, value=float(detail.montant_irsa))

            # Appliquer les bordures à toutes les cellules
            for cell in [nom_cell, embauche_cell, debauche_cell, fonction_cell, progr_cell, categ_cell, brut_cell, base_cell, irsa_cell]:
                cell.border = thin_border

            # Appliquer le format nombre avec séparateurs de milliers
            brut_cell.number_format = number_format
            base_cell.number_format = number_format
            irsa_cell.number_format = number_format

            # Alignement
            nom_cell.alignment = Alignment(horizontal='left', vertical='center')
            embauche_cell.alignment = Alignment(horizontal='center', vertical='center')
            debauche_cell.alignment = Alignment(horizontal='center', vertical='center')
            fonction_cell.alignment = Alignment(horizontal='left', vertical='center')
            progr_cell.alignment = Alignment(horizontal='center', vertical='center')
            categ_cell.alignment = Alignment(horizontal='center', vertical='center')
            brut_cell.alignment = Alignment(horizontal='right', vertical='center')
            base_cell.alignment = Alignment(horizontal='right', vertical='center')
            irsa_cell.alignment = Alignment(horizontal='right', vertical='center')

            current_row += 1

        # Ajouter la ligne "Total général" en gras avec fond gris (avec formules Excel)
        current_row += 1  # Ligne vide
        total_row_dn = current_row

        ws2.cell(row=total_row_dn, column=1, value='Total général').font = bold_font
        ws2.cell(row=total_row_dn, column=1).fill = header_fill
        ws2.cell(row=total_row_dn, column=1).border = thin_border
        ws2.cell(row=total_row_dn, column=1).alignment = Alignment(horizontal='left', vertical='center')

        # Colonnes 2-6 vides mais avec fond gris
        for col in range(2, 7):
            cell = ws2.cell(row=total_row_dn, column=col, value='')
            cell.fill = header_fill
            cell.border = thin_border

        # Totaux des montants avec formules Excel
        # Les données vont de la ligne 4 à (total_row_dn - 2)
        first_data_row_dn = 4
        last_data_row_dn = total_row_dn - 2

        total_brut_dn = ws2.cell(row=total_row_dn, column=7)
        total_brut_dn.value = f'=SUM(G{first_data_row_dn}:G{last_data_row_dn})'

        total_base_dn = ws2.cell(row=total_row_dn, column=8)
        total_base_dn.value = f'=SUM(H{first_data_row_dn}:H{last_data_row_dn})'

        total_irsa_dn = ws2.cell(row=total_row_dn, column=9)
        total_irsa_dn.value = f'=SUM(I{first_data_row_dn}:I{last_data_row_dn})'

        for cell in [total_brut_dn, total_base_dn, total_irsa_dn]:
            cell.font = bold_font
            cell.fill = header_fill
            cell.border = thin_border
            cell.number_format = number_format
            cell.alignment = Alignment(horizontal='right', vertical='center')

        # ========================================
        # ONGLET 3 : bordereau IRSA (préservation de tous les styles)
        # ========================================
        ws3 = wb['bordereau IRSA']

        # INFORMATIONS GÉOGRAPHIQUES
        # B8 = Province (ligne "TAMATAVE")
        ws3['B8'] = paiement.organisation.adresse_province if hasattr(paiement.organisation, 'adresse_province') else 'TAMATAVE'

        # B10 = District (ligne "VAVATENINA")
        ws3['B10'] = paiement.organisation.adresse_district if hasattr(paiement.organisation, 'adresse_district') else ''

        # B12 = Commune
        ws3['B12'] = paiement.organisation.adresse_commune if hasattr(paiement.organisation, 'adresse_commune') else ''

        # DATES
        # G10 = Année
        ws3['G10'] = paiement.annee
        ws3['F10'] = 'TAONA:'

        # G13 = Mois de (référence au mois en texte)
        ws3['G13'] = mois_annee  # Ex: "Janvier 2025"

        # IDENTIFICATION ORGANISATION
        # F16 = NIF (Numéro d'Identification Fiscale)
        ws3['F16'] = paiement.organisation.nif if hasattr(paiement.organisation, 'nif') else ''

        # F17 = Numéro CnaPS
        ws3['F17'] = paiement.organisation.numero_cnaps if hasattr(paiement.organisation, 'numero_cnaps') else ''

        # MONTANTS (utilisation de formules Excel pour calcul automatique)
        # F28 = Nombre d'employés concernés
        ws3['F28'] = details.count()

        # F30 = Base imposable totale (somme des lignes de données uniquement)
        ws3['F30'] = f'=SUM(\'D.N IRSA\'!H4:H{last_data_row_dn})'

        # G29 = IRSA total (somme des lignes de données uniquement)
        ws3['G29'] = f'=SUM(\'D.N IRSA\'!I4:I{last_data_row_dn})'

        # G39, G42, F54 = Cellules vides (à remplir manuellement selon besoins)
        ws3['G39'] = None
        ws3['G42'] = None
        ws3['F54'] = None

        # Nettoyer les colonnes V et W du bordereau
        for row_idx in range(1, ws3.max_row + 1):
            ws3.cell(row=row_idx, column=22, value=None)  # V
            ws3.cell(row=row_idx, column=23, value=None)  # W

        # Sauvegarder le fichier
        filename = f"Facture_IRSA_{paiement.organisation.nom_organisation}_{paiement.mois:02d}_{paiement.annee}.xlsx"
        output_path = os.path.join(settings.MEDIA_ROOT, 'factures_irsa', filename)
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

    except PaiementIRSA.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement IRSA introuvable'
        }, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
