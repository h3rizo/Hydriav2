"""
Vue pour exporter les transactions temporaires vers Access DiameX
"""
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from django.utils.html import escape
from datetime import datetime
import json
try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    pyodbc = None
import os

from .models import DiameXTemporaire
from .pointage_export import pointer_transaction, summarize as summarize_pointage
from apps.employees.models import EmployeBaseDiameX
from .views_temporaire import _filter_transactions_by_scope

EXPORT_FIN_VALUE = 'RL Activités'

# Comptes pour lesquels les colonnes Detail et Info ne doivent JAMAIS être
# remplies lors de l'export vers DiameX (707401 = recette volumétrique,
# 748411 = paiement forfaitaire)
COMPTES_SANS_DETAIL_INFO = {'707401', '748411'}


def _validate_access_tiers_requirements(transaction, journal, compte, pers, fournisseur_idxls):
    errors = []

    if (journal == '00PERS' or compte == '00PERS') and not (pers or '').strip():
        errors.append("journal/compte 00PERS sans valeur PERS")

    if getattr(transaction, 'purchase', None):
        if not getattr(transaction, 'fournisseur', None):
            errors.append("achat sans fournisseur rattache")
        elif not fournisseur_idxls:
            errors.append("fournisseur sans IDxls pour Access")

    return errors


def _get_export_transactions(request, export_type, transaction_ids, prog_base=None):
    """Retourne les transactions exportables selon le mode choisi."""
    if export_type == 'selection' and transaction_ids:
        transactions = DiameXTemporaire.objects.filter(
            id__in=transaction_ids,
            statut__in=['en_attente', 'valide'],
        ).exclude(
            statut='exporte'
        ).exclude(
            compte_code__isnull=True
        ).exclude(
            compte_code=''
        )
    else:
        from django.db.models import Q
        base_filter = Q(statut__in=['en_attente', 'valide']) & ~Q(statut='exporte') & ~Q(compte_code__isnull=True) & ~Q(compte_code='')
        transactions = DiameXTemporaire.objects.filter(base_filter)
        if prog_base:
            transactions = transactions.filter(Q(prog=prog_base) | Q(prog__isnull=True) | Q(prog=''))
    return _filter_transactions_by_scope(transactions, request.user)


@login_required
@require_http_methods(["POST"])
def export_to_access_prepare(request):
    """
    Prépare l'export vers Access pour exécution locale via l'agent DIAMEX.
    """
    base_id = request.POST.get('base_id')
    export_type = request.POST.get('export_type')
    transaction_ids = request.POST.getlist('transaction_ids[]')

    if not base_id:
        return JsonResponse({'success': False, 'error': 'Aucun fichier Access sélectionné'}, status=400)

    try:
        base_qs = EmployeBaseDiameX.objects.all()
        if not request.user.is_superuser:
            employe = getattr(request.user, 'employe', None)
            if not employe:
                return JsonResponse({'success': False, 'error': 'Employe non trouve pour cet utilisateur'}, status=403)
            base_qs = base_qs.filter(employe=employe)
        base_diamex = base_qs.get(id=base_id)
        access_path = base_diamex.chemin_complet
    except EmployeBaseDiameX.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Fichier Access introuvable'}, status=404)

    transactions = _get_export_transactions(request, export_type, transaction_ids)
    if not transactions.exists():
        return JsonResponse({'success': False, 'error': 'Aucune transaction a exporter (en_attente ou valide)'}, status=400)

    payload = []
    invalid_transactions = []
    for t in transactions.select_related('fournisseur'):
        if t.type_transaction == 'avance':
            surnom = t.pers or ''
            montant = t.montant_out if t.montant_out else t.montant_in
            montant_formate = f"{int(montant):,}".replace(',', ' ')
            description = f"Avance_{surnom}_{montant_formate}Ar" if surnom else f"Avance_{montant_formate}Ar"
        else:
            description = t.description or ''

        journal = t.journal_code or ''
        compte = t.compte_code or ''
        pers = (t.pers or '').upper() if (journal == '00PERS' or compte == '00PERS') else None
        fournisseur_idxls = t.fournisseur.idxls if getattr(t, 'purchase', None) and getattr(t, 'fournisseur', None) else None
        validation_errors = _validate_access_tiers_requirements(
            t,
            journal,
            compte,
            pers,
            fournisseur_idxls,
        )
        if validation_errors:
            invalid_transactions.append({
                'transaction_id': t.id,
                'description': description,
                'errors': validation_errors,
            })
            continue

        if compte in COMPTES_SANS_DETAIL_INFO:
            detail_value = ''
            info_value = ''
        else:
            detail_value = t.detail or ''
            info_value = t.info or ''

        payload.append({
            'transaction_id': t.id,
            'type': t.type_transaction,
            'description': description,
            'date_rec': t.date_rec.isoformat() if t.date_rec else None,
            'montant_in': float(t.montant_in or 0),
            'montant_out': float(t.montant_out or 0),
            'journal': journal,
            'compte': compte,
            'pers': pers,
            'detail': detail_value,
            'info': info_value,
            'fin': t.fin or EXPORT_FIN_VALUE,
            'scan': t.scan or '',
            'activ': t.activ if t.activ is not None else None,
            'fournisseur': fournisseur_idxls,
        })

    if invalid_transactions:
        first_invalid = invalid_transactions[0]
        return JsonResponse({
            'success': False,
            'error': (
                "Certaines transactions ne peuvent pas etre exportees vers Access car le tiers requis est manquant. "
                f"Exemple transaction {first_invalid['transaction_id']}: {', '.join(first_invalid['errors'])}"
            ),
            'invalid_transactions': invalid_transactions[:20],
        }, status=400)

    return JsonResponse({
        'success': True,
        'mode': 'local_agent',
        'base_id': str(base_diamex.id),
        'base_name': base_diamex.base_diamex,
        'access_path': access_path,
        'transactions': payload,
    })


