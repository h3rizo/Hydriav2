"""
Annuaire unifie des "personnes" du systeme : abonnes (PointEau), employes, autorites,
tiers et representantes des usagers. Complementaire a la recherche par mot-cle globale
(core:search / core:search_api) : ici on PARCOURT une liste filtrable (type, statut,
recherche texte), sans avoir a taper une recherche au prealable.

Chaque type garde le meme niveau de visibilite que dans sa propre page de gestion : les
employes restent scopes par organisation (comme apps.employees.views.employe_list), les
autorites/tiers/representantes restent visibles sans scoping organisation (comme sur
usagers:autorites_tiers_list et usagers:representants_list), pour ne pas introduire une
restriction plus stricte que ce que chaque module applique deja lui-meme.

Performance : pas d'UNION SQL possible entre modeles heterogenes. Pour eviter de charger
et serialiser TOUS les enregistrements de chaque table a chaque changement de page (lent
avec ~3800 lignes), on ne recupere en objets complets QUE les identifiants necessaires a
la page demandee : chaque queryset est trie et projete en (type, id) via values_list
(leger), fusionne/trie en Python, puis seule la tranche de la page courante est re-requetee
par type avec select_related pour la serialisation complete.
"""

import json

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from apps.billing.models import Fournisseur, PointEau
from apps.employees.models import Employe
from apps.usagers.models import Autorite, RepresentantUsager, TiersParticipant


PERSONNE_TYPES = [
    ('abonne', "Abonné"),
    ('employe', "Employé"),
    ('representant', "Représentante des usagers"),
    ('autorite', "Autorité"),
    ('tiers', "Tiers"),
    ('fournisseur', "Fournisseur"),
]

PAGE_SIZE = 30


def _serialize_abonne(p):
    return {
        'type': 'abonne',
        'type_display': 'Abonné',
        'id': str(p.id),
        'nom': p.nomabonne or 'Sans nom',
        'sous_titre': (
            f"IDXLS {p.idxls or '-'} · "
            f"{p.ouvrage.nom_ouvrage if p.ouvrage_id and p.ouvrage else 'Sans ouvrage'}"
        ),
        'contact': p.numeroteleph or p.contactabonne or '-',
        'actif': p.is_active,
        'icon': 'fa-tint',
        'detail_url': f"/recherche/details/point_eau/{p.id}/",
    }


def _serialize_employe(e):
    est_actif = e.date_debauchage is None
    return {
        'type': 'employe',
        'type_display': 'Employé',
        'id': str(e.id),
        'nom': e.nom_affichage,
        'sous_titre': e.poste.nom_poste if e.poste_id and e.poste else '-',
        'contact': e.telephone or e.mail or '-',
        'actif': est_actif,
        'icon': 'fa-user',
        'detail_url': f"/recherche/details/employe/{e.id}/",
    }


def _serialize_representant(r):
    return {
        'type': 'representant',
        'type_display': 'Représentante des usagers',
        'id': str(r.id),
        'nom': r.nom or 'Sans nom',
        'sous_titre': r.village.nom_village if r.village_id and r.village else '-',
        'contact': r.contact or '-',
        'actif': r.est_actif,
        'icon': 'fa-user-tie',
        'detail_url': f"/recherche/details/representant/{r.id}/",
    }


def _serialize_autorite(a):
    return {
        'type': 'autorite',
        'type_display': 'Autorité',
        'id': str(a.id),
        'nom': a.nom,
        'sous_titre': a.get_type_autorite_display() or a.zone_affichee or '-',
        'contact': a.contact or a.email or '-',
        'actif': a.actif,
        'icon': 'fa-landmark',
        'detail_url': f"/recherche/details/autorite/{a.id}/",
    }


def _serialize_tiers(t):
    return {
        'type': 'tiers',
        'type_display': 'Tiers',
        'id': str(t.id),
        'nom': t.nom,
        'sous_titre': t.organisme or t.get_type_tiers_display() or '-',
        'contact': t.contact or t.email or '-',
        'actif': t.actif,
        'icon': 'fa-handshake',
        'detail_url': f"/recherche/details/tiers/{t.id}/",
    }


