"""Calcul des contrôles et décisions manuelles. Aucune écriture vers Access.

Les empreintes sont recalculées à la lecture ET à chaque décision : même les
imports bulk_update rendent les visas anciens inopérants sans dépendre de signaux.
"""
import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import BaseDiameX, DocumentationComptable
from .models_pointage import MoisPointage, ObjetPointage, DecisionPointage

ROLES = ('caissiere', 'responsable', 'directeur')
LIBELLES = ('À pointer — caissière', 'À pointer — responsable opérationnel', 'À pointer — directeur', 'Pointé directeur')
POSTES = {
    'caissiere': ('Caissière', 'Caissier'),
    'responsable': ('Responsable opérationnel',),
    'directeur': ('Directeur', 'Directrice', 'Directeur adjoint'),
}


def roles_utilisateur(user):
    from apps.employees.permissions import get_user_poste_name, _normalize_poste_name, is_visiteur
    if not user.is_authenticated or not user.is_active or is_visiteur(user):
        return []
    employe = getattr(user, 'employe', None)
    # Employé rattaché, avec un poste, et non débauché.
    if not employe or not employe.poste_id or getattr(employe, 'date_debauchage', None) is not None:
        return []
    poste = _normalize_poste_name(get_user_poste_name(user))
    mapping = getattr(settings, 'POINTAGE_POSTES', POSTES)
    return [role for role in ROLES if poste in {_normalize_poste_name(p) for p in mapping.get(role, ())}]


def empreinte(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode('utf-8')).hexdigest()


def periode_mois(value):
    try:
        annee, mois = str(value).split('-')
        return date(int(annee), int(mois), 1)
    except (ValueError, TypeError):
        raise ValidationError('Choisir un mois valide (AAAA-MM).')


def lignes_autorisees(user):
    from .views_verification_unifiee import _get_scoped_diamex_queryset
    return _get_scoped_diamex_queryset(user)


def verifier_source(user, source):
    # Un mois ne peut pas être déclaré validé sur une partie seulement du fichier.
    autorisees = lignes_autorisees(user).filter(fichier_source=source)
    toutes = BaseDiameX.objects.filter(fichier_source=source)
    if not source or not autorisees.exists() or toutes.exclude(pk__in=autorisees.values('pk')).exists():
        raise PermissionDenied('Ce fichier comptable ne relève pas entièrement de votre périmètre.')


# Codes techniques DiameX reconnus sans fiche Compte : comptes de tiers (00PERS),
# transferts entre comptes (00BOOK / 00SPLITBOOK), comptes de financement (00FND*).
# Surchargeable via settings.POINTAGE_CODES_TECHNIQUES.
CODES_TECHNIQUES = ('00PERS', '00BOOK', '00SPLITBOOK', '00FND')


def est_code_technique(compte_code):
    prefixes = tuple(getattr(settings, 'POINTAGE_CODES_TECHNIQUES', CODES_TECHNIQUES))
    return (compte_code or '').strip().upper().startswith(prefixes)


