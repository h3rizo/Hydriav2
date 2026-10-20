from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from datetime import datetime
from decimal import Decimal
import json

from .models import Transfert, TransfertItem
from apps.organization.models import Magasin
from apps.employees.models import Employe
from apps.planning.models import Designation


@login_required
def export_transferts_excel(request):
    """Exporter les transferts en Excel"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Transferts"

    # En-têtes
    headers = [
        'ID Transfert', 'N° Transfert', 'Date Transfert',
        'ID Magasin Origine', 'Magasin Origine', 'Base Origine',
        'ID Magasin Destination', 'Magasin Destination', 'Base Destination',
        'Statut', 'ID Initié Par', 'Initié Par', 'ID Reçu Par', 'Reçu Par', 'Notes'
    ]
    ws.append(headers)

    # Style des en-têtes
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Récupérer les transferts
    transferts = Transfert.objects.select_related(
        'magasin_origine__base', 'magasin_destination__base', 'initiated_by', 'received_by'
    ).order_by('-transfer_date')

    for transfert in transferts:
        ws.append([
            str(transfert.id),
            transfert.transfer_number,
            transfert.transfer_date.strftime('%d/%m/%Y'),
            str(transfert.magasin_origine.id),
            transfert.magasin_origine.nom_magasin,
            transfert.magasin_origine.base.nom_base,
            str(transfert.magasin_destination.id),
            transfert.magasin_destination.nom_magasin,
            transfert.magasin_destination.base.nom_base,
            transfert.get_status_display(),
            str(transfert.initiated_by.id) if transfert.initiated_by else '',
            transfert.initiated_by.surnom if transfert.initiated_by else '',
            str(transfert.received_by.id) if transfert.received_by else '',
            transfert.received_by.surnom if transfert.received_by else '',
            transfert.notes or ''
        ])

    # Ajuster les largeurs
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    # Préparer la réponse
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=transferts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

    wb.save(response)
    return response


@login_required
def export_transferts_details_excel(request):
    """Exporter les transferts avec leurs items en Excel"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Détails Transferts"

    # En-têtes
    headers = [
        'ID Transfert', 'N° Transfert', 'Date Transfert',
        'Magasin Origine', 'Base Origine',
        'Magasin Destination', 'Base Destination',
        'Statut',
        'ID Désignation', 'Désignation', 'Unité', 'Quantité'
    ]
    ws.append(headers)

    # Style des en-têtes
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Récupérer les transferts avec items
    transferts = Transfert.objects.select_related(
        'magasin_origine__base', 'magasin_destination__base'
    ).prefetch_related('items__designation').order_by('-transfer_date')

    for transfert in transferts:
        for item in transfert.items.all():
            ws.append([
                str(transfert.id),
                transfert.transfer_number,
                transfert.transfer_date.strftime('%d/%m/%Y'),
                transfert.magasin_origine.nom_magasin,
                transfert.magasin_origine.base.nom_base,
                transfert.magasin_destination.nom_magasin,
                transfert.magasin_destination.base.nom_base,
                transfert.get_status_display(),
                str(item.designation.id),
                item.designation.nom,
                item.designation.unite or '',
                float(item.quantity_sent)
            ])

    # Ajuster les largeurs
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    # Préparer la réponse
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=transferts_details_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

    wb.save(response)
    return response


