import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Contrat, Employe, GrilleSalaire, Poste
from .models_grille_template import GrilleSalarialeTemplate
from .models_revalorisation import GrilleSalariale


# ============================================================
# API TEMPLATES DE GRILLES SALARIALES
# ============================================================

@login_required
def api_templates_list(request):
    """API pour lister tous les templates disponibles."""
    templates = _scoped_templates(request)
    data = []
    for template in templates:
        data.append({
            'id': str(template.id),
            'nom_template': template.nom_template,
            'description': template.description or '',
            'organisation_id': str(template.organisation.id) if template.organisation else None,
            'organisation_nom': template.organisation.nom_organisation if template.organisation else None,
            'anciennete_min': float(template.anciennete_min),
            'anciennete_max': float(template.anciennete_max),
            'fourchette_basse': float(template.fourchette_basse),
            'fourchette_haute': float(template.fourchette_haute) if template.fourchette_haute else None,
            'mode_fourchette_haute': template.mode_fourchette_haute,
            'mode_fourchette_haute_display': template.get_mode_fourchette_haute_display(),
            'date_debut_validite': template.date_debut_validite.isoformat() if template.date_debut_validite else None,
            'date_fin_validite': template.date_fin_validite.isoformat() if template.date_fin_validite else None,
        })
    return JsonResponse({'templates': data})


