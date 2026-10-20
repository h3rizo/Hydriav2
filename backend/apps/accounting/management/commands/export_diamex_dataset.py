"""
Phase 1 - Export et rapport qualite du dataset historique DiameX.

Cette commande est STRICTEMENT en lecture seule sur la base : elle lit les lignes
`BaseDiameX` (la table "diameX"), resout les libelles Journal / Compte / Fournisseur
a partir des referentiels, et ecrit dans un dossier :

  - dataset.jsonl              : 1 ecriture historique par ligne (features + labels)
  - eval_sample.jsonl          : sous-echantillon avec justificatif, pour le test Phase 2-4
  - eval_sample_groundtruth.csv: le meme echantillon en tableau lisible
  - quality_report.md / .json  : rapport de qualite des donnees (incoherences signalees,
                                 jamais corrigees automatiquement)
  - README.md                  : description des fichiers et du schema

Aucune ecriture en base. A lancer sur la prod (ou un dump prod) : la base de dev
locale ne contient pas de donnees DiameX reelles.

Exemples :
  python manage.py export_diamex_dataset
  python manage.py export_diamex_dataset --out /tmp/diamex --eval-sample 100 --seed 42
  python manage.py export_diamex_dataset --fichier "Base 1" --date-min 2024-01-01
"""
import csv
import json
import os
import random
import statistics
from collections import Counter, defaultdict
from datetime import datetime, date
from difflib import SequenceMatcher

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.models import BaseDiameX
from apps.billing.models import Fournisseur
from apps.organization.models import Base, Compte, Journal


# --- normalisation (copie locale des helpers de billing.views_fournisseurs pour
#     ne pas importer un module de vues lourd dans une commande) ---------------

def _norm_key(value):
    """minuscule alphanum, espaces normalises. 'Quincaillerie  SOA!' -> 'quincaillerie soa'"""
    cleaned = ''.join(ch.lower() if ch.isalnum() else ' ' for ch in str(value or '').strip())
    return ' '.join(cleaned.split())