def controles_ligne(entry):
    from .charte_verification import verifier_charte_compte
    from .views_verification_fournisseurs import verifier_format_charte_fournisseur
    from .views_verification_ouvrages import diviser_paiement_volume_multi
    from .extracteurs_description import extraire_ouvrage_et_mois_generique
    from .models import ScanVerificationCache

    erreurs = []
    compte = entry.compte

    if est_code_technique(entry.compte_code):
        # Compte technique DiameX : reconnu sans fiche Compte, sans contrôle
        # ouvrage / fournisseur / charte / financement et sans scan exigé
        # (mouvement interne). Seul le libellé est vérifié.
        controles = ['Compte technique']
        compte = None
        if not (entry.description or '').strip():
            erreurs.append('Libellé absent.')
    else:
        controles = ['Scan']
        if not (entry.scan or entry.scan_importe):
            erreurs.append('Scan absent.')
        elif entry.scan_importe and not entry.scan_importe.storage.exists(entry.scan_importe.name):
            erreurs.append('Scan importé introuvable.')
        if not (entry.description or '').strip():
            erreurs.append('Libellé absent.')
        if not compte or compte.compte != entry.compte_code:
            erreurs.append('Cat : compte non reconnu ou liaison à corriger.')
        else:
            controles.append('Avec ouvrage' if compte.necessite_ouvrage else 'Sans ouvrage')
            if compte.fournisseur_obligatoire:
                controles.append('Fournisseur')
                if not (entry.fournisseur or '').strip():
                    erreurs.append('Fournisseur obligatoire absent.')
                resultat = verifier_format_charte_fournisseur(entry.description, entry.fournisseur, entry.compte_code, entry.detail or '')
                erreurs.extend(resultat.get('erreurs', []))
            else:
                controles.append('Autres')
            if compte.employe_obligatoire and not (entry.pers or '').strip():
                erreurs.append('Employé obligatoire absent (Pers).')
            descriptions = [entry.description or '']
            if entry.compte_code == '707401':
                segments = diviser_paiement_volume_multi(entry.description or '', entry.compte_code, entry.montant_in or entry.montant_out)
                if segments:
                    descriptions = [s['description_partielle'] for s in segments]
            for description in descriptions:
                if compte.charte_verification:
                    resultat = verifier_charte_compte(description, compte.charte_verification, entry.compte_code)
                    if not resultat['conforme']:
                        erreurs.extend(resultat['erreurs'])
                if compte.necessite_ouvrage:
                    extraction = extraire_ouvrage_et_mois_generique(description, entry.compte_code)
                    if not (extraction.get('ouvrage_obj') or extraction.get('point_eau_obj')):
                        erreurs.append('Ouvrage non identifié dans le libellé.')
            if entry.financement_conforme is False:
                erreurs.append('Fin non conforme : attendu ' + entry.financement_attendu + '.')
        # Un résultat scan négatif connu bloque aussi un chemin non vide.
        cache = ScanVerificationCache.get_derniere_verification(entry.fichier_source)
        if cache and (entry.pk in cache.liens_morts_ids or str(entry.pk) in cache.liens_morts_ids) and not entry.scan_importe:
            erreurs.append('Le contrôle des scans signale un lien mort.')
    data = {name: getattr(entry, name) for name in (
        'id_access', 'fichier_source', 'date_m', 'date_rec', 'journal_code', 'rec',
        'description', 'montant_in', 'montant_out', 'compte_code', 'pers', 'detail',
        'info', 'fin', 'activ', 'prog', 'fournisseur', 'scan', 'match', 'bank_rec')}
    data['scan_importe'] = entry.scan_importe.name
    data['regles'] = {name: getattr(compte, name, None) for name in (
        'charte_verification', 'necessite_ouvrage', 'fournisseur_obligatoire', 'employe_obligatoire', 'financement')}
    data['erreurs'] = sorted(set(erreurs))
    return data, list(dict.fromkeys(erreurs)), controles


