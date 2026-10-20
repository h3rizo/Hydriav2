"""
Fusion des activités de réparation en doublon (FichePoste).

Exemple : « Remplacement robinet », « Remplacement du robinet BF » -> « Remplacement »,
avec le composant « Robinet » porté par chaque réparation concernée.

Le module est découpé en :
  - fonctions pures (fold, detect_composants, ...) testables sans base ;
  - analyse (aperçu, sans écriture) ;
  - application et annulation, transactionnelles, journalisées dans FusionFichePosteLog.
"""
import re
import unicodedata
from collections import Counter, defaultdict

from django.db import transaction
from django.utils import timezone

from apps.core.models import RepairActivityEquipmentPolicy, RepairActivityPointTypePolicy
from apps.employees.models import FichePoste
from apps.employees.models_evaluation import EvaluationDetail
from apps.inspections.models import ComposantTypeEquipement, ComposantTypePointEau
from apps.planning.models import ActivitePoste, FusionFichePosteLog, Planning
from apps.planning.repair_classification import get_reparations_fiches_queryset

PREFIXE_FUSIONNEE = '[Fusionnée] '
NOM_MAX = 255

# Mots de liaison retirés en fin de libellé une fois le composant enlevé.
FILLERS = {'du', 'de', 'des', 'd', 'la', 'le', 'les', 'l', 'au', 'aux', 'et', 'sur', 'en', 'un', 'une'}


class FusionError(ValueError):
    """Erreur de validation exposable telle quelle à l'utilisateur."""


# --------------------------------------------------------------------------- #
# Fonctions pures
# --------------------------------------------------------------------------- #

def fold(text):
    """Minuscule sans accents, caractère par caractère (mêmes indices que le texte d'origine)."""
    return ''.join(unicodedata.normalize('NFD', ch)[0].lower() for ch in (text or ''))


def detect_composants(tache, vocab):
    """
    Repère les composants du catalogue cités dans un libellé.

    vocab : liste de {'nom': str, 'fold': str}.
    Retourne (noms trouvés dans l'ordre d'apparition, spans [(debut, fin)] dans `tache`).
    """
    folded = fold(tache)
    spans, found = [], []
    for item in sorted(vocab, key=lambda v: -len(v['fold'])):
        if not item['fold']:
            continue
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(item['fold']) + r"s?(?![a-z0-9])")
        for match in pattern.finditer(folded):
            if any(match.start() < end and start < match.end() for start, end in spans):
                continue
            spans.append((match.start(), match.end()))
            found.append((match.start(), item['nom']))
    found.sort()
    ordered, seen = [], set()
    for _, nom in found:
        if nom not in seen:
            seen.add(nom)
            ordered.append(nom)
    return ordered, sorted(spans)


def strip_spans(tache, spans):
    """Retire les composants du libellé et nettoie les mots de liaison / ponctuation restants."""
    if not spans:
        return (tache or '').strip()
    out, cursor = [], 0
    for start, end in spans:
        out.append(tache[cursor:start])
        cursor = end
    out.append(tache[cursor:])
    tokens = ''.join(out).split()

    def is_filler(token):
        base = fold(token).strip("'’.,;:-–—/()+")
        return base == '' or all(part in FILLERS for part in re.split(r"['’]", base))

    while tokens and is_filler(tokens[-1]):
        tokens.pop()
    while tokens and fold(tokens[0]).strip("'’.,;:-–—/()+") == '':
        tokens.pop(0)
    return ' '.join(tokens).strip()


def split_composants_text(value):
    """« Robinet, clapet » -> ['Robinet', 'clapet'] (dédoublonné, insensible à la casse/accents)."""
    if isinstance(value, (list, tuple)):
        raw = [str(v) for v in value]
    else:
        raw = re.split(r'[,;\n]', str(value or ''))
    seen, out = set(), []
    for item in raw:
        item = item.strip()
        key = fold(item)
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


# --------------------------------------------------------------------------- #
# Catalogue de composants
# --------------------------------------------------------------------------- #

def catalogue_vocab():
    """Noms de composants des deux catalogues, dédoublonnés (insensible à la casse/accents)."""
    vocab, seen = [], set()
    for model in (ComposantTypeEquipement, ComposantTypePointEau):
        for nom in model.objects.values_list('nom_composant', flat=True).distinct():
            key = fold(nom)
            if key and key not in seen:
                seen.add(key)
                vocab.append({'nom': nom, 'fold': key})
    vocab.sort(key=lambda v: v['fold'])
    return vocab


