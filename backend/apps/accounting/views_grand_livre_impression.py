"""Vue imprimable du grand livre DiameX, par financement et par période.

Document destiné à l'impression (aucun élément d'interface) :

* en-tête : solde de début (depuis l'origine du journal), total de la période,
  solde de fin de période ;
* deux sections Recettes / Dépenses (et « Mouvements neutres » si des lignes ont
  une entrée égale à la sortie), chacune avec son sous-total ;
* dans chaque section, les écritures sont regroupées par Cat (compte) avec le nom
  du compte et un sous-total ;
* colonnes : Date (date reçue, JJ/MM/AAAA), Rec, Description, Detail, Fournisseur,
  Activ, CCY. Les libellés sont mis à la ligne (jamais tronqués).

Le périmètre reprend celui de la liste des écritures (organisation, lignes
sensibles masquées). Les transferts 00BOOK et les avances 00PERS sont exclus ;
les 00FND sont conservés.

Exemple :
    /comptabilite/entries/grand-livre/impression/?fin=Bailleur+A&date_debut=2025-01-01&date_fin=2025-03-31
"""

from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import render

from apps.organization.models import Compte

from .views import (
    _exclude_sensitive_diamex_lines_for_non_privileged,
    _extract_supplier_description_parts,
    _get_diamex_entries_scope_queryset,
    _get_user_organisation_id,
    _match_fournisseur_from_name,
    _normalize_text,
)

TOUS_LES_FINANCEMENTS = 'TOUS'
SANS_FINANCEMENT = '(Vide)'
SEUIL_DOCUMENT_VOLUMINEUX = 5000


def _parse_date(valeur):
    """Date ``AAAA-MM-JJ`` (ou JJ/MM/AAAA) → ``date`` ; ``None`` si vide ou invalide."""
    valeur = (valeur or '').strip()
    if not valeur:
        return None
    for format_attendu in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(valeur, format_attendu).date()
        except ValueError:
            continue
    return None


def _filtrer_fin(queryset, fin):
    """Applique le financement choisi (``(Vide)`` = lignes sans financement)."""
    if fin == SANS_FINANCEMENT:
        return queryset.filter(Q(fin__isnull=True) | Q(fin=''))
    if fin and fin != TOUS_LES_FINANCEMENTS:
        return queryset.filter(fin=fin)
    return queryset


def _libelle_financement(fin):
    if fin == SANS_FINANCEMENT:
        return 'Sans financement'
    if not fin or fin == TOUS_LES_FINANCEMENTS:
        return 'Tous les financements'
    return fin


def _libelle_cat(entry, noms_comptes):
    """« CODE - Nom du compte » (nom repris du plan comptable si la clé étrangère manque)."""
    code = (entry.compte_code or '').strip() or 'Sans compte'
    nom = ''
    if getattr(entry, 'compte', None) is not None:
        nom = (entry.compte.nom_compte or '').strip()
    if not nom:
        nom = noms_comptes.get(code, '')
    return f'{code} - {nom}' if nom else code


def _noms_comptes_manquants(codes, user):
    """Noms des comptes absents de la clé étrangère : plan comptable de l'organisation."""
    codes = [code for code in codes if code]
    if not codes:
        return {}
    comptes = Compte.objects.filter(compte__in=codes)
    organisation_id = _get_user_organisation_id(user)
    if organisation_id:
        comptes = comptes.filter(organisation_id=organisation_id)
    elif not getattr(user, 'is_superuser', False):
        comptes = comptes.none()
    return {
        (code or '').strip(): (nom or '').strip()
        for code, nom in comptes.values_list('compte', 'nom_compte')
    }


def _fournisseur_de_ligne(entry, fournisseurs_index, memo):
    """Fournisseur affiché : nom rapproché du référentiel, sinon nom lu dans le libellé."""
    parts = _extract_supplier_description_parts(entry.description or '')
    est_compte_fournisseur = bool(getattr(getattr(entry, 'compte', None), 'fournisseur_obligatoire', False))
    if not parts['nif_ou_isi'] and not est_compte_fournisseur:
        return ''
    brut = (parts['nom_fournisseur_brut'] or '').strip()
    if not brut:
        return ''
    cle = _normalize_text(brut)
    if cle in memo:
        return memo[cle]
    fournisseur = _match_fournisseur_from_name(brut, fournisseurs_index)
    libelle = getattr(fournisseur, 'nom_fournisseur', '') or brut
    memo[cle] = libelle
    return libelle


def _sens_ligne(ccy):
    if ccy > 0:
        return 'recettes'
    if ccy < 0:
        return 'depenses'
    return 'neutres'


