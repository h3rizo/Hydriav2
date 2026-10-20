from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from datetime import date
from decimal import Decimal
import calendar
from collections import defaultdict
from django.db.models import Q

from . import views
from apps.accounting import views as accounting_views
from apps.employees.permissions import has_compta_home_access


def health_check(request):
    return JsonResponse({
        'status': 'healthy',
        'version': '1.0.0',
        'service': 'hydria-accounting-workflow',
    })


@login_required
def compta_home(request):
    if not has_compta_home_access(request.user):
        messages.error(
            request,
            "Acces reserve aux postes suivants : Directeur, Responsable operationnel, Responsable administratif et financier, Assistant(e) admin."
        )
        return render(
            request,
            'accounting/compta_forbidden.html',
            status=403,
        )

    entries = accounting_views._get_diamex_scope_by_prog(request.user)
    entries = accounting_views._exclude_sensitive_diamex_lines_for_non_privileged(entries, request.user)
    entries = entries.filter(Q(montant_in__gt=0) | Q(montant_out__gt=0))
    available_files = sorted(
        {
            fichier
            for fichier in entries.exclude(fichier_source__isnull=True).exclude(fichier_source='').values_list('fichier_source', flat=True)
        }
    )
    available_months = sorted(
        {
            entry_date.strftime('%Y-%m')
            for entry_date in entries.exclude(date_m__isnull=True).values_list('date_m', flat=True)
        },
        reverse=True,
    )

    selected_month = (request.GET.get('mois') or '').strip()
    selected_file = (request.GET.get('fichier_source') or '').strip()
    cutoff_date = None
    if selected_month:
        try:
            selected_year, selected_month_number = selected_month.split('-', 1)
            selected_year = int(selected_year)
            selected_month_number = int(selected_month_number)
            last_day = calendar.monthrange(selected_year, selected_month_number)[1]
            cutoff_date = date(selected_year, selected_month_number, last_day)
        except (TypeError, ValueError):
            selected_month = ''
            cutoff_date = None

    if selected_file:
        entries = entries.filter(fichier_source=selected_file)

    if cutoff_date:
        entries = entries.filter(date_m__lte=cutoff_date)

    entries = entries.select_related('journal', 'compte').order_by('-date_m', '-id')

    from apps.billing.models import Fournisseur

    fournisseurs_dict = {
        str(f.idxls): f.nom_fournisseur
        for f in Fournisseur.objects.filter(idxls__isnull=False)
    }

    financements_map = defaultdict(lambda: {
        'label': '',
        'edf': Decimal('0'),
        'recettes': Decimal('0'),
        'depenses': Decimal('0'),
        'solde': Decimal('0'),
        'count': 0,
        'details': [],
    })
    journaux_map = defaultdict(lambda: {
        'label': '',
        'recettes': Decimal('0'),
        'depenses': Decimal('0'),
        'solde': Decimal('0'),
        'count': 0,
        'details': [],
    })
    tiers_map = defaultdict(lambda: {
        'label': '',
        'org_doit': Decimal('0'),
        'tiers_doit': Decimal('0'),
        'solde': Decimal('0'),
        'count': 0,
        'details': [],
    })

    for entry in entries:
        montant_in = Decimal(str(entry.montant_in or 0))
        montant_out = Decimal(str(entry.montant_out or 0))
        solde_entry = montant_in - montant_out
        date_label = entry.date_m.strftime('%d/%m/%Y') if entry.date_m else '-'
        date_m_value = entry.date_m.strftime('%Y-%m') if entry.date_m else ''
        date_rec_label = entry.date_rec.strftime('%d/%m/%Y') if entry.date_rec else '-'
        date_rec_value = entry.date_rec.isoformat() if entry.date_rec else ''
        cat_code = (entry.compte_code or '').strip() or '-'
        cat_name = (getattr(entry.compte, 'nom_compte', '') or '').strip()
        cat_label = f"{cat_code} - {cat_name}" if cat_name and cat_name != cat_code else cat_code

        detail_payload = {
            'date': date_label,
            'date_m_value': date_m_value,
            'date_rec': date_rec_label,
            'date_rec_value': date_rec_value,
            'rec': entry.rec or '',
            'cat': cat_code,
            'cat_label': cat_label,
            'description': entry.description or '-',
            'journal': entry.journal_code or '-',
            'compte': entry.compte_code or '-',
            'edf': 0.0,
            'recettes': float(montant_in),
            'depenses': float(montant_out),
            'solde': float(solde_entry),
            'financement': entry.fin or 'Sans financement',
            'tiers': entry.pers or 'Non specifie',
        }

        fin_raw = (entry.fin or '').strip()
        fin_label = accounting_views._clean_fin_label(fin_raw) or 'Sans financement'
        compte_code = (entry.compte_code or '').strip().upper()
        journal_code = (entry.journal_code or '').strip().upper()
        edf_categories = ('00FND1', '00FND2', '00FND3', '00FND4')
        is_edf_line = compte_code.startswith(edf_categories) or journal_code.startswith(edf_categories)
        is_excluded_financement_line = (
            compte_code.startswith('00PERS') or
            compte_code.startswith('00BOOK')
        )

        if not is_excluded_financement_line:
            fin_key = accounting_views._normalize_fin_bucket(fin_label) or accounting_views._normalize_text(fin_label)
            if not financements_map[fin_key]['label'] or len(fin_label) < len(financements_map[fin_key]['label']):
                financements_map[fin_key]['label'] = fin_label
            if is_edf_line:
                financements_map[fin_key]['edf'] += solde_entry
                detail_payload['edf'] = float(solde_entry)
                detail_payload['recettes'] = 0.0
                detail_payload['depenses'] = 0.0
            else:
                financements_map[fin_key]['recettes'] += montant_in
                financements_map[fin_key]['depenses'] += montant_out
            financements_map[fin_key]['solde'] += solde_entry
            financements_map[fin_key]['count'] += 1
            financements_map[fin_key]['details'].append(detail_payload)

        journal_label = (entry.journal_code or 'Sans journal').strip() or 'Sans journal'
        is_excluded_journal = journal_label in {'00PERS', '00SPLITBOOK-MGA'}
        if not is_excluded_journal:
            journal_key = accounting_views._normalize_text(journal_label)
            journaux_map[journal_key]['label'] = journal_label
            journaux_map[journal_key]['recettes'] += montant_in
            journaux_map[journal_key]['depenses'] += montant_out
            journaux_map[journal_key]['solde'] += solde_entry
            journaux_map[journal_key]['count'] += 1
            journaux_map[journal_key]['details'].append(detail_payload)

        if (
            ((entry.compte_code or '').startswith('00PERS') or (entry.journal_code or '').startswith('00PERS'))
            and not entry.match
        ):
            tiers_label = accounting_views._get_tiers_display_label(
                entry.pers or 'Non specifie',
                fournisseurs_dict,
            )
            tiers_key = accounting_views._normalize_text(entry.pers or 'Non specifie')
            impact = accounting_views._get_tiers_pointage_impact(entry)
            tiers_map[tiers_key]['label'] = tiers_label
            tiers_map[tiers_key]['count'] += 1
            if (entry.compte_code or '').startswith('00PERS'):
                tiers_map[tiers_key]['tiers_doit'] += montant_out
                tiers_map[tiers_key]['org_doit'] += montant_in
            else:
                tiers_map[tiers_key]['tiers_doit'] += montant_in
                tiers_map[tiers_key]['org_doit'] += montant_out
            tiers_map[tiers_key]['solde'] += impact
            tiers_map[tiers_key]['details'].append({
                **detail_payload,
                'impact': float(impact),
                'match': entry.match,
                'prog': entry.prog or '',
            })

    financements = sorted(financements_map.values(), key=lambda item: item['label'].lower())
    journaux = sorted(
        [
            item
            for item in journaux_map.values()
            if abs(float(item['solde'])) > 0.01
        ],
        key=lambda item: item['label'].lower()
    )
    for index, item in enumerate(journaux):
        item['modal_index'] = index

    tiers = sorted(
        [
            item
            for item in tiers_map.values()
            if abs(float(item['solde'])) > 0.01
        ],
        key=lambda item: item['label'].lower()
    )

    journaux_grouped_map = defaultdict(list)
    for item in journaux:
        label = (item.get('label') or '').strip().upper()
        if label.startswith('B'):
            journaux_grouped_map['Comptes en banque'].append(item)
        elif label.startswith('C'):
            journaux_grouped_map['Caisses'].append(item)
        else:
            journaux_grouped_map['Autres journaux'].append(item)

    journaux_grouped = [
        {'label': group_label, 'items': sorted(items, key=lambda item: item['label'].lower())}
        for group_label, items in (
            ('Comptes en banque', journaux_grouped_map.get('Comptes en banque', [])),
            ('Caisses', journaux_grouped_map.get('Caisses', [])),
            ('Autres journaux', journaux_grouped_map.get('Autres journaux', [])),
        )
        if items
    ]

    total_comptes_banque = sum(
        (item['solde'] for item in journaux if (item.get('label') or '').strip().upper().startswith('B')),
        Decimal('0'),
    )
    total_caisses = sum(
        (item['solde'] for item in journaux if (item.get('label') or '').strip().upper().startswith('C')),
        Decimal('0'),
    )
    nb_comptes_banque = sum(1 for item in journaux if (item.get('label') or '').strip().upper().startswith('B'))
    nb_caisses = sum(1 for item in journaux if (item.get('label') or '').strip().upper().startswith('C'))
    solde_tiers_total = sum((item['solde'] for item in tiers), Decimal('0'))
    total_solde_bailleurs = sum((item['solde'] for item in financements), Decimal('0'))
    total_recoupement_compta = total_comptes_banque + total_caisses + solde_tiers_total
    ecart_recoupement = total_recoupement_compta - total_solde_bailleurs
    recoupement_ok = abs(ecart_recoupement) <= Decimal('0.01')

    context = {
        'financements': financements,
        'journaux': journaux,
        'journaux_grouped': journaux_grouped,
        'tiers': tiers,
        'total_comptes_banque': total_comptes_banque,
        'total_caisses': total_caisses,
        'nb_comptes_banque': nb_comptes_banque,
        'nb_caisses': nb_caisses,
        'solde_tiers_total': solde_tiers_total,
        'total_solde_bailleurs': total_solde_bailleurs,
        'total_recoupement_compta': total_recoupement_compta,
        'ecart_recoupement': ecart_recoupement,
        'recoupement_ok': recoupement_ok,
        'available_months': available_months,
        'available_files': available_files,
        'selected_month': selected_month,
        'selected_file': selected_file,
        'cutoff_date': cutoff_date,
    }
    return render(request, 'accounting/compta_home.html', context)


urlpatterns = [
    path('favicon.ico', RedirectView.as_view(
        url='/static/images/icons/icons8-vase-94.png',
        permanent=False,
    )),
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path('accounts/login/visiteur/', views.visitor_email_login, name='visitor_email_login'),
    path(
        'accounts/login/',
        views.CustomLoginView.as_view(template_name='registration/login_compta.html'),
        name='login',
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', RedirectView.as_view(pattern_name='home_launcher', permanent=False), name='root_redirect'),
    path('accueil/', compta_home, name='home_launcher'),
    path('facturation/', include(('apps.billing.urls', 'billing'), namespace='billing')),
    path('', include(('apps.accounting.urls_saisie_workflow', 'accounting'), namespace='accounting')),
    path('', include(('apps.core.urls', 'core'), namespace='core')),
]