def montant(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def etat_objet(objet, fingerprint):
    if objet and objet.empreinte == fingerprint:
        return objet.niveau, objet.correction
    return 0, bool(objet and (objet.niveau or objet.correction or objet.empreinte))


def _noms_tiers(pers_values):
    """{valeur Pers -> nom lisible} pour les comptes de tiers 00PERS.
    Pers correspond à un surnom d'employé ou à un idxls de fournisseur (insensible à la casse)."""
    pers_values = {p for p in pers_values if p}
    if not pers_values:
        return {}
    from apps.employees.models import Employe
    from apps.billing.models import Fournisseur
    par_cle = {p.lower(): p for p in pers_values}
    noms = {}
    for surnom, nom_employe, nom, prenom in Employe.objects.exclude(surnom__isnull=True).exclude(surnom='').values_list('surnom', 'nom_employe', 'nom', 'prenom'):
        k = (surnom or '').lower()
        if k in par_cle and par_cle[k] not in noms:
            noms[par_cle[k]] = (nom_employe or (str(prenom or '') + ' ' + str(nom or '')).strip() or nom or surnom)
    for idxls, nom_fournisseur in Fournisseur.objects.exclude(idxls__isnull=True).values_list('idxls', 'nom_fournisseur'):
        k = str(idxls or '').lower()
        if k in par_cle and par_cle[k] not in noms:
            noms[par_cle[k]] = nom_fournisseur or par_cle[k]
    return noms


def solde_reel_reference(source, journal_code, periode):
    """Solde de référence importé depuis Access (table SoldesReels / `soldes_reels`)
    pour ce journal et ce mois : (montant, chemin_scan) ou (None, '')."""
    from django.db.models import Sum
    from .models import SoldesReels
    qs = SoldesReels.objects.filter(fichier_source=source, journal=journal_code, date_m=periode)
    total = qs.aggregate(total=Sum('ccy'))['total']
    if total is None:
        return None, ''
    dernier = qs.order_by('-date_rec', '-rec').first()
    return montant(total), (getattr(dernier, 'scan', '') or '')


def construire_mois(source, periode):
    mois = MoisPointage.objects.filter(fichier_source=source, periode=periode).first()
    objets = {o.cle: o for o in mois.objets.all()} if mois else {}
    # date_m est un DateField Access, sans conversion UTC ni heure implicite.
    fin = date(periode.year + (periode.month == 12), periode.month % 12 + 1, 1)
    historiques = list(BaseDiameX.objects.filter(fichier_source=source, date_m__lt=fin).select_related('compte').order_by('id_access'))
    lignes, soldes = [], []
    groupes = defaultdict(list)
    for entry in historiques:
        if entry.journal_code and not entry.journal_code.startswith(('00PERS', '00SPLITBOOK')):
            groupes['journal:' + entry.journal_code].append(entry)
        if (entry.compte_code or '').startswith('00PERS') or (entry.journal_code or '').startswith('00PERS'):
            groupes['tiers:' + (entry.pers or 'Non spécifié')].append(entry)
        if entry.date_m < periode:
            continue
        data, erreurs, controles = controles_ligne(entry)
        lignes.append(dict(cle='ligne:' + str(entry.id_access), nature='ligne', libelle=entry.description or '(Sans libellé)',
                           entry=entry, fingerprint=empreinte(data), erreurs=erreurs, controles=controles))
    noms_tiers = _noms_tiers({c[len('tiers:'):] for c in groupes if c.startswith('tiers:')})
    for cle, entries in sorted(groupes.items()):
        est_tiers = cle.startswith('tiers:')
        if est_tiers:
            calcule = sum((montant(e.montant_out) - montant(e.montant_in) if (e.compte_code or '').startswith('00PERS')
                           else montant(e.montant_in) - montant(e.montant_out) for e in entries), Decimal(0))
        else:
            calcule = sum((montant(e.montant_in) - montant(e.montant_out) for e in entries), Decimal(0))
        # Un compte de tiers soldé (mouvements qui s'annulent) n'a rien à rapprocher : on ne l'affiche pas.
        if est_tiers and calcule == 0:
            continue
        objet = objets.get(cle)
        erreurs = []
        manuel_reference = objet.solde_reference if (objet and objet.solde_reference is not None) else None
        document = objet.document if objet else None
        justification = (objet.justification if objet else '') or ''

        # Solde de référence : saisie caissière prioritaire, sinon solde réel importé
        # (journaux uniquement — un compte de tiers n'a pas de solde de référence externe).
        auto_reference, auto_scan = (None, '')
        if cle.startswith('journal:'):
            auto_reference, auto_scan = solde_reel_reference(source, cle[len('journal:'):], periode)
        reference = manuel_reference if manuel_reference is not None else auto_reference
        reference_source = 'manuel' if manuel_reference is not None else ('soldes_reels' if auto_reference is not None else '')

        # Le solde réel importé (fichier RAF validé) fait office de justificatif ;
        # sinon un DocumentationComptable présent ou le scan du solde réel.
        justificatif_ok = bool(
            reference_source == 'soldes_reels'
            or (document and document.statut == 'present' and document.chemin_document)
            or auto_scan
        )

        # Solde cumulé nul et aucun solde de référence : rien à rapprocher (compte
        # clôturé, ou tiers sans mouvement) — on ne bloque pas.
        rien_a_rapprocher = reference is None and calcule == 0

        if est_tiers:
            # Compte de tiers : pas de solde de référence externe. Les trois niveaux
            # valident directement que le solde calculé est correct (rien si solde nul).
            pass
        else:
            if reference is None and not rien_a_rapprocher:
                erreurs.append('Solde de référence à renseigner (aucun solde réel importé pour ce journal/mois).')
            if not justificatif_ok and not rien_a_rapprocher:
                erreurs.append('Justificatif de rapprochement présent requis.')
            if reference is not None and calcule != reference and not justification.strip():
                erreurs.append('Écart à justifier avant pointage.')
        if est_tiers:
            pers = cle[len('tiers:'):]
            nom_tiers = noms_tiers.get(pers, '')
            libelle = 'Tiers — ' + pers + ((' · ' + nom_tiers) if nom_tiers else '')
        else:
            nom_tiers = ''
            libelle = cle.replace(':', ' — ', 1)
        # Tous les mouvements alimentent l'empreinte, même en cas de solde inchangé.
        data = [(e.id_access, e.date_m, e.journal_code, e.compte_code, e.pers, e.montant_in, e.montant_out, e.match, e.bank_rec) for e in entries]
        evidence = (reference, reference_source, justification, auto_scan, rien_a_rapprocher, est_tiers,
                    (document.pk, document.updated_at, document.statut, document.chemin_document) if document else None)
        soldes.append(dict(cle=cle, nature='solde', libelle=libelle, calcule=calcule,
                           est_tiers=est_tiers, nom_tiers=nom_tiers, reference=reference, reference_source=reference_source,
                           rien_a_rapprocher=rien_a_rapprocher,
                           justificatif_document=document, justificatif_scan=auto_scan,
                           ecart=calcule-reference if reference is not None else None,
                           fingerprint=empreinte([data, evidence, erreurs]), erreurs=erreurs, controles=['Rapprochement']))
    rows = lignes + soldes
    for row in rows:
        objet = objets.get(row['cle'])
        row['objet'] = objet
        row['niveau'], row['correction'] = etat_objet(objet, row['fingerprint'])
        row['statut'] = 'À corriger / repointer' if row['correction'] else LIBELLES[row['niveau']]
        row['role_attendu'] = ROLES[row['niveau']] if row['niveau'] < 3 else ''
    fingerprint = empreinte([(r['cle'], r['fingerprint'], r['niveau'], r['correction']) for r in rows])
    sans_date = BaseDiameX.objects.filter(fichier_source=source, date_m__isnull=True).exists()
    pret = bool(lignes and soldes) and not sans_date and all(r['niveau'] == 3 and not r['erreurs'] and not r['correction'] for r in rows)
    valide = bool(pret and mois and mois.empreinte_validee == fingerprint)
    return dict(mois=mois, lignes=lignes, soldes=soldes, rows=rows, fingerprint=fingerprint,
                pret=pret, valide=valide, sans_date=sans_date,
                statut='Pointé et validé' if valide else ('À revalider' if mois and mois.valide_le else 'En cours de pointage'))


def journaliser(mois, objet, user, role, action, remarque, fingerprint):
    employe = getattr(user, 'employe', None)
    label = (getattr(employe, 'surnom', '') or getattr(employe, 'nom', '') or user.get_username())
    DecisionPointage.objects.create(mois=mois, objet=objet, auteur=user, auteur_libelle=label,
                                   role=role, action=action, remarque=remarque, empreinte=fingerprint)


@transaction.atomic
def decider(user, source, periode, cle, action, role, fingerprint, remarque='', preparation=None):
    verifier_source(user, source)
    if role not in roles_utilisateur(user):
        raise PermissionDenied('Votre poste ne permet pas ce niveau de pointage.')
    mois, _ = MoisPointage.objects.get_or_create(fichier_source=source, periode=periode)
    mois = MoisPointage.objects.select_for_update().get(pk=mois.pk)
    etat = construire_mois(source, periode)
    if action == 'valider_mois':
        if role != 'directeur' or not etat['pret']:
            raise ValidationError('Toutes les lignes et tous les rapprochements doivent être pointés par le directeur.')
        if fingerprint != etat['fingerprint']:
            raise ValidationError('Le mois a changé. Actualisez la page.')
        if etat['valide']:
            raise ValidationError('Ce mois est déjà validé.')
        mois.empreinte_validee = fingerprint
        mois.valide_le = timezone.now()
        mois.valide_par = user
        mois.save()
        journaliser(mois, None, user, role, action, remarque, fingerprint)
        return
    row = next((r for r in etat['rows'] if r['cle'] == cle), None)
    if not row:
        raise ValidationError('Cette ligne ou ce rapprochement ne fait plus partie du mois.')
    if fingerprint != row['fingerprint']:
        raise ValidationError('Les données ont changé. Actualisez avant de décider.')
    objet, _ = ObjetPointage.objects.get_or_create(mois=mois, cle=cle, defaults={'nature': row['nature']})
    if objet.empreinte and objet.empreinte != fingerprint:
        journaliser(mois, objet, user, role, 'invalidation', 'Données ou contrôles modifiés depuis le pointage.', objet.empreinte)
    niveau, correction = etat_objet(objet, fingerprint)
    if action == 'pointer':
        if niveau >= 3 or ROLES[niveau] != role:
            raise ValidationError('Respecter l’ordre caissière, responsable opérationnel, directeur.')
        if row['erreurs']:
            raise ValidationError(row['erreurs'])
        objet.niveau, objet.correction = niveau + 1, False
    elif action == 'correction':
        if not remarque.strip():
            raise ValidationError('Une remarque est obligatoire pour demander une correction.')
        if role != 'caissiere' and niveau < ROLES.index(role):
            raise ValidationError('Le pointage précédent est requis avant un retour en correction.')
        objet.niveau, objet.correction = 0, True
    elif action == 'remarque':
        if not remarque.strip():
            raise ValidationError('Saisir une remarque.')
        # Une observation ne modifie jamais les visas existants.
        journaliser(mois, objet, user, role, action, remarque, fingerprint)
        return
    elif action == 'preparer':
        if role != 'caissiere' or row['nature'] != 'solde':
            raise PermissionDenied('La caissière prépare les rapprochements.')
        preparation = preparation or {}
        # Solde de référence : facultatif si un solde réel est déjà importé (laisser vide = utiliser l'import).
        ref_raw = str(preparation.get('reference', '') or '').strip().replace(',', '.')
        if ref_raw:
            try:
                reference = Decimal(ref_raw)
                if not reference.is_finite() or abs(reference) >= Decimal('10000000000000000') or reference != reference.quantize(Decimal('.01')):
                    raise ValueError
            except (ValueError, ArithmeticError):
                raise ValidationError('Solde de référence invalide (deux décimales maximum).')
            objet.solde_reference = reference
        else:
            objet.solde_reference = None
        # Justificatif : facultatif si le solde réel importé porte déjà un scan.
        doc_id = preparation.get('document') or None
        if doc_id:
            document = DocumentationComptable.objects.filter(pk=doc_id, fichier_source=source,
                        annee=periode.year, mois=periode.month).first()
            types = ('recap_tiers', 'rapprochement_solde') if cle.startswith('tiers:') else ('comptage_caisse', 'releve_bancaire', 'rapprochement_solde')
            if not document or document.type_document not in types:
                raise ValidationError('Choisir un justificatif de rapprochement du même fichier et du même mois.')
            if document.journal_code and cle.startswith('journal:') and document.journal_code != cle[len('journal:'):]:
                raise ValidationError('Le justificatif appartient à un autre journal.')
            objet.document = document
        else:
            objet.document = None
        objet.justification = (preparation.get('justification', '') or '').strip()
        objet.niveau, objet.correction = 0, False
        objet.save()
        fingerprint = next(r['fingerprint'] for r in construire_mois(source, periode)['rows'] if r['cle'] == cle)
    else:
        raise ValidationError('Action inconnue.')
    objet.empreinte = fingerprint
    objet.save()
    journaliser(mois, objet, user, role, action, remarque, fingerprint)
