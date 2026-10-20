import re
import unicodedata
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.employees.forms import (
    AvenantContratTravailForm,
    ContratArticleModeleForm,
    ContratTravailCreateForm,
    ContratTravailForm,
)
from apps.employees.models import (
    AvenantArticleModifie,
    AvenantContratTravail,
    Contrat,
    ContratArticleModele,
    ContratTravail,
    ContratTravailArticle,
    Employe,
)
from apps.employees.models_evaluation import FichePoste
from apps.organization.models import Organisation

DEFAULT_CONTRAT_ARTICLES = [
    (
        1,
        "Le present contrat est etabli pour une duree determinee d'[Duree contrat] renouvelable. "
        "La prise du poste est comptee a partir du [Debut contrat] et se terminera le [Fin contrat]. "
        "Le travailleur effectuera une periode d'essai de six (6) mois a compter du meme jour.",
    ),
    (
        2,
        "Le lieu d'affectation du travailleur correspond aux zones d'intervention de l'ONG [Organisation] : "
        "les districts [Nom Base].",
    ),
    (
        3,
        "Le travailleur est recrute en qualite de [Poste] categorie professionnelle [Categorie]. "
        "Il lui sera alloue une remuneration mensuelle brute de [Salaire brut] MGA ([Salaire en lettre]).",
    ),
    (
        4,
        "Le travailleur s'engage a consacrer tout son temps et toute son activite dans la limite de la "
        "reglementation en vigueur aux fonctions qui lui sont confiees, a se conformer a toutes les "
        "instructions qui lui seront donnees a cet effet par l'employeur, et a ne fournir pendant la duree "
        "et apres l'expiration du contrat, aucune information confidentielle dont il aura pu acquerir "
        "connaissance a l'occasion de son travail.",
    ),
    (
        5,
        "Le travailleur, apres avoir lu et pris connaissance, accepte de se conformer aux termes du reglement "
        "interieur en vigueur au sein de [Organisation].",
    ),
    (
        6,
        "Le travailleur acquiert droit au conge paye a la charge de l'employeur a raison de 2 jours et demi "
        "calendaires par mois de service effectif.",
    ),
    (
        7,
        "Le travailleur sera affilie par les soins de l'employeur aupres de la CNAPS et beneficiera d'une "
        "couverture sociale maladie.",
    ),
    (
        8,
        "La resiliation du present contrat peut intervenir a tout moment, par l'une ou l'autre des parties, "
        "sous reserve de donner un preavis d'une duree fixee par la legislation en vigueur.",
    ),
    (
        9,
        "Le reglement de tout litige relatif a l'execution du present contrat sera de la competence de "
        "l'Inspection du Travail et du Tribunal du Travail du lieu de l'emploi. Le travailleur peut egalement, "
        "apres rupture de contrat de travail, saisir le tribunal du lieu de son domicile ou celui du domicile "
        "de l'employeur (Article 275 Alinea 2 code du travail).",
    ),
    (
        10,
        "Pour ce qui n'est pas stipule dans le present contrat, les parties s'en remettent au Code du Travail "
        "et a ses textes d'application.",
    ),
]


def _get_user_organisation(user):
    employe = getattr(user, 'employe', None)
    if employe and employe.base:
        return employe.base.organisation
    return None


def _get_organisation_directeur(organisation):
    if not organisation:
        return None
    return (
        Employe.objects.select_related('poste')
        .filter(
            base__organisation=organisation,
            date_debauchage__isnull=True,
            poste__nom_poste='Directeur',
        )
        .order_by('base__nom_base', 'nom', 'prenom')
        .first()
    )


def _normalize_token(token):
    if not token:
        return ''
    normalized = unicodedata.normalize('NFKD', token)
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '', ascii_only.lower())


def _format_date_fr(value):
    if not value:
        return '-'
    return value.strftime('%d/%m/%Y')


def _format_money(value):
    if value in (None, ''):
        return '0'
    amount = Decimal(value)
    if amount == amount.to_integral_value():
        return f"{int(amount):,}".replace(',', ' ')
    return f"{amount:,.2f}".replace(',', ' ').replace('.', ',')


