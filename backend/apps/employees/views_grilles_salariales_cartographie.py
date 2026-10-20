"""
Cartographie des employes actifs sur la grille salariale (niveau Junior + tranches
d'anciennete). Alimente les vues "Graphique" et "Matrice" de la page
/employes/grilles-salariales/, sur le modele de la page grilles-autonomie.

Regle metier :
- un employe sans date_sortie_junior (ou avec une date future) est Junior et se
  compare a la grille Junior de son poste, independante de l'anciennete ;
- sinon son anciennete grille est comptee depuis date_sortie_junior et il se
  compare a la tranche "confirme" correspondante.
"""
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import Contrat, Employe
from .models_revalorisation import GrilleSalariale
from .views_autonomie import _dernier_salaire_net_par_employe
from .views_grilles_salariales import (
    _build_gross_preview_for_poste,
    _build_net_preview_for_poste,
    _format_decimal_display,
    _get_request_organisation,
    _parse_date,
    _parse_decimal_input,
    _scoped_grilles,
    _validation_error_message,
)

CHAMPS_FOURCHETTE = (
    'fourchette_basse', 'fourchette_haute', 'mode_fourchette_haute',
    'fourchette_haute_reference', 'anciennete_reference_haute',
    'ratio_annuel_haute', 'mode_ratio_haute',
)


COLONNE_JUNIOR = 'junior'
TOLERANCE_FOURCHETTE = 0.02


def _cle_colonne(grille):
    if grille.est_junior:
        return COLONNE_JUNIOR
    return f"{_format_decimal_display(grille.anciennete_min)}-{_format_decimal_display(grille.anciennete_max)}"


def _libelle_colonne(grille):
    if grille.est_junior:
        return 'Junior'
    return f"{_format_decimal_display(grille.anciennete_min)} - {_format_decimal_display(grille.anciennete_max)} ans"


def _scoped_employes_actifs(request):
    queryset = Employe.objects.select_related('poste', 'base__organisation').filter(
        salarie=True, poste__isnull=False,
    ).filter(
        models.Q(date_debauchage__isnull=True) | models.Q(date_debauchage__gte=date.today())
    )
    # L'organisation du compte prime, meme pour un superutilisateur : la cartographie
    # ne montre que les employes de son organisation. Superutilisateur sans organisation : tout.
    organisation = _get_request_organisation(request)
    if organisation is not None:
        return queryset.filter(base__organisation=organisation)
    if getattr(request.user, 'is_superuser', False):
        return queryset
    return queryset.none()


def _contrat_en_vigueur(contrats, date_reference):
    """Contrat en vigueur a date_reference (le plus recent), sinon le plus recent tout court."""
    en_vigueur = [
        c for c in contrats
        if c.debut_contrat <= date_reference and (c.fin_contrat is None or c.fin_contrat >= date_reference)
    ]
    candidats = en_vigueur or contrats
    return max(candidats, key=lambda c: c.debut_contrat) if candidats else None


def _quotites_par_employe(employe_ids, date_reference):
    """{employe_id: quotite en %} d'apres le contrat en vigueur (100 si aucun contrat)."""
    contrats_par_employe = {}
    for contrat in Contrat.objects.filter(employe_id__in=employe_ids).only(
        'employe_id', 'debut_contrat', 'fin_contrat', 'quotite_temps_travail',
    ):
        contrats_par_employe.setdefault(contrat.employe_id, []).append(contrat)
    quotites = {}
    for employe_id, contrats in contrats_par_employe.items():
        contrat = _contrat_en_vigueur(contrats, date_reference)
        quotite = float(contrat.quotite_temps_travail or 100) if contrat else 100.0
        quotites[employe_id] = quotite if quotite > 0 else 100.0
    return quotites


def _grilles_organisation(request):
    """Grilles de l'organisation du compte (meme regle que pour les employes)."""
    organisation = _get_request_organisation(request)
    queryset = _scoped_grilles(request)
    if organisation is not None:
        queryset = queryset.filter(
            models.Q(organisation=organisation)
            | models.Q(organisation__isnull=True, poste__organisation=organisation)
        )
    return queryset


