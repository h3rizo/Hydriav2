"""Page des coûts types par activité, servie par le sous-domaine ouvrages."""
from django.shortcuts import render

from apps.employees.permissions import employe_required
from apps.ouvrages.views import _extend_context_with_ouvrages_scope, _get_ouvrages_scope
from apps.planning.views_couts_types import contexte_page


@employe_required
def couts_types_page(request):
    scope, _, _ = _get_ouvrages_scope(request)
    contexte = _extend_context_with_ouvrages_scope(contexte_page(request), scope, request=request)
    contexte['title'] = 'Coûts types par activité'
    return render(request, 'ouvrages/couts_types.html', contexte)