def _amount_to_words(value):
    if value in (None, ''):
        return 'ZERO ARIARY'
    try:
        from num2words import num2words

        return num2words(int(Decimal(value)), lang='fr').upper() + " ARIARY"
    except Exception:
        return str(value)


def _default_duree_contrat(contrat):
    if not contrat.fin_contrat:
        return "indeterminee"
    if not contrat.debut_contrat:
        return "determinee"
    delta_days = max((contrat.fin_contrat - contrat.debut_contrat).days + 1, 1)
    months = max(round(delta_days / 30), 1)
    return f"{months} mois"


def _build_placeholders(contrat_travail):
    contrat = contrat_travail.contrat
    employe = contrat.employe
    poste = contrat.poste or employe.poste
    organisation = contrat_travail.organisation
    base = employe.base
    salaire = contrat.salaire_brut_base or 0

    mapping = {
        'organisation': organisation.nom_organisation if organisation else '-',
        'nomcompletdirecteur': contrat_travail.nom_directeur or '-',
        'postedirecteur': contrat_travail.poste_directeur or '-',
        'nomcompletemploye': employe.nom_complet,
        'adresse': contrat_travail.adresse_employe or '-',
        'datedenaissance': _format_date_fr(employe.date_naissance),
        'lieudenaissance': contrat_travail.lieu_naissance_employe or '-',
        'ncin': employe.numero_cin or '-',
        'numerocin': employe.numero_cin or '-',
        'lieudelivrancecin': contrat_travail.lieu_delivrance_cin or '-',
        'datecin': _format_date_fr(contrat_travail.date_delivrance_cin),
        'dureecontrat': contrat_travail.duree_contrat_texte or _default_duree_contrat(contrat),
        'debutcontrat': _format_date_fr(contrat.debut_contrat),
        'fincontrat': _format_date_fr(contrat.fin_contrat) if contrat.fin_contrat else 'non definie',
        'nombase': contrat_travail.districts_affectation or (base.nom_base if base else '-'),
        'poste': poste.nom_poste if poste else '-',
        'categorie': contrat.categorie_professionnel or '-',
        'salairebrut': _format_money(salaire),
        'salaireenlettre': _amount_to_words(salaire),
        'lieucontrat': contrat_travail.lieu_contrat or '-',
        'datedebutcontrat': _format_date_fr(contrat.debut_contrat),
        'districts': contrat_travail.districts_affectation or '-',
    }
    return mapping


def _render_placeholders(content, mapping):
    if not content:
        return ''

    def _replace(match):
        key = _normalize_token(match.group(1))
        if key in mapping:
            return str(mapping[key])
        return match.group(0)

    return re.sub(r'\[([^\]]+)\]', _replace, content)


def _ensure_default_article_modeles(organisation):
    if not organisation:
        return 0
    created = 0
    for numero, contenu in DEFAULT_CONTRAT_ARTICLES:
        _, was_created = ContratArticleModele.objects.get_or_create(
            organisation=organisation,
            numero_article=numero,
            defaults={'contenu_article': contenu, 'actif': True},
        )
        if was_created:
            created += 1
    return created


def _sync_articles_from_modeles(contrat_travail, force_refresh=False):
    modeles = ContratArticleModele.objects.filter(
        organisation=contrat_travail.organisation,
        actif=True,
    ).order_by('numero_article')
    if not modeles.exists():
        _ensure_default_article_modeles(contrat_travail.organisation)
        modeles = ContratArticleModele.objects.filter(
            organisation=contrat_travail.organisation,
            actif=True,
        ).order_by('numero_article')

    mapping = _build_placeholders(contrat_travail)
    existing = {item.numero_article: item for item in contrat_travail.articles.all()}
    created_count = 0
    updated_count = 0

    for modele in modeles:
        rendered = _render_placeholders(modele.contenu_article, mapping)
        article = existing.get(modele.numero_article)
        if article:
            changed = False
            if article.modele_id != modele.id:
                article.modele = modele
                changed = True
            if force_refresh:
                if article.contenu_article != rendered:
                    article.contenu_article = rendered
                    changed = True
                if article.contenu_reference != rendered:
                    article.contenu_reference = rendered
                    changed = True
            else:
                if not article.contenu_article:
                    article.contenu_article = rendered
                    changed = True
                if not article.contenu_reference:
                    article.contenu_reference = rendered
                    changed = True
            if changed:
                article.save()
                updated_count += 1
        else:
            ContratTravailArticle.objects.create(
                contrat_travail=contrat_travail,
                modele=modele,
                numero_article=modele.numero_article,
                contenu_article=rendered,
                contenu_reference=rendered,
            )
            created_count += 1

    return created_count, updated_count