def _serialize_fournisseur(f):
    type_display = f.get_type_fournisseur_display() if f.type_fournisseur else '-'
    return {
        'type': 'fournisseur',
        'type_display': 'Fournisseur',
        'id': str(f.id),
        'nom': f.nom_fournisseur,
        'sous_titre': type_display,
        'contact': f.telephone or f.email or '-',
        'actif': f.actif,
        'icon': 'fa-truck',
        'detail_url': f"/recherche/details/fournisseur/{f.id}/",
    }


def _get_user_organisation_for_employes(user):
    """Meme regle que apps.employees.views.employe_list : organisation de la base de
    l'employe connecte, ou None (pas de restriction) si l'utilisateur n'a pas d'employe lie."""
    if hasattr(user, 'employe') and user.employe and user.employe.base:
        return user.employe.base.organisation
    return None


# Chaque entree : (type, queryset_de_base_fn, champ_de_tri, fn_serialisation, select_related)
# queryset_de_base_fn(request) retourne un queryset NON filtre par recherche/statut (juste
# le scoping de visibilite, ex: organisation pour employe).

def _employes_de_l_ouvrage(s):
    """Ids des employes affectes a un ouvrage dont le nom contient `s` : responsables
    actuels (EmployeOuvrages) ou employe de la modalite de gestion active.

    Sous-requete `id__in` plutot que jointure directe : un employe affecte a plusieurs
    ouvrages correspondants ne doit apparaitre qu'une fois dans la passe 1 (values_list)."""
    from apps.billing.models import ModaliteGestion
    from apps.employees.models import EmployeOuvrages

    responsables = EmployeOuvrages.objects.filter(
        date_fin__isnull=True, ouvrage__nom_ouvrage__icontains=s,
    ).values('employe_id')
    gestionnaires = ModaliteGestion.objects.filter(
        date_fin__isnull=True, employe__isnull=False, ouvrage__nom_ouvrage__icontains=s,
    ).values('employe_id')
    return Q(id__in=responsables) | Q(id__in=gestionnaires)


def _representants_de_l_ouvrage(s):
    """Representantes des villages desservis (via les points d'eau) par un ouvrage dont
    le nom contient `s`. RepresentantUsager n'a pas de lien direct vers l'ouvrage."""
    villages = PointEau.objects.filter(
        ouvrage__nom_ouvrage__icontains=s, parcelle__village__isnull=False,
    ).values('parcelle__village_id')
    return Q(village_id__in=villages)


def _qs_abonne(request):
    return PointEau.objects.all()


def _qs_employe(request):
    qs = Employe.objects.all()
    organisation = _get_user_organisation_for_employes(request.user)
    if organisation:
        qs = qs.filter(base__organisation=organisation)
    return qs


def _qs_representant(request):
    return RepresentantUsager.objects.all()


def _qs_autorite(request):
    return Autorite.objects.all()


def _qs_tiers(request):
    return TiersParticipant.objects.all()


def _qs_fournisseur(request):
    return Fournisseur.objects.all()


