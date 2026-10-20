"""
Vues pour la gestion des soldes réels des journaux.
"""
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from datetime import datetime
from decimal import Decimal
import json
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from .models import SoldesReels, BaseDiameX


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _filter_soldes_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset

    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()

    allowed_fichiers = list(
        BaseDiameX.objects.filter(imported_by__base__organisation_id=organisation_id)
        .exclude(fichier_source__isnull=True)
        .exclude(fichier_source='')
        .values_list('fichier_source', flat=True)
        .distinct()
    )

    return queryset.filter(
        Q(imported_by__base__organisation_id=organisation_id) |
        Q(fichier_source__in=allowed_fichiers)
    ).distinct()


@login_required
def soldes_reels_list(request):
    """
    Page de liste des soldes réels avec filtres.
    """
    # Récupérer les journaux distincts pour le filtre
    journaux = _filter_soldes_by_scope(
        SoldesReels.objects.all(),
        request.user
    ).values_list('journal', flat=True).distinct().order_by('journal')

    context = {
        'journaux': journaux,
    }

    return render(request, 'accounting/soldes_reels_list.html', context)


@login_required
@require_http_methods(["GET"])
def api_soldes_reels_list(request):
    """
    API pour récupérer la liste des soldes réels avec filtres.
    """
    try:
        # Récupérer les filtres
        journal = request.GET.get('journal')
        date_debut = request.GET.get('date_debut')
        date_fin = request.GET.get('date_fin')
        search = request.GET.get('search', '').strip()

        # Construire la requête
        queryset = _filter_soldes_by_scope(SoldesReels.objects.all(), request.user)

        # Filtrer par journal
        if journal:
            queryset = queryset.filter(journal=journal)

        # Filtrer par date
        if date_debut:
            queryset = queryset.filter(date_m__gte=date_debut)
        if date_fin:
            queryset = queryset.filter(date_m__lte=date_fin)

        # Recherche textuelle
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) |
                Q(journal__icontains=search) |
                Q(validation__icontains=search)
            )

        # Trier par date décroissante
        queryset = queryset.order_by('-date_m', '-date_input')

        # Préparer les données
        soldes = []
        for solde in queryset:
            soldes.append({
                'id': solde.id,
                'journal': solde.journal or '',
                'date_m': solde.date_m.strftime('%Y-%m-%d') if solde.date_m else '',
                'rec': float(solde.rec) if solde.rec else 0,
                'date_rec': solde.date_rec.strftime('%Y-%m-%d') if solde.date_rec else '',
                'description': solde.description or '',
                'ccy': solde.ccy or '',
                'validation': solde.validation or '',
                'scan': solde.scan or '',
                'fichier_source': solde.fichier_source or '',
                'date_import': solde.date_import.strftime('%Y-%m-%d %H:%M') if solde.date_import else '',
                'imported_by': f"{solde.imported_by.prenom} {solde.imported_by.nom}" if solde.imported_by else '',
            })

        return JsonResponse({
            'success': True,
            'soldes': soldes,
            'count': len(soldes)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_solde_reel_create(request):
    """
    API pour créer un nouveau solde réel.
    """
    try:
        data = json.loads(request.body)

        # Validation des champs obligatoires
        journal = data.get('journal', '').strip()
        date_m_str = data.get('date_m', '').strip()
        rec = data.get('rec')

        if not journal or not date_m_str:
            return JsonResponse({
                'success': False,
                'error': 'Le journal et la date sont obligatoires'
            }, status=400)

        # Convertir la date
        try:
            date_m = datetime.strptime(date_m_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Format de date invalide (attendu: YYYY-MM-DD)'
            }, status=400)

        # Créer le solde
        solde = SoldesReels.objects.create(
            journal=journal,
            date_m=date_m,
            rec=Decimal(str(rec)) if rec is not None else None,
            date_rec=datetime.strptime(data.get('date_rec'), '%Y-%m-%d').date() if data.get('date_rec') else None,
            description=data.get('description', '').strip(),
            ccy=data.get('ccy', '').strip(),
            validation=data.get('validation', '').strip(),
            scan=data.get('scan', '').strip(),
            imported_by=getattr(request.user, 'employe', None)
        )

        return JsonResponse({
            'success': True,
            'message': 'Solde créé avec succès',
            'solde_id': solde.id
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_solde_reel_update(request, solde_id):
    """
    API pour modifier un solde réel existant.
    """
    try:
        solde = _filter_soldes_by_scope(
            SoldesReels.objects.all(),
            request.user
        ).get(id=solde_id)
        data = json.loads(request.body)

        # Mettre à jour les champs
        if 'journal' in data:
            solde.journal = data['journal'].strip()

        if 'date_m' in data:
            try:
                solde.date_m = datetime.strptime(data['date_m'], '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Format de date invalide'
                }, status=400)

        if 'rec' in data:
            solde.rec = Decimal(str(data['rec'])) if data['rec'] is not None else None

        if 'date_rec' in data and data['date_rec']:
            try:
                solde.date_rec = datetime.strptime(data['date_rec'], '%Y-%m-%d').date()
            except ValueError:
                pass

        if 'description' in data:
            solde.description = data['description'].strip()

        if 'ccy' in data:
            solde.ccy = data['ccy'].strip()

        if 'validation' in data:
            solde.validation = data['validation'].strip()

        if 'scan' in data:
            solde.scan = data['scan'].strip()

        solde.save()

        return JsonResponse({
            'success': True,
            'message': 'Solde mis à jour avec succès'
        })

    except SoldesReels.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Solde non trouvé'
        }, status=404)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_solde_reel_delete(request, solde_id):
    """
    API pour supprimer un solde réel.
    """
    try:
        solde = _filter_soldes_by_scope(
            SoldesReels.objects.all(),
            request.user
        ).get(id=solde_id)
        journal = solde.journal
        date = solde.date_m

        solde.delete()

        return JsonResponse({
            'success': True,
            'message': f'Solde supprimé : {journal} - {date}'
        })

    except SoldesReels.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Solde non trouvé'
        }, status=404)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def export_excel_soldes_reels(request):
    """
    Exporter les soldes réels vers Excel.
    """
    try:
        # Récupérer les filtres (mêmes que la liste)
        journal = request.GET.get('journal')
        date_debut = request.GET.get('date_debut')
        date_fin = request.GET.get('date_fin')
        search = request.GET.get('search', '').strip()

        # Construire la requête
        queryset = _filter_soldes_by_scope(SoldesReels.objects.all(), request.user)

        if journal:
            queryset = queryset.filter(journal=journal)
        if date_debut:
            queryset = queryset.filter(date_m__gte=date_debut)
        if date_fin:
            queryset = queryset.filter(date_m__lte=date_fin)
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) |
                Q(journal__icontains=search)
            )

        queryset = queryset.order_by('journal', 'date_m')

        # Créer le workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Soldes Réels"

        # Styles
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID', 'Journal', 'Date', 'Montant (Rec)', 'Date Rec',
            'Description', 'Devise', 'Validation', 'Scan',
            'Fichier Source', 'Date Import', 'Importé par'
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = border

        # Données
        for row_num, solde in enumerate(queryset, 2):
            ws.cell(row=row_num, column=1, value=solde.id).border = border
            ws.cell(row=row_num, column=2, value=solde.journal or '').border = border
            ws.cell(row=row_num, column=3, value=solde.date_m.strftime('%Y-%m-%d') if solde.date_m else '').border = border
            ws.cell(row=row_num, column=4, value=float(solde.rec) if solde.rec else 0).border = border
            ws.cell(row=row_num, column=5, value=solde.date_rec.strftime('%Y-%m-%d') if solde.date_rec else '').border = border
            ws.cell(row=row_num, column=6, value=solde.description or '').border = border
            ws.cell(row=row_num, column=7, value=solde.ccy or '').border = border
            ws.cell(row=row_num, column=8, value=solde.validation or '').border = border
            ws.cell(row=row_num, column=9, value=solde.scan or '').border = border
            ws.cell(row=row_num, column=10, value=solde.fichier_source or '').border = border
            ws.cell(row=row_num, column=11, value=solde.date_import.strftime('%Y-%m-%d %H:%M') if solde.date_import else '').border = border
            ws.cell(row=row_num, column=12, value=f"{solde.imported_by.prenom} {solde.imported_by.nom}" if solde.imported_by else '').border = border

        # Ajuster la largeur des colonnes
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 15

        # Largeurs spécifiques
        ws.column_dimensions['F'].width = 40  # Description
        ws.column_dimensions['I'].width = 30  # Scan
        ws.column_dimensions['J'].width = 30  # Fichier source

        # Préparer la réponse
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=soldes_reels_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        return HttpResponse(f'Erreur lors de l\'export: {str(e)}', status=500)