class _ConvertisseurNet:
    """Conversion brut -> net (reference standard du poste), memoisee par (poste, brut)."""

    def __init__(self):
        self._cache = {}

    def net(self, poste, brut):
        if brut in (None, ''):
            return None
        cle = (poste.id, Decimal(str(brut)))
        if cle not in self._cache:
            preview, _ = _build_net_preview_for_poste(poste, brut)
            self._cache[cle] = float(preview.salaire_net)
        return self._cache[cle]


def _grilles_en_vigueur(request, date_reference):
    """Grilles valides a date_reference, une seule par (poste, colonne) : la plus recente."""
    grilles = _grilles_organisation(request).select_related('poste', 'template').filter(
        date_debut_validite__lte=date_reference,
    ).filter(
        models.Q(date_fin_validite__isnull=True) | models.Q(date_fin_validite__gte=date_reference)
    ).order_by('poste_id', 'niveau', 'anciennete_min', '-date_debut_validite')

    retenues = {}
    for grille in grilles:
        retenues.setdefault((grille.poste_id, _cle_colonne(grille)), grille)
    return list(retenues.values())


def _trouver_grille_employe(grilles_poste, est_junior, anciennete):
    """Grille Junior, ou tranche confirme contenant l'anciennete (borne basse prioritaire)."""
    if est_junior:
        return next((g for g in grilles_poste if g.est_junior), None)
    candidates = [
        g for g in grilles_poste
        if not g.est_junior and g.anciennete_min <= anciennete <= g.anciennete_max
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda g: g.anciennete_min)


def _statut_fourchette(salaire_net, basse, haute):
    """
    Situe un salaire net reel par rapport a la fourchette nette [basse, haute].
    Retourne 'sous', 'dans' ou 'au_dessus'.

    Tolerance de 2 % sur chaque borne : le net de grille est calcule a 0 personne
    a charge, le net reellement paye varie (IRSA, presence, prorata).
    """
    if salaire_net < basse * (1 - TOLERANCE_FOURCHETTE):
        return 'sous'
    if salaire_net > haute * (1 + TOLERANCE_FOURCHETTE):
        return 'au_dessus'
    return 'dans'


def _ecart_au_palier(salaire_net, basse, haute):
    """
    Cle de proximite entre un salaire net reel et la fourchette nette [basse, haute]
    d'un palier : plus elle est petite, plus le palier est proche. L'appelant prend
    le minimum ; a egalite, le premier palier dans l'ordre Junior -> anciennete.
    Distance a l'intervalle : 0 pour toute fourchette qui contient le salaire, donc
    dans des fourchettes qui se chevauchent c'est la plus basse qui l'emporte
    (ex : 950 000 Ar -> 0-2 ans [704 000 - 994 100] plutot que 2-4 ans [766 700 - 1 190 100]).
    Hors de toute fourchette : le palier dont une borne est la plus proche.
    """
    return max(basse - salaire_net, 0, salaire_net - haute)