TYPE_CONFIG = {
    'abonne': {
        'queryset_fn': _qs_abonne,
        'order_by': 'nomabonne',
        'serialize': _serialize_abonne,
        'select_related': ['ouvrage'],
        'search_q': lambda s: (
            Q(nomabonne__icontains=s) | Q(contactabonne__icontains=s) | Q(numeroteleph__icontains=s) |
            Q(ouvrage__nom_ouvrage__icontains=s) | Q(idxls__iexact=s)
        ),
        # Coherent avec PointEau.is_active : actif = branche ET pas de date d'arret.
        'statut_q': {
            'actif': Q(datebranchement__isnull=False, datearretbranchement__isnull=True),
            'inactif': Q(datebranchement__isnull=True) | Q(datearretbranchement__isnull=False),
        },
        # Champs reels derriere les 2 champs generiques "nom"/"telephone" du modal d'edition
        # rapide (cf. personne_update_champs) : nom du modele -> nom du champ ORM.
        'nom_field': 'nomabonne',
        # Vrai champ telephone de l'abonne (celui des rappels SMS) ; contactabonne est un
        # champ "Contact" libre, affiche en repli seulement.
        'contact_field': 'numeroteleph',
        # Second numero (numeroteleph est limite a 20 caracteres, donc un seul numero).
        # Les rappels SMS n'utilisent que numeroteleph.
        'contact2_field': 'contactabonne',
    },
    'employe': {
        'queryset_fn': _qs_employe,
        'order_by': ('nom', 'surnom'),
        'serialize': _serialize_employe,
        'select_related': ['poste', 'base', 'base__organisation'],
        'search_q': lambda s: (
            Q(nom__icontains=s) | Q(prenom__icontains=s) | Q(surnom__icontains=s) |
            Q(mail__icontains=s) | Q(telephone__icontains=s) | _employes_de_l_ouvrage(s)
        ),
        'statut_q': {
            'actif': Q(date_debauchage__isnull=True),
            'inactif': Q(date_debauchage__isnull=False),
        },
        # Employe n'a pas de "nom complet" unique (nom/prenom/surnom separes) : le champ
        # "nom" du modal edite le nom de famille, coherent avec le tri/recherche existants.
        'nom_field': 'nom',
        'contact_field': 'telephone',
        'email_field': 'mail',
    },
    'representant': {
        'queryset_fn': _qs_representant,
        'order_by': 'nom',
        'serialize': _serialize_representant,
        'select_related': ['village__fokontany__commune'],
        'search_q': lambda s: (
            Q(nom__icontains=s) | Q(contact__icontains=s) | Q(village__nom_village__icontains=s) |
            _representants_de_l_ouvrage(s)
        ),
        'statut_q': {
            'actif': Q(actif=True),
            'inactif': Q(actif=False),
        },
        'nom_field': 'nom',
        'contact_field': 'contact',
    },
    'autorite': {
        'queryset_fn': _qs_autorite,
        'order_by': 'nom',
        'serialize': _serialize_autorite,
        'select_related': ['fokontany', 'commune', 'district', 'region'],
        'search_q': lambda s: Q(nom__icontains=s) | Q(fonction__icontains=s) | Q(contact__icontains=s) | Q(email__icontains=s),
        'statut_q': {
            'actif': Q(actif=True),
            'inactif': Q(actif=False),
        },
        'nom_field': 'nom',
        'contact_field': 'contact',
        'email_field': 'email',
    },
    'tiers': {
        'queryset_fn': _qs_tiers,
        'order_by': 'nom',
        'serialize': _serialize_tiers,
        'select_related': [],
        'search_q': lambda s: Q(nom__icontains=s) | Q(organisme__icontains=s) | Q(fonction__icontains=s) | Q(contact__icontains=s) | Q(email__icontains=s),
        'statut_q': {
            'actif': Q(actif=True),
            'inactif': Q(actif=False),
        },
        'nom_field': 'nom',
        'contact_field': 'contact',
        'email_field': 'email',
    },
    'fournisseur': {
        'queryset_fn': _qs_fournisseur,
        'order_by': 'nom_fournisseur',
        'serialize': _serialize_fournisseur,
        'select_related': [],
        'search_q': lambda s: (
            Q(nom_fournisseur__icontains=s) | Q(telephone__icontains=s) |
            Q(email__icontains=s) | Q(numero_nif__icontains=s) | Q(code_tiers__icontains=s)
        ),
        'statut_q': {
            'actif': Q(actif=True),
            'inactif': Q(actif=False),
        },
        'nom_field': 'nom_fournisseur',
        'contact_field': 'telephone',
        'email_field': 'email',
    },
}

# Type de la page de detail (/recherche/details/<entity_type>/) -> cle TYPE_CONFIG.
DETAIL_TYPE_TO_KEY = {
    'point_eau': 'abonne',
    'employe': 'employe',
    'representant': 'representant',
    'autorite': 'autorite',
    'tiers': 'tiers',
    'fournisseur': 'fournisseur',
}


def contexte_coordonnees(request, entity_type, entity_id):
    """Valeurs actuelles pour le bloc "Coordonnees" editable de la page de detail
    (None si ce type d'entite n'est pas une personne ou n'est pas visible)."""
    type_key = DETAIL_TYPE_TO_KEY.get(entity_type)
    if not type_key:
        return None
    config = TYPE_CONFIG[type_key]
    try:
        obj = config['queryset_fn'](request).filter(id=entity_id).first()
    except (ValueError, TypeError):
        return None
    if obj is None:
        return None
    email_field = config.get('email_field')
    return {
        'type_key': type_key,
        'entity_id': str(obj.id),
        'nom': getattr(obj, config['nom_field']) or '',
        'telephone': getattr(obj, config['contact_field']) or '',
        'has_telephone2': bool(config.get('contact2_field')),
        'telephone2': (getattr(obj, config['contact2_field']) or '') if config.get('contact2_field') else '',
        'has_email': bool(email_field),
        'email': (getattr(obj, email_field) or '') if email_field else '',
    }