@login_required
def template_transferts_excel(request):
    """Générer un template Excel pour l'import de transferts"""
    wb = Workbook()

    # Feuille 1: Template
    ws = wb.active
    ws.title = "Template Transferts"

    headers = [
        'ID Transfert*', 'N° Transfert*', 'Date Transfert (JJ/MM/AAAA)*',
        'ID Magasin Origine*', 'ID Magasin Destination*', 'Notes'
    ]
    ws.append(headers)

    # Style
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font

    # Instructions
    ws.append([])
    ws.append(['INSTRUCTIONS:'])
    ws.append(['- Les colonnes avec * sont obligatoires'])
    ws.append(['- Pour créer un nouveau transfert, laissez ID Transfert vide'])
    ws.append(['- Pour modifier un transfert existant, renseignez ID Transfert'])
    ws.append(['- Les IDs de magasins sont disponibles dans la feuille "Magasins"'])
    ws.append([])

    # Exemples
    ws.append(['EXEMPLES:'])
    ws.append([
        '', 'TRANS-001', '15/11/2025',
        '(voir feuille Magasins)', '(voir feuille Magasins)', 'Transfert urgent'
    ])

    # Feuille 2: Liste des Magasins
    ws_mag = wb.create_sheet("Magasins")
    ws_mag.append(['ID Magasin', 'Nom Magasin', 'Base', 'Organisation'])

    for cell in ws_mag[1]:
        cell.fill = header_fill
        cell.font = header_font

    magasins = Magasin.objects.select_related('base__organisation').order_by('base__nom_base', 'nom_magasin')[:200]
    for mag in magasins:
        ws_mag.append([
            str(mag.id),
            mag.nom_magasin,
            mag.base.nom_base,
            mag.base.organisation.nom_organisation
        ])

    # Feuille 3: Liste des Employés
    ws_emp = wb.create_sheet("Employés")
    ws_emp.append(['ID Employé', 'Surnom', 'Nom Complet'])

    for cell in ws_emp[1]:
        cell.fill = header_fill
        cell.font = header_font

    employes = Employe.objects.filter(date_debauchage__isnull=True).order_by('surnom')[:200]
    for emp in employes:
        ws_emp.append([
            str(emp.id),
            emp.surnom,
            emp.nom_complet
        ])

    # Réponse
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=template_transferts.xlsx'
    wb.save(response)
    return response


@login_required
def template_transferts_items_excel(request):
    """Générer un template Excel pour l'import des items de transfert"""
    wb = Workbook()

    # Feuille 1: Template
    ws = wb.active
    ws.title = "Template Items"

    headers = [
        'ID Transfert*', 'N° Transfert (pour info)',
        'ID Désignation*', 'Quantité*'
    ]
    ws.append(headers)

    # Style
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font

    # Instructions
    ws.append([])
    ws.append(['INSTRUCTIONS:'])
    ws.append(['- Les colonnes avec * sont obligatoires'])
    ws.append(['- ID Transfert doit correspondre à un transfert existant'])
    ws.append(['- Les IDs de désignations sont disponibles dans la feuille "Désignations"'])
    ws.append([])

    # Exemples
    ws.append(['EXEMPLES:'])
    ws.append([
        '(ID du transfert)', 'TRANS-001',
        '(voir feuille Désignations)', '100'
    ])

    # Feuille 2: Liste des Désignations
    ws_desig = wb.create_sheet("Désignations")
    ws_desig.append(['ID Désignation', 'Nom', 'Unité', 'Type'])

    for cell in ws_desig[1]:
        cell.fill = header_fill
        cell.font = header_font

    designations = Designation.objects.filter(actif=True).order_by('nom')[:500]
    for desig in designations:
        ws_desig.append([
            str(desig.id),
            desig.nom,
            desig.unite or '',
            desig.type_designation.nom if desig.type_designation else ''
        ])

    # Feuille 3: Liste des Transferts récents
    ws_trans = wb.create_sheet("Transferts Récents")
    ws_trans.append(['ID Transfert', 'N° Transfert', 'Date', 'Magasin Origine', 'Magasin Destination', 'Statut'])

    for cell in ws_trans[1]:
        cell.fill = header_fill
        cell.font = header_font

    transferts = Transfert.objects.select_related(
        'magasin_origine', 'magasin_destination'
    ).order_by('-transfer_date')[:100]
    for t in transferts:
        ws_trans.append([
            str(t.id),
            t.transfer_number,
            t.transfer_date.strftime('%d/%m/%Y %H:%M'),
            t.magasin_origine.nom_magasin,
            t.magasin_destination.nom_magasin,
            t.get_status_display()
        ])

    # Réponse
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=template_transfert_items.xlsx'
    wb.save(response)
    return response