@login_required
def api_grilles_salariales_cartographie(request):
    date_reference = _parse_date(request.GET.get('date')) or date.today()
    convertisseur = _ConvertisseurNet()

    grilles = _grilles_en_vigueur(request, date_reference)
    grilles_par_poste = {}
    for grille in grilles:
        grilles_par_poste.setdefault(grille.poste_id, []).append(grille)

    # Colonnes communes a la matrice : Junior puis l'union des tranches, triees.
    colonnes = {}
    for grille in grilles:
        cle = _cle_colonne(grille)
        if cle not in colonnes:
            colonnes[cle] = {
                'cle': cle,
                'libelle': _libelle_colonne(grille),
                'est_junior': grille.est_junior,
                'anciennete_min': float(grille.anciennete_min),
                'anciennete_max': float(grille.anciennete_max),
            }
    colonnes_triees = sorted(
        colonnes.values(),
        key=lambda c: (not c['est_junior'], c['anciennete_min'], c['anciennete_max']),
    )

    # Postes qui partagent chaque template (pour prevenir avant une modification commune).
    postes_par_template = {}
    for template_id, poste_nom in _grilles_organisation(request).filter(template__isnull=False).values_list(
        'template_id', 'poste__nom_poste',
    ):
        postes_par_template.setdefault(template_id, set()).add(poste_nom)

    postes_data = {}
    for grille in grilles:
        poste = grille.poste
        entree = postes_data.setdefault(poste.id, {
            'poste_id': str(poste.id),
            'poste_nom': poste.nom_poste,
            'type_poste': poste.type_poste,
            'niveau_poste': poste.niveau_poste,
            'ordre_affichage': poste.ordre_affichage or 0,
            'paliers': {},
        })
        dynamique = grille.is_fourchette_haute_dynamic
        entree['paliers'][_cle_colonne(grille)] = {
            'grille_id': str(grille.id),
            'fourchette_basse': convertisseur.net(poste, grille.tpl_fourchette_basse),
            'fourchette_haute': convertisseur.net(
                poste, grille.get_fourchette_haute_for_anciennete(grille.anciennete_min)
            ),
            'fourchette_haute_max': convertisseur.net(
                poste, grille.get_fourchette_haute_for_anciennete(grille.anciennete_max)
            ) if dynamique else None,
            'dynamique': dynamique,
            'fourchette_haute_reference': convertisseur.net(poste, grille.tpl_fourchette_haute_reference) if dynamique else None,
            'ratio_annuel_haute': float(grille.tpl_ratio_annuel_haute) if dynamique and grille.tpl_ratio_annuel_haute is not None else None,
            'anciennete_reference_haute': float(grille.tpl_anciennete_reference_haute) if dynamique and grille.tpl_anciennete_reference_haute is not None else None,
            'template_id': str(grille.template_id) if grille.template_id else None,
            'template_nom': grille.template.nom_template if grille.template_id else None,
            'template_postes': sorted(postes_par_template.get(grille.template_id, ())) if grille.template_id else [],
            'template_modifiable': bool(grille.template_id) and _template_modifiable(request, grille.template),
        }

    ordre_colonnes = [c['cle'] for c in colonnes_triees]
    employes = list(_scoped_employes_actifs(request))
    salaires = _dernier_salaire_net_par_employe([e.id for e in employes])
    quotites = _quotites_par_employe([e.id for e in employes], date_reference)

    employes_data = []
    for employe in employes:
        # Temps partiel : les fourchettes (temps plein) sont proratisees a la quotite du contrat.
        quotite_pct = quotites.get(employe.id, 100.0)
        prorata = quotite_pct / 100
        est_junior = employe.est_junior(date_reference)
        anciennete = employe.anciennete_grille_annees(date_reference)
        # Palier theorique : Junior, ou tranche d'anciennete depuis la sortie Junior.
        grille_theorique = _trouver_grille_employe(grilles_par_poste.get(employe.poste_id, []), est_junior, anciennete)
        colonne_theorique = _cle_colonne(grille_theorique) if grille_theorique else None
        salaire_info = salaires.get(employe.id)
        salaire_net = float(salaire_info[0]) if salaire_info and salaire_info[0] is not None else None

        # Palier estime : celui dont la fourchette est la plus proche du salaire reel.
        # Sans salaire paye, on garde le palier theorique.
        paliers = postes_data.get(employe.poste_id, {}).get('paliers', {})
        colonne = colonne_theorique
        if salaire_net is not None and paliers:
            colonne = min(
                (cle for cle in ordre_colonnes if cle in paliers),
                key=lambda cle: _ecart_au_palier(
                    salaire_net,
                    paliers[cle]['fourchette_basse'] * prorata,
                    (paliers[cle]['fourchette_haute_max'] or paliers[cle]['fourchette_haute']) * prorata,
                ),
            )

        basse = haute = None
        statut = 'sans_grille'
        ecart = None
        palier = paliers.get(colonne) if colonne else None
        if palier is not None:
            basse = palier['fourchette_basse'] * prorata
            haute = (palier['fourchette_haute_max'] or palier['fourchette_haute']) * prorata
            if salaire_net is None:
                statut = 'sans_salaire'
            else:
                statut = _statut_fourchette(salaire_net, basse, haute)
                if statut == 'sous':
                    ecart = salaire_net - basse
                elif statut == 'au_dessus':
                    ecart = salaire_net - haute
                else:
                    ecart = 0.0

        employes_data.append({
            'employe_id': str(employe.id),
            'nom_affichage': employe.nom_affichage,
            'poste_id': str(employe.poste_id),
            'poste_nom': employe.poste.nom_poste,
            'date_embauche': employe.date_embauche.isoformat() if employe.date_embauche else None,
            'date_sortie_junior': employe.date_sortie_junior.isoformat() if employe.date_sortie_junior else None,
            'est_junior': est_junior,
            'anciennete_grille': float(anciennete),
            'colonne': colonne if palier is not None else None,
            'colonne_theorique': colonne_theorique,
            'coherent': colonne is not None and colonne == colonne_theorique,
            'grille_id': palier['grille_id'] if palier else None,
            'fourchette_basse': basse,
            'fourchette_haute': haute,
            'salaire_net_reel': salaire_net,
            'quotite': quotite_pct,
            # Position sur les graphiques (fourchettes dessinees a temps plein) : le salaire ramene
            # a 100 %, ce qui equivaut a le comparer a la fourchette proratisee.
            'salaire_position': salaire_net / prorata if salaire_net is not None else None,
            'date_paiement': salaire_info[1].isoformat() if salaire_info and salaire_info[1] else None,
            'statut': statut,
            'ecart_ariary': ecart,
        })
    employes_data.sort(key=lambda e: (e['poste_nom'].lower(), (e['nom_affichage'] or '').lower()))

    postes_tries = sorted(postes_data.values(), key=lambda p: (p['ordre_affichage'], p['poste_nom'].lower()))

    return JsonResponse({
        'success': True,
        'date_reference': date_reference.isoformat(),
        'colonnes': colonnes_triees,
        'postes': postes_tries,
        'employes': employes_data,
    })


