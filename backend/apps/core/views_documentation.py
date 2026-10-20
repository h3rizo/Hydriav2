"""Vues de documentation et protocoles."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.employees.permissions import has_admin_access

from .models import (
    CalculationRule,
    DocumentationChangeLog,
    DocumentationModule,
    IndicatorDefinition,
    KnownLimitation,
    TestExecution,
    TestProtocol,
)


DOCUMENTATION_LINKS_BY_WORKSPACE = {
    'main': [
        {
            'label': "Manuel d'utilisateur",
            'url_name': 'system:manuel_utilisateur',
            'icon': 'fas fa-book',
            'category': 'Documentation utilisateur',
        },
        {
            'label': 'Architecture & Workflows',
            'url_name': 'core:architecture_documentation',
            'icon': 'fas fa-sitemap',
            'category': 'Documentation protocolaire par module',
        },
        {
            'label': 'Workflow Facturation volumetrique',
            'url_name': 'core:facturation_workflow_documentation',
            'icon': 'fas fa-file-invoice-dollar',
            'category': 'Documentation protocolaire par module',
        },
        {
            'label': 'Workflow Cartes sociales',
            'url_name': 'core:cartes_sociales_workflow_documentation',
            'icon': 'fas fa-id-card',
            'category': 'Documentation protocolaire par module',
        },
        {
            'label': 'Workflow Recherche des ouvrages',
            'url_name': 'core:recherche_ouvrages_workflow_documentation',
            'icon': 'fas fa-building-circle-check',
            'category': 'Documentation protocolaire par module',
        },
    ],
    'accounting': [
        {
            'label': 'Documentation comptable - saisie',
            'url_name': 'accounting:documentation_saisie',
            'icon': 'fas fa-folder-open',
            'category': 'Documentation utilisateur',
        },
        {
            'label': 'Documentation comptable - rapport',
            'url_name': 'accounting:documentation_rapport',
            'icon': 'fas fa-chart-bar',
            'category': 'Documentation utilisateur',
        },
        {
            'label': 'Workflow Module caissiere',
            'url_name': 'core:caissiere_workflow_documentation',
            'icon': 'fas fa-cash-register',
            'category': 'Documentation protocolaire par module',
        },
    ],
    'payroll': [
        {
            'label': 'Workflow Fiches de paie',
            'url_name': 'core:fiches_paie_workflow_documentation',
            'icon': 'fas fa-file-invoice',
            'category': 'Documentation protocolaire par module',
        },
        {
            'label': 'Workflow Paiements IRSA',
            'url_name': 'core:paiements_irsa_workflow_documentation',
            'icon': 'fas fa-receipt',
            'category': 'Documentation protocolaire par module',
        },
    ],
    'admin': [
        {
            'label': 'Workflow Planning terrain',
            'url_name': 'core:workflow_terrain_documentation',
            'icon': 'fas fa-route',
            'category': 'Documentation protocolaire par module',
        },
        {
            'label': "Workflow Analyses d'eau",
            'url_name': 'core:analyses_eau_workflow_documentation',
            'icon': 'fas fa-vial',
            'category': 'Documentation protocolaire par module',
        },
    ],
    'analyses': [],
    'ouvrages': [],
    'planning': [
        {
            'label': 'Workflow Planning',
            'url_name': 'core:planning_workflow_documentation',
            'icon': 'fas fa-calendar-alt',
            'category': 'Documentation protocolaire par module',
        },
        {
            'label': 'Workflow Reparations',
            'url_name': 'core:reparations_workflow_documentation',
            'icon': 'fas fa-wrench',
            'category': 'Documentation protocolaire par module',
        },
    ],
    'logistics': [
        {
            'label': 'Workflow Gestion des stocks',
            'url_name': 'core:inventory_workflow_documentation',
            'icon': 'fas fa-warehouse',
            'category': 'Documentation protocolaire par module',
        },
    ],
}


def _get_documentation_workspace(request):
    if getattr(request, 'is_planning_subdomain', False):
        return 'planning'
    if getattr(request, 'is_logistics_subdomain', False):
        return 'logistics'
    if getattr(request, 'is_accounting_subdomain', False) or getattr(request, 'is_accounting_workflow_subdomain', False):
        return 'accounting'
    if getattr(request, 'is_payroll_subdomain', False):
        return 'payroll'
    if getattr(request, 'is_admin_subdomain', False):
        return 'admin'
    if getattr(request, 'is_analyses_subdomain', False):
        return 'analyses'
    if getattr(request, 'is_ouvrages_subdomain', False):
        return 'ouvrages'
    return 'main'


def _planning_module_filter():
    return (
        Q(slug__icontains='planning')
        | Q(slug__icontains='reparation')
        | Q(slug__icontains='maintenance')
        | Q(name__icontains='planning')
        | Q(name__icontains='reparation')
        | Q(name__icontains='maintenance')
        | Q(workflow_url__icontains='/documentation/workflow/planning/')
        | Q(workflow_url__icontains='/documentation/workflow/reparations/')
    )


def _logistics_module_filter():
    return (
        Q(slug__icontains='stock')
        | Q(slug__icontains='inventaire')
        | Q(name__icontains='stock')
        | Q(name__icontains='inventaire')
        | Q(workflow_url__icontains='/documentation/workflow/inventory/')
    )


def _base_module_queryset_for_workspace(workspace):
    if workspace == 'planning':
        return DocumentationModule.objects.filter(workspace=DocumentationModule.WORKSPACE_MAIN).filter(_planning_module_filter())
    if workspace == 'logistics':
        return DocumentationModule.objects.filter(workspace=DocumentationModule.WORKSPACE_MAIN).filter(_logistics_module_filter())
    if workspace == 'main':
        return DocumentationModule.objects.filter(workspace=workspace).exclude(
            _planning_module_filter() | _logistics_module_filter()
        )
    return DocumentationModule.objects.filter(workspace=workspace)


def _workspace_module_queryset(request):
    workspace = _get_documentation_workspace(request)
    return _base_module_queryset_for_workspace(workspace)


def _workspace_test_queryset(request):
    workspace = _get_documentation_workspace(request)
    queryset = TestProtocol.objects.select_related('module')
    if workspace in {'planning', 'logistics'}:
        return queryset.filter(module__in=_base_module_queryset_for_workspace(workspace))
    if workspace == 'main':
        return queryset.filter(module__workspace=DocumentationModule.WORKSPACE_MAIN).exclude(
            module__in=_base_module_queryset_for_workspace('planning')
        ).exclude(
            module__in=_base_module_queryset_for_workspace('logistics')
        )
    return queryset.filter(module__workspace=workspace)


def _relocated_sections(workspace):
    return []


def _redirect_relocated_documentation(request, module):
    workspace = _get_documentation_workspace(request)
    if workspace != 'main':
        return None
    slug = (module.slug or '').lower()
    name = (module.name or '').lower()
    workflow_url = (module.workflow_url or '').lower()
    is_planning_related = any(token in slug or token in name or token in workflow_url for token in ('planning', 'reparation', 'maintenance'))
    is_logistics_related = any(token in slug or token in name or token in workflow_url for token in ('stock', 'inventaire'))
    if is_planning_related:
        target_base = (getattr(settings, 'PLANNING_SUBDOMAIN_URL', 'https://planning.hydria.mg') or 'https://planning.hydria.mg').rstrip('/')
        return redirect(f"{target_base}{request.path}")
    if is_logistics_related:
        target_base = (getattr(settings, 'LOGISTICS_SUBDOMAIN_URL', 'https://logistique.hydria.mg') or 'https://logistique.hydria.mg').rstrip('/')
        return redirect(f"{target_base}{request.path}")
    return None


def _can_record_test_execution(user):
    return user.is_superuser or user.is_staff or has_admin_access(user)


def _split_lines(value):
    return [line.strip() for line in (value or '').splitlines() if line.strip()]


def _module_payload_from_post(post):
    return {
        'name': (post.get('name') or '').strip(),
        'short_name': (post.get('short_name') or '').strip(),
        'icon': (post.get('icon') or 'fas fa-book').strip(),
        'display_order': int((post.get('display_order') or '0').strip() or 0),
        'is_priority': bool(post.get('is_priority')),
        'objective': (post.get('objective') or '').strip(),
        'target_audience': (post.get('target_audience') or '').strip(),
        'data_used': (post.get('data_used') or '').strip(),
        'pages_in_scope': _split_lines(post.get('pages_in_scope')),
        'buttons': _split_lines(post.get('buttons')),
        'filters': _split_lines(post.get('filters')),
        'tables': _split_lines(post.get('tables')),
        'statistics': _split_lines(post.get('statistics')),
        'charts': _split_lines(post.get('charts')),
        'calculation_rules_text': (post.get('calculation_rules_text') or '').strip(),
        'display_conditions': (post.get('display_conditions') or '').strip(),
        'edge_cases': (post.get('edge_cases') or '').strip(),
        'possible_errors': (post.get('possible_errors') or '').strip(),
        'known_limits': (post.get('known_limits') or '').strip(),
        'test_notes': (post.get('test_notes') or '').strip(),
        'workflow_url': (post.get('workflow_url') or '').strip(),
        'source_code_refs': _split_lines(post.get('source_code_refs')),
        'validation_status': (post.get('validation_status') or DocumentationModule.STATUS_DRAFT).strip(),
    }


def _clean_slug_value(value):
    return (value or '').strip().lower().replace(' ', '-')


def _get_module_related_or_404(model, module, object_id):
    return get_object_or_404(model, id=(object_id or '').strip(), module=module)


def _protocol_payload_from_post(post, module):
    return {
        'code': (post.get('code') or '').strip().upper(),
        'module': module,
        'test_type': (post.get('test_type') or TestProtocol.TYPE_FUNCTIONAL).strip(),
        'objective': (post.get('objective') or '').strip(),
        'preconditions': (post.get('preconditions') or '').strip(),
        'required_data': (post.get('required_data') or '').strip(),
        'steps': (post.get('steps') or '').strip(),
        'expected_result': (post.get('expected_result') or '').strip(),
        'criticality': (post.get('criticality') or TestProtocol.CRITICALITY_MEDIUM).strip(),
    }


def _change_log_payload_from_post(post, module):
    return {
        'module': module,
        'title': (post.get('title') or '').strip(),
        'entry_type': (post.get('entry_type') or DocumentationChangeLog.TYPE_DOC).strip(),
        'details': (post.get('details') or '').strip(),
        'happened_on': (post.get('happened_on') or '').strip(),
    }


def _test_status_counts(queryset):
    return {
        'total': queryset.count(),
        'success': queryset.filter(status=TestProtocol.STATUS_SUCCESS).count(),
        'failed': queryset.filter(status=TestProtocol.STATUS_FAILED).count(),
        'todo': queryset.filter(status=TestProtocol.STATUS_TODO).count(),
        'to_fix': queryset.filter(status=TestProtocol.STATUS_FIX).count(),
        'blocked': queryset.filter(status=TestProtocol.STATUS_BLOCKED).count(),
        'critical_failed': queryset.filter(
            status__in=[TestProtocol.STATUS_FAILED, TestProtocol.STATUS_FIX],
            criticality=TestProtocol.CRITICALITY_CRITICAL,
        ).count(),
    }


@login_required
def documentation_protocols_home(request):
    workspace = _get_documentation_workspace(request)
    modules = _workspace_module_queryset(request).filter(is_active=True)
    tests = _workspace_test_queryset(request)
    stats = _test_status_counts(tests)
    stats['documented_modules'] = modules.exclude(validation_status=DocumentationModule.STATUS_DRAFT).count()
    stats['incomplete_modules'] = modules.filter(
        Q(validation_status=DocumentationModule.STATUS_DRAFT) |
        Q(objective='') |
        Q(target_audience='')
    ).count()
    stats['success_rate'] = round((stats['success'] / stats['total']) * 100, 1) if stats['total'] else 0

    context = {
        'title': 'Documentation & Protocoles',
        'modules': modules[:12],
        'existing_links': DOCUMENTATION_LINKS_BY_WORKSPACE.get(workspace, []),
        'documentation_workspace': workspace,
        'recent_executions': TestExecution.objects.select_related('protocol', 'protocol__module').filter(protocol__in=tests)[:10],
        'indicator_definitions': IndicatorDefinition.objects.select_related('module').filter(module__in=modules)[:12],
        'calculation_rules': CalculationRule.objects.select_related('module').filter(module__in=modules)[:12],
        'known_limitations': KnownLimitation.objects.select_related('module').filter(module__in=modules)[:12],
        'change_logs': DocumentationChangeLog.objects.select_related('module').filter(module__in=modules)[:12],
        'stats': stats,
        'relocated_sections': _relocated_sections(workspace),
    }
    return render(request, 'documentation/protocols_home.html', context)


@login_required
def documentation_module_list(request):
    workspace = _get_documentation_workspace(request)
    can_record_execution = _can_record_test_execution(request.user)
    modules = _workspace_module_queryset(request).filter(is_active=True).annotate(
        test_count=Count('test_protocols', distinct=True),
        failed_test_count=Count('test_protocols', filter=Q(test_protocols__status__in=[TestProtocol.STATUS_FAILED, TestProtocol.STATUS_FIX]), distinct=True),
    )

    if request.method == 'POST':
        if not can_record_execution:
            return HttpResponseForbidden("Vous n'avez pas les droits pour creer un module.")

        payload = _module_payload_from_post(request.POST)
        module = DocumentationModule.objects.create(
            slug=(request.POST.get('slug') or '').strip(),
            workspace=workspace,
            **payload,
        )
        messages.success(request, f"Module {module.name} cree.")
        return redirect('core:documentation_module_detail', slug=module.slug)

    status_filter = (request.GET.get('status') or '').strip()
    priority_filter = (request.GET.get('priority') or '').strip()
    search = (request.GET.get('q') or '').strip()

    if status_filter:
        modules = modules.filter(validation_status=status_filter)
    if priority_filter == '1':
        modules = modules.filter(is_priority=True)
    if search:
        modules = modules.filter(
            Q(name__icontains=search) |
            Q(short_name__icontains=search) |
            Q(objective__icontains=search)
        )

    context = {
        'title': 'Documentation par module',
        'modules': modules,
        'filters': {
            'status': status_filter,
            'priority': priority_filter,
            'q': search,
        },
        'status_choices': DocumentationModule.STATUS_CHOICES,
        'can_record_execution': can_record_execution,
    }
    return render(request, 'documentation/module_list.html', context)


@login_required
def documentation_module_detail(request, slug):
    module = get_object_or_404(
        _workspace_module_queryset(request).prefetch_related(
            'indicator_definitions',
            'calculation_rules',
            'known_limitations',
            'test_protocols',
            'change_logs',
        ),
        slug=slug,
        is_active=True,
    )
    redirect_response = _redirect_relocated_documentation(request, module)
    if redirect_response:
        return redirect_response
    can_record_execution = _can_record_test_execution(request.user)

    if request.method == 'POST':
        if not can_record_execution:
            return HttpResponseForbidden("Vous n'avez pas les droits pour modifier un module.")

        form_type = (request.POST.get('form_type') or 'module').strip()

        if form_type == 'module':
            payload = _module_payload_from_post(request.POST)
            for field, value in payload.items():
                setattr(module, field, value)
            module.save()
            messages.success(request, f"Module {module.name} mis a jour.")
        elif form_type == 'indicator':
            indicator = IndicatorDefinition.objects.create(
                module=module,
                name=(request.POST.get('name') or '').strip(),
                slug=_clean_slug_value(request.POST.get('slug') or request.POST.get('name')),
                objective=(request.POST.get('objective') or '').strip(),
                formula=(request.POST.get('formula') or '').strip(),
                data_source=(request.POST.get('data_source') or '').strip(),
                refresh_frequency=(request.POST.get('refresh_frequency') or IndicatorDefinition.UPDATE_MONTHLY).strip(),
                interpretation=(request.POST.get('interpretation') or '').strip(),
                limitations=(request.POST.get('limitations') or '').strip(),
                example=(request.POST.get('example') or '').strip(),
                display_order=int((request.POST.get('display_order') or '0').strip() or 0),
            )
            messages.success(request, f"Indicateur {indicator.name} ajoute.")
        elif form_type == 'rule':
            rule = CalculationRule.objects.create(
                module=module,
                title=(request.POST.get('title') or '').strip(),
                description=(request.POST.get('description') or '').strip(),
                formula=(request.POST.get('formula') or '').strip(),
                source_fields=(request.POST.get('source_fields') or '').strip(),
                caveats=(request.POST.get('caveats') or '').strip(),
                example=(request.POST.get('example') or '').strip(),
                display_order=int((request.POST.get('display_order') or '0').strip() or 0),
            )
            messages.success(request, f"Regle {rule.title} ajoutee.")
        elif form_type == 'limitation':
            limitation = KnownLimitation.objects.create(
                module=module,
                title=(request.POST.get('title') or '').strip(),
                description=(request.POST.get('description') or '').strip(),
                impact=(request.POST.get('impact') or '').strip(),
                workaround=(request.POST.get('workaround') or '').strip(),
                severity=(request.POST.get('severity') or KnownLimitation.SEVERITY_MEDIUM).strip(),
                status=(request.POST.get('status') or KnownLimitation.STATUS_OPEN).strip(),
                display_order=int((request.POST.get('display_order') or '0').strip() or 0),
            )
            messages.success(request, f"Limite {limitation.title} ajoutee.")
        elif form_type == 'indicator_update':
            indicator = _get_module_related_or_404(IndicatorDefinition, module, request.POST.get('object_id'))
            indicator.name = (request.POST.get('name') or '').strip()
            indicator.slug = _clean_slug_value(request.POST.get('slug') or request.POST.get('name'))
            indicator.objective = (request.POST.get('objective') or '').strip()
            indicator.formula = (request.POST.get('formula') or '').strip()
            indicator.data_source = (request.POST.get('data_source') or '').strip()
            indicator.refresh_frequency = (request.POST.get('refresh_frequency') or IndicatorDefinition.UPDATE_MONTHLY).strip()
            indicator.interpretation = (request.POST.get('interpretation') or '').strip()
            indicator.limitations = (request.POST.get('limitations') or '').strip()
            indicator.example = (request.POST.get('example') or '').strip()
            indicator.display_order = int((request.POST.get('display_order') or '0').strip() or 0)
            indicator.save()
            messages.success(request, f"Indicateur {indicator.name} mis a jour.")
        elif form_type == 'indicator_delete':
            indicator = _get_module_related_or_404(IndicatorDefinition, module, request.POST.get('object_id'))
            indicator_name = indicator.name
            indicator.delete()
            messages.success(request, f"Indicateur {indicator_name} supprime.")
        elif form_type == 'rule_update':
            rule = _get_module_related_or_404(CalculationRule, module, request.POST.get('object_id'))
            rule.title = (request.POST.get('title') or '').strip()
            rule.description = (request.POST.get('description') or '').strip()
            rule.formula = (request.POST.get('formula') or '').strip()
            rule.source_fields = (request.POST.get('source_fields') or '').strip()
            rule.caveats = (request.POST.get('caveats') or '').strip()
            rule.example = (request.POST.get('example') or '').strip()
            rule.display_order = int((request.POST.get('display_order') or '0').strip() or 0)
            rule.save()
            messages.success(request, f"Regle {rule.title} mise a jour.")
        elif form_type == 'rule_delete':
            rule = _get_module_related_or_404(CalculationRule, module, request.POST.get('object_id'))
            rule_title = rule.title
            rule.delete()
            messages.success(request, f"Regle {rule_title} supprimee.")
        elif form_type == 'limitation_update':
            limitation = _get_module_related_or_404(KnownLimitation, module, request.POST.get('object_id'))
            limitation.title = (request.POST.get('title') or '').strip()
            limitation.description = (request.POST.get('description') or '').strip()
            limitation.impact = (request.POST.get('impact') or '').strip()
            limitation.workaround = (request.POST.get('workaround') or '').strip()
            limitation.severity = (request.POST.get('severity') or KnownLimitation.SEVERITY_MEDIUM).strip()
            limitation.status = (request.POST.get('status') or KnownLimitation.STATUS_OPEN).strip()
            limitation.display_order = int((request.POST.get('display_order') or '0').strip() or 0)
            limitation.save()
            messages.success(request, f"Limite {limitation.title} mise a jour.")
        elif form_type == 'limitation_delete':
            limitation = _get_module_related_or_404(KnownLimitation, module, request.POST.get('object_id'))
            limitation_title = limitation.title
            limitation.delete()
            messages.success(request, f"Limite {limitation_title} supprimee.")
        elif form_type == 'change_log':
            change_log = DocumentationChangeLog.objects.create(**_change_log_payload_from_post(request.POST, module))
            messages.success(request, f"Historique {change_log.title} ajoute.")
        elif form_type == 'change_log_update':
            change_log = _get_module_related_or_404(DocumentationChangeLog, module, request.POST.get('object_id'))
            payload = _change_log_payload_from_post(request.POST, module)
            for field, value in payload.items():
                setattr(change_log, field, value)
            change_log.save()
            messages.success(request, f"Historique {change_log.title} mis a jour.")
        elif form_type == 'change_log_delete':
            change_log = _get_module_related_or_404(DocumentationChangeLog, module, request.POST.get('object_id'))
            change_log_title = change_log.title
            change_log.delete()
            messages.success(request, f"Historique {change_log_title} supprime.")
        else:
            return HttpResponseForbidden("Type de formulaire non pris en charge.")

        return redirect('core:documentation_module_detail', slug=module.slug)

    context = {
        'title': f'Documentation - {module.name}',
        'module': module,
        'tests': module.test_protocols.all(),
        'indicators': module.indicator_definitions.all(),
        'rules': module.calculation_rules.all(),
        'limitations': module.known_limitations.all(),
        'changes': module.change_logs.all()[:10],
        'status_choices': DocumentationModule.STATUS_CHOICES,
        'can_record_execution': can_record_execution,
        'indicator_frequency_choices': IndicatorDefinition.UPDATE_CHOICES,
        'limitation_severity_choices': KnownLimitation.SEVERITY_CHOICES,
        'limitation_status_choices': KnownLimitation.STATUS_CHOICES,
        'change_log_type_choices': DocumentationChangeLog.TYPE_CHOICES,
    }
    return render(request, 'documentation/module_detail.html', context)


@login_required
def test_protocol_list(request):
    workspace = _get_documentation_workspace(request)
    tests = _workspace_test_queryset(request)
    can_record_execution = _can_record_test_execution(request.user)

    if request.method == 'POST':
        if not can_record_execution:
            return HttpResponseForbidden("Vous n'avez pas les droits pour creer un protocole.")

        form_type = (request.POST.get('form_type') or 'create').strip()
        module_id = (request.POST.get('module_id') or '').strip()
        module = get_object_or_404(DocumentationModule, id=module_id, workspace=workspace, is_active=True)
        if form_type == 'create':
            protocol = TestProtocol.objects.create(
                **_protocol_payload_from_post(request.POST, module),
                status=TestProtocol.STATUS_TODO,
            )
            messages.success(request, f"Protocole {protocol.code} cree.")
            return redirect('core:test_protocol_detail', code=protocol.code)

        return HttpResponseForbidden("Type de formulaire non pris en charge.")

    module_slug = (request.GET.get('module') or '').strip()
    status_filter = (request.GET.get('status') or '').strip()
    criticality_filter = (request.GET.get('criticality') or '').strip()
    type_filter = (request.GET.get('type') or '').strip()

    if module_slug:
        tests = tests.filter(module__slug=module_slug)
    if status_filter:
        tests = tests.filter(status=status_filter)
    if criticality_filter:
        tests = tests.filter(criticality=criticality_filter)
    if type_filter:
        tests = tests.filter(test_type=type_filter)

    stats = _test_status_counts(tests)
    stats['success_rate'] = round((stats['success'] / stats['total']) * 100, 1) if stats['total'] else 0

    context = {
        'title': 'Protocoles de tests',
        'tests': tests,
        'modules': _workspace_module_queryset(request).filter(is_active=True),
        'filters': {
            'module': module_slug,
            'status': status_filter,
            'criticality': criticality_filter,
            'type': type_filter,
        },
        'status_choices': TestProtocol.STATUS_CHOICES,
        'criticality_choices': TestProtocol.CRITICALITY_CHOICES,
        'type_choices': TestProtocol.TYPE_CHOICES,
        'stats': stats,
        'can_record_execution': can_record_execution,
        'relocated_sections': _relocated_sections(workspace),
    }
    return render(request, 'documentation/test_protocol_list.html', context)


@login_required
def test_protocol_detail(request, code):
    protocol = get_object_or_404(
        _workspace_test_queryset(request).prefetch_related('executions'),
        code=code,
    )
    redirect_response = _redirect_relocated_documentation(request, protocol.module)
    if redirect_response:
        return redirect_response
    can_record_execution = _can_record_test_execution(request.user)

    if request.method == 'POST':
        if not can_record_execution:
            return HttpResponseForbidden("Vous n'avez pas les droits pour enregistrer une execution.")

        form_type = (request.POST.get('form_type') or 'execution').strip()
        if form_type == 'execution':
            execution = TestExecution.objects.create(
                protocol=protocol,
                status=(request.POST.get('status') or TestProtocol.STATUS_TODO).strip(),
                result_obtained=(request.POST.get('result_obtained') or '').strip(),
                executed_by_name=(request.POST.get('executed_by_name') or request.user.get_username()).strip(),
                comment=(request.POST.get('comment') or '').strip(),
                evidence_path=(request.POST.get('evidence_path') or '').strip(),
                related_issue=(request.POST.get('related_issue') or '').strip(),
            )

            protocol.status = execution.status
            protocol.last_result = execution.result_obtained
            protocol.last_executed_at = execution.executed_at
            protocol.executed_by_name = execution.executed_by_name
            protocol.comment = execution.comment
            protocol.evidence_path = execution.evidence_path
            protocol.related_issue = execution.related_issue
            protocol.save(
                update_fields=[
                    'status',
                    'last_result',
                    'last_executed_at',
                    'executed_by_name',
                    'comment',
                    'evidence_path',
                    'related_issue',
                    'updated_at',
                ]
            )
            messages.success(request, f"Execution du test {protocol.code} enregistree.")
        elif form_type == 'protocol_update':
            module_id = (request.POST.get('module_id') or '').strip()
            module = get_object_or_404(DocumentationModule, id=module_id, is_active=True)
            payload = _protocol_payload_from_post(request.POST, module)
            for field, value in payload.items():
                setattr(protocol, field, value)
            protocol.status = (request.POST.get('protocol_status') or protocol.status).strip()
            protocol.last_result = (request.POST.get('last_result') or '').strip()
            protocol.executed_by_name = (request.POST.get('executed_by_name') or '').strip()
            protocol.comment = (request.POST.get('comment') or '').strip()
            protocol.evidence_path = (request.POST.get('evidence_path') or '').strip()
            protocol.related_issue = (request.POST.get('related_issue') or '').strip()
            protocol.save()
            messages.success(request, f"Protocole {protocol.code} mis a jour.")
        elif form_type == 'protocol_delete':
            protocol_code = protocol.code
            protocol.delete()
            messages.success(request, f"Protocole {protocol_code} supprime.")
            return redirect('core:test_protocol_list')
        else:
            return HttpResponseForbidden("Type de formulaire non pris en charge.")

        return redirect('core:test_protocol_detail', code=protocol.code)

    context = {
        'title': f'Test - {protocol.code}',
        'protocol': protocol,
        'executions': protocol.executions.all(),
        'can_record_execution': can_record_execution,
        'status_choices': TestProtocol.STATUS_CHOICES,
        'criticality_choices': TestProtocol.CRITICALITY_CHOICES,
        'type_choices': TestProtocol.TYPE_CHOICES,
        'modules': DocumentationModule.objects.filter(is_active=True),
    }
    return render(request, 'documentation/test_protocol_detail.html', context)


@login_required
def architecture_documentation(request):
    """Page de documentation de l'architecture de l'application"""

    context = {
        'title': 'Architecture & Documentation',
    }

    return render(request, 'core/architecture_documentation.html', context)


@login_required
def planning_workflow_documentation(request):
    """Page de documentation détaillée du workflow Planning"""

    context = {
        'title': 'Documentation - Workflow Planning',
    }

    return render(request, 'documentation/planning_workflow.html', context)


@login_required
def facturation_workflow_documentation(request):
    """Page de documentation détaillée du workflow Facturation Volumétrique"""

    context = {
        'title': 'Documentation - Workflow Facturation Volumétrique',
    }

    return render(request, 'documentation/facturation_workflow.html', context)


@login_required
def reparations_workflow_documentation(request):
    """Page de documentation détaillée du workflow Réparations & Réhabilitations"""

    context = {
        'title': 'Documentation - Workflow Réparations & Réhabilitations',
    }

    return render(request, 'documentation/reparations_workflow.html', context)


@login_required
def fiches_paie_workflow_documentation(request):
    """Page de documentation détaillée du workflow Fiches de Paie"""

    context = {
        'title': 'Documentation - Workflow Fiches de Paie',
    }

    return render(request, 'documentation/fiches_paie_workflow.html', context)


@login_required
def inventory_workflow_documentation(request):
    """Page de documentation détaillée du workflow Gestion des Stocks"""

    context = {
        'title': 'Documentation - Workflow Gestion des Stocks',
    }

    return render(request, 'documentation/inventory_workflow.html', context)


@login_required
def paiements_irsa_workflow_documentation(request):
    """Page de documentation détaillée du workflow Paiements IRSA"""

    context = {
        'title': 'Documentation - Workflow Paiements IRSA',
    }

    return render(request, 'documentation/paiements_irsa_workflow.html', context)


@login_required
def caissiere_workflow_documentation(request):
    """Page de documentation détaillée du workflow Module Caissière - Retours"""

    context = {
        'title': 'Documentation - Workflow Module Caissière',
    }

    return render(request, 'documentation/caissiere_workflow.html', context)


@login_required
def cartes_sociales_workflow_documentation(request):
    """Page de documentation détaillée du workflow Cartes Sociales"""

    context = {
        'title': 'Documentation - Workflow Cartes Sociales',
    }

    return render(request, 'documentation/cartes_sociales_workflow.html', context)

@login_required
def workflow_terrain_documentation(request):
    """Page de documentation detaillee du workflow planning terrain"""

    context = {
        'title': 'Documentation - Workflow Planning Terrain',
    }

    return render(request, 'documentation/workflow_terrain.html', context)


@login_required
def analyses_eau_workflow_documentation(request):
    """Page de documentation détaillée du workflow Analyses d'Eau"""

    context = {
        'title': 'Documentation - Workflow Analyses d\'Eau',
    }

    return render(request, 'documentation/analyses_eau_workflow.html', context)


@login_required
def recherche_ouvrages_workflow_documentation(request):
    """Documentation du workflow de recherche et de suivi des ouvrages."""

    context = {
        'title': 'Documentation - Workflow Recherche des ouvrages',
    }
    return render(request, 'documentation/recherche_ouvrages_workflow.html', context)