def _filtered_queryset(request, type_key, statut_filter, search):
    """Queryset filtre (recherche + statut + scoping) mais PAS encore trie/limite, pour un type."""
    config = TYPE_CONFIG[type_key]
    qs = config['queryset_fn'](request)
    if search:
        qs = qs.filter(config['search_q'](search))
    statut_q = config['statut_q'].get(statut_filter)
    if statut_q is not None:
        qs = qs.filter(statut_q)
    return qs


def _order_by(type_key):
    order = TYPE_CONFIG[type_key]['order_by']
    return order if isinstance(order, (list, tuple)) else (order,)


@login_required
def personnes_annuaire(request):
    """Page annuaire : rend le squelette, la liste est chargee/filtree en JS via personnes_annuaire_json."""
    return render(request, 'core/personnes_annuaire.html', {
        'title': 'Annuaire des personnes',
        'personne_types': PERSONNE_TYPES,
    })


@login_required
@require_http_methods(["GET"])
def personnes_annuaire_json(request):
    """
    API paginee de l'annuaire. Parametres : type (abonne/employe/representant/autorite/tiers,
    vide = tous), statut (actif/inactif/tous, defaut actif), search (texte libre), page.

    Strategie a 2 passes pour rester rapide meme avec ~3800 lignes au total :
    1. Pour chaque type actif, ne recuperer que (nom, id) via values_list (leger, pas de
       select_related), fusionner et trier en Python -> determine l'ordre global et permet
       de compter sans jamais instancier les objets complets.
    2. Ne re-requeter en objets complets (avec select_related, pour serialisation) que les
       identifiants qui tombent dans la page demandee.
    """
    type_filter = (request.GET.get('type') or '').strip()
    if type_filter and type_filter not in dict(PERSONNE_TYPES):
        type_filter = ''
    statut_filter = (request.GET.get('statut') or 'actif').strip()
    search = (request.GET.get('search') or '').strip()

    try:
        page_number = max(1, int(request.GET.get('page', '1')))
    except ValueError:
        page_number = 1

    types_a_charger = [type_filter] if type_filter else [v for v, _ in PERSONNE_TYPES]

    # Passe 1 : pour chaque type, ne recuperer que (id, nom) via values_list (leger, pas de
    # select_related). Fusionne en une seule liste (type, id, nom_normalise) triee en Python
    # sur le nom, ce qui donne l'ordre alphabetique global cross-type et le total exact.
    entrees = []
    compte_par_type = {}
    for type_key in types_a_charger:
        qs = _filtered_queryset(request, type_key, statut_filter, search)
        nom_field = _order_by(type_key)[0]
        rows = list(qs.values_list('id', nom_field))
        compte_par_type[type_key] = len(rows)
        entrees.extend((type_key, row_id, (row_nom or '').lower()) for row_id, row_nom in rows)

    entrees.sort(key=lambda e: e[2])

    total = len(entrees)
    num_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page_number = min(page_number, num_pages)
    start = (page_number - 1) * PAGE_SIZE
    page_entrees = entrees[start:start + PAGE_SIZE]

    # Passe 2 : ne recharger en objets complets (select_related) que les ids de cette page,
    # regroupes par type pour minimiser le nombre de requetes (1 par type present sur la page).
    ids_par_type = {}
    for type_key, row_id, _ in page_entrees:
        ids_par_type.setdefault(type_key, []).append(row_id)

    objets_par_id = {}
    for type_key, ids in ids_par_type.items():
        config = TYPE_CONFIG[type_key]
        qs = config['queryset_fn'](request).filter(id__in=ids)
        if config['select_related']:
            qs = qs.select_related(*config['select_related'])
        for obj in qs:
            objets_par_id[(type_key, obj.id)] = config['serialize'](obj)

    results = [
        objets_par_id[(type_key, row_id)]
        for type_key, row_id, _ in page_entrees
        if (type_key, row_id) in objets_par_id
    ]

    return JsonResponse({
        'success': True,
        'results': results,
        'total': total,
        'page': page_number,
        'num_pages': num_pages,
        'has_next': page_number < num_pages,
        'has_previous': page_number > 1,
        'compte_par_type': compte_par_type,
    })