# --------------------------------------------------------------------------- #
# Suggestion de groupes
# --------------------------------------------------------------------------- #

def build_groups():
    """
    Groupes de fiches de réparation candidats à la fusion.

    Une fiche entre dans un groupe si elle partage (type d'activité, libellé sans composant)
    avec au moins une autre, ou si son libellé cite un composant (à renommer en générique).
    """
    from django.db.models import Count

    vocab = catalogue_vocab()
    fiches = (
        get_reparations_fiches_queryset()
        .annotate(nb_plannings=Count('plannings', distinct=True))
        .order_by('tache')
    )
    buckets = defaultdict(list)
    for fiche in fiches:
        composants, spans = detect_composants(fiche.tache or '', vocab)
        propre = strip_spans(fiche.tache or '', spans) if composants else (fiche.tache or '').strip()
        if not propre:  # le libellé n'est que le composant : on ne touche pas
            composants, propre = [], (fiche.tache or '').strip()
        key = (fiche.type_activites_id, fold(propre))
        buckets[key].append({
            'id': str(fiche.id),
            'tache': fiche.tache,
            'nb_plannings': fiche.nb_plannings,
            'composants_detectes': composants,
            'nom_propre': propre,
            'type_id': str(fiche.type_activites_id) if fiche.type_activites_id else None,
            'type_nom': getattr(fiche.type_activites, 'nomtype', '') or '',
        })

    groups = []
    for (_, _), members in buckets.items():
        if len(members) < 2 and not any(m['composants_detectes'] for m in members):
            continue
        noms = Counter(m['nom_propre'] for m in members)
        nom_suggere = sorted(noms, key=lambda n: (-noms[n], len(n), n))[0]
        exact = [m for m in members if m['tache'].strip() == nom_suggere]
        cible = (exact or sorted(members, key=lambda m: -m['nb_plannings']))[0]
        groups.append({
            'nom_suggere': nom_suggere,
            'type_nom': members[0]['type_nom'],
            'cible_suggeree_id': cible['id'],
            'fiches': sorted(members, key=lambda m: (-m['nb_plannings'], m['tache'])),
            'nb_plannings': sum(m['nb_plannings'] for m in members),
        })
    groups.sort(key=lambda g: (-len(g['fiches']), g['nom_suggere'].lower()))
    return groups


def toutes_fiches():
    """Toutes les fiches de réparation (fusion manuelle), avec leur nombre de réparations."""
    from django.db.models import Count
    return [
        {
            'id': str(f.id), 'tache': f.tache, 'nb_plannings': f.nb_plannings,
            'composants_detectes': [],
            'type_nom': getattr(f.type_activites, 'nomtype', '') or '',
        }
        for f in get_reparations_fiches_queryset()
        .annotate(nb_plannings=Count('plannings', distinct=True)).order_by('tache')
    ]


# --------------------------------------------------------------------------- #
# Analyse des composants à affecter aux réparations (sans écriture)
# --------------------------------------------------------------------------- #

def _planning_target(planning):
    """(kind, objet) où kind vaut 'eq' ou 'pe' ; (None, None) si la cible est absente/ambiguë."""
    if planning.cible_equipement_id:
        return 'eq', planning.cible_equipement
    if planning.cible_point_eau_id:
        return 'pe', planning.cible_point_eau
    equipements, points = {}, {}
    for detail in planning.details.all():
        if detail.equipement_constitutif_id:
            equipements[detail.equipement_constitutif_id] = detail.equipement_constitutif
        if detail.point_eau_id:
            points[detail.point_eau_id] = detail.point_eau
    if len(equipements) == 1 and not points:
        return 'eq', next(iter(equipements.values()))
    if len(points) == 1 and not equipements:
        return 'pe', next(iter(points.values()))
    return None, None


def _plannings_queryset(fiche_id):
    from django.db.models import Prefetch
    from apps.planning.models import PlanningDetail
    return (
        Planning.objects.filter(fiche_poste_id=fiche_id)
        .select_related('cible_equipement', 'cible_point_eau')
        .prefetch_related(Prefetch(
            'details', queryset=PlanningDetail.objects.select_related('equipement_constitutif', 'point_eau')))
    )


