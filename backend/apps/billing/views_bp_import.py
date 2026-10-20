"""
Import Excel spécifique pour les colonnes de paiements BP
Met à jour uniquement les 8 colonnes sans toucher aux autres données (GPS, etc.)
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from openpyxl import load_workbook, Workbook
from datetime import datetime
import io

from .models import PointEau


def import_paiements_bp_page(request):
    """Page d'import des paiements BP"""
    return render(request, 'billing/import_paiements_bp.html')


@csrf_exempt
@require_http_methods(["POST"])
def api_import_paiements_bp(request):
    """
    API pour importer les données de paiements BP depuis Excel
    Met à jour uniquement les 8 colonnes :
    - montantdemandepaye
    - montantdevispaye
    - numerodiamexdemande
    - basediamexdemande
    - datepaiementdemande
    - numerodiamexpaiementdevis
    - basediamexpaiementdevis (ou basediamexdevis)
    - datepaiementdevis
    """
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'Aucun fichier fourni'}, status=400)

        file = request.FILES['file']

        # Vérifier l'extension
        if not file.name.endswith(('.xlsx', '.xls')):
            return JsonResponse({
                'success': False,
                'error': 'Format de fichier non supporté. Utilisez .xlsx ou .xls'
            }, status=400)

        # Charger le fichier Excel
        wb = load_workbook(file, data_only=True)
        ws = wb.active

        # Lire les en-têtes (première ligne) et normaliser
        headers = []
        for cell in ws[1]:
            # Normaliser : minuscules + remplacer espaces par underscores
            header = cell.value.lower().replace(' ', '_') if cell.value else ''
            headers.append(header)

        # Vérifier que la colonne ID est présente
        if 'id' not in headers and 'id_point_eau' not in headers:
            return JsonResponse({
                'success': False,
                'error': 'Le fichier doit contenir une colonne "id" ou "id_point_eau" (UUID du point d\'eau)'
            }, status=400)

        updated_count = 0
        not_found_count = 0
        error_count = 0
        errors = []

        # Traiter chaque ligne à partir de la ligne 2
        for row_num in range(2, ws.max_row + 1):
            try:
                # Créer un dictionnaire avec les données de la ligne
                row_data = {}
                for col_num, header in enumerate(headers, 1):
                    cell_value = ws.cell(row=row_num, column=col_num).value
                    row_data[header] = str(cell_value).strip() if cell_value is not None else ''

                # Identifier le point d'eau par UUID (priorité à "id")
                point_eau = None
                identifier = None

                # Récupérer l'ID (supporter "id" et "id_point_eau")
                point_eau_id = row_data.get('id', '') or row_data.get('id_point_eau', '')

                if not point_eau_id or point_eau_id == 'None':
                    errors.append(f"Ligne {row_num}: ID point d'eau manquant")
                    not_found_count += 1
                    continue

                identifier = point_eau_id
                try:
                    point_eau = PointEau.objects.get(id=point_eau_id)
                except PointEau.DoesNotExist:
                    not_found_count += 1
                    errors.append(f"Ligne {row_num}: Point d'eau avec ID '{point_eau_id}' introuvable")
                    continue
                except ValueError:
                    not_found_count += 1
                    errors.append(f"Ligne {row_num}: ID '{point_eau_id}' invalide (doit être un UUID)")
                    continue

                # Flag pour savoir si au moins un champ a été mis à jour
                updated = False

                # Mettre à jour montantdemandepaye (supporter les deux formats)
                montant_demande = row_data.get('montantdemandepaye', '') or row_data.get('montant_demande_paye', '')
                if montant_demande and montant_demande != 'None':
                    try:
                        point_eau.montantdemandepaye = float(montant_demande)
                        updated = True
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Montant demande invalide '{montant_demande}'")

                # Mettre à jour montantdevispaye (supporter les deux formats)
                montant_devis = row_data.get('montantdevispaye', '') or row_data.get('montant_devis_paye', '')
                if montant_devis and montant_devis != 'None':
                    try:
                        point_eau.montantdevispaye = float(montant_devis)
                        updated = True
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Montant devis invalide '{montant_devis}'")

                # Mettre à jour numerodiamexdemande (supporter les deux formats)
                num_diamex_demande = row_data.get('numerodiamexdemande', '') or row_data.get('numero_diamex_demande', '')
                if num_diamex_demande and num_diamex_demande != 'None':
                    try:
                        point_eau.numerodiamexdemande = int(num_diamex_demande)
                        updated = True
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Numéro DiameX demande invalide '{num_diamex_demande}'")

                # Mettre à jour basediamexdemande (supporter les deux formats)
                base_diamex_demande = row_data.get('basediamexdemande', '') or row_data.get('base_diamex_demande', '')
                if base_diamex_demande and base_diamex_demande != 'None':
                    point_eau.basediamexdemande = base_diamex_demande
                    updated = True

                # Mettre à jour datepaiementdemande (supporter les deux formats)
                date_paiement_demande = row_data.get('datepaiementdemande', '') or row_data.get('date_paiement_demande', '')
                if date_paiement_demande and date_paiement_demande != 'None':
                    try:
                        # Essayer plusieurs formats de date
                        date_obj = None
                        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                            try:
                                date_obj = datetime.strptime(date_paiement_demande, fmt).date()
                                break
                            except ValueError:
                                continue

                        if date_obj:
                            point_eau.datepaiementdemande = date_obj
                            updated = True
                        else:
                            errors.append(f"Ligne {row_num}: Format de date paiement demande invalide '{date_paiement_demande}'")
                    except Exception as e:
                        errors.append(f"Ligne {row_num}: Erreur date paiement demande - {str(e)}")

                # Mettre à jour numerodiamexpaiementdevis (supporter les deux formats)
                num_diamex_devis = row_data.get('numerodiamexpaiementdevis', '') or row_data.get('numero_diamex_paiement_devis', '') or row_data.get('numerodiamexdevis', '')
                if num_diamex_devis and num_diamex_devis != 'None':
                    try:
                        point_eau.numerodiamexpaiementdevis = int(num_diamex_devis)
                        updated = True
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Numéro DiameX devis invalide '{num_diamex_devis}'")

                # Mettre à jour basediamexpaiementdevis (supporter les deux formats)
                base_diamex_devis = row_data.get('basediamexpaiementdevis', '') or row_data.get('base_diamex_paiement_devis', '') or row_data.get('basediamexdevis', '')
                if base_diamex_devis and base_diamex_devis != 'None':
                    point_eau.basediamexpaiementdevis = base_diamex_devis
                    updated = True

                # Mettre à jour datepaiementdevis (supporter les deux formats)
                date_paiement_devis = row_data.get('datepaiementdevis', '') or row_data.get('date_paiement_devis', '')
                if date_paiement_devis and date_paiement_devis != 'None':
                    try:
                        # Essayer plusieurs formats de date
                        date_obj = None
                        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                            try:
                                date_obj = datetime.strptime(date_paiement_devis, fmt).date()
                                break
                            except ValueError:
                                continue

                        if date_obj:
                            point_eau.datepaiementdevis = date_obj
                            updated = True
                        else:
                            errors.append(f"Ligne {row_num}: Format de date paiement devis invalide '{date_paiement_devis}'")
                    except Exception as e:
                        errors.append(f"Ligne {row_num}: Erreur date paiement devis - {str(e)}")

                # Sauvegarder si au moins un champ a été mis à jour
                if updated:
                    point_eau.save()
                    updated_count += 1

            except Exception as e:
                error_count += 1
                errors.append(f"Ligne {row_num}: Erreur - {str(e)}")

        return JsonResponse({
            'success': True,
            'updated': updated_count,
            'not_found': not_found_count,
            'errors': error_count,
            'error_details': errors[:20]  # Limiter à 20 erreurs pour ne pas surcharger
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de l\'import : {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_template_paiements_bp(request):
    """
    API pour télécharger un template Excel pour l'import des paiements BP
    """
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Paiements BP"

        # En-têtes des colonnes
        headers = [
            'id',
            'montantdemandepaye',
            'montantdevispaye',
            'numerodiamexdemande',
            'basediamexdemande',
            'datepaiementdemande',
            'numerodiamexpaiementdevis',
            'basediamexpaiementdevis',
            'datepaiementdevis'
        ]

        # Écrire les en-têtes
        for col_num, header in enumerate(headers, 1):
            ws.cell(row=1, column=col_num, value=header)

        # Exemples de données (UUID fictifs)
        examples = [
            ['12345678-1234-5678-1234-567812345678', '5000', '75000', '1048', '1', '10/01/2024', '1050', '1', '15/01/2024'],
            ['87654321-4321-8765-4321-876543218765', '3000', '50000', '1049', '2', '12/01/2024', '', '', ''],
            ['abcdef12-3456-7890-abcd-ef1234567890', '10000', '', '1051', '1', '20/01/2024', '', '', '']
        ]

        for row_num, example in enumerate(examples, 2):
            for col_num, value in enumerate(example, 1):
                ws.cell(row=row_num, column=col_num, value=value)

        # Sauvegarder dans un buffer
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        # Retourner le fichier Excel
        from django.http import HttpResponse
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=template_paiements_bp.xlsx'
        return response

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de la génération du template : {str(e)}'
        }, status=500)