def _refresh_articles_values_without_override(contrat_travail):
    mapping = _build_placeholders(contrat_travail)
    refreshed_count = 0
    for article in contrat_travail.articles.select_related('modele').all():
        if not article.modele:
            continue
        # If user already edited article manually, do not overwrite.
        if (article.contenu_article or '') != (article.contenu_reference or ''):
            continue
        rendered = _render_placeholders(article.modele.contenu_article, mapping)
        if article.contenu_article != rendered:
            article.contenu_article = rendered
            article.save(update_fields=['contenu_article', 'date_modification'])
            refreshed_count += 1
    return refreshed_count


def _get_changed_articles(contrat_travail):
    changed = []
    for article in contrat_travail.articles.all().order_by('numero_article'):
        if (article.contenu_article or '').strip() != (article.contenu_reference or '').strip():
            changed.append(article)
    return changed


def _build_contrat_travail_initial(contrat, organisation_user=None):
    employe = contrat.employe
    organisation = organisation_user or (employe.base.organisation if employe and employe.base else None)
    directeur = _get_organisation_directeur(organisation)
    base_name = employe.base.nom_base if employe and employe.base else ''

    nom_directeur = ''
    poste_directeur = 'Directeur'
    if directeur:
        nom_directeur = directeur.nom_complet
        if directeur.poste:
            poste_directeur = directeur.poste.nom_poste

    return {
        'nom_directeur': nom_directeur,
        'poste_directeur': poste_directeur,
        'districts_affectation': base_name,
        'adresse_employe': getattr(employe, 'adresse', '') or '',
        'lieu_naissance_employe': getattr(employe, 'lieu_naissance', '') or '',
        'lieu_delivrance_cin': getattr(employe, 'lieu_delivrance_cin', '') or '',
        'date_delivrance_cin': getattr(employe, 'date_delivrance_cin', None),
        'duree_contrat_texte': _default_duree_contrat(contrat),
        'lieu_contrat': organisation.localite if organisation and organisation.localite else base_name,
        'date_signature': contrat.debut_contrat,
    }


def _sync_employe_identity_fields_from_contrat(contrat_travail):
    contrat = getattr(contrat_travail, 'contrat', None)
    employe = getattr(contrat, 'employe', None)
    if not employe:
        return 0

    updates = {}
    field_map = {
        'adresse': 'adresse_employe',
        'lieu_naissance': 'lieu_naissance_employe',
        'lieu_delivrance_cin': 'lieu_delivrance_cin',
        'date_delivrance_cin': 'date_delivrance_cin',
    }

    for employe_field, contrat_field in field_map.items():
        value = getattr(contrat_travail, contrat_field, None)
        if isinstance(value, str):
            value = value.strip()
        if value in (None, ''):
            # Ne pas ecraser la fiche employe avec des valeurs vides.
            continue

        current = getattr(employe, employe_field, None)
        if isinstance(current, str):
            current = current.strip()
        if current != value:
            updates[employe_field] = value

    if updates:
        for field_name, value in updates.items():
            setattr(employe, field_name, value)
        employe.save(update_fields=list(updates.keys()))

    return len(updates)


def _get_fiches_for_poste(poste):
    if not poste:
        return FichePoste.objects.none()

    fiches = FichePoste.objects.filter(
        activites_postes__poste=poste,
        a_evaluer=True,
    ).distinct()
    if fiches.exists():
        return fiches.order_by('ordre', 'tache')

    poste_nom = (poste.nom_poste or '').strip()
    if not poste_nom:
        return fiches.order_by('ordre', 'tache')

    return FichePoste.objects.filter(
        activites_postes__poste__isnull=True,
        activites_postes__nom__icontains=poste_nom,
        a_evaluer=True,
    ).distinct().order_by('ordre', 'tache')