def analyse_composants(composants_par_fiche):
    """
    composants_par_fiche : {fiche_id: [noms de composants]}.

    Retourne :
      affectations : [{planning, kind, type_id, composant_id|None, nom, backfill}]
      sans_cible   : [planning] réparations dont on ne peut pas déduire l'équipement / le point d'eau
      manquants    : {(kind, type_id, type_nom, fold_nom): {'nom', 'count'}} absents du catalogue du type
    """
    catalogs = {
        'eq': defaultdict(dict),
        'pe': defaultdict(dict),
    }
    for c in ComposantTypeEquipement.objects.all():
        catalogs['eq'][c.type_equipement_id][fold(c.nom_composant)] = c.id
    for c in ComposantTypePointEau.objects.all():
        catalogs['pe'][c.type_point_eau_id][fold(c.nom_composant)] = c.id

    affectations, sans_cible = [], []
    manquants = {}
    for fiche_id, noms in composants_par_fiche.items():
        if not noms:
            continue
        for planning in _plannings_queryset(fiche_id):
            kind, cible = _planning_target(planning)
            if not cible:
                sans_cible.append(planning)
                continue
            type_id = cible.type_equipement_id if kind == 'eq' else cible.type_point_eau_id
            backfill = not (planning.cible_equipement_id or planning.cible_point_eau_id)
            if not type_id:
                sans_cible.append(planning)
                continue
            for nom in noms:
                comp_id = catalogs[kind][type_id].get(fold(nom))
                if comp_id is None:
                    type_obj = cible.type_equipement if kind == 'eq' else cible.type_point_eau
                    key = (kind, type_id, getattr(type_obj, 'nom_type', '') or '', fold(nom))
                    entry = manquants.setdefault(key, {'nom': nom, 'count': 0})
                    entry['count'] += 1
                affectations.append({
                    'planning': planning, 'kind': kind, 'type_id': type_id,
                    'composant_id': comp_id, 'nom': nom, 'backfill': backfill, 'cible': cible,
                })
    return {'affectations': affectations, 'sans_cible': sans_cible, 'manquants': manquants}


# --------------------------------------------------------------------------- #
# Validation et aperçu
# --------------------------------------------------------------------------- #

def _load_scope(target_id, source_ids):
    # Toute fiche peut être fusionnée (réparation, inspection, ...), mais pas à cheval sur
    # la famille « réparation/installation » : ses politiques et composants lui sont propres.
    repair_ids = {str(i) for i in get_reparations_fiches_queryset().values_list('id', flat=True)}
    if not target_id or not FichePoste.objects.filter(id=target_id).exists():
        raise FusionError("Activité cible introuvable")
    source_ids = [str(s) for s in (source_ids or []) if str(s) != str(target_id)]
    if len(set(source_ids)) != len(source_ids):
        source_ids = list(dict.fromkeys(source_ids))
    target_est_reparation = str(target_id) in repair_ids
    for sid in source_ids:
        if (sid in repair_ids) != target_est_reparation:
            raise FusionError(
                "Impossible de fusionner une activité de réparation avec une activité d'une autre famille "
                "(inspection, etc.) : choisissez des activités de la même famille")
    target = FichePoste.objects.select_related('type_activites').get(id=target_id)
    sources = list(FichePoste.objects.select_related('type_activites').filter(id__in=source_ids))
    if len(sources) != len(source_ids):
        raise FusionError("Une activité à fusionner est introuvable")
    return target, sources


def _normalise_payload(payload):
    target_id = str(payload.get('target_id') or '').strip()
    source_ids = payload.get('source_ids') or []
    if not isinstance(source_ids, list):
        raise FusionError("source_ids doit être une liste")
    composants = {}
    for fiche_id, value in (payload.get('composants') or {}).items():
        noms = split_composants_text(value)
        if noms:
            composants[str(fiche_id)] = noms
    nouveau_nom = ' '.join(str(payload.get('nouveau_nom') or '').split())
    if len(nouveau_nom) > NOM_MAX:
        raise FusionError("Le nouveau nom est trop long")
    return target_id, source_ids, composants, nouveau_nom