@login_required
def api_templates_create(request):
    """API pour créer un nouveau template de grille salariale."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)
    
    try:
        data = json.loads(request.body)
        
        # Validation des champs obligatoires
        required_fields = ['nom_template', 'anciennete_min', 'anciennete_max', 
                          'fourchette_basse', 'date_debut_validite']
        for field in required_fields:
            if field not in data or not data[field]:
                return JsonResponse({
                    'success': False, 
                    'error': f'Le champ {field} est obligatoire.'
                }, status=400)
        
        # Récupérer l'organisation
        organisation = _get_request_organisation(request)
        if not organisation and not getattr(request.user, 'is_superuser', False):
            return JsonResponse({
                'success': False, 
                'error': 'Aucune organisation associée à votre compte.'
            }, status=400)
        
        # Créer le template avec normalisation des choix en minuscules
        template = GrilleSalarialeTemplate.objects.create(
            nom_template=data['nom_template'],
            description=data.get('description', ''),
            organisation=organisation,
            anciennete_min=Decimal(str(data['anciennete_min'])),
            anciennete_max=Decimal(str(data['anciennete_max'])),
            fourchette_basse=Decimal(str(data['fourchette_basse'])),
            fourchette_haute=Decimal(str(data['fourchette_haute'])) if data.get('fourchette_haute') else None,
            mode_fourchette_haute=_normalize_choice_value(GrilleSalarialeTemplate.MODE_FOURCHETTE_HAUTE_CHOICES, data.get('mode_fourchette_haute'), default='fixe'),
            fourchette_haute_reference=Decimal(str(data['fourchette_haute_reference'])) if data.get('fourchette_haute_reference') else None,
            anciennete_reference_haute=Decimal(str(data['anciennete_reference_haute'])) if data.get('anciennete_reference_haute') else None,
            ratio_annuel_haute=Decimal(str(data['ratio_annuel_haute'])) if data.get('ratio_annuel_haute') else None,
            mode_ratio_haute=_normalize_choice_value(GrilleSalarialeTemplate.MODE_RATIO_HAUTE_CHOICES, data.get('mode_ratio_haute'), default='compose'),
            date_debut_validite=_parse_date(data['date_debut_validite']),
            date_fin_validite=_parse_date(data.get('date_fin_validite'))
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Template créé avec succès.',
            'template': {
                'id': str(template.id),
                'nom_template': template.nom_template,
            }
        })
        
    except Exception as exc:
        return JsonResponse({
            'success': False, 
            'error': str(exc)
        }, status=500)


def _get_request_organisation(request):
    employe_auth = getattr(request.user, 'employe', None)
    if not employe_auth or not getattr(employe_auth, 'base', None):
        return None
    return employe_auth.base.organisation


def _scoped_postes(request):
    queryset = Poste.objects.select_related('organisation').all()
    if getattr(request.user, 'is_superuser', False):
        return queryset

    organisation = _get_request_organisation(request)
    if organisation is None:
        return queryset.none()
    return queryset.filter(organisation=organisation)


def _scoped_grilles(request):
    queryset = GrilleSalariale.objects.select_related('poste__organisation', 'organisation').all()
    if getattr(request.user, 'is_superuser', False):
        return queryset

    organisation = _get_request_organisation(request)
    if organisation is None:
        return queryset.none()
    return queryset.filter(
        models.Q(organisation=organisation) |
        models.Q(organisation__isnull=True, poste__organisation=organisation)
    )


def _scoped_templates(request):
    queryset = GrilleSalarialeTemplate.objects.select_related('organisation').all()
    if getattr(request.user, 'is_superuser', False):
        return queryset

    organisation = _get_request_organisation(request)
    if organisation is None:
        return queryset.none()
    return queryset.filter(
        models.Q(organisation=organisation) |
        models.Q(organisation__isnull=True)
    )


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _excel_headers():
    return [
        ('id', 'ID'),
        ('niveau_display', 'Niveau'),
        ('poste_id', 'Poste ID'),
        ('poste_nom', 'Poste'),
        ('template_id', 'Template ID'),
        ('template_nom', 'Template'),
        ('organisation_nom', 'Organisation'),
        ('anciennete_min', 'Anciennete minimum'),
        ('anciennete_max', 'Anciennete maximum'),
        ('fourchette_basse', 'Fourchette basse nette (Ar)'),
        ('fourchette_haute', 'Fourchette haute nette (Ar)'),
        ('mode_fourchette_haute', 'Mode fourchette haute'),
        ('fourchette_haute_reference', 'Reference haute nette (Ar)'),
        ('anciennete_reference_haute', 'Anciennete reference haute'),
        ('ratio_annuel_haute', 'Ratio annuel haute (%)'),
        ('mode_ratio_haute', 'Type ratio haute'),
        ('fourchette_haute_resume', 'Resume fourchette haute'),
        ('date_debut_validite', 'Date debut validite'),
        ('date_fin_validite', 'Date fin validite'),
        ('est_active', 'Active'),
    ]


def _format_decimal_display(value):
    if value in (None, ''):
        return ''
    decimal_value = Decimal(str(value))
    normalized = format(decimal_value.normalize(), 'f')
    if '.' in normalized:
        normalized = normalized.rstrip('0').rstrip('.')
    return normalized or '0'


def _parse_decimal_input(value, allow_empty=False):
    if value in (None, ''):
        if allow_empty:
            return None
        raise ValidationError("Cette valeur numerique est obligatoire.")

    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    value_str = str(value).strip().replace('\xa0', '').replace(' ', '')
    if value_str == '':
        if allow_empty:
            return None
        raise ValidationError("Cette valeur numerique est obligatoire.")

    if ',' in value_str and '.' in value_str:
        value_str = value_str.replace('.', '').replace(',', '.')
    else:
        value_str = value_str.replace(',', '.')

    try:
        return Decimal(value_str)
    except (InvalidOperation, ValueError):
        raise ValidationError(f"Valeur numerique invalide: {value}")


def _write_excel_headers(ws):
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='1D4ED8', end_color='1D4ED8', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center')

    for col_num, (_, label) in enumerate(_excel_headers(), 1):
        cell = ws.cell(row=1, column=col_num, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment


def _autosize_worksheet(ws):
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                max_length = max(max_length, len(str(cell.value or '')))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 40)


def _build_postes_sheet(wb, request):
    ws = wb.create_sheet('Postes')
    headers = ['Poste ID', 'Poste', 'Organisation']
    for idx, label in enumerate(headers, 1):
        ws.cell(row=1, column=idx, value=label)

    row_num = 2
    for poste in _scoped_postes(request).order_by('organisation__nom_organisation', 'ordre_affichage', 'nom_poste'):
        ws.cell(row=row_num, column=1, value=str(poste.id))
        ws.cell(row=row_num, column=2, value=poste.nom_poste)
        ws.cell(row=row_num, column=3, value=poste.organisation.nom_organisation if poste.organisation else '')
        row_num += 1

    _autosize_worksheet(ws)


def _build_templates_sheet(wb, request):
    ws = wb.create_sheet('Templates')
    headers = [
        'Template ID',
        'Template',
        'Organisation',
        'Anciennete minimum',
        'Anciennete maximum',
        'Mode fourchette haute',
        'Date debut validite',
        'Date fin validite',
    ]
    for idx, label in enumerate(headers, 1):
        ws.cell(row=1, column=idx, value=label)

    row_num = 2
    templates = _scoped_templates(request).order_by(
        'organisation__nom_organisation',
        'nom_template',
        'anciennete_min',
        '-date_debut_validite',
    )
    for template in templates:
        ws.cell(row=row_num, column=1, value=str(template.id))
        ws.cell(row=row_num, column=2, value=template.nom_template)
        ws.cell(
            row=row_num,
            column=3,
            value=template.organisation.nom_organisation if template.organisation else '',
        )
        ws.cell(row=row_num, column=4, value=float(template.anciennete_min))
        ws.cell(row=row_num, column=5, value=float(template.anciennete_max))
        ws.cell(
            row=row_num,
            column=6,
            value=_choice_label(
                GrilleSalarialeTemplate.MODE_FOURCHETTE_HAUTE_CHOICES,
                template.mode_fourchette_haute,
            ),
        )
        ws.cell(
            row=row_num,
            column=7,
            value=template.date_debut_validite.isoformat() if template.date_debut_validite else '',
        )
        ws.cell(
            row=row_num,
            column=8,
            value=template.date_fin_validite.isoformat() if template.date_fin_validite else '',
        )
        row_num += 1

    _autosize_worksheet(ws)


def _build_instructions_sheet(wb):
    ws = wb.create_sheet('Instructions')
    lines = [
        'IMPORT GRILLES SALARIALES',
        '',
        '1. Remplir ou modifier uniquement la feuille "Grilles salariales".',
        '2. L import accepte en priorite la colonne "Poste ID".',
        '3. La colonne "Template ID" est prioritaire sur "Template" pour lier un modele reutilisable.',
        '4. Si un template est renseigne, les parametres de fourchette sont herites du template.',
        '5. La colonne "ID" permet de mettre a jour une ligne existante.',
        '6. Sans "ID", une nouvelle grille sera creee.',
        '7. Les fourchettes attendues sont des salaires nets estimes.',
        '8. Pour une fourchette haute fixe, remplir "Fourchette haute nette (Ar)".',
        '9. Pour une fourchette haute dynamique, remplir le mode, la reference nette, l anciennete de reference et le ratio annuel.',
        '10. Le brut correspondant est recalcule automatiquement en base.',
        '11. Les dates peuvent etre au format YYYY-MM-DD ou DD/MM/YYYY.',
        '12. Si une ligne est invalide, tout l import est annule.',
        '13. Les anciennetes decimales sont acceptees: 0,5 et 0.5 sont equivalents.',
        '14. Les bornes adjacentes sont autorisees: 0-0,5 puis 0,5-1 ne se chevauchent pas.',
        '15. Sur une borne exacte, la tranche dont l anciennete minimum correspond a la borne est privilegiee.',
        '16. En cas de conflit, le message indique la ligne Excel concernee.',
        '17. Colonne "Niveau" : "Junior (non autonome)" ou "Confirme (par anciennete)" (vide = Confirme).',
        '18. Une ligne Junior ignore template et anciennetes : une seule fourchette fixe par poste et periode.',
    ]
    for idx, line in enumerate(lines, 1):
        ws.cell(row=idx, column=1, value=line)
    ws.column_dimensions['A'].width = 100


def _validation_error_message(exc):
    if hasattr(exc, 'message_dict'):
        messages = []
        for field, field_messages in exc.message_dict.items():
            prefix = field.replace('_', ' ').capitalize()
            for message in field_messages:
                messages.append(f"{prefix}: {message}")
        return " ".join(messages)

    if hasattr(exc, 'messages'):
        return " ".join(exc.messages)

    return str(exc)


def _resolve_poste_from_row(request, row_data):
    poste_id = row_data.get('poste_id')
    if poste_id:
        poste = _scoped_postes(request).filter(id=str(poste_id).strip()).first()
        if poste is None:
            raise ValidationError(f"Poste introuvable: {poste_id}")
        return poste

    poste_nom = str(row_data.get('poste_nom') or '').strip()
    if not poste_nom:
        raise ValidationError("Le poste est obligatoire.")

    queryset = _scoped_postes(request).filter(nom_poste__iexact=poste_nom)
    count = queryset.count()
    if count == 0:
        raise ValidationError(f"Poste introuvable: {poste_nom}")
    if count > 1:
        raise ValidationError(f"Plusieurs postes correspondent a: {poste_nom}. Utilisez Poste ID.")
    return queryset.first()


def _resolve_template_from_row(request, row_data):
    template_id = row_data.get('template_id')
    if template_id not in (None, ''):
        template = _scoped_templates(request).filter(id=str(template_id).strip()).first()
        if template is None:
            raise ValidationError(f"Template introuvable: {template_id}")
        return template

    template_nom = str(row_data.get('template_nom') or '').strip()
    if not template_nom:
        return None

    queryset = _scoped_templates(request).filter(nom_template__iexact=template_nom)
    count = queryset.count()
    if count == 0:
        raise ValidationError(f"Template introuvable: {template_nom}")
    if count > 1:
        raise ValidationError(f"Plusieurs templates correspondent a: {template_nom}. Utilisez Template ID.")
    return queryset.first()


def _build_reference_preview_instance(poste):
    employe_fictif = Employe(poste=poste, personnes_charge=0)
    contrat_reference = Contrat(
        employe=employe_fictif,
        poste=poste,
        type_contrat='temps_plein',
        debut_contrat=timezone.now().date(),
        salaire_brut_base=Decimal('0.00'),
    )
    reference_label = "Reference standard: temps plein, 0 personne a charge"

    preview = GrilleSalaire(
        contrat=contrat_reference,
        date_salaire=timezone.now().date(),
        personnes_charge=0,
        nb_jours_presence=0,
        est_prorata=False,
        nb_jours_feries_gardien=0,
        nb_heures_remplacement_gardien=Decimal('0.00'),
        salaire_brut_base=Decimal('0.00'),
    )
    return preview, reference_label


def _build_net_preview_for_poste(poste, salaire_brut):
    preview, reference_label = _build_reference_preview_instance(poste)
    preview.salaire_brut_base = Decimal(str(salaire_brut or 0))
    preview.calculer_tous_les_champs()
    return preview, reference_label


def _build_gross_preview_for_poste(poste, salaire_net):
    preview, reference_label = _build_reference_preview_instance(poste)
    preview.salaire_brut_base = preview.calculer_salaire_brut_depuis_net(Decimal(str(salaire_net or 0)))
    preview.calculer_tous_les_champs()
    return preview, reference_label


def _choice_label(choices, value):
    for key, label in choices:
        if key == value:
            return label
    return value


def _normalize_choice_value(choices, value, default=None):
    if value in (None, ''):
        return default

    value_str = str(value).strip()
    for key, label in choices:
        if value_str == key or value_str.lower() == str(label).lower():
            return key
    return value_str


def _format_ratio_percent(value):
    if value in (None, ''):
        return ''
    decimal_value = _parse_decimal_input(value)
    return f"{decimal_value.quantize(Decimal('0.01'))}%"


def _anciennete_ranges_overlap(min_a, max_a, min_b, max_b):
    return min_a < max_b and min_b < max_a


def _date_ranges_overlap(start_a, end_a, start_b, end_b):
    end_a = end_a or date.max
    end_b = end_b or date.max
    return start_a <= end_b and start_b <= end_a


def _find_database_overlap(grille, exclude_pks=None):
    conflits = GrilleSalariale.objects.filter(poste=grille.poste, niveau=grille.niveau)
    # Une grille Junior est unique par poste et periode : pas de tranche d'anciennete.
    if not grille.est_junior:
        conflits = conflits.filter(
            anciennete_min__lt=grille.anciennete_max,
            anciennete_max__gt=grille.anciennete_min,
        )
    if exclude_pks:
        conflits = conflits.exclude(pk__in=[pk for pk in exclude_pks if pk])
    if grille.pk:
        conflits = conflits.exclude(pk=grille.pk)

    conflits = conflits.filter(
        models.Q(date_fin_validite__isnull=True) | models.Q(date_fin_validite__gte=grille.date_debut_validite)
    )
    if grille.date_fin_validite:
        conflits = conflits.filter(date_debut_validite__lte=grille.date_fin_validite)

    return conflits.order_by('date_debut_validite', 'anciennete_min').first()


def _find_import_overlap(grille, imported_grilles):
    for other_row_number, other_grille in imported_grilles:
        if other_grille.poste_id != grille.poste_id or other_grille.niveau != grille.niveau:
            continue
        if not grille.est_junior and not _anciennete_ranges_overlap(
            other_grille.anciennete_min,
            other_grille.anciennete_max,
            grille.anciennete_min,
            grille.anciennete_max,
        ):
            continue
        if not _date_ranges_overlap(
            other_grille.date_debut_validite,
            other_grille.date_fin_validite,
            grille.date_debut_validite,
            grille.date_fin_validite,
        ):
            continue
        return other_row_number, other_grille
    return None, None


def _validate_no_overlap(grille, exclude_pks=None):
    conflit = _find_database_overlap(grille, exclude_pks=exclude_pks)
    if conflit:
        date_fin = conflit.date_fin_validite.isoformat() if conflit.date_fin_validite else 'indefinie'
        if grille.est_junior:
            raise ValidationError(
                "Une grille Junior existe deja pour ce poste sur une periode de validite qui se chevauche "
                f"({conflit.date_debut_validite.isoformat()} -> {date_fin})."
            )
        raise ValidationError(
            "Une autre grille salariale existe deja en base pour ce poste avec une tranche "
            f"d'anciennete et une periode de validite qui se chevauchent "
            f"({_format_decimal_display(conflit.anciennete_min)}-{_format_decimal_display(conflit.anciennete_max)} ans, "
            f"{conflit.date_debut_validite.isoformat()} -> {date_fin})."
        )


def _serialize_grille(grille):
    organisation = grille.organisation or getattr(grille.poste, 'organisation', None)
    preview_basse, reference_label = _build_net_preview_for_poste(grille.poste, grille.tpl_fourchette_basse)
    is_dynamic = grille.is_fourchette_haute_dynamic

    fourchette_haute_value = None
    fourchette_haute_brut_value = None
    fourchette_haute_min_value = None
    fourchette_haute_max_value = None
    fourchette_haute_brut_min = None
    fourchette_haute_brut_max = None
    fourchette_haute_reference = None
    fourchette_haute_reference_brut = None
    fourchette_haute_resume = ''

    if is_dynamic:
        high_min_brut = grille.get_fourchette_haute_for_anciennete(grille.anciennete_min)
        high_max_brut = grille.get_fourchette_haute_for_anciennete(grille.anciennete_max)
        preview_haute_min, _ = _build_net_preview_for_poste(grille.poste, high_min_brut)
        preview_haute_max, _ = _build_net_preview_for_poste(grille.poste, high_max_brut)
        fourchette_haute_min_value = float(preview_haute_min.salaire_net)
        fourchette_haute_max_value = float(preview_haute_max.salaire_net)
        fourchette_haute_brut_min = float(high_min_brut)
        fourchette_haute_brut_max = float(high_max_brut)
        if grille.tpl_fourchette_haute_reference not in (None, ''):
            preview_reference, _ = _build_net_preview_for_poste(grille.poste, grille.tpl_fourchette_haute_reference)
            fourchette_haute_reference = float(preview_reference.salaire_net)
            fourchette_haute_reference_brut = float(grille.tpl_fourchette_haute_reference)
        fourchette_haute_resume = (
            f"Reference {fourchette_haute_reference:,.0f} Ar, "
            f"+{_format_ratio_percent(grille.tpl_ratio_annuel_haute)}/an "
            f"des {_format_decimal_display(grille.tpl_anciennete_reference_haute)} ans "
            f"({_choice_label(GrilleSalariale.MODE_RATIO_HAUTE_CHOICES, grille.tpl_mode_ratio_haute).lower()})"
            if fourchette_haute_reference is not None else
            f"+{_format_ratio_percent(grille.tpl_ratio_annuel_haute)}/an"
        )
    else:
        preview_haute, _ = _build_net_preview_for_poste(grille.poste, grille.tpl_fourchette_haute)
        fourchette_haute_value = float(preview_haute.salaire_net)
        fourchette_haute_brut_value = float(grille.tpl_fourchette_haute)
        fourchette_haute_resume = 'Montant fixe'

    return {
        'id': str(grille.id),
        'niveau': grille.niveau,
        'niveau_display': _choice_label(GrilleSalariale.NIVEAU_CHOICES, grille.niveau),
        'poste_id': str(grille.poste_id) if grille.poste_id else None,
        'poste_nom': grille.poste.nom_poste if grille.poste else 'Sans poste',
        'template_id': str(grille.template_id) if grille.template_id else None,
        'template_nom': grille.template.nom_template if grille.template else '',
        'organisation_id': str(organisation.id) if organisation else None,
        'organisation_nom': organisation.nom_organisation if organisation else 'Sans organisation',
        'anciennete_min': float(grille.anciennete_min),
        'anciennete_max': float(grille.anciennete_max),
        'fourchette_basse': float(preview_basse.salaire_net),
        'fourchette_haute': fourchette_haute_value,
        'fourchette_basse_brut': float(grille.tpl_fourchette_basse),
        'fourchette_haute_brut': fourchette_haute_brut_value,
        'mode_fourchette_haute': grille.tpl_mode_fourchette_haute,
        'mode_fourchette_haute_display': _choice_label(GrilleSalariale.MODE_FOURCHETTE_HAUTE_CHOICES, grille.tpl_mode_fourchette_haute),
        'fourchette_haute_reference': fourchette_haute_reference,
        'fourchette_haute_reference_brut': fourchette_haute_reference_brut,
        'anciennete_reference_haute': float(grille.tpl_anciennete_reference_haute) if grille.tpl_anciennete_reference_haute not in (None, '') else None,
        'ratio_annuel_haute': float(grille.tpl_ratio_annuel_haute) if grille.tpl_ratio_annuel_haute not in (None, '') else None,
        'mode_ratio_haute': grille.tpl_mode_ratio_haute,
        'mode_ratio_haute_display': _choice_label(GrilleSalariale.MODE_RATIO_HAUTE_CHOICES, grille.tpl_mode_ratio_haute),
        'fourchette_haute_min': fourchette_haute_min_value,
        'fourchette_haute_max': fourchette_haute_max_value,
        'fourchette_haute_brut_min': fourchette_haute_brut_min,
        'fourchette_haute_brut_max': fourchette_haute_brut_max,
        'fourchette_haute_resume': fourchette_haute_resume,
        'reference_net_label': reference_label,
        'date_debut_validite': grille.date_debut_validite.isoformat() if grille.date_debut_validite else None,
        'date_fin_validite': grille.date_fin_validite.isoformat() if grille.date_fin_validite else None,
        'est_active': grille.est_active,
    }


def _build_grille_from_payload(request, data, instance=None, validate_overlap=True, exclude_pks=None, poste=None, template=None):
    niveau = _normalize_choice_value(GrilleSalariale.NIVEAU_CHOICES, data.get('niveau'), default=GrilleSalariale.NIVEAU_CONFIRME)
    if niveau not in {choice for choice, _ in GrilleSalariale.NIVEAU_CHOICES}:
        raise ValidationError("Le niveau de grille est invalide.")
    est_junior = niveau == GrilleSalariale.NIVEAU_JUNIOR

    if not poste:
        poste = _resolve_poste_from_row(request, data)
    if est_junior:
        # Grille Junior : pas de template ni de tranche d'anciennete.
        template = None
        data = {**data, 'anciennete_min': 0, 'anciennete_max': 0, 'mode_fourchette_haute': 'fixe'}
    elif not template:
        template = _resolve_template_from_row(request, data)
    date_debut_validite = _parse_date(data.get('date_debut_validite'))
    date_fin_validite = _parse_date(data.get('date_fin_validite'))

    if template and template.organisation_id and poste.organisation_id != template.organisation_id:
        raise ValidationError("Le template selectionne n'appartient pas a la meme organisation que le poste.")

    if template and date_debut_validite is None:
        date_debut_validite = template.date_debut_validite
    if template and data.get('date_fin_validite') in (None, ''):
        date_fin_validite = template.date_fin_validite

    if date_debut_validite is None:
        raise ValidationError("La date de debut de validite est obligatoire.")

    try:
        anciennete_min = _parse_decimal_input(
            template.anciennete_min if template and data.get('anciennete_min') in (None, '') else data.get('anciennete_min')
        )
        anciennete_max = _parse_decimal_input(
            template.anciennete_max if template and data.get('anciennete_max') in (None, '') else data.get('anciennete_max')
        )
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError("Les valeurs numeriques fournies sont invalides.")

    anciennete_min = anciennete_min.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    anciennete_max = anciennete_max.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    grille = instance or GrilleSalariale()
    grille.niveau = niveau
    grille.poste = poste
    grille.organisation = poste.organisation
    grille.template = template
    grille.anciennete_min = anciennete_min
    grille.anciennete_max = anciennete_max
    grille.date_debut_validite = date_debut_validite
    grille.date_fin_validite = date_fin_validite
    grille.personnes_charge = int(data.get('personnes_charge', getattr(getattr(poste, 'employe', None), 'personnes_charge', 0)) or 0)
    grille.nb_jours_presence = int(data.get('nb_jours_presence', 0) or 0)
    grille.est_prorata = str(data.get('est_prorata', '')).lower() in {'1', 'true', 'yes', 'on'}
    grille.nb_jours_feries_gardien = int(data.get('nb_jours_feries_gardien', 0) or 0)
    grille.nb_heures_remplacement_gardien = Decimal(str(data.get('nb_heures_remplacement_gardien', 0) or 0))

    if template:
        grille.fourchette_basse = template.fourchette_basse
        grille.fourchette_haute = template.fourchette_haute
        # Normalisation robuste via _normalize_choice_value (ex: 'Ratio annuel' -> 'ratio_annuel')
        grille.mode_fourchette_haute = _normalize_choice_value(GrilleSalariale.MODE_FOURCHETTE_HAUTE_CHOICES, template.mode_fourchette_haute, default='fixe')
        grille.fourchette_haute_reference = template.fourchette_haute_reference
        grille.anciennete_reference_haute = template.anciennete_reference_haute
        grille.ratio_annuel_haute = template.ratio_annuel_haute
        grille.mode_ratio_haute = _normalize_choice_value(GrilleSalariale.MODE_RATIO_HAUTE_CHOICES, template.mode_ratio_haute, default='compose')
    else:
        try:
            fourchette_basse_net = _parse_decimal_input(data.get('fourchette_basse'))
        except (TypeError, ValueError, ArithmeticError):
            raise ValidationError("La fourchette basse nette est invalide.")

        if fourchette_basse_net <= 0:
            raise ValidationError("La fourchette basse nette doit etre superieure a zero.")

        mode_fourchette_haute = _normalize_choice_value(
            GrilleSalariale.MODE_FOURCHETTE_HAUTE_CHOICES,
            data.get('mode_fourchette_haute'),
            default='fixe',
        )
        if mode_fourchette_haute not in {choice for choice, _ in GrilleSalariale.MODE_FOURCHETTE_HAUTE_CHOICES}:
            raise ValidationError("Le mode de fourchette haute est invalide.")

        preview_basse, _ = _build_gross_preview_for_poste(poste, fourchette_basse_net)
        grille.fourchette_basse = preview_basse.salaire_brut_base.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        grille.mode_fourchette_haute = mode_fourchette_haute

    if not template and mode_fourchette_haute == 'fixe':
        try:
            fourchette_haute_net = _parse_decimal_input(data.get('fourchette_haute'))
        except (TypeError, ValueError, ArithmeticError):
            raise ValidationError("La fourchette haute nette est invalide.")

        if fourchette_haute_net <= 0:
            raise ValidationError("La fourchette haute nette doit etre superieure a zero.")

        preview_haute, _ = _build_gross_preview_for_poste(poste, fourchette_haute_net)
        grille.fourchette_haute = preview_haute.salaire_brut_base.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        grille.fourchette_haute_reference = None
        grille.anciennete_reference_haute = None
        grille.ratio_annuel_haute = None
        grille.mode_ratio_haute = 'compose'
    elif not template:
        try:
            fourchette_haute_reference_net = _parse_decimal_input(data.get('fourchette_haute_reference'))
            anciennete_reference_haute = _parse_decimal_input(data.get('anciennete_reference_haute'))
            ratio_annuel_haute = _parse_decimal_input(data.get('ratio_annuel_haute'))
        except (TypeError, ValueError, ArithmeticError):
            raise ValidationError("Les parametres du ratio annuel de la fourchette haute sont invalides.")

        if fourchette_haute_reference_net <= 0:
            raise ValidationError("La reference haute nette doit etre superieure a zero.")

        mode_ratio_haute = _normalize_choice_value(
            GrilleSalariale.MODE_RATIO_HAUTE_CHOICES,
            data.get('mode_ratio_haute'),
            default='compose',
        )
        if mode_ratio_haute not in {choice for choice, _ in GrilleSalariale.MODE_RATIO_HAUTE_CHOICES}:
            raise ValidationError("Le type de ratio haute est invalide.")

        preview_reference, _ = _build_gross_preview_for_poste(poste, fourchette_haute_reference_net)
        grille.fourchette_haute_reference = preview_reference.salaire_brut_base.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        grille.anciennete_reference_haute = anciennete_reference_haute.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        grille.ratio_annuel_haute = ratio_annuel_haute.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        grille.mode_ratio_haute = mode_ratio_haute
    grille.update_fourchette_haute_cache()

    grille.full_clean()
    if validate_overlap:
        _validate_no_overlap(grille, exclude_pks=exclude_pks)
    return grille


def _parse_import_rows(ws):
    headers = []
    for cell in ws[1]:
        headers.append(str(cell.value or '').strip())

    normalized_headers = {header: index for index, header in enumerate(headers)}
    rows = []
    for row_number, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(value not in (None, '') for value in row):
            continue

        row_data = {
            'id': row[normalized_headers['ID']] if 'ID' in normalized_headers else None,
            'niveau': row[normalized_headers['Niveau']] if 'Niveau' in normalized_headers else None,
            'poste_id': row[normalized_headers['Poste ID']] if 'Poste ID' in normalized_headers else None,
            'poste_nom': row[normalized_headers['Poste']] if 'Poste' in normalized_headers else None,
            'template_id': row[normalized_headers['Template ID']] if 'Template ID' in normalized_headers else None,
            'template_nom': row[normalized_headers['Template']] if 'Template' in normalized_headers else None,
            'anciennete_min': row[normalized_headers['Anciennete minimum']] if 'Anciennete minimum' in normalized_headers else None,
            'anciennete_max': row[normalized_headers['Anciennete maximum']] if 'Anciennete maximum' in normalized_headers else None,
            'fourchette_basse': row[normalized_headers['Fourchette basse nette (Ar)']] if 'Fourchette basse nette (Ar)' in normalized_headers else None,
            'fourchette_haute': row[normalized_headers['Fourchette haute nette (Ar)']] if 'Fourchette haute nette (Ar)' in normalized_headers else None,
            'mode_fourchette_haute': row[normalized_headers['Mode fourchette haute']] if 'Mode fourchette haute' in normalized_headers else None,
            'fourchette_haute_reference': row[normalized_headers['Reference haute nette (Ar)']] if 'Reference haute nette (Ar)' in normalized_headers else None,
            'anciennete_reference_haute': row[normalized_headers['Anciennete reference haute']] if 'Anciennete reference haute' in normalized_headers else None,
            'ratio_annuel_haute': row[normalized_headers['Ratio annuel haute (%)']] if 'Ratio annuel haute (%)' in normalized_headers else None,
            'mode_ratio_haute': row[normalized_headers['Type ratio haute']] if 'Type ratio haute' in normalized_headers else None,
            'date_debut_validite': row[normalized_headers['Date debut validite']] if 'Date debut validite' in normalized_headers else None,
            'date_fin_validite': row[normalized_headers['Date fin validite']] if 'Date fin validite' in normalized_headers else None,
        }
        rows.append((row_number, row_data))
    return rows


@login_required
def grilles_salariales_list(request):
    organisation = _get_request_organisation(request)
    postes = []
    for poste in _scoped_postes(request).order_by('organisation__nom_organisation', 'ordre_affichage', 'nom_poste'):
        postes.append({
            'id': str(poste.id),
            'nom_poste': poste.nom_poste,
            'organisation_id': str(poste.organisation_id) if poste.organisation_id else None,
            'organisation_nom': poste.organisation.nom_organisation if poste.organisation else 'Sans organisation',
        })

    templates = []
    for template in _scoped_templates(request).order_by(
        'organisation__nom_organisation',
        'nom_template',
        'anciennete_min',
        '-date_debut_validite',
    ):
        templates.append({
            'id': str(template.id),
            'nom_template': template.nom_template,
            'organisation_id': str(template.organisation_id) if template.organisation_id else None,
            'organisation_nom': template.organisation.nom_organisation if template.organisation else 'Template global',
            'anciennete_min': float(template.anciennete_min),
            'anciennete_max': float(template.anciennete_max),
            'date_debut_validite': template.date_debut_validite.isoformat() if template.date_debut_validite else None,
            'date_fin_validite': template.date_fin_validite.isoformat() if template.date_fin_validite else None,
            'mode_fourchette_haute': template.mode_fourchette_haute,
            'mode_fourchette_haute_display': _choice_label(
                GrilleSalarialeTemplate.MODE_FOURCHETTE_HAUTE_CHOICES,
                template.mode_fourchette_haute,
            ),
        })

    context = {
        'page_title': 'Grilles Salariales',
        'postes_data': postes,
        'templates_data': templates,
        'today': timezone.now().date().isoformat(),
        'user_organisation_name': organisation.nom_organisation if organisation else None,
        'is_superuser': getattr(request.user, 'is_superuser', False),
        'can_manage': getattr(request.user, 'is_superuser', False) or organisation is not None,
    }
    return render(request, 'employees/grilles_salariales_list.html', context)


@login_required
def api_grilles_salariales_list(request):
    grilles = _scoped_grilles(request).order_by(
        'poste__organisation__nom_organisation',
        'poste__nom_poste',
        'anciennete_min',
        '-date_debut_validite'
    )
    data = [_serialize_grille(grille) for grille in grilles]
    return JsonResponse({'success': True, 'data': data})


@login_required
def api_grilles_salariales_create(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body or '{}')
        
        # Cas special: affectation directe d'un poste a un template (creer toutes les tranches)
        if 'template_id' in data and 'poste_id' in data and len(data.keys()) == 2:
            return _assign_poste_to_template(request, data)
        
        # Cas normal: creation d'une seule grille
        grille = _build_grille_from_payload(request, data)
        grille.save()
        return JsonResponse({
            'success': True,
            'message': 'Grille salariale creee avec succes',
            'grille': _serialize_grille(grille),
        })
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': _validation_error_message(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


def _assign_poste_to_template(request, data):
    """Creer automatiquement toutes les tranches d'anciennete pour un template donne."""
    from django.db import transaction
    from apps.employees.models import FichePoste
    
    print(f"=== DEBUG AFFECTATION ===")
    print(f"Donnees recues: {data}")
    
    template_id = data.get('template_id')
    poste_id = data.get('poste_id')
    
    print(f"template_id: {template_id}")
    print(f"poste_id: {poste_id}")
    
    if not template_id or not poste_id:
        print("ERREUR: Template ID ou Poste ID manquant")
        return JsonResponse({'success': False, 'error': 'Template ID et Poste ID requis'}, status=400)
    
    try:
        # Recuperer LE template selectionne (une tranche specifique)
        print(f"Recherche template avec id={template_id}...")
        template_reference = get_object_or_404(GrilleSalarialeTemplate.objects.all(), id=template_id)
        print(f"Template trouve: {template_reference.nom_template}")
    except Exception as e:
        print(f"ERREUR TEMPLATE: {e}")
        return JsonResponse({'success': False, 'error': f'Template introuvable: {str(e)}'}, status=404)
    
    try:
        print(f"Recherche poste avec id={poste_id}...")

        # Debug: lister tous les IDs de postes disponibles
        all_poste_ids = list(Poste.objects.all().values_list('id', flat=True)[:10])
        print(f"IDs des 10 premiers postes: {all_poste_ids}")

        # Utiliser filter().first() au lieu de get_object_or_404 pour plus de flexibilité
        poste = Poste.objects.filter(id=poste_id).first()
        if not poste:
            # Essayer avec tous les postes sans filtre d'organisation
            poste = Poste.objects.all().filter(id=poste_id).first()

        if poste:
            print(f"Poste trouve: {poste.nom_poste} (ID: {poste.id})")
        else:
            print(f"ERREUR POSTE: Aucun poste trouve avec ID {poste_id}")
            print(f"Type de poste_id: {type(poste_id)}")
            print(f"Recherche brute avec UUID...")

            # Essayer avec uuid.UUID si c'est une string
            import uuid
            try:
                uuid_poste_id = uuid.UUID(poste_id)
                poste = Poste.objects.filter(id=uuid_poste_id).first()
                if poste:
                    print(f"Poste trouve avec UUID: {poste.nom_poste}")
                else:
                    print(f"Toujours pas trouve avec UUID")
            except Exception as uuid_error:
                print(f"Erreur conversion UUID: {uuid_error}")

            return JsonResponse({'success': False, 'error': f'Poste introuvable: ID {poste_id}'}, status=404)
    except Exception as e:
        print(f"ERREUR POSTE: {e}")
        return JsonResponse({'success': False, 'error': f'Poste introuvable: {str(e)}'}, status=404)
    
    # Verifier que l'organisation correspond
    if template_reference.organisation_id and poste.organisation_id:
        if template_reference.organisation_id != poste.organisation_id:
            return JsonResponse({
                'success': False, 
                'error': f"Incompatibilite d'organisation: Le template appartient a {template_reference.organisation.nom if template_reference.organisation else 'N/A'}, le poste appartient a {poste.organisation.nom if poste.organisation else 'N/A'}"
            }, status=400)
    
    # Trouver TOUS les templates avec le meme nom (toutes les tranches d'anciennete)
    all_tranches = GrilleSalarialeTemplate.objects.filter(
        nom_template=template_reference.nom_template
    ).order_by('anciennete_min')
    
    if template_reference.organisation_id:
        all_tranches = all_tranches.filter(organisation_id=template_reference.organisation_id)
    
    # Verifier si des grilles existent deja pour ce combo
    existing_grilles = GrilleSalariale.objects.filter(
        poste=poste,
        template__in=all_tranches
    )
    
    if existing_grilles.exists():
        return JsonResponse({
            'success': False, 
            'error': f'Des grilles existent deja pour ce poste et ce template. Supprimez-les d\'abord ou utilisez un autre template.'
        }, status=400)
    
    # Une seule grille par tranche d'anciennete, meme si le template a ete importe
    # en plusieurs exemplaires (sinon chaque copie produisait une grille en double).
    # Priorite au template selectionne, puis a l'exemplaire le plus recent.
    tranches_uniques = {}
    for template in sorted(
        all_tranches,
        key=lambda t: (t.id != template_reference.id, -t.date_debut_validite.toordinal() if t.date_debut_validite else 0),
    ):
        tranches_uniques.setdefault((template.anciennete_min, template.anciennete_max), template)

    # Créer automatiquement une grille pour chaque tranche d'ancienneté
    created_count = 0
    created_grilles = []

    with transaction.atomic():
        for template in sorted(tranches_uniques.values(), key=lambda t: t.anciennete_min):
            grille_data = {
                'template_id': str(template.id),
                'poste_id': str(poste.id),
                'date_debut_validite': template.date_debut_validite.isoformat() if template.date_debut_validite else None,
                'date_fin_validite': template.date_fin_validite.isoformat() if template.date_fin_validite else None,
            }
            
            # On passe directement les objets poste et template
            # validate_overlap=False car on a vérifié au début qu'aucune grille n'existe pour ce combo
            grille = _build_grille_from_payload(request, grille_data, validate_overlap=False, poste=poste, template=template)
            grille.save()
            created_grilles.append(grille)
            created_count += 1
    
    if created_count == 0:
        return JsonResponse({
            'success': False, 
            'error': 'Aucune tranche n\'a pu etre identifiee pour ce template. Verifiez sa configuration.'
        }, status=400)
    
    return JsonResponse({
        'success': True,
        'message': f'Poste "{poste.nom_poste}" affecte avec succes au template "{template_reference.nom_template}". {created_count} tranche(s) creee(s).',
        'grilles': [_serialize_grille(g) for g in created_grilles],
    })