@login_required
@require_http_methods(["POST"])
def personne_update_champs(request, type_key, entity_id):
    """
    Modal d'edition rapide (nom + telephone) depuis l'annuaire. Le nom du champ ORM reel
    varie selon le type (cf. TYPE_CONFIG[type]['nom_field'/'contact_field']) : cette vue
    fait la correspondance pour presenter un contrat JSON uniforme {nom, telephone} au
    frontend, quelle que soit la table modifiee derriere.

    Reutilise le queryset scope de chaque type (queryset_fn) pour le get_object_or_404 :
    un employe hors organisation de l'utilisateur connecte n'est ainsi ni visible ni
    modifiable via cette API, comme pour la liste de l'annuaire.
    """
    if type_key not in TYPE_CONFIG:
        return JsonResponse({'success': False, 'error': 'Type de personne invalide.'}, status=400)

    config = TYPE_CONFIG[type_key]
    obj = get_object_or_404(config['queryset_fn'](request), id=entity_id)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide.'}, status=400)

    # Mise a jour PARTIELLE : seules les cles presentes dans le JSON sont modifiees, ce qui
    # permet a la page de detail de n'envoyer que telephone/email sans reposter le nom.
    champs_modifies = []
    if 'nom' in data:
        nom = (data.get('nom') or '').strip()
        if not nom:
            return JsonResponse({'success': False, 'error': 'Le nom est obligatoire.'}, status=400)
        setattr(obj, config['nom_field'], nom)
        champs_modifies.append(config['nom_field'])
    if 'telephone' in data:
        telephone = (data.get('telephone') or '').strip()
        max_len = obj._meta.get_field(config['contact_field']).max_length
        if max_len and len(telephone) > max_len:
            return JsonResponse(
                {'success': False, 'error': f'Numéro trop long ({max_len} caractères maximum).'},
                status=400,
            )
        # Le champ telephone est partout nullable/blank : chaine vide -> None pour rester
        # coherent avec la maniere dont chaque module gere deja l'absence de contact.
        setattr(obj, config['contact_field'], telephone or None)
        champs_modifies.append(config['contact_field'])
    contact2_field = config.get('contact2_field')
    if 'telephone2' in data and contact2_field:
        telephone2 = (data.get('telephone2') or '').strip()
        setattr(obj, contact2_field, telephone2 or None)
        champs_modifies.append(contact2_field)
    email_field = config.get('email_field')
    if 'email' in data and email_field:
        email = (data.get('email') or '').strip()
        setattr(obj, email_field, email or None)
        champs_modifies.append(email_field)
    if not champs_modifies:
        return JsonResponse({'success': False, 'error': 'Aucune donnée à modifier.'}, status=400)
    obj.save(update_fields=champs_modifies)

    return JsonResponse({
        'success': True,
        'nom': getattr(obj, config['nom_field']),
        'telephone': getattr(obj, config['contact_field']) or '',
        'telephone2': (getattr(obj, contact2_field) or '') if contact2_field else '',
        'email': (getattr(obj, email_field) or '') if email_field else '',
    })


# ---------------------------------------------------------------------------
# Details enrichis (modal "Voir plus"), par type de personne.
# ---------------------------------------------------------------------------