def apercu(payload):
    target_id, source_ids, composants, nouveau_nom = _normalise_payload(payload)
    target, sources = _load_scope(target_id, source_ids)
    if not sources and not nouveau_nom and not composants:
        raise FusionError("Rien à faire : choisissez des activités à fusionner, un nouveau nom ou des composants")
    for fiche_id in composants:
        if fiche_id not in {str(target.id)} | {str(s.id) for s in sources}:
            raise FusionError("Composants indiqués pour une activité hors de la fusion")

    changement_type = [
        {'id': str(s.id), 'tache': s.tache, 'type_nom': getattr(s.type_activites, 'nomtype', '') or ''}
        for s in sources if s.type_activites_id != target.type_activites_id
    ]
    fiches = []
    for s in sources:
        fiches.append({
            'id': str(s.id),
            'tache': s.tache,
            'plannings': Planning.objects.filter(fiche_poste=s).count(),
            'activites_postes': ActivitePoste.objects.filter(fiche_poste=s).count(),
            'evaluations': EvaluationDetail.objects.filter(fiche_poste=s).count(),
            'politiques': (
                RepairActivityEquipmentPolicy.objects.filter(allowed_activities=s).count()
                + RepairActivityPointTypePolicy.objects.filter(allowed_activities=s).count()
            ),
        })

    analyse = analyse_composants(composants)
    manquants = [
        {'type': kind_label(k[0]), 'type_nom': k[2], 'composant': v['nom'], 'reparations': v['count']}
        for k, v in sorted(analyse['manquants'].items(), key=lambda kv: (kv[0][2], kv[0][3]))
    ]
    return {
        'cible': {'id': str(target.id), 'tache': target.tache,
                  'nouveau_nom': nouveau_nom or target.tache,
                  'type_nom': getattr(target.type_activites, 'nomtype', '') or ''},
        'fiches': fiches,
        'changement_type': changement_type,
        'composants': {
            'affectations': len({(a['planning'].id, a['nom']) for a in analyse['affectations'] if a['composant_id']}),
            'a_creer': sum(v['count'] for v in analyse['manquants'].values()),
            'manquants': manquants,
            'sans_cible': len({p.id for p in analyse['sans_cible']}),
            'sans_cible_exemples': [
                {'id': str(p.id), 'date': p.date.date().isoformat() if p.date else '',
                 'ouvrage': getattr(p.ouvrage, 'nom_ouvrage', '') if p.ouvrage_id else ''}
                for p in analyse['sans_cible'][:15]
            ],
            'cibles_deduites': len({a['planning'].id for a in analyse['affectations'] if a['backfill']}),
        },
    }


def kind_label(kind):
    return "Équipement" if kind == 'eq' else "Point d'eau"


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #

