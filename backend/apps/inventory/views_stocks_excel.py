from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from .models import Stock
from apps.organization.models import Base
from apps.planning.models import Designation
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from decimal import Decimal
import json


@login_required
def export_stocks_excel(request):
    """Exporter les stocks en Excel"""
    from .views import _filter_stocks_by_scope
    wb = Workbook()
    ws = wb.active
    ws.title = "Stocks"

    # En-têtes
    headers = [
        'ID Stock', 'ID Désignation', 'Nom Désignation', 
        'ID Magasin', 'Nom Magasin', 
        'ID Base', 'Nom Base',
        'Date Inventaire', 'Rapproché', 'ID Utilisateur', 'Surnom Utilisateur',
        'Stock Actuel', 'Stock Réservé', 'Stock Disponible', 'Unité'
    ]
    ws.append(headers)

    # Style des en-têtes
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Récupérer les stocks
    from apps.organization.models import Magasin
    from .models import FicheStock
    from decimal import Decimal
    from types import SimpleNamespace
    import re
    from .views import _filter_bases_by_scope

    scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)
    scoped_magasins = Magasin.objects.select_related('base').filter(base_id__in=scoped_bases.values('id'))
    
    stocks = _filter_stocks_by_scope(
        Stock.objects.select_related('designation', 'base', 'utilisateur'),
        request.user
    )

    stock_lookup = {}
    for stock in stocks:
        if stock.designation_id:
            stock_lookup[(str(stock.base_id), str(stock.designation_id))] = stock

    magasins_by_id = {str(m.id): m for m in scoped_magasins}
    magasins_by_name = {
        (m.nom_magasin or '').strip().lower(): m
        for m in scoped_magasins
        if m.nom_magasin
    }
    magasin_id_pattern = re.compile(
        r'Magasin ID\s*:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
    )
    magasin_name_pattern = re.compile(r'Magasin\s*:\s*([^|]+)')

    def _extract_magasin_from_notes(notes_value):
        if not notes_value:
            return '', 'Non ventilé (base)'
        notes_text = str(notes_value)
        magasin_id_match = magasin_id_pattern.search(notes_text)
        if magasin_id_match:
            magasin_id_value = magasin_id_match.group(1)
            magasin_obj = magasins_by_id.get(magasin_id_value)
            if magasin_obj:
                return magasin_id_value, magasin_obj.nom_magasin
            return magasin_id_value, 'Non ventilé (base)'
        magasin_name_match = magasin_name_pattern.search(notes_text)
        if magasin_name_match:
            magasin_label = magasin_name_match.group(1).strip()
            magasin_obj = magasins_by_name.get(magasin_label.lower())
            if magasin_obj:
                return str(magasin_obj.id), magasin_obj.nom_magasin
            return '', magasin_label or 'Non ventilé (base)'
        return '', 'Non ventilé (base)'

    inventaires_qs = FicheStock.objects.filter(
        operation_type='inventaire',
        designation__isnull=False,
        base_id__in=scoped_bases.values('id')
    ).select_related('designation', 'base', 'employee')

    latest_inventaires = {}
    for fiche in inventaires_qs.order_by('-operation_date', '-created_at'):
        if not fiche.designation_id:
            continue
        magasin_uuid, magasin_label = _extract_magasin_from_notes(fiche.notes or '')
        key = (str(fiche.base_id), str(fiche.designation_id), magasin_uuid or magasin_label)
        if key in latest_inventaires:
            continue
        latest_inventaires[key] = (fiche, magasin_uuid, magasin_label)

    projected_stocks = []
    
    for fiche, magasin_uuid, magasin_label in latest_inventaires.values():
        qty = Decimal(str(fiche.quantity or 0))
        base_stock = stock_lookup.get((str(fiche.base_id), str(fiche.designation_id)))
        
        projected_stocks.append(SimpleNamespace(
            id=str(base_stock.id) if base_stock else '',
            designation=fiche.designation,
            base=fiche.base,
            base_id=fiche.base_id,
            magasin_nom=magasin_label or 'Non ventilé (base)',
            magasin_id=magasin_uuid or '',
            current_quantity=qty,
            reserved_quantity=Decimal('0'),
            available_quantity=qty,
            inventory_date=fiche.operation_date.date() if fiche.operation_date else None,
            rapproche=True,
            utilisateur=fiche.employee if fiche.employee else (base_stock.utilisateur if base_stock else None),
        ))

    # Ajouter les stocks qui n'ont pas d'inventaire
    for stock in stocks:
        if not stock.inventory_date:
            continue
        if any(p.base_id == stock.base_id and getattr(p.designation, 'id', None) == stock.designation_id for p in projected_stocks):
            continue
            
        projected_stocks.append(SimpleNamespace(
            id=str(stock.id),
            designation=stock.designation,
            base=stock.base,
            base_id=stock.base_id,
            magasin_nom='Non ventilé (base)',
            magasin_id='',
            current_quantity=Decimal(str(stock.current_quantity or 0)),
            reserved_quantity=Decimal(str(stock.reserved_quantity or 0)),
            available_quantity=Decimal(str(stock.available_quantity or 0)),
            inventory_date=stock.inventory_date,
            rapproche=bool(stock.rapproche),
            utilisateur=stock.utilisateur,
        ))

    projected_stocks.sort(
        key=lambda s: (
            (s.base.nom_base or '').lower() if s.base else '',
            (s.magasin_nom or '').lower(),
            (s.designation.nom or '').lower() if getattr(s, 'designation', None) else ''
        )
    )

    for stock in projected_stocks:
        ws.append([
            stock.id,
            str(stock.designation.id) if stock.designation else '',
            stock.designation.nom if stock.designation else '',
            stock.magasin_id,
            stock.magasin_nom,
            str(stock.base.id) if stock.base else '',
            stock.base.nom_base if stock.base else '',
            stock.inventory_date.strftime('%d/%m/%Y') if stock.inventory_date else '',
            'Oui' if stock.rapproche else 'Non',
            str(stock.utilisateur.id) if stock.utilisateur else '',
            stock.utilisateur.surnom if stock.utilisateur else '',
            float(stock.current_quantity),
            float(stock.reserved_quantity),
            float(stock.available_quantity),
            stock.designation.unite if stock.designation else ''
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

    # Retourner le fichier
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=stocks_export.xlsx'
    wb.save(response)

    return response


@login_required
def template_stocks_excel(request):
    from .views import _filter_bases_by_scope, _filter_employes_by_scope
    """Générer un template Excel pour l'import de stocks"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Template Stocks"

    # En-têtes avec instructions
    headers = [
        'ID Stock (laisser vide pour création)*', 'ID Désignation (UUID)*', 'ID Magasin (UUID)* - voir feuille Magasins',
        'Date Inventaire (DD/MM/YYYY)', 'Rapproché (Oui/Non)', 'ID Utilisateur (UUID)',
        'Stock Actuel*', 'Stock Réservé', 'Notes'
    ]
    ws.append(headers)

    # Style des en-têtes
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Exemples avec des IDs réels
    from datetime import date
    from apps.employees.models import Employe
    first_designation = Designation.objects.first()
    first_base = _filter_bases_by_scope(Base.objects.all(), request.user).first()
    first_employe = _filter_employes_by_scope(
        Employe.objects.filter(date_debauchage__isnull=True),
        request.user
    ).first()

    if first_designation and first_base:
        ws.append([
            '',  # Laisser vide pour création
            str(first_designation.id),
            str(first_base.id),
            date.today().strftime('%d/%m/%Y'),
            'Non',
            str(first_employe.id) if first_employe else '',
            100,
            0,
            'Stock initial'
        ])

    # Instructions
    ws.append([])
    ws.append(['INSTRUCTIONS:'])
    ws.append(['- Les colonnes marquées * sont obligatoires'])
    ws.append(['- ID Stock: Laisser vide pour créer un nouveau stock, remplir pour mise à jour'])
    ws.append(['- Date Inventaire: Format DD/MM/YYYY (optionnel)'])
    ws.append(['- Rapproché: Oui ou Non (optionnel, Non par défaut)'])
    ws.append(['- ID Utilisateur: UUID de l\'employé responsable (optionnel)'])
    ws.append(['- Stock Réservé: Optionnel, 0 par défaut'])
    ws.append(['- Stock Disponible sera calculé automatiquement (Actuel - Réservé)'])
    ws.append(['- Copiez les ID depuis les feuilles de référence ci-dessous'])
    ws.append([])

    # Feuille de référence - Désignations
    ws_designations = wb.create_sheet("Désignations")
    ws_designations.append(['ID Désignation', 'Nom', 'Unité'])
    designations = Designation.objects.order_by('nom')[:500]
    for designation in designations:
        ws_designations.append([
            str(designation.id),
            designation.nom,
            designation.unite or ''
        ])

    # Feuille de référence - Magasins
    from apps.organization.models import Magasin
    ws_magasins = wb.create_sheet("Magasins")
    ws_magasins.append(['ID Magasin', 'Nom Magasin', 'Base'])
    scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)
    magasins = Magasin.objects.select_related('base').filter(
        base_id__in=scoped_bases.values('id')
    ).order_by('nom_magasin')
    for magasin in magasins:
        ws_magasins.append([
            str(magasin.id),
            magasin.nom_magasin,
            magasin.base.nom_base
        ])

    # Feuille de référence - Employés
    ws_employes = wb.create_sheet("Employés")
    ws_employes.append(['ID Employé', 'Surnom', 'Nom Complet'])
    employes = _filter_employes_by_scope(
        Employe.objects.filter(date_debauchage__isnull=True),
        request.user
    ).order_by('surnom')
    for employe in employes:
        ws_employes.append([
            str(employe.id),
            employe.surnom or '',
            employe.nom_employe
        ])

    # Retourner le fichier
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=template_stocks.xlsx'
    wb.save(response)

    return response


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def import_stocks_excel(request):
    """Importer des stocks depuis Excel"""
    from .views import _filter_bases_by_scope, _filter_employes_by_scope, _filter_stocks_by_scope
    from .models import FicheStock
    from apps.organization.models import Magasin
    from apps.employees.models import Employe
    from django.utils import timezone
    if request.method == 'POST':
        fichier = request.FILES.get('fichier') or request.FILES.get('file')
        if not fichier:
            return JsonResponse({'success': False, 'error': 'Aucun fichier fourni'}, status=400)
        try:
            wb = load_workbook(fichier)
            ws = wb.active

            count = 0
            errors = []

            from datetime import datetime, time

            def parse_date(date_value):
                """Parse date in DD/MM/YYYY or YYYY-MM-DD format"""
                if not date_value:
                    return None
                if isinstance(date_value, datetime):
                    return date_value.date()
                try:
                    return datetime.strptime(str(date_value).strip(), '%d/%m/%Y').date()
                except:
                    try:
                        return datetime.strptime(str(date_value).strip(), '%Y-%m-%d').date()
                    except:
                        return None

            scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)
            scoped_magasins = Magasin.objects.select_related('base').filter(
                base_id__in=scoped_bases.values('id')
            )
            scoped_employes = _filter_employes_by_scope(Employe.objects.all(), request.user)

            for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row[1]:  # Pas d'ID Désignation
                    continue

                try:
                    with transaction.atomic():
                        # ID Stock (colonne 0) - optionnel
                        stock_id = str(row[0]).strip() if row[0] else None

                        # ID Désignation (colonne 1) - obligatoire
                        try:
                            designation = Designation.objects.get(id=str(row[1]).strip())
                        except Designation.DoesNotExist:
                            errors.append(f"Ligne {idx}: Désignation introuvable ({row[1]})")
                            continue

                        # ID Magasin (colonne 2) - obligatoire
                        try:
                            magasin_id = str(row[2]).strip()
                            # Récupérer le magasin et sa base associée
                            magasin = scoped_magasins.get(id=magasin_id)
                            base = magasin.base
                        except Magasin.DoesNotExist:
                            # Suggérer les premiers magasins valides
                            suggestions = ', '.join([f"{m.nom_magasin} - {m.base.nom_base} ({str(m.id)[:8]}...)" for m in scoped_magasins[:3]])
                            errors.append(f"Ligne {idx}: Magasin introuvable. ID fourni: '{magasin_id}'. Magasins disponibles: {suggestions}. Vérifiez la feuille 'Magasins' du template.")
                            continue

                        # Date inventaire (colonne 3) - optionnel
                        # Si absente, utiliser la date du jour.
                        inventory_date = parse_date(row[3]) if row[3] else timezone.localdate()

                        # Rapproché (colonne 4) - optionnel
                        rapproche_value = str(row[4]).strip().lower() if row[4] else 'non'
                        rapproche = rapproche_value in ['oui', 'yes', 'true', '1']

                        # ID Utilisateur (colonne 5) - optionnel
                        utilisateur = None
                        if row[5]:
                            try:
                                utilisateur = scoped_employes.get(id=str(row[5]).strip())
                            except Employe.DoesNotExist:
                                pass  # Ignorer si employé introuvable

                        # Stock actuel (colonne 6) - obligatoire
                        try:
                            current_quantity = Decimal(str(row[6]))
                        except (ValueError, TypeError):
                            errors.append(f"Ligne {idx}: Stock actuel invalide")
                            continue

                        # Stock réservé (colonne 7) - optionnel
                        try:
                            reserved_quantity = Decimal(str(row[7])) if row[7] else Decimal('0')
                        except (ValueError, TypeError):
                            reserved_quantity = Decimal('0')

                        # Mise à jour ou création
                        if stock_id:
                            try:
                                stock = _filter_stocks_by_scope(Stock.objects.all(), request.user).get(id=stock_id)
                                stock.current_quantity = current_quantity
                                stock.reserved_quantity = reserved_quantity
                                stock.inventory_date = inventory_date
                                stock.rapproche = rapproche
                                stock.utilisateur = utilisateur
                                stock.save()
                            except Stock.DoesNotExist:
                                errors.append(f"Ligne {idx}: Stock introuvable ({stock_id})")
                                continue
                        else:
                            # Vérifier si un stock existe déjà pour cette désignation/magasin
                            stock, created = Stock.objects.get_or_create(
                                designation=designation,
                                base=base,
                                defaults={
                                    'current_quantity': current_quantity,
                                    'reserved_quantity': reserved_quantity,
                                    'inventory_date': inventory_date,
                                    'rapproche': rapproche,
                                    'utilisateur': utilisateur
                                }
                            )
                            if not created:
                                stock.current_quantity = current_quantity
                                stock.reserved_quantity = reserved_quantity
                                stock.inventory_date = inventory_date
                                stock.rapproche = rapproche
                                stock.utilisateur = utilisateur
                                stock.save()

                        # Create/update inventory movement for selected magasin so
                        # magasin-filtered stock view can recalculate correctly.
                        operation_date = timezone.now()
                        if inventory_date:
                            parsed_naive = datetime.combine(inventory_date, time(23, 59, 59))
                            operation_date = timezone.make_aware(parsed_naive, timezone.get_current_timezone())

                        notes_source = str(row[8]).strip() if len(row) > 8 and row[8] else 'Inventaire importe via Excel'
                        notes_value = f"{notes_source} | Magasin ID: {magasin.id} | Magasin: {magasin.nom_magasin}"

                        employee_for_fiche = utilisateur
                        if not employee_for_fiche and hasattr(request.user, 'employe'):
                            employee_for_fiche = request.user.employe

                        fiche = FicheStock.objects.filter(
                            operation_type='inventaire',
                            designation=designation,
                            base=base,
                            operation_date=operation_date
                        ).filter(
                            notes__icontains=f"Magasin ID: {magasin.id}"
                        ).first()

                        if fiche:
                            fiche.quantity = current_quantity
                            fiche.employee = employee_for_fiche
                            fiche.reference = 'IMPORT_EXCEL_STOCK'
                            fiche.notes = notes_value
                            fiche.save()
                        else:
                            FicheStock.objects.create(
                                operation_date=operation_date,
                                operation_type='inventaire',
                                quantity=current_quantity,
                                designation=designation,
                                base=base,
                                employee=employee_for_fiche,
                                reference='IMPORT_EXCEL_STOCK',
                                notes=notes_value
                            )

                        count += 1

                except Exception as e:
                    errors.append(f"Ligne {idx}: {str(e)}")

            if errors:
                return JsonResponse({
                    'success': True,
                    'nb_imported': count,
                    'errors': errors[:20]  # Limiter à 20 erreurs
                })

            return JsonResponse({
                'success': True,
                'nb_imported': count,
                'message': f'{count} stock(s) importé(s) avec succès'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)

    return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)
