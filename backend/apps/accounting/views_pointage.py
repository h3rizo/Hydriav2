from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import DocumentationComptable
from .pointage_workflow import (construire_mois, decider, lignes_autorisees,
                               periode_mois, roles_utilisateur, verifier_source)


@login_required
@require_http_methods(['GET', 'POST'])
def pointage_mensuel(request):
    params = request.POST if request.method == 'POST' else request.GET
    source = params.get('source', '')
    periode_str = params.get('periode', timezone.localdate().strftime('%Y-%m'))
    roles = roles_utilisateur(request.user)
    context = dict(source=source, periode=periode_str, roles=roles,
                   sources=lignes_autorisees(request.user).values_list('fichier_source', flat=True).distinct().order_by('fichier_source'))
    try:
        periode = periode_mois(periode_str)
        if source:
            verifier_source(request.user, source)
            if request.method == 'POST':
                if params.get('action') == 'pointer' and params.get('confirme') != 'oui':
                    raise ValidationError('Confirmer les vérifications manuelles avant de pointer.')
                decider(request.user, source, periode, params.get('cle', ''), params.get('action', ''),
                        params.get('role', ''), params.get('fingerprint', ''), params.get('remarque', ''),
                        {'reference': params.get('reference', ''), 'document': params.get('document') or None,
                         'justification': params.get('justification', '')})
                messages.success(request, 'Décision enregistrée dans Hydria.')
                return redirect(request.path + '?' + urlencode({'source': source, 'periode': periode_str,
                                'onglet': params.get('onglet', 'ligne'), 'filtre': params.get('filtre', '')}))
            etat = construire_mois(source, periode)
            onglet = params.get('onglet', 'ligne')
            filtre = params.get('filtre', '')
            rows = etat['soldes'] if onglet == 'solde' else etat['lignes']

            def _compteurs(lot):
                return dict(
                    total=len(lot),
                    bloques=sum(bool(r['erreurs']) for r in lot),
                    corrections=sum(r['correction'] for r in lot),
                    attente_caissiere=sum(r['role_attendu'] == 'caissiere' and not r['erreurs'] for r in lot),
                    attente_responsable=sum(r['role_attendu'] == 'responsable' and not r['erreurs'] for r in lot),
                    attente_directeur=sum(r['role_attendu'] == 'directeur' and not r['erreurs'] for r in lot),
                    valides=sum(r['niveau'] == 3 and not r['erreurs'] and not r['correction'] for r in lot),
                )

            # Compteurs de l'onglet courant + vue d'ensemble du mois (les deux natures).
            compteurs = _compteurs(rows)
            compteurs_mois = dict(
                lignes=_compteurs(etat['lignes']),
                soldes=_compteurs(etat['soldes']),
                total=_compteurs(etat['rows']),
            )
            if filtre == 'bloques':
                rows = [r for r in rows if r['erreurs']]
            elif filtre == 'corrections':
                rows = [r for r in rows if r['correction']]
            elif filtre == 'valides':
                rows = [r for r in rows if r['niveau'] == 3 and not r['erreurs'] and not r['correction']]
            elif filtre in ('caissiere', 'responsable', 'directeur'):
                rows = [r for r in rows if r['role_attendu'] == filtre and not r['erreurs']]
            page = Paginator(rows, 25).get_page(params.get('page'))
            for row in page:
                row['peut_pointer'] = row['role_attendu'] in roles and not row['erreurs']
                if row['objet']:
                    row['historique'] = row['objet'].decisions.all()[:20]
            context.update(etat=etat, page=page, onglet=onglet, filtre=filtre,
                           compteurs=compteurs, compteurs_mois=compteurs_mois,
                           documents=DocumentationComptable.objects.filter(fichier_source=source, annee=periode.year,
                                      mois=periode.month, statut='present').exclude(chemin_document=''),
                           historique_mois=etat['mois'].decisions.filter(objet__isnull=True)[:20] if etat['mois'] else [],
                           query=urlencode({'source': source, 'periode': periode_str, 'onglet': onglet, 'filtre': filtre}))
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
        if request.method == 'POST':
            return redirect(request.path + '?' + urlencode({'source': source, 'periode': periode_str, 'onglet': params.get('onglet', 'ligne')}))
    return render(request, 'accounting/pointage_mensuel.html', context)