def _details_abonne(obj):
    from apps.billing.models import PaiementForfaitaire, Releve

    paiements = list(
        PaiementForfaitaire.objects.filter(point_eau=obj)
        .order_by('-date_facture')[:10]
        .values('date_facture', 'quantite', 'montant', 'paye')
    )
    releves = list(
        Releve.objects.filter(point_eau=obj)
        .order_by('-datereleve')[:10]
        .values('datereleve', 'consommation', 'montant', 'statut')
    )

    return {
        'idxls': obj.idxls,
        'ouvrage': obj.ouvrage.nom_ouvrage if obj.ouvrage_id and obj.ouvrage else None,
        'paiements_forfaitaires_total': PaiementForfaitaire.objects.filter(point_eau=obj).count(),
        'paiements_forfaitaires_recents': [
            {
                'date': p['date_facture'].strftime('%d/%m/%Y') if p['date_facture'] else '-',
                'montant': float(p['montant']) if p['montant'] is not None else 0,
                'label': f"{p['quantite']} période(s)",
                'statut': 'Payé' if p['paye'] else 'Impayé',
            }
            for p in paiements
        ],
        'releves_total': Releve.objects.filter(point_eau=obj).count(),
        'releves_recents': [
            {
                'date': r['datereleve'].strftime('%d/%m/%Y') if r['datereleve'] else '-',
                'montant': float(r['montant']) if r['montant'] is not None else 0,
                'consommation': float(r['consommation']) if r['consommation'] is not None else None,
                'statut': dict(Releve.STATUT_CHOICES).get(r['statut'], r['statut'] or '-'),
            }
            for r in releves
        ],
    }


def _details_employe(obj):
    from apps.employees.models import EmployeOuvrages, HierarchieEmploye

    ouvrages_responsable = list(
        EmployeOuvrages.objects.filter(employe=obj, date_fin__isnull=True)
        .select_related('ouvrage')
        .order_by('-est_responsable_principal', 'ouvrage__nom_ouvrage')
    )
    superieurs = list(
        HierarchieEmploye.objects.filter(employe=obj, date_fin__isnull=True)
        .select_related('superieur')
        .order_by('-date_debut')
    )
    subordonnes = list(
        HierarchieEmploye.objects.filter(superieur=obj, date_fin__isnull=True)
        .select_related('employe')
        .order_by('employe__nom')
    )

    from apps.billing.models import ModaliteGestion
    ouvrages_gestion = list(
        ModaliteGestion.objects.filter(employe=obj, date_fin__isnull=True)
        .select_related('ouvrage').order_by('ouvrage__nom_ouvrage')
    )

    return {
        'ouvrages_gestion': [
            {'id': str(m.ouvrage_id), 'nom': m.ouvrage.nom_ouvrage if m.ouvrage else '-'}
            for m in ouvrages_gestion
        ],
        'base': obj.base.nom_base if obj.base_id and obj.base else None,
        'organisation': obj.base.organisation.nom_organisation if obj.base_id and obj.base and obj.base.organisation_id else None,
        'ouvrages_responsable': [
            {
                'id': str(eo.ouvrage_id),
                'nom': eo.ouvrage.nom_ouvrage if eo.ouvrage else '-',
                'principal': eo.est_responsable_principal,
            }
            for eo in ouvrages_responsable
        ],
        'superieurs': [
            {'nom': h.superieur.nom_affichage if h.superieur else '-'}
            for h in superieurs
        ],
        'subordonnes_total': HierarchieEmploye.objects.filter(superieur=obj, date_fin__isnull=True).count(),
        'subordonnes': [
            {'nom': h.employe.nom_affichage if h.employe else '-'}
            for h in subordonnes[:10]
        ],
    }


def _details_reunions_participant(obj):
    """Commun a representant/autorite/tiers : liste des reunions auxquelles la fiche a participe."""
    participations = list(
        obj.participations_reunions.select_related('reunion')
        .order_by('-reunion__date_reunion')[:10]
    )
    return {
        'reunions_total': obj.participations_reunions.count(),
        'reunions_recentes': [
            {
                'date': p.reunion.date_reunion.strftime('%d/%m/%Y') if p.reunion and p.reunion.date_reunion else '-',
                'objet': p.reunion.objet if p.reunion else '-',
                'reunion_id': str(p.reunion_id) if p.reunion_id else None,
                'present': p.present,
            }
            for p in participations
        ],
    }


def _details_representant(obj):
    # score_satisfaction est une @property calculee (pas une colonne), donc on charge les
    # objets complets ici plutot que .values() qui ne peut porter que des champs reels.
    data = _details_reunions_participant(obj)
    avis = list(obj.avis.order_by('-date_avis')[:10])
    data['avis_total'] = obj.avis.count()
    data['avis_recents'] = [
        {
            'date': a.date_avis.strftime('%d/%m/%Y') if a.date_avis else '-',
            'score': a.score_satisfaction,
        }
        for a in avis
    ]
    return data