@csrf_exempt
@require_http_methods(["POST"])
def import_transferts_excel(request):
    """Importer des transferts depuis Excel"""
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'Aucun fichier fourni'}, status=400)

        file = request.FILES['file']
        wb = load_workbook(file)
        ws = wb.active

        nb_imported = 0
        errors = []

        # Parcourir les lignes (sauter l'en-tête)
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                transfert_id = row[0]
                transfer_number = row[1]
                transfer_date_str = row[2]
                magasin_origine_id = row[3]
                magasin_destination_id = row[4]
                notes = row[5] if len(row) > 5 else ''

                # Validation
                if not transfer_number or not transfer_date_str:
                    errors.append(f"Ligne {idx}: Numéro et date de transfert requis")
                    continue

                if not magasin_origine_id or not magasin_destination_id:
                    errors.append(f"Ligne {idx}: Magasins origine et destination requis")
                    continue

                # Parser la date (format DD/MM/YYYY)
                try:
                    if isinstance(transfer_date_str, datetime):
                        transfer_date = transfer_date_str
                    else:
                        transfer_date = datetime.strptime(str(transfer_date_str), '%d/%m/%Y')
                except:
                    try:
                        transfer_date = datetime.strptime(str(transfer_date_str), '%Y-%m-%d')
                    except:
                        errors.append(f"Ligne {idx}: Format de date invalide (attendu: JJ/MM/AAAA)")
                        continue

                # Récupérer les magasins
                try:
                    magasin_origine = Magasin.objects.get(id=str(magasin_origine_id))
                    magasin_destination = Magasin.objects.get(id=str(magasin_destination_id))
                except Magasin.DoesNotExist:
                    errors.append(f"Ligne {idx}: Magasin non trouvé")
                    continue

                # Créer ou mettre à jour
                if transfert_id:
                    # Mise à jour
                    try:
                        transfert = Transfert.objects.get(id=str(transfert_id))
                        transfert.transfer_number = transfer_number
                        transfert.transfer_date = transfer_date
                        transfert.magasin_origine = magasin_origine
                        transfert.magasin_destination = magasin_destination
                        transfert.notes = notes or ''
                        transfert.save()
                        nb_imported += 1
                    except Transfert.DoesNotExist:
                        errors.append(f"Ligne {idx}: Transfert {transfert_id} non trouvé")
                else:
                    # Création
                    Transfert.objects.create(
                        transfer_number=transfer_number,
                        transfer_date=transfer_date,
                        magasin_origine=magasin_origine,
                        magasin_destination=magasin_destination,
                        initiated_by=request.user.employe if hasattr(request.user, 'employe') else None,
                        notes=notes or ''
                    )
                    nb_imported += 1

            except Exception as e:
                errors.append(f"Ligne {idx}: {str(e)}")

        return JsonResponse({
            'success': True,
            'nb_imported': nb_imported,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def import_transferts_items_excel(request):
    """Importer des items de transfert depuis Excel"""
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'Aucun fichier fourni'}, status=400)

        file = request.FILES['file']
        wb = load_workbook(file)
        ws = wb.active

        nb_imported = 0
        errors = []

        # Parcourir les lignes (sauter l'en-tête)
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                transfert_id = row[0]
                designation_id = row[2]
                quantity = row[3]

                # Validation
                if not transfert_id or not designation_id or not quantity:
                    errors.append(f"Ligne {idx}: Transfert ID, Désignation ID et Quantité requis")
                    continue

                # Récupérer le transfert et la désignation
                try:
                    transfert = Transfert.objects.get(id=str(transfert_id))
                    designation = Designation.objects.get(id=str(designation_id))
                except (Transfert.DoesNotExist, Designation.DoesNotExist):
                    errors.append(f"Ligne {idx}: Transfert ou Désignation non trouvé")
                    continue

                # Créer l'item
                TransfertItem.objects.create(
                    transfert=transfert,
                    designation=designation,
                    quantity_sent=Decimal(str(quantity)),
                    quantity_received=Decimal(str(quantity))  # Par défaut, quantité reçue = quantité envoyée
                )
                nb_imported += 1

            except Exception as e:
                errors.append(f"Ligne {idx}: {str(e)}")

        return JsonResponse({
            'success': True,
            'nb_imported': nb_imported,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