def _iso(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return None


def _sens(montant_in, montant_out):
    has_in = bool(montant_in) and montant_in > 0
    has_out = bool(montant_out) and montant_out > 0
    if has_in and has_out:
        return 'ambigu'
    if has_in:
        return 'in'
    if has_out:
        return 'out'
    return 'nul'


class Command(BaseCommand):
    help = "Phase 1 : exporte le dataset historique DiameX (JSONL) et un rapport qualite. Lecture seule."

    def add_arguments(self, parser):
        parser.add_argument('--out', type=str, default=None,
                            help="Dossier de sortie (defaut: <BASE_DIR>/exports/diamex_dataset/<horodatage>)")
        parser.add_argument('--fichier', action='append', default=None,
                            help="Filtre fichier_source (icontains). Repetable.")
        parser.add_argument('--date-min', type=str, default=None, help="date_m >= YYYY-MM-DD")
        parser.add_argument('--date-max', type=str, default=None, help="date_m <= YYYY-MM-DD")
        parser.add_argument('--limit', type=int, default=None, help="Nombre max de lignes (tests)")
        parser.add_argument('--with-scan-only', action='store_true',
                            help="N'exporte que les lignes ayant un justificatif (hyperlien ou copie serveur)")
        parser.add_argument('--eval-sample', type=int, default=0,
                            help="Taille du sous-echantillon d'evaluation (lignes avec justificatif)")
        parser.add_argument('--seed', type=int, default=1234, help="Graine aleatoire pour l'echantillon")

    # ------------------------------------------------------------------ #

    def handle(self, *args, **opts):
        out_dir = opts['out'] or os.path.join(
            settings.BASE_DIR, 'exports', 'diamex_dataset',
            timezone.now().strftime('%Y%m%d-%H%M%S'),
        )
        os.makedirs(out_dir, exist_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Sortie : {out_dir}"))

        date_min = self._parse_date(opts['date_min'])
        date_max = self._parse_date(opts['date_max'])

        # --- referentiels charges une seule fois -----------------------
        self.stdout.write("Chargement des referentiels...")
        bases_by_prog = defaultdict(list)
        for b in Base.objects.select_related('organisation').all():
            if b.prog_diamex:
                bases_by_prog[b.prog_diamex.strip()].append(b)

        journals_by_code = defaultdict(list)   # code -> [Journal]
        for j in Journal.objects.select_related('base').all():
            if j.code:
                journals_by_code[j.code.strip()].append(j)

        comptes_by_code = defaultdict(list)    # compte -> [Compte]
        for c in Compte.objects.select_related('organisation').all():
            if c.compte:
                comptes_by_code[c.compte.strip()].append(c)

        fournisseurs = list(Fournisseur.objects.only('id', 'idxls', 'nom_fournisseur'))
        four_by_idxls = {f.idxls: f for f in fournisseurs if f.idxls is not None}
        four_by_norm = {}
        for f in fournisseurs:
            four_by_norm.setdefault(_norm_key(f.nom_fournisseur), f)

        # --- queryset ------------------------------------------------- #
        qs = BaseDiameX.objects.select_related('journal', 'compte').all()
        if opts['fichier']:
            from django.db.models import Q
            q = Q()
            for frag in opts['fichier']:
                q |= Q(fichier_source__icontains=frag)
            qs = qs.filter(q)
        if date_min:
            qs = qs.filter(date_m__gte=date_min)
        if date_max:
            qs = qs.filter(date_m__lte=date_max)
        qs = qs.order_by('fichier_source', 'id')
        if opts['limit']:
            qs = qs[:opts['limit']]

        total_scanne = qs.count()
        self.stdout.write(f"Lignes a traiter : {total_scanne:,}")
        if total_scanne == 0:
            self.stdout.write(self.style.WARNING(
                "Aucune ligne. Sur la base de dev locale c'est normal (pas de donnees DiameX). "
                "Lancer sur la prod / un dump prod."
            ))

        # --- accumulateurs rapport qualite --------------------------- #
        agg = {
            'total': 0,
            'par_fichier': Counter(),
            'par_annee': Counter(),
            'scan_hyperlien': 0,
            'scan_copie_serveur': 0,
            'scan_aucun': 0,
            'journal_codes': Counter(),
            'journal_non_resolu': Counter(),
            'compte_codes': Counter(),
            'compte_non_resolu': Counter(),
            'four_vide': 0,
            'four_raw': Counter(),
            'four_non_resolu': Counter(),
            'four_norm_to_raw': defaultdict(set),
            'sens': Counter(),
            'desc_vide': 0,
            'desc_counter': Counter(),
            'desc_egale_fournisseur': 0,
            'desc_len': [],
            'date_min': None,
            'date_max': None,
        }

        dataset_path = os.path.join(out_dir, 'dataset.jsonl')
        # L'echantillon d'eval doit etre rejouable cote serveur : seule la copie
        # serveur (scan_importe, sous MEDIA_ROOT du VPS) est atteignable par la
        # commande d'eval. Repli sur l'hyperlien si aucune copie serveur.
        eval_pool_server = []   # rec avec copie serveur (prioritaire)
        eval_pool_hyperlink = []  # rec avec seulement l'hyperlien Access

        with open(dataset_path, 'w', encoding='utf-8') as fh:
            for entry in qs.iterator(chunk_size=2000):
                rec = self._build_record(
                    entry, bases_by_prog, journals_by_code, comptes_by_code,
                    four_by_idxls, four_by_norm,
                )
                has_scan = rec['scan']['has_hyperlink'] or rec['scan']['has_server_copy']
                if opts['with_scan_only'] and not has_scan:
                    self._accumulate(agg, rec)  # compte quand meme dans le rapport
                    continue

                fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
                self._accumulate(agg, rec)
                if rec['scan']['has_server_copy']:
                    eval_pool_server.append(rec)
                elif rec['scan']['has_hyperlink']:
                    eval_pool_hyperlink.append(rec)

        eval_pool = eval_pool_server or eval_pool_hyperlink
        if not eval_pool_server and eval_pool_hyperlink:
            self.stdout.write(self.style.WARNING(
                "Aucune copie serveur (scan_importe) : l'echantillon d'eval utilisera "
                "les hyperliens Access, non atteignables depuis le VPS. Verifier que le "
                "workflow d'import a bien pousse les scans."
            ))

        # --- rapport qualite ---------------------------------------- #
        report = self._build_report(agg, {
            'journaux': Journal.objects.count(),
            'comptes': Compte.objects.count(),
            'fournisseurs': len(fournisseurs),
            'fournisseurs_avec_idxls': len(four_by_idxls),
        })
        with open(os.path.join(out_dir, 'quality_report.json'), 'w', encoding='utf-8') as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
        with open(os.path.join(out_dir, 'quality_report.md'), 'w', encoding='utf-8') as fh:
            fh.write(self._render_report_md(report))

        # --- echantillon d'evaluation ------------------------------- #
        n_eval = opts['eval_sample']
        if n_eval and eval_pool:
            rnd = random.Random(opts['seed'])
            # stratification legere par prefixe de compte (classe de charge)
            buckets = defaultdict(list)
            for r in eval_pool:
                code = (r['labels']['compte_code'] or '')[:3] or '???'
                buckets[code].append(r)
            sample = []
            keys = sorted(buckets)
            i = 0
            while len(sample) < min(n_eval, len(eval_pool)):
                b = buckets[keys[i % len(keys)]]
                if b:
                    sample.append(b.pop(rnd.randrange(len(b))))
                i += 1
                if i > n_eval * 20:
                    break
            rnd.shuffle(sample)
            self._write_eval_sample(out_dir, sample)
            self.stdout.write(self.style.SUCCESS(f"Echantillon d'evaluation : {len(sample)} lignes"))
        elif n_eval:
            self.stdout.write(self.style.WARNING(
                "--eval-sample demande mais aucune ligne avec justificatif disponible."
            ))

        self._write_readme(out_dir)
        self.stdout.write(self.style.SUCCESS("Termine."))
        self.stdout.write(f"  dataset.jsonl        : {agg['total']:,} lignes exportees")
        self.stdout.write(f"  quality_report.md    : rapport qualite")

    # ------------------------------------------------------------------ #
    # construction d'un enregistrement
    # ------------------------------------------------------------------ #

    def _build_record(self, e, bases_by_prog, journals_by_code, comptes_by_code,
                      four_by_idxls, four_by_norm):
        prog = (e.prog or '').strip()
        base_list = bases_by_prog.get(prog, [])
        base = base_list[0] if base_list else None

        # --- Journal ---
        jcode = (e.journal_code or '').strip()
        journal_obj = e.journal
        if journal_obj is None and jcode:
            cands = journals_by_code.get(jcode, [])
            if base is not None:
                cands = [j for j in cands if j.base_id == base.id] or cands
            journal_obj = cands[0] if cands else None

        # --- Compte ---
        ccode = (e.compte_code or '').strip()
        compte_obj = e.compte
        if compte_obj is None and ccode:
            cands = comptes_by_code.get(ccode, [])
            if base is not None:
                cands = [c for c in cands if c.organisation_id == base.organisation_id] or cands
            compte_obj = cands[0] if cands else None

        # --- Fournisseur ---
        raw_four = (e.fournisseur or '').strip()
        four_obj = None
        four_kind = 'none'
        if raw_four:
            if raw_four.isdigit() and int(raw_four) in four_by_idxls:
                four_obj = four_by_idxls[int(raw_four)]
                four_kind = 'idxls'
            elif _norm_key(raw_four) in four_by_norm:
                four_obj = four_by_norm[_norm_key(raw_four)]
                four_kind = 'nom_exact'

        montant_in = float(e.montant_in or 0)
        montant_out = float(e.montant_out or 0)

        has_server_copy = bool(getattr(e.scan_importe, 'name', '') or '')

        return {
            'id': e.id,
            'id_access': e.id_access,
            'fichier_source': e.fichier_source,
            'prog': prog or None,
            'base': ({
                'id': str(base.id), 'nom': base.nom_base,
                'organisation': base.organisation.nom_organisation if base.organisation_id else None,
            } if base else None),
            'base_ambigu': len(base_list) > 1,
            'date_m': _iso(e.date_m),
            'date_rec': _iso(e.date_rec),
            'rec': e.rec,
            'labels': {
                'journal_code': jcode or None,
                'journal_name': journal_obj.nom_journal if journal_obj else None,
                'journal_matched': journal_obj is not None,
                'compte_code': ccode or None,
                'compte_name': compte_obj.nom_compte if compte_obj else None,
                'compte_matched': compte_obj is not None,
                'fournisseur_raw': raw_four or None,
                'fournisseur_norm': _norm_key(raw_four) or None,
                'fournisseur_id': str(four_obj.id) if four_obj else None,
                'fournisseur_name': four_obj.nom_fournisseur if four_obj else None,
                'fournisseur_match_kind': four_kind,
                'montant_in': montant_in,
                'montant_out': montant_out,
                'sens': _sens(montant_in, montant_out),
            },
            'features': {
                'description': e.description or '',
                'info': e.info or '',
                'pers': e.pers or '',
                'detail': e.detail or '',
                'activ': e.activ or '',
                'fin': e.fin or '',
            },
            'scan': {
                'hyperlink': e.scan or None,
                'has_hyperlink': bool((e.scan or '').strip()),
                'server_copy': (getattr(e.scan_importe, 'name', '') or None),
                'has_server_copy': has_server_copy,
            },
        }

    # ------------------------------------------------------------------ #

    def _accumulate(self, agg, rec):
        agg['total'] += 1
        agg['par_fichier'][rec['fichier_source']] += 1
        lab = rec['labels']

        if rec['date_m']:
            y = rec['date_m'][:4]
            agg['par_annee'][y] += 1
            if agg['date_min'] is None or rec['date_m'] < agg['date_min']:
                agg['date_min'] = rec['date_m']
            if agg['date_max'] is None or rec['date_m'] > agg['date_max']:
                agg['date_max'] = rec['date_m']

        if rec['scan']['has_hyperlink']:
            agg['scan_hyperlien'] += 1
        if rec['scan']['has_server_copy']:
            agg['scan_copie_serveur'] += 1
        if not rec['scan']['has_hyperlink'] and not rec['scan']['has_server_copy']:
            agg['scan_aucun'] += 1

        if lab['journal_code']:
            agg['journal_codes'][lab['journal_code']] += 1
            if not lab['journal_matched']:
                agg['journal_non_resolu'][lab['journal_code']] += 1
        if lab['compte_code']:
            agg['compte_codes'][lab['compte_code']] += 1
            if not lab['compte_matched']:
                agg['compte_non_resolu'][lab['compte_code']] += 1

        raw = lab['fournisseur_raw']
        if not raw:
            agg['four_vide'] += 1
        else:
            agg['four_raw'][raw] += 1
            agg['four_norm_to_raw'][lab['fournisseur_norm']].add(raw)
            if lab['fournisseur_match_kind'] == 'none':
                agg['four_non_resolu'][raw] += 1

        agg['sens'][lab['sens']] += 1

        desc = rec['features']['description'].strip()
        if not desc:
            agg['desc_vide'] += 1
        else:
            agg['desc_counter'][desc] += 1
            agg['desc_len'].append(len(desc))
            if raw and _norm_key(desc) == _norm_key(raw):
                agg['desc_egale_fournisseur'] += 1

    # ------------------------------------------------------------------ #

    def _build_report(self, agg, referentiels):
        total = agg['total'] or 1

        # variantes orthographiques : meme forme normalisee, >= 2 ecritures brutes
        variantes = sorted(
            ((norm, sorted(raws)) for norm, raws in agg['four_norm_to_raw'].items() if len(raws) > 1),
            key=lambda kv: -len(kv[1]),
        )[:40]

        # clusters flous sur les valeurs brutes distinctes (petit ensemble)
        distinct_raw = [r for r, _ in agg['four_raw'].most_common()]
        fuzzy_clusters = self._fuzzy_clusters(distinct_raw, agg['four_raw'])

        desc_len = agg['desc_len']
        desc_stats = {}
        if desc_len:
            desc_stats = {
                'min': min(desc_len),
                'median': int(statistics.median(desc_len)),
                'p90': int(statistics.quantiles(desc_len, n=10)[8]) if len(desc_len) > 10 else max(desc_len),
                'max': max(desc_len),
            }
        desc_dupes = sum(c for c in agg['desc_counter'].values() if c > 1)

        return {
            'genere_le': timezone.now().isoformat(),
            'referentiels': referentiels,
            'volumetrie': {
                'total_exporte': agg['total'],
                'periode': [agg['date_min'], agg['date_max']],
                'par_fichier_source': dict(agg['par_fichier'].most_common()),
                'par_annee': dict(sorted(agg['par_annee'].items())),
            },
            'justificatifs': {
                'avec_hyperlien': agg['scan_hyperlien'],
                'avec_hyperlien_pct': round(100 * agg['scan_hyperlien'] / total, 1),
                'avec_copie_serveur': agg['scan_copie_serveur'],
                'avec_copie_serveur_pct': round(100 * agg['scan_copie_serveur'] / total, 1),
                'sans_aucun_justificatif': agg['scan_aucun'],
                'sans_aucun_justificatif_pct': round(100 * agg['scan_aucun'] / total, 1),
            },
            'journal': {
                'codes_distincts': len(agg['journal_codes']),
                'lignes_code_non_resolu': sum(agg['journal_non_resolu'].values()),
                'top_codes_non_resolus': agg['journal_non_resolu'].most_common(20),
            },
            'compte_cat': {
                'codes_distincts': len(agg['compte_codes']),
                'lignes_code_non_resolu': sum(agg['compte_non_resolu'].values()),
                'top_codes_non_resolus': agg['compte_non_resolu'].most_common(20),
            },
            'fournisseur': {
                'lignes_vides': agg['four_vide'],
                'lignes_vides_pct': round(100 * agg['four_vide'] / total, 1),
                'valeurs_brutes_distinctes': len(agg['four_raw']),
                'formes_normalisees_distinctes': len(agg['four_norm_to_raw']),
                'lignes_non_rattachees_au_referentiel': sum(agg['four_non_resolu'].values()),
                'top_brutes_non_rattachees': agg['four_non_resolu'].most_common(30),
                'variantes_orthographiques': variantes,
                'clusters_flous': fuzzy_clusters,
            },
            'montant_sens': {
                'repartition_sens': dict(agg['sens']),
                'ambigus_in_et_out': agg['sens'].get('ambigu', 0),
                'nuls_ni_in_ni_out': agg['sens'].get('nul', 0),
            },
            'description': {
                'vides': agg['desc_vide'],
                'lignes_dupliquees_exact': desc_dupes,
                'egale_au_fournisseur': agg['desc_egale_fournisseur'],
                'longueur': desc_stats,
            },
        }

    @staticmethod
    def _fuzzy_clusters(distinct_raw, counter, threshold=0.88, cap=400):
        """Regroupe les valeurs brutes proches (orthographe). Cap pour rester rapide."""
        items = distinct_raw[:cap]
        norms = [_norm_key(x) for x in items]
        used = set()
        clusters = []
        for i, a in enumerate(items):
            if i in used or not norms[i]:
                continue
            grp = [a]
            for j in range(i + 1, len(items)):
                if j in used or not norms[j]:
                    continue
                if abs(len(norms[i]) - len(norms[j])) > 3:
                    continue
                if SequenceMatcher(None, norms[i], norms[j]).ratio() >= threshold:
                    grp.append(items[j])
                    used.add(j)
            if len(grp) > 1:
                clusters.append(sorted(grp, key=lambda x: -counter[x]))
        clusters.sort(key=lambda g: -sum(counter[x] for x in g))
        return clusters[:25]

    # ------------------------------------------------------------------ #

    def _render_report_md(self, r):
        L = []
        w = L.append
        w(f"# Rapport qualite - dataset DiameX\n")
        w(f"_Genere le {r['genere_le']}_\n")
        ref = r['referentiels']
        w(f"Referentiels : {ref['journaux']} journaux, {ref['comptes']} comptes, "
          f"{ref['fournisseurs']} fournisseurs (dont {ref['fournisseurs_avec_idxls']} avec IDxls).\n")

        v = r['volumetrie']
        w(f"## Volumetrie\n")
        w(f"- Total exporte : **{v['total_exporte']:,}**")
        w(f"- Periode : {v['periode'][0]} -> {v['periode'][1]}")
        w(f"- Par fichier source :")
        for k, n in v['par_fichier_source'].items():
            w(f"  - {k} : {n:,}")
        w(f"- Par annee : {', '.join(f'{k}={n}' for k, n in v['par_annee'].items())}\n")

        j = r['justificatifs']
        w(f"## Justificatifs\n")
        w(f"- Avec hyperlien Access : {j['avec_hyperlien']:,} ({j['avec_hyperlien_pct']} %)")
        w(f"- Avec copie serveur (`scan_importe`) : {j['avec_copie_serveur']:,} ({j['avec_copie_serveur_pct']} %)")
        w(f"- **Sans aucun justificatif : {j['sans_aucun_justificatif']:,} ({j['sans_aucun_justificatif_pct']} %)** "
          f"-> inutilisables comme verite terrain\n")

        w(f"## Journal\n")
        w(f"- Codes distincts : {r['journal']['codes_distincts']}")
        w(f"- Lignes avec code non resolu dans le referentiel : {r['journal']['lignes_code_non_resolu']:,}")
        for code, n in r['journal']['top_codes_non_resolus']:
            w(f"  - `{code}` : {n:,}")
        w("")

        w(f"## Compte (Cat)\n")
        w(f"- Codes distincts : {r['compte_cat']['codes_distincts']}")
        w(f"- Lignes avec code non resolu : {r['compte_cat']['lignes_code_non_resolu']:,}")
        for code, n in r['compte_cat']['top_codes_non_resolus']:
            w(f"  - `{code}` : {n:,}")
        w("")

        f = r['fournisseur']
        w(f"## Fournisseur\n")
        w(f"- Lignes vides : {f['lignes_vides']:,} ({f['lignes_vides_pct']} %)")
        w(f"- Valeurs brutes distinctes : {f['valeurs_brutes_distinctes']:,}")
        w(f"- Formes normalisees distinctes : {f['formes_normalisees_distinctes']:,}")
        w(f"- Lignes non rattachees a la table Fournisseur : {f['lignes_non_rattachees_au_referentiel']:,}")
        w(f"\n### Top valeurs brutes non rattachees")
        for val, n in f['top_brutes_non_rattachees']:
            w(f"  - {val!r} : {n:,}")
        w(f"\n### Variantes orthographiques (meme forme normalisee, plusieurs graphies)")
        for norm, raws in f['variantes_orthographiques']:
            w(f"  - {norm!r} <- {raws}")
        w(f"\n### Clusters d'orthographe proche")
        for grp in f['clusters_flous']:
            w(f"  - {grp}")
        w("")

        m = r['montant_sens']
        w(f"## Montant / sens\n")
        w(f"- Repartition : {m['repartition_sens']}")
        w(f"- **Ambigus (In>0 ET Out>0) : {m['ambigus_in_et_out']:,}**")
        w(f"- Nuls (ni In ni Out) : {m['nuls_ni_in_ni_out']:,}\n")

        d = r['description']
        w(f"## Description (libelle)\n")
        w(f"- Vides : {d['vides']:,}")
        w(f"- Lignes dupliquees a l'identique : {d['lignes_dupliquees_exact']:,}")
        w(f"- Description == Fournisseur : {d['egale_au_fournisseur']:,}")
        w(f"- Longueur : {d['longueur']}\n")

        return '\n'.join(L)

    # ------------------------------------------------------------------ #

    def _write_eval_sample(self, out_dir, sample):
        with open(os.path.join(out_dir, 'eval_sample.jsonl'), 'w', encoding='utf-8') as fh:
            for r in sample:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        with open(os.path.join(out_dir, 'eval_sample_groundtruth.csv'), 'w', encoding='utf-8', newline='') as fh:
            wr = csv.writer(fh, delimiter=';')
            wr.writerow(['id', 'fichier_source', 'date_m', 'description',
                         'journal_code', 'journal_name', 'compte_code', 'compte_name',
                         'fournisseur_raw', 'fournisseur_name', 'montant_in', 'montant_out', 'sens',
                         'scan_hyperlink', 'scan_server_copy'])
            for r in sample:
                lab = r['labels']
                wr.writerow([
                    r['id'], r['fichier_source'], r['date_m'], r['features']['description'],
                    lab['journal_code'], lab['journal_name'], lab['compte_code'], lab['compte_name'],
                    lab['fournisseur_raw'], lab['fournisseur_name'],
                    lab['montant_in'], lab['montant_out'], lab['sens'],
                    r['scan']['hyperlink'], r['scan']['server_copy'],
                ])

    def _write_readme(self, out_dir):
        txt = """# Dataset DiameX - Phase 1

Genere par `python manage.py export_diamex_dataset`. Lecture seule sur la base.

## Fichiers

| Fichier | Contenu |
|---|---|
| `dataset.jsonl` | 1 ecriture historique `BaseDiameX` par ligne. Voir schema ci-dessous. |
| `eval_sample.jsonl` | Sous-echantillon (option `--eval-sample N`) de lignes ayant une **copie serveur** du justificatif (`scan_importe`, atteignable sous MEDIA_ROOT du VPS), stratifie par prefixe de compte. Repli sur l'hyperlien Access si aucune copie serveur. Sert de verite terrain pour tester le pipeline Phase 2-4. |
| `eval_sample_groundtruth.csv` | Le meme echantillon, aplati, separateur `;` (Excel FR). |
| `quality_report.md` / `.json` | Rapport de qualite : incoherences **signalees, jamais corrigees**. |

## Schema d'une ligne de `dataset.jsonl`

```
id, id_access, fichier_source, prog, base{id,nom,organisation}, base_ambigu,
date_m, date_rec, rec
labels:
  journal_code, journal_name, journal_matched(bool)
  compte_code, compte_name, compte_matched(bool)
  fournisseur_raw, fournisseur_norm, fournisseur_id, fournisseur_name,
  fournisseur_match_kind (idxls|nom_exact|none)
  montant_in, montant_out, sens (in|out|ambigu|nul)
features:
  description, info, pers, detail, activ, fin   <- ce que voit / saisit l'operateur
scan:
  hyperlink, has_hyperlink, server_copy, has_server_copy
```

`labels` = cibles a predire. `features` + le scan = entrees du pipeline.
Les lignes sans justificatif (`has_hyperlink=false` ET `has_server_copy=false`)
restent dans `dataset.jsonl` (utiles pour l'index de similarite Phase 3) mais ne
peuvent pas servir de verite terrain pour l'extraction.
"""
        with open(os.path.join(out_dir, 'README.md'), 'w', encoding='utf-8') as fh:
            fh.write(txt)

    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_date(s):
        if not s:
            return None
        try:
            return datetime.strptime(s, '%Y-%m-%d').date()
        except ValueError:
            raise CommandError(f"Date invalide (attendu YYYY-MM-DD) : {s}")