def _get_scoped_contrats_queryset(user):
    queryset = Contrat.objects.select_related(
        'employe',
        'employe__base',
        'employe__base__organisation',
        'poste',
    )
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation = _get_user_organisation(user)
    if not organisation:
        return queryset.none()
    return queryset.filter(employe__base__organisation=organisation)


def _get_scoped_contrats_travail_queryset(user):
    queryset = ContratTravail.objects.select_related(
        'contrat',
        'contrat__employe',
        'contrat__employe__base',
        'contrat__employe__base__organisation',
        'contrat__poste',
        'organisation',
    )
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation = _get_user_organisation(user)
    if not organisation:
        return queryset.none()
    return queryset.filter(organisation=organisation)


@login_required
def contrat_travail_list(request):
    queryset = _get_scoped_contrats_travail_queryset(request.user).order_by('-date_creation')
    search = (request.GET.get('search') or '').strip()
    if search:
        queryset = queryset.filter(
            Q(contrat__employe__nom__icontains=search)
            | Q(contrat__employe__prenom__icontains=search)
            | Q(contrat__employe__surnom__icontains=search)
            | Q(contrat__employe__nom_employe__icontains=search)
        )

    return render(
        request,
        'employees/contrat_travail_list.html',
        {
            'title': 'Contrats de travail et avenants',
            'contrats_travail': queryset,
            'search': search,
        },
    )


@login_required
def contrat_travail_open_for_contrat(request, contrat_id):
    contrat = get_object_or_404(_get_scoped_contrats_queryset(request.user), id=contrat_id)
    contrat_travail = getattr(contrat, 'contrat_travail', None)
    if contrat_travail:
        return redirect('employees:contrat_travail_detail', contrat_travail_id=contrat_travail.id)
    return redirect(f"{redirect('employees:contrat_travail_create').url}?contrat_id={contrat.id}")


@login_required
def contrat_travail_create(request):
    organisation_user = _get_user_organisation(request.user)
    contrats_qs = _get_scoped_contrats_queryset(request.user).exclude(contrat_travail__isnull=False)
    if organisation_user:
        contrats_qs = contrats_qs.filter(employe__base__organisation=organisation_user)
    contrats_qs = contrats_qs.select_related('employe', 'employe__base', 'employe__base__organisation')

    initial = {}
    contrat_id = request.GET.get('contrat_id')
    selected_contrat = None

    if contrat_id:
        selected_contrat = contrats_qs.filter(id=contrat_id).first()

    form_organisation = organisation_user
    if selected_contrat and selected_contrat.employe and selected_contrat.employe.base:
        form_organisation = selected_contrat.employe.base.organisation
        initial.update(_build_contrat_travail_initial(selected_contrat, organisation_user=form_organisation))
        initial['contrat'] = selected_contrat

    if request.method == 'POST':
        post_contrat = contrats_qs.filter(id=request.POST.get('contrat')).first()
        if post_contrat and post_contrat.employe and post_contrat.employe.base:
            form_organisation = post_contrat.employe.base.organisation

        form = ContratTravailCreateForm(
            request.POST,
            organisation=form_organisation,
            contrat_queryset=contrats_qs.order_by('-debut_contrat'),
        )
        if form.is_valid():
            contrat_travail = form.save(commit=False)
            contrat = form.cleaned_data['contrat']
            organisation = contrat.employe.base.organisation if contrat.employe and contrat.employe.base else None
            if not organisation:
                messages.error(request, "Organisation introuvable pour ce contrat.")
                return redirect('employees:contrat_travail_create')
            contrat_travail.organisation = organisation
            contrat_travail.save()
            synced_count = _sync_employe_identity_fields_from_contrat(contrat_travail)
            _sync_articles_from_modeles(contrat_travail, force_refresh=True)
            if synced_count:
                messages.success(
                    request,
                    f"Contrat de travail genere avec ses articles. Fiche employe mise a jour ({synced_count} champ(s)).",
                )
            else:
                messages.success(request, "Contrat de travail genere avec ses articles.")
            return redirect('employees:contrat_travail_detail', contrat_travail_id=contrat_travail.id)
        messages.error(request, "Le formulaire contient des erreurs.")
    else:
        form = ContratTravailCreateForm(
            initial=initial,
            organisation=form_organisation,
            contrat_queryset=contrats_qs.order_by('-debut_contrat'),
        )

    return render(
        request,
        'employees/contrat_travail_create.html',
        {
            'title': 'Nouveau contrat de travail',
            'form': form,
        },
    )