@transaction.atomic
def appliquer(payload, user):
    target_id, source_ids, composants, nouveau_nom = _normalise_payload(payload)
    target, sources = _load_scope(target_id, source_ids)
    if not sources and not nouveau_nom and not composants:
        raise FusionError("Rien à faire : choisissez des activités à fusionner, un nouveau nom ou des composants")
    in_scope = {str(target.id)} | {str(s.id) for s in sources}
    if any(fiche_id not in in_scope for fiche_id in composants):
        raise FusionError("Composants indiqués pour une activité hors de la fusion")
    if any(s.type_activites_id != target.type_activites_id for s in sources) \
            and not payload.get('accepter_changement_type'):
        raise FusionError(
            "Des activités ont un type différent de la cible : confirmez le changement de type pour continuer")

    # L'analyse doit précéder le repointage : elle retrouve les réparations par leur fiche d'origine.
    analyse = analyse_composants(composants)
    creer = bool(payload.get('creer_composants_manquants'))
    if analyse['manquants'] and not creer:
        raise FusionError(
            "Des composants n'existent pas dans le catalogue de certains types : "
            "cochez « créer les composants manquants » ou corrigez les noms")

    nom_avant = target.tache
    log_data = {'sources': [], 'composants': [], 'cibles_deduites': [], 'composants_crees': []}
    now = timezone.now()

    # 1) Repointage des dépendances de chaque source
    seen_evals = set(EvaluationDetail.objects.filter(fiche_poste=target).values_list('evaluation_id', flat=True))
    conflits_evaluations = 0
    total = Counter()
    for src in sources:
        entry = {
            'id': str(src.id), 'tache': src.tache,
            'type_id': str(src.type_activites_id) if src.type_activites_id else None,
            'dans_planning': src.dans_planning, 'a_evaluer': src.a_evaluer,
            'plannings': [], 'plannings_type_avant': {}, 'activites_postes': [],
            'evaluations': [], 'politiques': [],
        }
        for pid, tid in Planning.objects.filter(fiche_poste=src).values_list('id', 'type_activite_id'):
            entry['plannings'].append(str(pid))
            entry['plannings_type_avant'][str(pid)] = str(tid) if tid else None
        Planning.objects.filter(fiche_poste=src).update(
            fiche_poste=target, type_activite_id=target.type_activites_id, updated_at=now)

        ap_ids = list(ActivitePoste.objects.filter(fiche_poste=src).values_list('id', flat=True))
        entry['activites_postes'] = [str(i) for i in ap_ids]
        ActivitePoste.objects.filter(id__in=ap_ids).update(fiche_poste=target)

        for ed in EvaluationDetail.objects.filter(fiche_poste=src):
            if ed.evaluation_id in seen_evals:
                conflits_evaluations += 1
                continue
            seen_evals.add(ed.evaluation_id)
            ed.fiche_poste = target
            ed.save(update_fields=['fiche_poste'])
            entry['evaluations'].append(str(ed.id))

        for kind, model in (('eq', RepairActivityEquipmentPolicy), ('pe', RepairActivityPointTypePolicy)):
            for policy in model.objects.filter(allowed_activities=src):
                cible_ajoutee = not policy.allowed_activities.filter(id=target.id).exists()
                policy.allowed_activities.add(target)
                policy.allowed_activities.remove(src)
                entry['politiques'].append(
                    {'kind': kind, 'id': str(policy.id), 'cible_ajoutee': cible_ajoutee})

        total['plannings'] += len(entry['plannings'])
        total['activites_postes'] += len(ap_ids)
        total['evaluations'] += len(entry['evaluations'])
        total['politiques'] += len(entry['politiques'])

        # 2) Désactivation de la source (conservée pour l'annulation)
        src.type_activites = None
        src.dans_planning = False
        src.a_evaluer = False
        if not (src.tache or '').startswith(PREFIXE_FUSIONNEE):
            src.tache = (PREFIXE_FUSIONNEE + (src.tache or ''))[:NOM_MAX]
        src.save()
        log_data['sources'].append(entry)

    # 3) Renommage de la cible
    if nouveau_nom and nouveau_nom != target.tache:
        target.tache = nouveau_nom
        target.save(update_fields=['tache'])

    # 4) Composants sur les réparations
    catalog_new = {}  # (kind, type_id, fold) -> id
    for (kind, type_id, _type_nom, fnom), info in analyse['manquants'].items():
        if kind == 'eq':
            obj = ComposantTypeEquipement.objects.create(
                type_equipement_id=type_id, nom_composant=info['nom'], est_obligatoire=False,
                ordre_affichage=ComposantTypeEquipement.objects.filter(type_equipement_id=type_id).count() + 1)
        else:
            obj = ComposantTypePointEau.objects.create(
                type_point_eau_id=type_id, nom_composant=info['nom'], est_obligatoire=False,
                ordre_affichage=ComposantTypePointEau.objects.filter(type_point_eau_id=type_id).count() + 1)
        catalog_new[(kind, type_id, fnom)] = obj.id
        log_data['composants_crees'].append({'kind': kind, 'id': str(obj.id)})

    through_eq = Planning.composants_equipement.through
    through_pe = Planning.composants_point_eau.through
    added = defaultdict(lambda: {'eq': set(), 'pe': set()})
    backfilled = {}
    existing_cache = {}
    for a in analyse['affectations']:
        comp_id = a['composant_id'] or catalog_new.get((a['kind'], a['type_id'], fold(a['nom'])))
        pid = a['planning'].id
        if a['backfill'] and pid not in backfilled:
            backfilled[pid] = (a['kind'], a['cible'])
        cache_key = (pid, a['kind'])
        if cache_key not in existing_cache:
            existing_cache[cache_key] = _existing_composants(pid, a['kind'])
        if comp_id not in existing_cache[cache_key]:
            existing_cache[cache_key].add(comp_id)
            added[pid][a['kind']].add(comp_id)

    for pid, (kind, cible) in backfilled.items():
        if kind == 'eq':
            Planning.objects.filter(id=pid).update(cible_equipement=cible)
        else:
            Planning.objects.filter(id=pid).update(cible_point_eau=cible)
        log_data['cibles_deduites'].append(str(pid))
    eq_rows, pe_rows = [], []
    for pid, kinds in added.items():
        eq_rows += [through_eq(planning_id=pid, composanttypeequipement_id=c) for c in kinds['eq']]
        pe_rows += [through_pe(planning_id=pid, composanttypepointeau_id=c) for c in kinds['pe']]
        log_data['composants'].append(
            {'planning': str(pid), 'eq': [str(c) for c in kinds['eq']], 'pe': [str(c) for c in kinds['pe']]})
    through_eq.objects.bulk_create(eq_rows, ignore_conflicts=True)
    through_pe.objects.bulk_create(pe_rows, ignore_conflicts=True)
    if added:
        Planning.objects.filter(id__in=list(added)).update(updated_at=now)

    log_data['nom_cible_avant'] = nom_avant
    resume = {
        'sources': len(sources), **dict(total),
        'conflits_evaluations': conflits_evaluations,
        'composants_affectes': sum(len(k['eq']) + len(k['pe']) for k in added.values()),
        'composants_crees': len(log_data['composants_crees']),
        'sans_cible': len({p.id for p in analyse['sans_cible']}),
    }
    log = FusionFichePosteLog.objects.create(
        created_by=user if getattr(user, 'is_authenticated', False) else None,
        fiche_cible=target, nom_cible_avant=nom_avant, nom_cible_apres=target.tache,
        resume=resume, donnees=log_data)
    return {'log_id': str(log.id), 'resume': resume}