@login_required
def api_grilles_salariales_update(request, grille_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body or '{}')
        grille = get_object_or_404(_scoped_grilles(request), id=grille_id)
        grille = _build_grille_from_payload(request, data, instance=grille)
        grille.save()
        return JsonResponse({
            'success': True,
            'message': 'Grille salariale mise a jour avec succes',
            'grille': _serialize_grille(grille),
        })
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': _validation_error_message(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_grilles_salariales_delete(request, grille_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    grille = get_object_or_404(_scoped_grilles(request), id=grille_id)
    grille.delete()
    return JsonResponse({
        'success': True,
        'message': 'Grille salariale supprimee avec succes',
    })


@login_required
def export_grilles_salariales_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Grilles salariales'

    _write_excel_headers(ws)

    grilles = _scoped_grilles(request).order_by(
        'poste__organisation__nom_organisation',
        'poste__nom_poste',
        'anciennete_min',
        '-date_debut_validite'
    )

    for row_num, grille in enumerate(grilles, start=2):
        serialized = _serialize_grille(grille)
        for col_num, (key, _) in enumerate(_excel_headers(), 1):
            value = serialized.get(key, '')
            if isinstance(value, bool):
                value = 'Oui' if value else 'Non'
            ws.cell(row=row_num, column=col_num, value=value)

    _autosize_worksheet(ws)
    _build_postes_sheet(wb, request)
    _build_templates_sheet(wb, request)
    _build_instructions_sheet(wb)

    filename = f"grilles_salariales_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