@login_required
def contrat_article_modele_list(request):
    selected_org = _get_user_organisation(request.user)
    if not selected_org and getattr(request.user, 'is_superuser', False):
        selected_org = Organisation.objects.order_by('nom_organisation').first()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'init_default':
            if not selected_org:
                messages.error(request, "Selectionnez une organisation.")
            else:
                created = _ensure_default_article_modeles(selected_org)
                messages.success(request, f"{created} article(s) modele crees.")
            return redirect('employees:contrat_article_modele_list')

        form = ContratArticleModeleForm(request.POST)
        if form.is_valid():
            if not selected_org:
                messages.error(request, "Selectionnez une organisation avant de creer un article.")
            else:
                article = form.save(commit=False)
                article.organisation = selected_org
                article.save()
                messages.success(request, "Article modele enregistre.")
            return redirect('employees:contrat_article_modele_list')
        messages.error(request, "Le formulaire d'article contient des erreurs.")
    else:
        form = ContratArticleModeleForm()

    if selected_org and not ContratArticleModele.objects.filter(organisation=selected_org).exists():
        _ensure_default_article_modeles(selected_org)

    articles = ContratArticleModele.objects.none()
    if selected_org:
        articles = ContratArticleModele.objects.filter(organisation=selected_org).order_by('numero_article')

    return render(
        request,
        'employees/contrat_article_modele_list.html',
        {
            'title': "Modeles d'articles de contrat",
            'form': form,
            'articles': articles,
            'selected_org': selected_org,
        },
    )


@login_required
def contrat_article_modele_update(request, article_id):
    article_qs = ContratArticleModele.objects.select_related('organisation')
    organisation = _get_user_organisation(request.user)
    if not organisation and getattr(request.user, 'is_superuser', False):
        organisation = Organisation.objects.order_by('nom_organisation').first()
    article_qs = article_qs.filter(organisation=organisation) if organisation else article_qs.none()
    article = get_object_or_404(article_qs, id=article_id)

    if request.method == 'POST':
        form = ContratArticleModeleForm(request.POST, instance=article)
        if form.is_valid():
            form.save()
            messages.success(request, "Article modele modifie.")
            return redirect('employees:contrat_article_modele_list')
    else:
        form = ContratArticleModeleForm(instance=article)

    return render(
        request,
        'employees/contrat_article_modele_edit.html',
        {
            'title': "Modifier article modele",
            'form': form,
            'article': article,
        },
    )


@login_required
def contrat_article_modele_delete(request, article_id):
    if request.method != 'POST':
        return redirect('employees:contrat_article_modele_list')

    article_qs = ContratArticleModele.objects.select_related('organisation')
    organisation = _get_user_organisation(request.user)
    if not organisation and getattr(request.user, 'is_superuser', False):
        organisation = Organisation.objects.order_by('nom_organisation').first()
    article_qs = article_qs.filter(organisation=organisation) if organisation else article_qs.none()
    article = get_object_or_404(article_qs, id=article_id)
    article.delete()
    messages.success(request, "Article modele supprime.")
    return redirect('employees:contrat_article_modele_list')