def _details_fournisseur(request, obj):
    """
    Compte les lignes comptables BaseDiameX rattachees a ce fournisseur, avec le meme
    rapprochement textuel (idxls en priorite, sinon nom normalise) que
    apps.billing.views_fournisseurs.fournisseur_compta_details_api, pour rester coherent
    avec ce que la page de gestion des fournisseurs affiche deja.
    """
    from django.db.models import Case, CharField, F, Func, Value, When
    from django.db.models.functions import Lower, Trim

    from apps.accounting.views_controle_conversion import _get_scoped_diamex_queryset

    keys = set()
    if obj.idxls is not None:
        idxls_value = str(obj.idxls).strip()
        if idxls_value:
            keys.add(str(int(idxls_value)) if idxls_value.isdigit() else idxls_value.lower())
    if not keys:
        nom_value = (obj.nom_fournisseur or '').strip().lower()
        if nom_value:
            keys.add(nom_value)

    if not keys:
        return {'lignes_diamex_total': 0, 'lignes_diamex_recentes': []}

    diamex_qs = _get_scoped_diamex_queryset(request.user).annotate(
        fournisseur_norm=Case(
            When(
                fournisseur__regex=r'^\s*0*\d+\s*$',
                then=Func(Lower(Trim(F('fournisseur'))), Value(r'^0+(?!$)'), Value(''), function='REGEXP_REPLACE', output_field=CharField()),
            ),
            default=Lower(Trim(F('fournisseur'))),
            output_field=CharField(),
        )
    ).filter(fournisseur_norm__in=keys)

    lignes = list(
        diamex_qs.order_by('-date_m')[:10].values('date_m', 'description', 'montant_in', 'montant_out')
    )
    from django.db.models import Sum
    totaux = diamex_qs.aggregate(total_in=Sum('montant_in'), total_out=Sum('montant_out'))

    return {
        'lignes_diamex_total': diamex_qs.count(),
        'lignes_diamex_total_in': totaux['total_in'] or 0,
        'lignes_diamex_total_out': totaux['total_out'] or 0,
        'lignes_diamex_recentes': [
            {
                'date': l['date_m'].strftime('%d/%m/%Y') if l['date_m'] else '-',
                'description': l['description'] or '-',
                'montant': l['montant_in'] if l['montant_in'] else -(l['montant_out'] or 0),
            }
            for l in lignes
        ],
    }


DETAILS_HANDLERS = {
    'abonne': lambda request, obj: _details_abonne(obj),
    'employe': lambda request, obj: _details_employe(obj),
    'representant': lambda request, obj: _details_representant(obj),
    'autorite': lambda request, obj: _details_reunions_participant(obj),
    'tiers': lambda request, obj: _details_reunions_participant(obj),
    'fournisseur': _details_fournisseur,
}


def complements_detail(request, entity_type, entity_id):
    """Donnees liees supplementaires pour la page /recherche/details/ (fournisseur : lignes
    DiameX ; employe : ouvrages affectes). Memes fonctions que le modal de l'annuaire."""
    if entity_type == 'fournisseur':
        return _details_fournisseur(request, Fournisseur.objects.get(id=entity_id))
    if entity_type == 'employe':
        employe = Employe.objects.get(id=entity_id)
        d = _details_employe(employe)
        return {
            'ouvrages_responsable': d['ouvrages_responsable'],
            'ouvrages_gestion': d['ouvrages_gestion'],
            'superieurs': d['superieurs'],
            'subordonnes_total': d['subordonnes_total'],
            'subordonnes': d['subordonnes'],
        }
    return {}


@login_required
@require_http_methods(["GET"])
def personne_details_json(request, type_key, entity_id):
    """
    Details enrichis pour le modal "Voir plus" de l'annuaire : relations propres a chaque
    type (cf. DETAILS_HANDLERS). Reutilise le queryset scope de chaque type pour le
    get_object_or_404, comme pour l'edition rapide (personne_update_champs).
    """
    if type_key not in TYPE_CONFIG:
        return JsonResponse({'success': False, 'error': 'Type de personne invalide.'}, status=400)

    config = TYPE_CONFIG[type_key]
    obj = get_object_or_404(config['queryset_fn'](request), id=entity_id)

    handler = DETAILS_HANDLERS.get(type_key)
    details = handler(request, obj) if handler else {}

    return JsonResponse({
        'success': True,
        'details': details,
    })