def export_grilles_salariales_template_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Grilles salariales'
    _write_excel_headers(ws)
    _autosize_worksheet(ws)
    _build_postes_sheet(wb, request)
    _build_templates_sheet(wb, request)
    _build_instructions_sheet(wb)

    filename = f"modele_grilles_salariales_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
def import_grilles_salariales_excel(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    excel_file = request.FILES.get('file')
    if not excel_file:
        return JsonResponse({'success': False, 'error': 'Aucun fichier Excel fourni.'}, status=400)

    try:
        workbook = load_workbook(excel_file, data_only=True)
        worksheet = workbook['Grilles salariales'] if 'Grilles salariales' in workbook.sheetnames else workbook.active
        import_rows = _parse_import_rows(worksheet)

        if not import_rows:
            return JsonResponse({'success': False, 'error': 'Le fichier ne contient aucune ligne a importer.'}, status=400)

        created_count = 0
        updated_count = 0

        prepared_grilles = []
        seen_ids = {}
        for row_number, row_data in import_rows:
            try:
                row_data['date_debut_validite'] = _parse_date(row_data.get('date_debut_validite'))
                row_data['date_fin_validite'] = _parse_date(row_data.get('date_fin_validite'))

                grille_id = str(row_data.get('id') or '').strip()
                if grille_id:
                    if grille_id in seen_ids:
                        raise ValidationError(
                            f"L ID {grille_id} est duplique dans le fichier (deja present ligne {seen_ids[grille_id]})."
                        )
                    seen_ids[grille_id] = row_number
                    instance = get_object_or_404(_scoped_grilles(request), id=grille_id)
                    grille = _build_grille_from_payload(
                        request,
                        row_data,
                        instance=instance,
                        validate_overlap=False,
                    )
                    updated_count += 1
                else:
                    grille = _build_grille_from_payload(
                        request,
                        row_data,
                        validate_overlap=False,
                    )
                    created_count += 1

                prepared_grilles.append((row_number, grille))
            except Exception as exc:
                raise ValidationError(f"Ligne {row_number}: {_validation_error_message(exc)}")

        imported_existing_pks = {
            grille.pk for _, grille in prepared_grilles if grille.pk
        }

        validated_grilles = []
        for row_number, grille in prepared_grilles:
            try:
                overlap_row_number, overlap_grille = _find_import_overlap(grille, validated_grilles)
                if overlap_row_number:
                    overlap_end = (
                        overlap_grille.date_fin_validite.isoformat()
                        if overlap_grille.date_fin_validite else 'indefinie'
                    )
                    raise ValidationError(
                        "Cette ligne chevauche une autre ligne du fichier "
                        f"(ligne {overlap_row_number}) pour le poste {grille.poste.nom_poste} "
                        f"avec la tranche {_format_decimal_display(overlap_grille.anciennete_min)}-{_format_decimal_display(overlap_grille.anciennete_max)} ans "
                        f"et la periode {overlap_grille.date_debut_validite.isoformat()} -> {overlap_end}."
                    )

                _validate_no_overlap(grille, exclude_pks=imported_existing_pks)
                validated_grilles.append((row_number, grille))
            except Exception as exc:
                raise ValidationError(f"Ligne {row_number}: {_validation_error_message(exc)}")

        with transaction.atomic():
            for _, grille in validated_grilles:
                grille.save()

        return JsonResponse({
            'success': True,
            'message': f'Import termine: {created_count} creees, {updated_count} mises a jour.',
        })
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': _validation_error_message(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ============================================================
# EXPORT/IMPORT TEMPLATES EXCEL
# ============================================================

@login_required
def export_templates_excel(request):
    """Export Excel des templates de grilles salariales."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Templates'
    
    # En-têtes simples et clairs (sans parenthèses ni abréviations)
    headers = [
        ('id', 'ID'),
        ('nom_template', 'Nom du template'),
        ('description', 'Description'),
        ('organisation', 'Organisation'),
        ('anciennete_min', 'Anciennete min'),
        ('anciennete_max', 'Anciennete max'),
        ('fourchette_basse', 'Fourchette basse'),
        ('fourchette_haute', 'Fourchette haute'),
        ('mode_fourchette_haute', 'Mode fourchette haute'),
        ('fourchette_haute_reference', 'Reference haute'),
        ('anciennete_reference_haute', 'Anciennete reference'),
        ('ratio_annuel_haute', 'Ratio annuel'),
        ('mode_ratio_haute', 'Type ratio'),
        ('date_debut_validite', 'Date debut validite'),
        ('date_fin_validite', 'Date fin validite'),
    ]
    
    # Style des en-têtes
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='1D4ED8', end_color='1D4ED8', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center')
    
    # Écrire les en-têtes
    for col_num, (_, label) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
    
    # Récupérer les templates
    templates = _scoped_templates(request)
    
    # Écrire les données
    for row_num, template in enumerate(templates, start=2):
        ws.cell(row=row_num, column=1, value=str(template.id))
        ws.cell(row=row_num, column=2, value=template.nom_template)
        ws.cell(row=row_num, column=3, value=template.description or '')
        ws.cell(row=row_num, column=4, value=template.organisation.nom if template.organisation else '')
        ws.cell(row=row_num, column=5, value=float(template.anciennete_min))
        ws.cell(row=row_num, column=6, value=float(template.anciennete_max))
        ws.cell(row=row_num, column=7, value=float(template.fourchette_basse))
        ws.cell(row=row_num, column=8, value=float(template.fourchette_haute) if template.fourchette_haute else '')
        ws.cell(row=row_num, column=9, value=template.mode_fourchette_haute)
        ws.cell(row=row_num, column=10, value=float(template.fourchette_haute_reference) if template.fourchette_haute_reference else '')
        ws.cell(row=row_num, column=11, value=float(template.anciennete_reference_haute) if template.anciennete_reference_haute else '')
        ws.cell(row=row_num, column=12, value=float(template.ratio_annuel_haute) if template.ratio_annuel_haute else '')
        ws.cell(row=row_num, column=13, value=template.mode_ratio_haute)
        ws.cell(row=row_num, column=14, value=template.date_debut_validite.isoformat() if template.date_debut_validite else '')
        ws.cell(row=row_num, column=15, value=template.date_fin_validite.isoformat() if template.date_fin_validite else '')
    
    # Ajuster la largeur des colonnes
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Feuille d'instructions
    instructions_ws = wb.create_sheet(title='Instructions')
    instructions_ws.append(['INSTRUCTIONS POUR L\'IMPORT DES TEMPLATES'])
    instructions_ws.append([])
    instructions_ws.append(['Colonnes obligatoires :'])
    instructions_ws.append(['  - Nom du template : Nom complet du template'])
    instructions_ws.append(['  - Anciennete min : Ancienneté minimale en années (ex: 0, 0.5, 1)'])
    instructions_ws.append(['  - Anciennete max : Ancienneté maximale en années (ex: 2, 2.5, 3)'])
    instructions_ws.append(['  - Fourchette basse : Salaire minimum en Ariary'])
    instructions_ws.append(['  - Date debut validite : Format AAAA-MM-JJ (ex: 2025-01-01)'])
    instructions_ws.append([])
    instructions_ws.append(['Colonnes optionnelles :'])
    instructions_ws.append(['  - Description : Description du template'])
    instructions_ws.append(['  - Fourchette haute : Salaire maximum en Ariary'])
    instructions_ws.append(['  - Mode fourchette haute : "fixe" ou "ratio_annuel"'])
    instructions_ws.append(['  - Reference haute, Anciennete reference, Ratio annuel : Si mode=ratio_annuel'])
    instructions_ws.append(['  - Type ratio : "compose" ou "simple"'])
    instructions_ws.append(['  - Date fin validite : Format AAAA-MM-JJ'])
    instructions_ws.append([])
    instructions_ws.append(['Notes importantes :'])
    instructions_ws.append(['  - Laisser la colonne ID vide pour créer un nouveau template'])
    instructions_ws.append(['  - Remplir l\'ID pour mettre à jour un template existant'])
    instructions_ws.append(['  - Toutes les tranches d\'ancienneté doivent être définies pour chaque template'])
    instructions_ws.append(['  - Exemple : 0-0.5, 0.5-1, 1-3, 3-5, 5-7, 7-10, 10-20 ans'])
    
    filename = f"templates_grilles_salariales_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
def import_templates_excel(request):
    """Import de templates de grilles salariales depuis Excel."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    excel_file = request.FILES.get('file')
    if not excel_file:
        return JsonResponse({'success': False, 'error': 'Aucun fichier Excel fourni.'}, status=400)

    try:
        workbook = load_workbook(excel_file, data_only=True)
        worksheet = workbook['Templates'] if 'Templates' in workbook.sheetnames else workbook.active
        
        # Parser les en-têtes
        headers = {}
        for col_idx, cell in enumerate(worksheet[1], start=1):
            if cell.value:
                header_name = str(cell.value).lower().strip()
                headers[header_name] = col_idx
        
        # Vérifier les colonnes obligatoires
        required_columns = ['nom du template', 'anciennete min', 'anciennete max', 'fourchette basse', 'date debut validite']
        missing_columns = []
        for col in required_columns:
            found = False
            for header in headers.keys():
                if col in header:
                    found = True
                    break
            if not found:
                missing_columns.append(col)
        
        if missing_columns:
            return JsonResponse({
                'success': False, 
                'error': f'Colonnes obligatoires manquantes: {", ".join(missing_columns)}'
            }, status=400)

        # Parser les données
        templates_data = []
        for row_idx, row in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
            if all(cell is None for cell in row):
                continue
            
            row_data = {}
            for col_idx, cell in enumerate(row, start=1):
                # Trouver l'en-tête correspondant
                for header_name, header_col in headers.items():
                    if header_col == col_idx:
                        row_data[header_name] = cell
                        break
            
            templates_data.append((row_idx, row_data))

        if not templates_data:
            return JsonResponse({'success': False, 'error': 'Le fichier ne contient aucune ligne a importer.'}, status=400)

        created_count = 0
        updated_count = 0
        organisation = _get_request_organisation(request)

        for row_number, row_data in templates_data:
            try:
                # Helper pour récupérer une valeur par mot-clé partiel
                def get_value(*keywords):
                    for key, value in row_data.items():
                        for keyword in keywords:
                            if keyword.lower() in key.lower():
                                return value
                    return None

                # Validation des champs obligatoires
                nom_template = get_value('nom du template', 'nom template')
                if not nom_template or str(nom_template).strip() == '':
                    raise ValidationError(f"Ligne {row_number}: Nom du template obligatoire.")
                nom_template = str(nom_template).strip()

                anciennete_min = get_value('anciennete min', 'ancienneté min')
                anciennete_max = get_value('anciennete max', 'ancienneté max')
                fourchette_basse = get_value('fourchette basse')
                date_debut_validite = get_value('date debut', 'debut validite')

                if anciennete_min is None or anciennete_max is None or fourchette_basse is None or date_debut_validite is None:
                    missing = []
                    if anciennete_min is None: missing.append('Anciennete min')
                    if anciennete_max is None: missing.append('Anciennete max')
                    if fourchette_basse is None: missing.append('Fourchette basse')
                    if date_debut_validite is None: missing.append('Date debut validite')
                    raise ValidationError(f"Ligne {row_number}: Champs obligatoires manquants: {', '.join(missing)}")

                # Convertir les valeurs
                from decimal import Decimal, InvalidOperation
                try:
                    anciennete_min_dec = Decimal(str(anciennete_min).replace(',', '.'))
                    anciennete_max_dec = Decimal(str(anciennete_max).replace(',', '.'))
                    fourchette_basse_dec = Decimal(str(fourchette_basse).replace(',', '.'))
                except (InvalidOperation, ValueError):
                    raise ValidationError(f"Ligne {row_number}: Valeurs numeriques invalides.")

                # Parser la date
                try:
                    date_str = str(date_debut_validite)
                    # Si c'est un nombre Excel (ex: 45292.0), convertir en date
                    if isinstance(date_debut_validite, (int, float)):
                        from datetime import datetime, timedelta
                        excel_epoch = datetime(1899, 12, 30)
                        delta = timedelta(days=float(date_debut_validite))
                        date_debut = (excel_epoch + delta).date()
                    else:
                        # Nettoyer la chaîne - gérer les formats avec heure
                        if ' ' in date_str:
                            # Format: "2025-01-01 00:00:00" -> extraire juste la date
                            date_str = date_str.split(' ')[0]
                        elif '.' in date_str and len(date_str) > 10:
                            # Format: "2025-01-01.0" -> enlever le .0
                            date_str = date_str.split('.')[0]
                        date_debut = date.fromisoformat(date_str)
                except (ValueError, TypeError, ImportError) as e:
                    raise ValidationError(f"Ligne {row_number}: Format de date invalide (utilisez AAAA-MM-JJ). Valeur reçue: {date_debut_validite}")

                # Récupérer les autres champs avec normalisation des choix
                description = get_value('description') or ''
                description = str(description).strip() if description else ''

                fourchette_haute_val = get_value('fourchette haute')
                mode_fourchette = _normalize_choice_value(GrilleSalarialeTemplate.MODE_FOURCHETTE_HAUTE_CHOICES, get_value('mode fourchette', 'mode fourchette haute'), default='fixe')
                ref_haute_val = get_value('reference haute', 'ref haute')
                anciennete_ref_val = get_value('anciennete reference', 'ancienneté reference')
                ratio_annuel_val = get_value('ratio annuel')
                mode_ratio = _normalize_choice_value(GrilleSalarialeTemplate.MODE_RATIO_HAUTE_CHOICES, get_value('type ratio'), default='compose')
                date_fin_val = get_value('date fin', 'fin validite')

                date_fin = None
                if date_fin_val:
                    try:
                        date_str = str(date_fin_val)
                        # Si c'est un nombre Excel
                        if isinstance(date_fin_val, (int, float)):
                            from datetime import datetime, timedelta
                            excel_epoch = datetime(1899, 12, 30)
                            delta = timedelta(days=float(date_fin_val))
                            date_fin = (excel_epoch + delta).date()
                        else:
                            # Gérer les formats avec heure
                            if ' ' in date_str:
                                date_str = date_str.split(' ')[0]
                            elif '.' in date_str and len(date_str) > 10:
                                date_str = date_str.split('.')[0]
                            date_fin = date.fromisoformat(date_str)
                    except (ValueError, TypeError):
                        raise ValidationError(f"Ligne {row_number}: Format de date de fin invalide.")

                # Vérifier si mise à jour ou création
                template_id = get_value('id')
                if template_id and str(template_id).strip():
                    template_id = str(template_id).strip()
                    try:
                        template = GrilleSalarialeTemplate.objects.get(id=template_id)
                        if template.organisation and template.organisation != organisation and not getattr(request.user, 'is_superuser', False):
                            raise ValidationError(f"Ligne {row_number}: Vous ne pouvez pas modifier ce template.")
                        
                        # Mise à jour
                        template.nom_template = nom_template
                        template.description = description
                        template.anciennete_min = anciennete_min_dec
                        template.anciennete_max = anciennete_max_dec
                        template.fourchette_basse = fourchette_basse_dec
                        
                        # Gérer fourchette_haute - obligatoire meme en ratio_annuel
                        if fourchette_haute_val is not None and fourchette_haute_val != '':
                            try:
                                template.fourchette_haute = Decimal(str(fourchette_haute_val).replace(',', '.'))
                                # Si c'est 0 et mode=ratio_annuel, utiliser reference_haute
                                if template.fourchette_haute == 0 and ref_haute_val and str(mode_fourchette).strip() == 'ratio_annuel':
                                    template.fourchette_haute = Decimal(str(ref_haute_val).replace(',', '.'))
                            except:
                                pass
                        elif ref_haute_val and str(mode_fourchette).strip() == 'ratio_annuel':
                            # Si mode=ratio_annuel et fourchette_haute vide, utiliser reference_haute
                            template.fourchette_haute = Decimal(str(ref_haute_val).replace(',', '.'))
                        
                        # Validation
                        if template.fourchette_haute is None:
                            raise ValidationError(f"Ligne {row_number}: Fourchette haute obligatoire")
                            
                        template.mode_fourchette_haute = str(mode_fourchette).strip()
                        if ref_haute_val:
                            template.fourchette_haute_reference = Decimal(str(ref_haute_val).replace(',', '.'))
                        if anciennete_ref_val:
                            template.anciennete_reference_haute = Decimal(str(anciennete_ref_val).replace(',', '.'))
                        if ratio_annuel_val:
                            template.ratio_annuel_haute = Decimal(str(ratio_annuel_val).replace(',', '.'))
                        template.mode_ratio_haute = str(mode_ratio).strip()
                        template.date_debut_validite = date_debut
                        template.date_fin_validite = date_fin
                        template.save()
                        updated_count += 1
                    except GrilleSalarialeTemplate.DoesNotExist:
                        raise ValidationError(f"Ligne {row_number}: Template introuvable avec cet ID.")
                else:
                    # Création
                    # Calculer fourchette_haute si necessaire
                    fourchette_haute_final = None
                    if fourchette_haute_val is not None and fourchette_haute_val != '':
                        # Convertir la valeur
                        try:
                            fourchette_haute_final = Decimal(str(fourchette_haute_val).replace(',', '.'))
                            # Si c'est 0 ou vide, utiliser reference_haute si disponible (pour ratio_annuel)
                            if fourchette_haute_final == 0 and ref_haute_val and str(mode_fourchette).strip() == 'ratio_annuel':
                                fourchette_haute_final = Decimal(str(ref_haute_val).replace(',', '.'))
                        except:
                            fourchette_haute_final = None
                    
                    # Derniere verification : si toujours None et mode=ratio_annuel avec reference, utiliser reference
                    if fourchette_haute_final is None and ref_haute_val and str(mode_fourchette).strip() == 'ratio_annuel':
                        fourchette_haute_final = Decimal(str(ref_haute_val).replace(',', '.'))
                    
                    # Validation finale
                    if fourchette_haute_final is None:
                        raise ValidationError(f"Ligne {row_number}: Fourchette haute obligatoire (mettez la même valeur que Reference haute si mode=ratio_annuel)")
                    
                    GrilleSalarialeTemplate.objects.create(
                        nom_template=nom_template,
                        description=description,
                        organisation=organisation,
                        anciennete_min=anciennete_min_dec,
                        anciennete_max=anciennete_max_dec,
                        fourchette_basse=fourchette_basse_dec,
                        fourchette_haute=fourchette_haute_final,
                        mode_fourchette_haute=str(mode_fourchette).strip(),
                        fourchette_haute_reference=Decimal(str(ref_haute_val).replace(',', '.')) if ref_haute_val else None,
                        anciennete_reference_haute=Decimal(str(anciennete_ref_val).replace(',', '.')) if anciennete_ref_val else None,
                        ratio_annuel_haute=Decimal(str(ratio_annuel_val).replace(',', '.')) if ratio_annuel_val else None,
                        mode_ratio_haute=str(mode_ratio).strip(),
                        date_debut_validite=date_debut,
                        date_fin_validite=date_fin
                    )
                    created_count += 1

            except ValidationError as exc:
                return JsonResponse({'success': False, 'error': str(exc)}, status=400)
            except Exception as exc:
                return JsonResponse({'success': False, 'error': f'Ligne {row_number}: {str(exc)}'}, status=400)

        return JsonResponse({
            'success': True,
            'message': f'Import termine: {created_count} cree(s), {updated_count} mis(es) a jour.',
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)