@login_required
def template_excel_soldes_reels(request):
    """
    Télécharger un template Excel pour l'import de soldes réels.
    """
    try:
        # Créer le workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Template Import"

        # Styles
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        example_fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

        # En-têtes avec instructions
        headers = [
            'Journal*', 'Date (YYYY-MM-DD)*', 'Montant (Rec)', 'Date Rec (YYYY-MM-DD)',
            'Description', 'Devise', 'Validation', 'Scan'
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment

        # Instructions
        ws.cell(row=2, column=1, value="Instructions:")
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
        ws.cell(row=2, column=1).font = Font(bold=True, color="FF0000")

        instructions = [
            "- Les colonnes avec * sont obligatoires",
            "- Format de date: YYYY-MM-DD (ex: 2025-12-14)",
            "- Journal: Code du journal comptable",
            "- Montant (Rec): Montant en nombre décimal",
            "- Ne pas modifier les en-têtes de colonnes",
            "- Supprimer ces lignes d'instructions avant l'import"
        ]

        for i, instruction in enumerate(instructions, 3):
            ws.cell(row=i, column=1, value=instruction)
            ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=len(headers))

        # Exemples
        example_row = len(instructions) + 3
        ws.cell(row=example_row, column=1, value="Exemples:")
        ws.merge_cells(start_row=example_row, start_column=1, end_row=example_row, end_column=len(headers))
        ws.cell(row=example_row, column=1).font = Font(bold=True, italic=True)

        examples = [
            ['JV01', '2025-01-15', '150000.50', '2025-01-15', 'Solde initial', 'MGA', 'OK', ''],
            ['JV02', '2025-02-01', '250000', '2025-02-01', 'Solde février', 'MGA', 'OK', 'scan_fev.pdf'],
            ['CA01', '2025-03-10', '500000.75', '', 'Solde caisse', 'MGA', '', ''],
        ]

        for row_offset, example in enumerate(examples, 1):
            row_num = example_row + row_offset
            for col_num, value in enumerate(example, 1):
                cell = ws.cell(row=row_num, column=col_num, value=value)
                cell.fill = example_fill

        # Ajuster largeurs
        ws.column_dimensions['A'].width = 12  # Journal
        ws.column_dimensions['B'].width = 20  # Date
        ws.column_dimensions['C'].width = 15  # Montant
        ws.column_dimensions['D'].width = 20  # Date Rec
        ws.column_dimensions['E'].width = 40  # Description
        ws.column_dimensions['F'].width = 10  # Devise
        ws.column_dimensions['G'].width = 12  # Validation
        ws.column_dimensions['H'].width = 20  # Scan

        # Préparer la réponse
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=template_import_soldes_reels.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        return HttpResponse(f'Erreur: {str(e)}', status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def import_excel_soldes_reels(request):
    """
    Importer des soldes réels depuis un fichier Excel.
    """
    try:
        if 'file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'Aucun fichier fourni'
            }, status=400)

        excel_file = request.FILES['file']

        # Charger le fichier Excel
        try:
            wb = load_workbook(excel_file, data_only=True)
            ws = wb.active
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Fichier Excel invalide: {str(e)}'
            }, status=400)

        # Vérifier les en-têtes
        expected_headers = ['Journal*', 'Date (YYYY-MM-DD)*', 'Montant (Rec)', 'Date Rec (YYYY-MM-DD)',
                          'Description', 'Devise', 'Validation', 'Scan']

        actual_headers = [cell.value for cell in ws[1]]

        if actual_headers[:len(expected_headers)] != expected_headers:
            return JsonResponse({
                'success': False,
                'error': 'Les en-têtes du fichier ne correspondent pas au template. Téléchargez le template et réessayez.'
            }, status=400)

        # Importer les données
        nb_imported = 0
        errors = []

        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            # Ignorer les lignes vides
            if not row[0]:
                continue

            # Ignorer les lignes d'instructions/exemples
            if row[0] and str(row[0]).startswith(('Instructions:', 'Exemples:', '-')):
                continue

            try:
                journal = str(row[0]).strip() if row[0] else None
                date_m_str = str(row[1]).strip() if row[1] else None
                rec = row[2] if row[2] is not None else None
                date_rec_str = str(row[3]).strip() if row[3] else None
                description = str(row[4]).strip() if row[4] else ''
                ccy = str(row[5]).strip() if row[5] else ''
                validation = str(row[6]).strip() if row[6] else ''
                scan = str(row[7]).strip() if row[7] else ''

                # Validation
                if not journal or not date_m_str:
                    errors.append(f'Ligne {row_num}: Journal et Date sont obligatoires')
                    continue

                # Convertir les dates
                try:
                    date_m = datetime.strptime(date_m_str, '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f'Ligne {row_num}: Format de date invalide pour Date (attendu: YYYY-MM-DD)')
                    continue

                date_rec = None
                if date_rec_str:
                    try:
                        date_rec = datetime.strptime(date_rec_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f'Ligne {row_num}: Format de date invalide pour Date Rec')
                        continue

                # Créer le solde
                SoldesReels.objects.create(
                    journal=journal,
                    date_m=date_m,
                    rec=Decimal(str(rec)) if rec is not None else None,
                    date_rec=date_rec,
                    description=description,
                    ccy=ccy,
                    validation=validation,
                    scan=scan,
                    fichier_source=excel_file.name,
                    imported_by=getattr(request.user, 'employe', None)
                )

                nb_imported += 1

            except Exception as e:
                errors.append(f'Ligne {row_num}: {str(e)}')

        return JsonResponse({
            'success': True,
            'message': f'{nb_imported} solde(s) importé(s) avec succès',
            'nb_imported': nb_imported,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
