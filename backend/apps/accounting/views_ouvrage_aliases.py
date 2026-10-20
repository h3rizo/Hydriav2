from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.organization.models import Ouvrage, OuvrageAlias


class OuvrageAliasForm(forms.ModelForm):
    class Meta:
        model = OuvrageAlias
        fields = ('alias',)
        widgets = {
            'alias': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': "Ex. Ambodivohitra/TsaratamponaII",
                'autocomplete': 'off',
            }),
        }

    def __init__(self, *args, ouvrage=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ouvrage is not None:
            self.instance.ouvrage = ouvrage


def _redirect_to_alias_page(ouvrage_id=None, query=''):
    params = {}
    if ouvrage_id:
        params['ouvrage'] = str(ouvrage_id)
    if query:
        params['q'] = query
    url = reverse('accounting:gestion_aliases_ouvrages')
    return redirect(f'{url}?{urlencode(params)}' if params else url)


@login_required
@require_http_methods(['GET', 'POST'])
def gestion_aliases_ouvrages(request):
    query = (request.GET.get('q') or request.POST.get('q') or '').strip()
    ouvrage_id = request.GET.get('ouvrage') or request.POST.get('ouvrage_id')
    ouvrage_selectionne = None
    if ouvrage_id:
        ouvrage_selectionne = get_object_or_404(
            Ouvrage.objects.select_related('type_ouvrage'),
            pk=ouvrage_id,
        )

    form = OuvrageAliasForm(ouvrage=ouvrage_selectionne)
    if request.method == 'POST':
        action = request.POST.get('action', 'add')
        if action == 'delete':
            alias = get_object_or_404(OuvrageAlias, pk=request.POST.get('alias_id'))
            ouvrage_id = alias.ouvrage_id
            alias_texte = alias.alias
            alias.delete()
            messages.success(request, f'La variante "{alias_texte}" a été supprimée.')
            return _redirect_to_alias_page(ouvrage_id, query)

        if not ouvrage_selectionne:
            messages.error(request, "Sélectionnez d'abord un ouvrage.")
        else:
            form = OuvrageAliasForm(request.POST, ouvrage=ouvrage_selectionne)
            if form.is_valid():
                try:
                    alias = form.save()
                except ValidationError as exc:
                    errors = exc.message_dict.get('alias', exc.messages) if hasattr(exc, 'error_dict') else exc.messages
                    for error in errors:
                        form.add_error('alias', error)
                else:
                    messages.success(
                        request,
                        f'La variante "{alias.alias}" reconnaîtra maintenant "{ouvrage_selectionne.nom_ouvrage}".',
                    )
                    return _redirect_to_alias_page(ouvrage_selectionne.id, query)

    ouvrages = Ouvrage.objects.none()
    if query:
        ouvrages = Ouvrage.objects.select_related('type_ouvrage').annotate(
            nb_aliases=Count('aliases_extraction', distinct=True)
        ).filter(
            Q(nom_ouvrage__icontains=query) |
            Q(aliases_extraction__alias__icontains=query)
        ).distinct().order_by('nom_ouvrage')[:100]

    aliases = OuvrageAlias.objects.none()
    if ouvrage_selectionne:
        aliases = ouvrage_selectionne.aliases_extraction.all().order_by('alias')

    context = {
        'query': query,
        'ouvrages': ouvrages,
        'ouvrage_selectionne': ouvrage_selectionne,
        'aliases': aliases,
        'form': form,
        'total_aliases': OuvrageAlias.objects.count(),
        'verification_nav_key': 'aliases_ouvrages',
    }
    return render(request, 'accounting/gestion_aliases_ouvrages.html', context)