def _template_modifiable(request, template):
    if getattr(request.user, 'is_superuser', False):
        return True
    organisation = _get_request_organisation(request)
    # Un template global (sans organisation) peut servir a d'autres organisations.
    return organisation is not None and template.organisation_id == organisation.id


@login_required
def api_grille_modifier_fourchette(request, grille_id):
    """
    Modifie la fourchette (nette) d'un palier depuis la matrice ou le graphique.
    portee='grille'   : cette grille seulement (detachee de son template si besoin) ;
    portee='template' : le template, et toutes les grilles qui le partagent.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    grille = get_object_or_404(_scoped_grilles(request).select_related('poste', 'template'), id=grille_id)
    try:
        data = json.loads(request.body or '{}')
        portee = data.get('portee') or 'grille'
        mode = grille.tpl_mode_fourchette_haute

        def en_brut(net):
            preview, _ = _build_gross_preview_for_poste(grille.poste, net)
            return preview.salaire_brut_base.quantize(Decimal('0.01'))

        basse_net = _parse_decimal_input(data.get('fourchette_basse'))
        if basse_net <= 0:
            raise ValidationError("La fourchette basse nette doit etre superieure a zero.")
        valeurs = {'fourchette_basse': en_brut(basse_net)}
        if mode == 'ratio_annuel':
            reference_net = _parse_decimal_input(data.get('fourchette_haute_reference'))
            ratio = _parse_decimal_input(data.get('ratio_annuel_haute'))
            anciennete_ref = _parse_decimal_input(data.get('anciennete_reference_haute'))
            if reference_net <= 0 or ratio <= 0 or anciennete_ref < 0:
                raise ValidationError("Reference haute, ratio et anciennete de reference doivent etre positifs.")
            valeurs.update({
                'fourchette_haute_reference': en_brut(reference_net),
                'ratio_annuel_haute': ratio.quantize(Decimal('0.01')),
                'anciennete_reference_haute': anciennete_ref.quantize(Decimal('0.01')),
            })
        else:
            haute_net = _parse_decimal_input(data.get('fourchette_haute'))
            if haute_net <= 0:
                raise ValidationError("La fourchette haute nette doit etre superieure a zero.")
            valeurs['fourchette_haute'] = en_brut(haute_net)

        if portee == 'template' and grille.template_id:
            template = grille.template
            if not _template_modifiable(request, template):
                return JsonResponse({
                    'success': False,
                    'error': "Ce template n'appartient pas a votre organisation : modifiez ce poste seulement.",
                }, status=403)
            for champ, valeur in valeurs.items():
                setattr(template, champ, valeur)
            template.update_fourchette_haute_cache()
            template.full_clean()
            with transaction.atomic():
                template.save()
                grilles_liees = list(template.grilles_liees.all())
                # Les grilles gardent une copie des valeurs du template : on la rafraichit.
                for liee in grilles_liees:
                    for champ in CHAMPS_FOURCHETTE:
                        setattr(liee, champ, getattr(template, champ))
                    liee.save()
            message = f"Template modifie : {len(grilles_liees)} grille(s) mise(s) a jour."
        else:
            if grille.template_id:
                # Detachement : la grille recupere les valeurs du template comme valeurs propres.
                for champ in CHAMPS_FOURCHETTE:
                    setattr(grille, champ, getattr(grille.template, champ))
                grille.template = None
            for champ, valeur in valeurs.items():
                setattr(grille, champ, valeur)
            grille.update_fourchette_haute_cache()
            grille.full_clean()
            grille.save()
            message = f"Fourchette de {grille.poste.nom_poste} mise a jour."
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': _validation_error_message(exc)}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    return JsonResponse({'success': True, 'message': message})


@login_required
def api_employe_quotite(request, employe_id):
    """Regle la quotite de temps de travail (%) du contrat en vigueur de l'employe."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    employe = get_object_or_404(_scoped_employes_actifs(request), id=employe_id)
    contrat = _contrat_en_vigueur(list(Contrat.objects.filter(employe=employe)), date.today())
    if contrat is None:
        return JsonResponse({'success': False, 'error': "Cet employe n'a aucun contrat."}, status=400)
    try:
        data = json.loads(request.body or '{}')
        quotite = _parse_decimal_input(data.get('quotite'))
        if not (Decimal('1') <= quotite <= Decimal('100')):
            raise ValidationError("La quotite doit etre comprise entre 1 et 100 %.")
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': _validation_error_message(exc)}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    contrat.quotite_temps_travail = quotite.quantize(Decimal('0.01'))
    contrat.save(update_fields=['quotite_temps_travail'])
    return JsonResponse({
        'success': True,
        'message': f"Temps de travail de {employe.nom_affichage} : {_format_decimal_display(quotite)} %.",
    })


@login_required
def api_employe_date_sortie_junior(request, employe_id):
    """Saisit (ou efface) la date de sortie du niveau Junior d'un employe."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    employe = get_object_or_404(_scoped_employes_actifs(request), id=employe_id)
    try:
        data = json.loads(request.body or '{}')
        valeur = data.get('date_sortie_junior')
        nouvelle_date = _parse_date(valeur) if valeur else None
        if valeur and nouvelle_date is None:
            raise ValidationError("Date invalide (format attendu AAAA-MM-JJ).")
        if nouvelle_date and employe.date_embauche and nouvelle_date < employe.date_embauche:
            raise ValidationError("La sortie du niveau Junior ne peut pas preceder la date d'embauche.")
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': ' '.join(exc.messages)}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    employe.date_sortie_junior = nouvelle_date
    employe.save(update_fields=['date_sortie_junior'])
    return JsonResponse({
        'success': True,
        'message': 'Date de sortie Junior enregistree.' if nouvelle_date else 'Employe repasse au niveau Junior.',
        'date_sortie_junior': nouvelle_date.isoformat() if nouvelle_date else None,
    })
