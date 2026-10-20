"""Contrôle des frais de déplacement par la distance et la durée de route.

Pour chaque ligne de frais, on détermine un trajet (A -> B) :
  * « saisi »  : les points A et B enregistrés sur la ligne ;
  * « estimé » : sinon, base de l'agent <-> lieu du planning (aller : base -> lieu, retour : lieu -> base).
On calcule la distance et la durée par le réseau routier (profil « voiture » : taxi-brousse), on compare
le prix unitaire au prix habituel de la table des déplacements, et on additionne le temps de route par
agent et par jour. Rien ne modifie un montant : ce sont des alertes d'aide au contrôle.
"""
from collections import defaultdict

import pytz
from django.db.models import Q

from apps.geography.services import itineraire as it
from apps.geography.services import lieux
from apps.planning.models import Deplacement
from apps.planning.views_tournee_routiere import villages_des_plannings

TZ = pytz.timezone('Indian/Antananarivo')
PROFIL_BILLET = 'voiture'          # taxi-brousse : véhicule routier
MOYENS_ROUTIERS = (None, '', 'taxi-brousse')   # pirogue / bac : pas de calcul routier
RATIO_PRIX_HAUT = 1.5              # prix unitaire > 150 % du prix habituel
RATIO_PRIX_BAS = 0.5               # prix unitaire < 50 % du prix habituel
JOURNEE_MAX_MIN = 10 * 60          # temps de route cumulé au-delà duquel la journée est jugée chargée


def _alerte(code, niveau, texte):
    return {'code': code, 'niveau': niveau, 'texte': texte}


def _fmt_duree(minutes):
    h, m = divmod(int(round(minutes)), 60)
    return f'{h} h {m:02d}' if h else f'{m} min'


def _prix_reference(cache, a_id, b_id, moyen):
    """Prix habituel (dernier relevé, dans les deux sens) entre deux villages : (prix, date) ou None."""
    cle = (a_id, b_id, moyen or 'taxi-brousse')
    if cle not in cache:
        d = (Deplacement.objects.filter(Q(point_a_id=a_id, point_b_id=b_id) | Q(point_a_id=b_id, point_b_id=a_id),
                                        moyen_transport=moyen or 'taxi-brousse').order_by('-date_prix').first())
        cache[cle] = (float(d.prix_unitaire), d.date_prix) if d else None
    return cache[cle]