@login_required
@require_http_methods(["POST"])
def export_to_access_finalize(request):
    """
    Finalise l'export après insertion locale (agent DIAMEX).
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    base_id = data.get('base_id')
    results = data.get('results') or []
    prog = data.get('prog') or ''

    if not base_id:
        return JsonResponse({'success': False, 'error': 'base_id manquant'}, status=400)

    try:
        base_qs = EmployeBaseDiameX.objects.all()
        if not request.user.is_superuser:
            employe = getattr(request.user, 'employe', None)
            if not employe:
                return JsonResponse({'success': False, 'error': 'Employe non trouve pour cet utilisateur'}, status=403)
            base_qs = base_qs.filter(employe=employe)
        base_diamex = base_qs.get(id=base_id)
    except EmployeBaseDiameX.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Fichier Access introuvable'}, status=404)

    success_rows = [r for r in results if r.get('success') and r.get('transaction_id') and r.get('access_id')]
    if not success_rows:
        return JsonResponse({'success': False, 'error': 'Aucune transaction inseree localement'}, status=400)

    export_batch = f"EXP_LOCAL_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    export_details = []
    updated_count = 0
    pointage_warnings = []

    for row in success_rows:
        tx_id = row.get('transaction_id')
        access_id = row.get('access_id')
        try:
            transaction = _filter_transactions_by_scope(
                DiameXTemporaire.objects.select_related('planning_detail', 'purchase', 'salaire'),
                request.user
            ).get(id=tx_id)
        except DiameXTemporaire.DoesNotExist:
            pointage_warnings.append(
                f"Transaction {tx_id} : introuvable ou hors de votre périmètre, numéro DiameX {access_id} non reporté")
            continue

        transaction.id_diamex = str(access_id)
        transaction.prog = prog or transaction.prog or base_diamex.base_diamex
        transaction.statut = 'exporte'
        transaction.export_batch = export_batch
        transaction.save(update_fields=['id_diamex', 'prog', 'statut', 'export_batch'])

        # Pointage : reporte le numero DiameX sur tous les objets a l'origine de la ligne
        pointage = pointer_transaction(transaction, access_id, transaction.prog)
        update_target, update_count = summarize_pointage(pointage)
        pointage_warnings.extend(
            escape(f"Transaction {transaction.id} : {warning}") for warning in pointage['warnings'])

        updated_count += 1
        export_details.append({
            'transaction_id': transaction.id,
            'type': transaction.type_transaction,
            'description': transaction.description[:50] + '...' if len(transaction.description or '') > 50 else (transaction.description or ''),
            'montant': float(transaction.montant_in if transaction.montant_in else transaction.montant_out),
            'access_id': int(access_id),
            'update_target': update_target,
            'update_count': update_count,
            'prog': transaction.prog
        })

    return JsonResponse({
        'success': True,
        'inserted': updated_count,
        'message': f'Les transactions ont ete inserees localement dans {base_diamex.base_diamex}',
        'export_batch': export_batch,
        'details': export_details,
        'errors': [r.get('error') for r in results if not r.get('success') and r.get('error')] + pointage_warnings,
        'pointage_warnings': pointage_warnings,
    })


@login_required
@require_http_methods(["POST"])
def export_to_access(request):
    """
    Exporter les transactions validées vers un fichier Access DiameX
    """
    print("=" * 80)
    print("DEBUT EXPORT_TO_ACCESS")
    print("=" * 80)

    base_id = request.POST.get('base_id')
    export_type = request.POST.get('export_type')  # 'selection' ou 'all'
    transaction_ids = request.POST.getlist('transaction_ids[]')

    print(f"POST data: base_id={base_id}, export_type={export_type}, transaction_ids={transaction_ids}")

    if not base_id:
        return JsonResponse({
            'success': False,
            'error': 'Aucun fichier Access sélectionné'
        }, status=400)

    # Récupérer la base DiameX
    try:
        base_qs = EmployeBaseDiameX.objects.all()
        if not request.user.is_superuser:
            employe = getattr(request.user, 'employe', None)
            if not employe:
                return JsonResponse({
                    'success': False,
                    'error': 'Employe non trouve pour cet utilisateur'
                }, status=403)
            base_qs = base_qs.filter(employe=employe)
        base_diamex = base_qs.get(id=base_id)
        access_path = base_diamex.chemin_complet
    except EmployeBaseDiameX.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Fichier Access introuvable'
        }, status=404)

    # Vérifier que le fichier existe
    if not os.path.exists(access_path):
        return JsonResponse({
            'success': False,
            'error': f'Fichier Access introuvable: {access_path}'
        }, status=404)

    # ✅ WORKFLOW ROBUSTE : Lire le Prog directement depuis le fichier Access
    # Au lieu d'utiliser base_diamex.base_diamex (qui peut être obsolète),
    # on lit la valeur réelle depuis la table Programme du fichier Access
    try:
        conn_str_temp = (
            r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            f'DBQ={access_path};'
        )
        conn_temp = pyodbc.connect(conn_str_temp)
        cursor_temp = conn_temp.cursor()
        cursor_temp.execute("SELECT * FROM Programme")
        row = cursor_temp.fetchone()
        prog_base = row[0] if row else None  # ✅ Premier champ = nom du programme (SOURCE DE VÉRITÉ)
        cursor_temp.close()
        conn_temp.close()

        if not prog_base:
            return JsonResponse({
                'success': False,
                'error': 'Aucun programme trouvé dans la table Programme d\'Access'
            }, status=400)

        print(f"✅ PROG récupéré depuis fichier Access (table Programme): '{prog_base}'")
        print(f"   (base_diamex.base_diamex dans Django: '{base_diamex.base_diamex}' - ignoré)")

    except pyodbc.Error as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur Access lors de la lecture de la table Programme: {str(e)}'
        }, status=500)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de la lecture de la table Programme: {str(e)}'
        }, status=500)

    # Récupérer les transactions à exporter (en_attente ou valide, jamais exportées)
    print(f"DEBUG export_type: {export_type}")
    print(f"DEBUG transaction_ids: {transaction_ids}")

    if export_type == 'selection' and transaction_ids:
        # Pour sélection: exporter les IDs sélectionnés sans filtrer par prog
        # (permet d'exporter vers n'importe quelle base même si prog différent)
        transactions = DiameXTemporaire.objects.filter(
            id__in=transaction_ids,
            statut__in=['en_attente', 'valide'],  # ✅ Accepter en_attente ET valide
        ).exclude(
            statut='exporte'  # Exclure les transactions déjà exportées
        ).exclude(
            compte_code__isnull=True  # ✅ Exclure transactions sans compte
        ).exclude(
            compte_code=''  # ✅ Exclure transactions avec compte vide
        )
    else:
        # Si export_type est 'all': filtrer par prog pour éviter de mélanger les bases
        from django.db.models import Q
        transactions = DiameXTemporaire.objects.filter(
            statut__in=['en_attente', 'valide'],  # ✅ Accepter en_attente ET valide
        ).filter(
            Q(prog=prog_base) | Q(prog__isnull=True) | Q(prog='')  # ✅ Pour "Exporter tous": filtrer par prog
        ).exclude(
            statut='exporte'
        ).exclude(
            compte_code__isnull=True  # ✅ Exclure transactions sans compte
        ).exclude(
            compte_code=''  # ✅ Exclure transactions avec compte vide
        )

    # Debug: Afficher les programmes des transactions sélectionnées
    if export_type == 'selection' and transaction_ids:
        selected_transactions = _filter_transactions_by_scope(
            DiameXTemporaire.objects.filter(id__in=transaction_ids),
            request.user
        )
        print(f"DEBUG transactions sélectionnées: {selected_transactions.count()}")
        for t in selected_transactions:
            print(f"  - Transaction ID {t.id}: prog='{t.prog}' (statut={t.statut}, compte={t.compte_code})")
            print(f"    Match avec prog_base '{prog_base}': {t.prog == prog_base}")

    print(f"DEBUG transactions count AVANT filtre prog: {_filter_transactions_by_scope(DiameXTemporaire.objects.filter(statut__in=['en_attente', 'valide']), request.user).count()}")
    print(f"DEBUG transactions count APRÈS filtre prog='{prog_base}': {transactions.count()}")

    transactions = _filter_transactions_by_scope(transactions, request.user)
    if not transactions.exists():
        return JsonResponse({
            'success': False,
            'error': 'Aucune transaction à exporter (en_attente ou valide)'
        }, status=400)

    # Connexion à Access
    try:
        conn_str = (
            r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            f'DBQ={access_path};'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        inserted_count = 0
        export_batch = f"EXP_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_details = []  # Liste des détails de chaque transaction exportée
        export_errors = []  # Liste des erreurs rencontrées

        print(f"DEBUG: Début boucle d'insertion, {transactions.count()} transactions à traiter")

        # Dictionnaire pour stocker le dernier Rec par mois (clé: 'YYYY-MM')
        rec_par_mois = {}

        for transaction in transactions:
            try:
                print(f"DEBUG: Traitement transaction ID {transaction.id}")

                # Préparer les données
                journal = transaction.journal_code or ''

                # DateRec (format français DD/MM/YYYY pour Access)
                date_rec = transaction.date_rec.strftime('%d/%m/%Y') if transaction.date_rec else None

                # DateM = Premier jour du mois de DateRec (format français DD/MM/YYYY)
                if transaction.date_rec:
                    # Créer une date au 1er jour du mois de DateRec
                    premier_jour_mois = transaction.date_rec.replace(day=1)
                    date_m = premier_jour_mois.strftime('%d/%m/%Y')
                else:
                    date_m = None

                # Formater la description selon le type de transaction
                if transaction.type_transaction == 'avance':
                    # Format: Avance_[Surnom]_[Montant]Ar (avec séparateur de milliers)
                    surnom = transaction.pers or ''  # Laisser vide si pas de PERS (pas 'Inconnu')
                    montant = transaction.montant_out if transaction.montant_out else transaction.montant_in
                    montant_formate = f"{int(montant):,}".replace(',', ' ')
                    if surnom:
                        description = f"Avance_{surnom}_{montant_formate}Ar"
                    else:
                        description = f"Avance_{montant_formate}Ar"  # Sans surnom si vide
                else:
                    description = transaction.description or ''

                montant_in = transaction.montant_in if transaction.montant_in else 0
                montant_out = transaction.montant_out if transaction.montant_out else 0
                compte = transaction.compte_code or ''

                # PERS : Si Journal = 00PERS OU Cat (compte) = 00PERS → PERS = surnom en MAJUSCULES, sinon NULL
                if journal == '00PERS' or compte == '00PERS':
                    pers = (transaction.pers or '').upper()  # PERS en MAJUSCULES si 00PERS dans Journal ou Cat
                else:
                    pers = None  # NULL pour les autres cas (pas de chaîne vide)

                if compte in COMPTES_SANS_DETAIL_INFO:
                    detail = ''
                    info = ''
                else:
                    detail = transaction.detail or ''
                    info = transaction.info or ''
                fin = transaction.fin or EXPORT_FIN_VALUE
                scan = transaction.scan or ''

                # ✅ PROG OBLIGATOIRE: TOUJOURS utiliser le prog de la base Access sélectionnée
                # Cela garantit que le prog existe dans la table Programme du fichier Access
                prog = prog_base
                print(f"✅ PROG: transaction.prog='{transaction.prog}' → prog forcé='{prog}' (depuis base Access)")

                # ACTIV: Si None, on garde None (NULL dans Access), sinon on prend la valeur ou ''
                activ = transaction.activ if transaction.activ is not None else None

                # Calculer le Rec (auto-increment par mois basé sur DateRec)
                if transaction.date_rec:
                    mois_key = transaction.date_rec.strftime('%Y-%m')

                    # Si on n'a pas encore récupéré le dernier Rec pour ce mois
                    if mois_key not in rec_par_mois:
                        # Récupérer le dernier Rec pour ce mois dans Access
                        sql_max_rec = """
                            SELECT MAX(Rec) FROM DATA
                            WHERE FORMAT(DateM, 'yyyy-mm') = ?
                        """
                        cursor.execute(sql_max_rec, (mois_key,))
                        max_rec_row = cursor.fetchone()
                        max_rec = max_rec_row[0] if max_rec_row and max_rec_row[0] else 0
                        rec_par_mois[mois_key] = max_rec
                        print(f"DEBUG: Dernier Rec pour {mois_key}: {max_rec}")

                    # Incrémenter le Rec pour ce mois
                    rec_par_mois[mois_key] += 1
                    rec = rec_par_mois[mois_key]
                else:
                    rec = 1

                # Fournisseur : pour les achats, utiliser l'IDxls du fournisseur
                fournisseur_idxls = None
                if transaction.purchase and transaction.fournisseur:
                    fournisseur_idxls = transaction.fournisseur.idxls
                    print(f"  Fournisseur (Achat): '{transaction.fournisseur.nom_fournisseur}' → IDxls={fournisseur_idxls}")

                validation_errors = _validate_access_tiers_requirements(
                    transaction,
                    journal,
                    compte,
                    pers,
                    fournisseur_idxls,
                )
                if validation_errors:
                    error_msg = (
                        f"Transaction ID {transaction.id} - Export Access impossible: "
                        + ", ".join(validation_errors)
                    )
                    print(f"❌ {error_msg}")
                    export_errors.append(error_msg)
                    continue

                print(f"DEBUG: Données - Journal={journal}, Date_M={date_m}, Rec={rec}, Desc={description[:30] if len(description) > 30 else description}")

                # INSERT INTO DATA avec Rec, ACTIV et fournisseur
                # Note: CCY est un champ calculé, on utilise Cat pour le compte
                sql = """
                    INSERT INTO DATA (Journal, DateM, Rec, DateRec, Description, [In], [Out],
                                     Cat, PERS, Detail, Info, Fin, Scan, Prog, ACTIV, fournisseur)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                cursor.execute(sql, (
                    journal, date_m, rec, date_rec, description, montant_in, montant_out,
                    compte, pers, detail, info, fin, scan, prog, activ, fournisseur_idxls
                ))

                print(f"DEBUG: INSERT réussi pour transaction {transaction.id}")

                # Récupérer l'ID auto-généré par Access
                cursor.execute("SELECT @@IDENTITY")
                access_id = cursor.fetchone()[0]
                print(f"DEBUG: ID Access généré: {access_id}")

                # Mettre à jour PlanningDetail OU Releve selon le type de transaction
                update_target = None  # Pour tracking visuel
                update_count = 0  # Nombre d'enregistrements mis à jour

                if transaction.type_transaction == 'recette' and not transaction.planning_detail:
                    # RECETTE DE PAIEMENT AU VOLUME (encaissement factures)
                    # Retrouver tous les relevés concernés par cette transaction
                    # Format description:
                    # Paiement au volume "Nom de l'ouvrage" DD/MM/YYYY (1;2;3)
                    # ou Paiement au volume "Nom de l'ouvrage" DD/MM/YYYY (8 relevés)
                    from apps.billing.models import Releve
                    from apps.organization.models import Ouvrage
                    import re

                    update_target = 'Releve (Paiement au volume)'

                    if transaction.description and transaction.description.startswith('Paiement au volume "'):
                        match = re.match(r'^Paiement au volume "(.+)" (\d{2}/\d{2}/\d{4}) \((.+)\)$', transaction.description)
                        if match:
                            ouvrage_nom = match.group(1)
                            date_encaissement_str = match.group(2)

                            try:
                                ouvrage = Ouvrage.objects.get(nom_ouvrage=ouvrage_nom)
                                releves_qs = Releve.objects.filter(
                                    point_eau__ouvrage=ouvrage,
                                    datepaiement=transaction.date_rec,
                                )

                                detail_value = (transaction.detail or '').strip()
                                if detail_value.startswith('IDXLS:'):
                                    idxls_values = [value.strip() for value in detail_value[6:].split(';') if value.strip()]
                                    releves_qs = releves_qs.filter(point_eau__idxls__in=idxls_values)
                                elif detail_value.startswith('NB_RELEVES:'):
                                    releves_qs = releves_qs.filter(numeroDiameX__isnull=True)

                                update_count = releves_qs.update(
                                    numeroDiameX=str(access_id),
                                    baseDiameX=prog
                                )
                                print(f"✅ MISE À JOUR: {update_count} Releve(s) → numeroDiameX={access_id} | Ouvrage: {ouvrage_nom} {date_encaissement_str}")
                            except Ouvrage.DoesNotExist:
                                print(f"⚠️ AVERTISSEMENT: Ouvrage '{ouvrage_nom}' introuvable")

                # PAIEMENT DEMANDE BP (venant de PointEau)
                elif transaction.info == 'hydria paiement demande' or (transaction.description and 'Paiement demande BP' in transaction.description):
                    update_target = 'PointEau (Paiement demande BP)'

                    # Extraire le nom de l'abonné depuis la description
                    # Format: "Paiement demande BP - NOM_ABONNE (Village)"
                    try:
                        if ' - ' in transaction.description:
                            nom_partie = transaction.description.split(' - ')[1]
                            if '(' in nom_partie:
                                nom_abonne = nom_partie.split('(')[0].strip()

                                # Mettre à jour le PointEau correspondant
                                from apps.billing.models import PointEau
                                update_count = PointEau.objects.filter(
                                    nomabonne__iexact=nom_abonne
                                ).update(
                                    numerodiamexdemande=str(access_id),
                                    basediamexdemande=prog,
                                    datepaiementdemande=transaction.date_rec
                                )

                                if update_count > 0:
                                    print(f"✅ MISE À JOUR: {update_count} PointEau(x) (Paiement demande BP) → numerodiamexdemande={access_id} | Abonné: {nom_abonne}")
                                else:
                                    print(f"⚠️ AVERTISSEMENT: Aucun PointEau trouvé pour l'abonné '{nom_abonne}'")
                    except Exception as e:
                        print(f"⚠️ ERREUR: Parsing description paiement demande BP: {e}")

                # PAIEMENT DEVIS BP (venant de PointEau)
                elif transaction.info == 'hydria paiement devis' or (transaction.description and 'Paiement devis BP' in transaction.description):
                    update_target = 'PointEau (Paiement devis BP)'

                    # Extraire le nom de l'abonné depuis la description
                    # Format: "Paiement devis BP - NOM_ABONNE (Village) - Distance: X.XX m"
                    try:
                        if ' - ' in transaction.description:
                            nom_partie = transaction.description.split(' - ')[1]
                            if '(' in nom_partie:
                                nom_abonne = nom_partie.split('(')[0].strip()

                                # Mettre à jour le PointEau correspondant
                                from apps.billing.models import PointEau
                                update_count = PointEau.objects.filter(
                                    nomabonne__iexact=nom_abonne
                                ).update(
                                    numerodiamexpaiementdevis=str(access_id),
                                    basediamexpaiementdevis=prog,
                                    datepaiementdevis=transaction.date_rec
                                )

                                if update_count > 0:
                                    print(f"✅ MISE À JOUR: {update_count} PointEau(x) (Paiement devis BP) → numerodiamexpaiementdevis={access_id} | Abonné: {nom_abonne}")
                                else:
                                    print(f"⚠️ AVERTISSEMENT: Aucun PointEau trouvé pour l'abonné '{nom_abonne}'")
                    except Exception as e:
                        print(f"⚠️ ERREUR: Parsing description paiement devis BP: {e}")

                elif transaction.type_transaction == 'recette' and transaction.planning_detail:
                    # RECETTE FORFAITAIRE (paiement forfaitaire via planning)
                    planning_detail = transaction.planning_detail
                    update_target = 'PlanningDetail (Paiement forfaitaire)'

                    planning_detail.numeroDiameX = int(access_id)
                    planning_detail.BaseDiameX = prog
                    planning_detail.save(update_fields=['numeroDiameX', 'BaseDiameX'])
                    update_count = 1
                    print(f"✅ MISE À JOUR: PlanningDetail ID {planning_detail.id} → numeroDiameX={access_id}")

                elif transaction.purchase:
                    # ACHATS (dépenses liées aux achats réceptionnés)
                    purchase = transaction.purchase
                    update_target = 'Purchase (Achat réceptionné)'

                    purchase.numeroDiameX = str(access_id)
                    purchase.baseDiameX = prog
                    purchase.save(update_fields=['numeroDiameX', 'baseDiameX'])
                    update_count = 1
                    print(f"✅ MISE À JOUR: Purchase ID {purchase.id} (N° {purchase.purchase_number}) → numeroDiameX={access_id}, baseDiameX={prog}")

                    # Mettre à jour les prix unitaires des désignations
                    from apps.inventory.models import PurchaseItem
                    from apps.planning.models import Designation

                    purchase_items = PurchaseItem.objects.filter(purchase=purchase).select_related('designation')
                    designations_updated = 0

                    for item in purchase_items:
                        if item.designation and item.unit_price:
                            # Mettre à jour le prix unitaire et la date
                            item.designation.prix_unitaire = item.unit_price
                            item.designation.date_prix = purchase.order_date or purchase.purchase_date
                            item.designation.save(update_fields=['prix_unitaire', 'date_prix'])
                            designations_updated += 1
                            print(f"  ✅ PRIX MIS À JOUR: Designation '{item.designation.nom}' → {item.unit_price} Ar (date: {item.designation.date_prix})")

                    if designations_updated > 0:
                        print(f"✅ {designations_updated} prix de désignation(s) mis à jour")

                elif transaction.planning_detail:
                    # WORKFLOW CLASSIQUE (Avances, Bons de livraison, dépenses)
                    planning_detail = transaction.planning_detail

                    # Déterminer quel champ mettre à jour selon le type
                    if transaction.type_transaction == 'avance':
                        update_target = 'PlanningDetail (Avance)'
                        planning_detail.numeroDiameXAvance = int(access_id)
                        planning_detail.BaseDiameXAvance = prog
                        planning_detail.save(update_fields=['numeroDiameXAvance', 'BaseDiameXAvance'])
                        update_count = 1
                        print(f"✅ MISE À JOUR: PlanningDetail ID {planning_detail.id} → numeroDiameXAvance={access_id}")
                    else:
                        # Recette, dépense, transfert (bon de livraison, etc.)
                        update_target = f'PlanningDetail ({transaction.type_transaction.capitalize()})'
                        planning_detail.numeroDiameX = int(access_id)
                        planning_detail.BaseDiameX = prog
                        planning_detail.save(update_fields=['numeroDiameX', 'BaseDiameX'])
                        update_count = 1
                        print(f"✅ MISE À JOUR: PlanningDetail ID {planning_detail.id} → numeroDiameX={access_id}")

                # Marquer comme exporté dans Django
                transaction.statut = 'exporte'
                transaction.export_batch = export_batch
                transaction.save(update_fields=['statut', 'export_batch'])

                inserted_count += 1
                print(f"DEBUG: Transaction {transaction.id} marquée comme exportée")

                # Ajouter les détails pour le retour JSON
                export_details.append({
                    'transaction_id': transaction.id,
                    'type': transaction.type_transaction,
                    'description': transaction.description[:50] + '...' if len(transaction.description or '') > 50 else (transaction.description or ''),
                    'montant': float(transaction.montant_in if transaction.montant_in else transaction.montant_out),
                    'access_id': int(access_id),
                    'update_target': update_target or 'Aucune mise à jour',
                    'update_count': update_count,
                    'prog': prog
                })

            except pyodbc.Error as e:
                # En cas d'erreur sur une transaction, continuer avec les autres
                error_msg = f"Transaction ID {transaction.id} - Erreur Access: {str(e)}"
                print(f"❌ {error_msg}")
                export_errors.append(error_msg)
                continue
            except Exception as e:
                error_msg = f"Transaction ID {transaction.id} - Erreur: {str(e)}"
                print(f"❌ {error_msg}")
                export_errors.append(error_msg)
                continue

        # Commit toutes les insertions
        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({
            'success': True,
            'inserted': inserted_count,
            'message': f'Les transactions ont été insérées dans {base_diamex.base_diamex}',
            'export_batch': export_batch,
            'details': export_details,  # ✅ Ajouter les détails de traitement
            'errors': export_errors  # ✅ Ajouter les erreurs rencontrées
        })

    except pyodbc.Error as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur Access: {str(e)}'
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de l\'export: {str(e)}'
        }, status=500)