def construire_grand_livre(base_queryset, *, date_debut, date_fin, fournisseurs_index,
                           noms_comptes=None):
    """Construit le document du grand livre (soldes, sections, regroupements par Cat).

    ``base_queryset`` : écritures du financement choisi, transferts 00BOOK/00PERS déjà
    exclus. Tout est calculé en deux requêtes (solde de début, lignes de la période) :
    aucune requête par écriture.
    """
    noms_comptes = noms_comptes or {}

    solde_avant = base_queryset.filter(date_rec__lt=date_debut).aggregate(
        total_in=Sum('montant_in'), total_out=Sum('montant_out'))
    solde_debut = (
        Decimal(str(solde_avant['total_in'] or 0)) - Decimal(str(solde_avant['total_out'] or 0))
    )

    lignes_periode = base_queryset.filter(date_rec__gte=date_debut, date_rec__lte=date_fin)
    nb_sans_date = base_queryset.filter(date_rec__isnull=True).count()

    # select_related(None) : le queryset de périmètre joint déjà journal/compte ; ici on ne
    # charge que le compte, et seulement les colonnes utiles au document.
    entree = lignes_periode.select_related(None).select_related('compte').only(
        'date_rec', 'date_m', 'rec', 'description', 'detail', 'activ', 'fin',
        'compte_code', 'montant_in', 'montant_out',
        'compte__nom_compte', 'compte__fournisseur_obligatoire',
    ).order_by('date_rec', 'id')

    memo_fournisseurs = {}
    sections = {
        'recettes': {'cle': 'recettes', 'titre': 'RECETTES (entrées)', 'groupes': [], 'total': Decimal('0'), 'nb': 0},
        'depenses': {'cle': 'depenses', 'titre': 'DÉPENSES (sorties)', 'groupes': [], 'total': Decimal('0'), 'nb': 0},
        'neutres': {'cle': 'neutres', 'titre': 'MOUVEMENTS NEUTRES (entrée = sortie)', 'groupes': [], 'total': Decimal('0'), 'nb': 0},
    }
    groupes_par_cat = {cle: {} for cle in sections}

    total_in = Decimal('0')
    total_out = Decimal('0')
    nb_lignes = 0

    for entry in entree:
        montant_in = Decimal(str(entry.montant_in or 0))
        montant_out = Decimal(str(entry.montant_out or 0))
        ccy = montant_in - montant_out
        total_in += montant_in
        total_out += montant_out
        nb_lignes += 1

        sens = _sens_ligne(ccy)
        cat_code = (entry.compte_code or '').strip()
        if cat_code not in groupes_par_cat[sens]:
            groupes_par_cat[sens][cat_code] = {
                'code': cat_code or 'Sans compte',
                'label': _libelle_cat(entry, noms_comptes),
                'lignes': [],
                'total': Decimal('0'),
                'nb': 0,
            }
        groupe = groupes_par_cat[sens][cat_code]
        ligne = {
            'date': entry.date_rec or entry.date_m,
            'rec': entry.rec,
            'description': entry.description or '',
            'detail': entry.detail or '',
            'fournisseur': _fournisseur_de_ligne(entry, fournisseurs_index, memo_fournisseurs),
            'activ': entry.activ or '',
            'ccy': ccy,
        }
        groupe['lignes'].append(ligne)
        groupe['total'] += ccy
        groupe['nb'] += 1
        sections[sens]['total'] += ccy
        sections[sens]['nb'] += 1

    for sens, groupes in groupes_par_cat.items():
        sections[sens]['groupes'] = [
            groupes[code] for code in sorted(groupes, key=lambda valeur: (_normalize_text(valeur), valeur))
        ]

    total_periode = total_in - total_out
    return {
        'solde_debut': solde_debut,
        'total_in': total_in,
        'total_out': total_out,
        'total_periode': total_periode,
        'solde_fin': solde_debut + total_periode,
        'sections': [sections['recettes'], sections['depenses'], sections['neutres']],
        'nb_lignes': nb_lignes,
        'nb_sans_date': nb_sans_date,
        'nb_cats': sum(len(groupes) for groupes in groupes_par_cat.values()),
        'volumineux': nb_lignes > SEUIL_DOCUMENT_VOLUMINEUX,
    }


@login_required
def entries_grand_livre_impression(request):
    """Grand livre imprimable d'un financement sur une période choisie."""
    fin = request.GET.get('fin', '').strip()
    date_debut_brute = request.GET.get('date_debut', '').strip()
    date_fin_brute = request.GET.get('date_fin', '').strip()
    afficher = any(cle in request.GET for cle in ('fin', 'date_debut', 'date_fin'))

    base = _get_diamex_entries_scope_queryset(request)
    base = _exclude_sensitive_diamex_lines_for_non_privileged(base, request.user)
    base = base.exclude(
        Q(compte_code__startswith='00BOOK') | Q(compte_code__startswith='00PERS')
    )
    base_financement = _filtrer_fin(base, fin)

    fins = sorted(
        {valeur for valeur in base.values_list('fin', flat=True).distinct() if (valeur or '').strip()},
        key=_normalize_text,
    )

    aujourdhui = datetime.now().date()
    erreurs = []
    document = None

    if afficher:
        date_debut = _parse_date(date_debut_brute) or aujourdhui.replace(month=1, day=1)
        date_fin = _parse_date(date_fin_brute) or aujourdhui
        if date_debut_brute and _parse_date(date_debut_brute) is None:
            erreurs.append(f"Date de début invalide : « {date_debut_brute} ».")
        if date_fin_brute and _parse_date(date_fin_brute) is None:
            erreurs.append(f"Date de fin invalide : « {date_fin_brute} ».")
        if date_debut > date_fin:
            erreurs.append('La date de début est postérieure à la date de fin.')

        if not erreurs:
            from .views import _build_fournisseurs_index

            codes = {
                (code or '').strip()
                for code in base_financement.values_list('compte_code', flat=True).distinct()
            }
            document = construire_grand_livre(
                base_financement,
                date_debut=date_debut,
                date_fin=date_fin,
                fournisseurs_index=_build_fournisseurs_index(),
                noms_comptes=_noms_comptes_manquants(codes, request.user),
            )
            document['date_debut'] = date_debut
            document['date_fin'] = date_fin
            document['titre'] = (
                f"Grand livre — {_libelle_financement(fin)} — "
                f"du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
            )

    return render(request, 'accounting/grand_livre_impression.html', {
        'fin': fin,
        'fins': fins,
        'sans_financement': SANS_FINANCEMENT,
        'tous_les_financements': TOUS_LES_FINANCEMENTS,
        'libelle_financement': _libelle_financement(fin),
        'date_debut_brute': date_debut_brute,
        'date_fin_brute': date_fin_brute,
        'afficher': afficher,
        'erreurs': erreurs,
        'document': document,
        'date_edition': aujourdhui,
    })