@login_required
def contrat_travail_detail(request, contrat_travail_id):
    contrat_travail = get_object_or_404(
        _get_scoped_contrats_travail_queryset(request.user),
        id=contrat_travail_id,
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_meta':
            form = ContratTravailForm(request.POST, instance=contrat_travail)
            if form.is_valid():
                contrat_travail = form.save()
                synced_count = _sync_employe_identity_fields_from_contrat(contrat_travail)
                if synced_count:
                    messages.success(
                        request,
                        f"Informations du contrat mises a jour. Fiche employe synchronisee ({synced_count} champ(s)).",
                    )
                else:
                    messages.success(request, "Informations du contrat mises a jour.")
            else:
                messages.error(request, "Erreur de validation des informations du contrat.")
            return redirect('employees:contrat_travail_detail', contrat_travail_id=contrat_travail.id)

        if action == 'save_articles':
            changes = 0
            for article in contrat_travail.articles.all():
                field_name = f'article_{article.id}'
                if field_name not in request.POST:
                    continue
                new_content = (request.POST.get(field_name) or '').strip()
                if new_content != (article.contenu_article or '').strip():
                    article.contenu_article = new_content
                    article.save(update_fields=['contenu_article', 'date_modification'])
                    changes += 1
            messages.success(request, f"{changes} article(s) mis a jour.")
            return redirect('employees:contrat_travail_detail', contrat_travail_id=contrat_travail.id)

        if action == 'sync_articles':
            created_count, updated_count = _sync_articles_from_modeles(contrat_travail, force_refresh=False)
            messages.success(request, f"Synchronisation terminee: {created_count} cree(s), {updated_count} mis a jour.")
            return redirect('employees:contrat_travail_detail', contrat_travail_id=contrat_travail.id)

        if action == 'refresh_values':
            refreshed_count = _refresh_articles_values_without_override(contrat_travail)
            messages.success(request, f"{refreshed_count} article(s) recalcules depuis les valeurs du contrat.")
            return redirect('employees:contrat_travail_detail', contrat_travail_id=contrat_travail.id)

        if action == 'classer':
            contrat_travail.statut = 'classe'
            contrat_travail.date_classement = timezone.now()
            contrat_travail.save(update_fields=['statut', 'date_classement', 'date_modification'])
            messages.success(request, "Contrat classe.")
            return redirect('employees:contrat_travail_detail', contrat_travail_id=contrat_travail.id)

    form = ContratTravailForm(instance=contrat_travail)
    articles = contrat_travail.articles.all().order_by('numero_article')
    changed_articles = _get_changed_articles(contrat_travail)
    poste = contrat_travail.contrat.poste or contrat_travail.contrat.employe.poste
    fiches_poste = _get_fiches_for_poste(poste)

    return render(
        request,
        'employees/contrat_travail_detail.html',
        {
            'title': 'Contrat de travail',
            'contrat_travail': contrat_travail,
            'form': form,
            'articles': articles,
            'changed_articles': changed_articles,
            'avenants': contrat_travail.avenants.all().order_by('-numero_avenant'),
            'fiches_poste': fiches_poste,
        },
    )


@login_required
def contrat_travail_print(request, contrat_travail_id):
    contrat_travail = get_object_or_404(
        _get_scoped_contrats_travail_queryset(request.user),
        id=contrat_travail_id,
    )
    now = timezone.now()
    updates = []
    if not contrat_travail.date_impression:
        contrat_travail.date_impression = now
        updates.append('date_impression')
    if contrat_travail.statut == 'brouillon':
        contrat_travail.statut = 'imprime'
        updates.append('statut')
    if updates:
        updates.append('date_modification')
        contrat_travail.save(update_fields=updates)

    poste = contrat_travail.contrat.poste or contrat_travail.contrat.employe.poste
    fiches_poste = _get_fiches_for_poste(poste)

    return render(
        request,
        'employees/contrat_travail_print.html',
        {
            'contrat_travail': contrat_travail,
            'articles': contrat_travail.articles.all().order_by('numero_article'),
            'fiches_poste': fiches_poste,
            'placeholder_values': _build_placeholders(contrat_travail),
        },
    )


@login_required
def avenant_create(request, contrat_travail_id):
    contrat_travail = get_object_or_404(
        _get_scoped_contrats_travail_queryset(request.user),
        id=contrat_travail_id,
    )
    changed_articles = _get_changed_articles(contrat_travail)
    if not changed_articles:
        messages.warning(request, "Aucun article modifie a mettre en avenant.")
        return redirect('employees:contrat_travail_detail', contrat_travail_id=contrat_travail.id)

    if request.method == 'POST':
        form = AvenantContratTravailForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                max_num = contrat_travail.avenants.aggregate(max_num=Max('numero_avenant')).get('max_num') or 0
                avenant = form.save(commit=False)
                avenant.contrat_travail = contrat_travail
                avenant.numero_avenant = max_num + 1
                avenant.save()

                for article in changed_articles:
                    AvenantArticleModifie.objects.create(
                        avenant=avenant,
                        article_contrat=article,
                        numero_article=article.numero_article,
                        ancien_contenu=article.contenu_reference or '',
                        nouveau_contenu=article.contenu_article or '',
                    )

            messages.success(request, "Avenant cree avec les articles modifies.")
            return redirect('employees:avenant_detail', avenant_id=avenant.id)
        messages.error(request, "Le formulaire d'avenant contient des erreurs.")
    else:
        form = AvenantContratTravailForm(initial={
            'date_effet': timezone.localdate(),
            'date_signature': timezone.localdate(),
            'lieu_signature': contrat_travail.lieu_contrat,
        })

    return render(
        request,
        'employees/avenant_create.html',
        {
            'title': "Creer un avenant",
            'contrat_travail': contrat_travail,
            'form': form,
            'changed_articles': changed_articles,
        },
    )


@login_required
def avenant_detail(request, avenant_id):
    avenant_qs = AvenantContratTravail.objects.select_related(
        'contrat_travail',
        'contrat_travail__contrat',
        'contrat_travail__contrat__employe',
        'contrat_travail__contrat__employe__base',
        'contrat_travail__contrat__employe__base__organisation',
    )
    if not getattr(request.user, 'is_superuser', False):
        organisation = _get_user_organisation(request.user)
        avenant_qs = avenant_qs.filter(contrat_travail__organisation=organisation) if organisation else avenant_qs.none()
    avenant = get_object_or_404(avenant_qs, id=avenant_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_infos':
            form = AvenantContratTravailForm(request.POST, instance=avenant)
            if form.is_valid():
                form.save()
                messages.success(request, "Informations de l'avenant mises a jour.")
            else:
                messages.error(request, "Erreur de validation des informations d'avenant.")
            return redirect('employees:avenant_detail', avenant_id=avenant.id)

        if action == 'appliquer':
            with transaction.atomic():
                for ligne in avenant.articles_modifies.select_related('article_contrat').all():
                    article = ligne.article_contrat
                    if not article:
                        article = ContratTravailArticle.objects.filter(
                            contrat_travail=avenant.contrat_travail,
                            numero_article=ligne.numero_article,
                        ).first()
                    if article:
                        article.contenu_reference = ligne.nouveau_contenu
                        article.save(update_fields=['contenu_reference', 'date_modification'])
                avenant.est_applique = True
                avenant.date_application = timezone.now()
                avenant.save(update_fields=['est_applique', 'date_application', 'date_modification'])
            messages.success(request, "Avenant applique au contrat (reference mise a jour).")
            return redirect('employees:avenant_detail', avenant_id=avenant.id)

        if action == 'classer':
            avenant.statut = 'classe'
            avenant.date_classement = timezone.now()
            avenant.save(update_fields=['statut', 'date_classement', 'date_modification'])
            messages.success(request, "Avenant classe.")
            return redirect('employees:avenant_detail', avenant_id=avenant.id)

    form = AvenantContratTravailForm(instance=avenant)
    return render(
        request,
        'employees/avenant_detail.html',
        {
            'title': 'Avenant de contrat',
            'avenant': avenant,
            'form': form,
            'articles_modifies': avenant.articles_modifies.all().order_by('numero_article'),
        },
    )


@login_required
def avenant_print(request, avenant_id):
    avenant_qs = AvenantContratTravail.objects.select_related(
        'contrat_travail',
        'contrat_travail__contrat',
        'contrat_travail__contrat__employe',
        'contrat_travail__organisation',
    )
    if not getattr(request.user, 'is_superuser', False):
        organisation = _get_user_organisation(request.user)
        avenant_qs = avenant_qs.filter(contrat_travail__organisation=organisation) if organisation else avenant_qs.none()
    avenant = get_object_or_404(avenant_qs, id=avenant_id)

    now = timezone.now()
    updates = []
    if not avenant.date_impression:
        avenant.date_impression = now
        updates.append('date_impression')
    if avenant.statut == 'brouillon':
        avenant.statut = 'imprime'
        updates.append('statut')
    if updates:
        updates.append('date_modification')
        avenant.save(update_fields=updates)

    return render(
        request,
        'employees/avenant_print.html',
        {
            'avenant': avenant,
            'articles_modifies': avenant.articles_modifies.all().order_by('numero_article'),
        },
    )