def _existing_composants(planning_id, kind):
    if kind == 'eq':
        through = Planning.composants_equipement.through
        return set(through.objects.filter(planning_id=planning_id)
                   .values_list('composanttypeequipement_id', flat=True))
    through = Planning.composants_point_eau.through
    return set(through.objects.filter(planning_id=planning_id)
               .values_list('composanttypepointeau_id', flat=True))


# --------------------------------------------------------------------------- #
# Annulation
# --------------------------------------------------------------------------- #

@transaction.atomic
def annuler(log_id, user):
    log = FusionFichePosteLog.objects.select_for_update().filter(id=log_id).first()
    if not log:
        raise FusionError("Fusion introuvable")
    if log.annulee_le:
        raise FusionError("Cette fusion est déjà annulée")
    target = log.fiche_cible
    if not target:
        raise FusionError("L'activité cible n'existe plus : annulation impossible")
    data = log.donnees
    now = timezone.now()

    # Composants et cibles ajoutés
    through_eq = Planning.composants_equipement.through
    through_pe = Planning.composants_point_eau.through
    for row in data.get('composants', []):
        if row['eq']:
            through_eq.objects.filter(planning_id=row['planning'], composanttypeequipement_id__in=row['eq']).delete()
        if row['pe']:
            through_pe.objects.filter(planning_id=row['planning'], composanttypepointeau_id__in=row['pe']).delete()
    if data.get('cibles_deduites'):
        Planning.objects.filter(id__in=data['cibles_deduites']).update(
            cible_equipement=None, cible_point_eau=None)
    for created in data.get('composants_crees', []):
        model, field = (ComposantTypeEquipement, 'plannings') if created['kind'] == 'eq' \
            else (ComposantTypePointEau, 'plannings')
        obj = model.objects.filter(id=created['id']).first()
        if obj and not getattr(obj, field).exists():
            obj.delete()

    # Sources
    for entry in data.get('sources', []):
        src = FichePoste.objects.filter(id=entry['id']).first()
        if not src:
            continue
        src.tache = entry['tache']
        src.type_activites_id = entry['type_id']
        src.dans_planning = entry['dans_planning']
        src.a_evaluer = entry['a_evaluer']
        src.save()
        for pid in entry['plannings']:
            Planning.objects.filter(id=pid, fiche_poste=target).update(
                fiche_poste=src, type_activite_id=entry['plannings_type_avant'].get(pid), updated_at=now)
        ActivitePoste.objects.filter(id__in=entry['activites_postes'], fiche_poste=target).update(fiche_poste=src)
        EvaluationDetail.objects.filter(id__in=entry['evaluations'], fiche_poste=target).update(fiche_poste=src)
        for pol in entry['politiques']:
            model = RepairActivityEquipmentPolicy if pol['kind'] == 'eq' else RepairActivityPointTypePolicy
            policy = model.objects.filter(id=pol['id']).first()
            if not policy:
                continue
            policy.allowed_activities.add(src)
            if pol['cible_ajoutee']:
                policy.allowed_activities.remove(target)

    if target.tache != log.nom_cible_avant:
        target.tache = log.nom_cible_avant
        target.save(update_fields=['tache'])

    log.annulee_le = now
    log.annulee_par = user if getattr(user, 'is_authenticated', False) else None
    log.save(update_fields=['annulee_le', 'annulee_par'])
    return {'log_id': str(log.id)}