def analyser(details):
    """details : liste de PlanningDetail (avec planning, planning.employe, planning.employe.base chargés).

    Retourne {'lignes': {id: info}, 'jours': [...], 'resume': {...}}.
    """
    details = list(details)
    plannings = [d.planning for d in details if d.planning]
    village_du_planning = villages_des_plannings(plannings)

    # Villages impliqués -> accès au réseau (une seule requête)
    ids_villages = set()
    for d in details:
        for v in (d.point_a, d.point_b, village_du_planning.get(d.planning_id) if d.planning_id else None):
            if v is not None:
                ids_villages.add(v.id)
    acces_villages = it.acces_villages(ids_villages)

    bases, trajets, prix_cache = {}, {}, {}

    def acces_de_base(base):
        if base is None:
            return None, 'Base non renseignée pour cet agent.'
        if base.id not in bases:
            try:
                bases[base.id] = (lieux.acces_base(base), None) if base.lieu_depart else (
                    None, f'Base « {base.nom_base} » non localisée (Géographie → Lieux des bases).')
            except it.ItineraireIntrouvable as exc:
                bases[base.id] = (None, f'Base « {base.nom_base} » : {exc}')
        return bases[base.id]

    def trajet_routier(a, b):
        cle = (a['troncon_id'], round(a['fraction'], 5), round(a['distance_m']), b['troncon_id'], round(b['fraction'], 5), round(b['distance_m']))
        if cle not in trajets:
            try:
                trajets[cle] = it.reseau().itineraire(a, b, 'temps', PROFIL_BILLET)
            except it.ItineraireIntrouvable:
                trajets[cle] = None
        return trajets[cle]

    lignes = {}
    for d in details:
        planning = d.planning
        employe = planning.employe if planning else None
        moyen = d.moyen_transport
        info = {'source': None, 'de': '', 'vers': '', 'distance_km': None, 'duree_min': None,
                'prix_reference': None, 'date_prix': None, 'ecart_pct': None, 'alertes': []}
        lignes[d.id] = info
        a_village, b_village = d.point_a, d.point_b
        acces_a = acces_b = None
        if a_village and b_village:
            info.update(source='saisi', de=a_village.nom_village, vers=b_village.nom_village)
            acces_a, acces_b = acces_villages.get(a_village.id), acces_villages.get(b_village.id)
        else:
            lieu_planning = village_du_planning.get(planning.id) if planning else None
            base = getattr(employe, 'base', None)
            acces_base, raison = acces_de_base(base)
            if lieu_planning is None:
                info['alertes'].append(_alerte('lieu_inconnu', 'info', "Aucun trajet saisi et le lieu du planning est inconnu (ni point d'eau ni ouvrage localisé)."))
            elif acces_base is None:
                info['alertes'].append(_alerte('base_non_localisee', 'info', f'Aucun trajet saisi ; estimation impossible. {raison}'))
            else:
                depart_est_base = (d.trajet or 'aller') != 'retour'
                nom_base = acces_base['nom']
                info.update(source='estime', de=nom_base if depart_est_base else lieu_planning.nom_village,
                            vers=lieu_planning.nom_village if depart_est_base else nom_base)
                acces_lieu = acces_villages.get(lieu_planning.id)
                acces_a, acces_b = (acces_base, acces_lieu) if depart_est_base else (acces_lieu, acces_base)
                if base.village_depart_id:
                    a_village, b_village = (base.village_depart, lieu_planning) if depart_est_base else (lieu_planning, base.village_depart)

        if info['source'] and moyen in MOYENS_ROUTIERS:
            if acces_a and acces_b:
                r = trajet_routier(acces_a, acces_b)
                if r:
                    info['distance_km'] = round(r['distance_m'] / 1000, 1)
                    info['duree_min'] = round(r['duree_s'] / 60)
                else:
                    info['alertes'].append(_alerte('trajet_introuvable', 'warning',
                                                   f"Aucune route entre {info['de']} et {info['vers']} dans le réseau."))
            else:
                info['alertes'].append(_alerte('village_hors_reseau', 'info', "Un des lieux n'est pas rattaché au réseau routier."))

        # Comparaison au prix habituel (villages connus des deux côtés)
        if a_village and b_village and d.pu:
            ref = _prix_reference(prix_cache, a_village.id, b_village.id, moyen)
            if ref:
                prix, date_prix = ref
                info['prix_reference'], info['date_prix'] = prix, date_prix.strftime('%d/%m/%Y')
                if prix > 0:
                    ratio = float(d.pu) / prix
                    info['ecart_pct'] = round((ratio - 1) * 100)
                    if ratio > RATIO_PRIX_HAUT:
                        info['alertes'].append(_alerte('prix_eleve', 'warning',
                                                       f'Prix unitaire {float(d.pu):,.0f} Ar : {info["ecart_pct"]:+d} % par rapport au prix habituel ({prix:,.0f} Ar).'.replace(',', ' ')))
                    elif ratio < RATIO_PRIX_BAS:
                        info['alertes'].append(_alerte('prix_bas', 'info',
                                                       f'Prix unitaire {float(d.pu):,.0f} Ar : {info["ecart_pct"]:+d} % par rapport au prix habituel ({prix:,.0f} Ar).'.replace(',', ' ')))

    # Temps de route cumulé par agent et par jour. Un même trajet (même départ, même arrivée) répété sur plusieurs
    # lignes du même jour (plusieurs billets, plusieurs désignations) n'est compté qu'UNE fois : ce n'est pas du
    # temps de route en plus.
    par_jour = defaultdict(lambda: {'trajets': {}, 'ids': []})
    for d in details:
        info = lignes[d.id]
        if info['duree_min'] is None or not d.planning or not d.planning.date or not d.planning.employe_id:
            continue
        jour = d.planning.date.astimezone(TZ).date()
        cle = (d.planning.employe_id, jour)
        par_jour[cle]['ids'].append(d.id)
        par_jour[cle]['trajets'].setdefault((info['de'], info['vers']), (info['duree_min'], info['distance_km'] or 0))
    jours = []
    for (employe_id, jour), v in sorted(par_jour.items(), key=lambda kv: kv[0][1]):
        duree = sum(t[0] for t in v['trajets'].values())
        distance = sum(t[1] for t in v['trajets'].values())
        chargee = duree > JOURNEE_MAX_MIN
        jours.append({'date': jour.strftime('%Y-%m-%d'), 'date_display': jour.strftime('%d/%m/%Y'),
                      'duree_min': duree, 'distance_km': round(distance, 1),
                      'nb_lignes': len(v['ids']), 'nb_trajets': len(v['trajets']), 'chargee': chargee})
        if chargee:
            for i in v['ids']:
                lignes[i]['alertes'].append(_alerte(
                    'journee_chargee', 'warning',
                    f"Temps de route de la journée : {_fmt_duree(duree)} (plus de {JOURNEE_MAX_MIN // 60} h)."))

    nb_alertes = sum(1 for i in lignes.values() if any(a['niveau'] == 'warning' for a in i['alertes']))
    resume = {
        'duree_min': sum(j['duree_min'] for j in jours), 'distance_km': round(sum(j['distance_km'] for j in jours), 1),
        'nb_lignes': len(lignes), 'nb_estimees': sum(1 for i in lignes.values() if i['source'] == 'estime'),
        'nb_sans_trajet': sum(1 for i in lignes.values() if i['source'] is None),
        'nb_avec_alerte': nb_alertes, 'jours_charges': sum(1 for j in jours if j['chargee']),
    }
    return {'lignes': lignes, 'jours': jours, 'resume': resume}
