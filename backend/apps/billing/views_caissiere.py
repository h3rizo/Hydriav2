"""
Views pour le traitement des retours de tickets par la caissière
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import json

from apps.planning.models import PlanningDetail, BonLivraison
from apps.accounting.models import DiameXTemporaire
from apps.inventory.models import Stock, StockMovement
from apps.billing.models import Fournisseur, PaiementForfaitaire


def _build_forfaitaire_idxls_suffix(point_eau):
    idxls_value = str(getattr(point_eau, 'idxls', '') or '').strip()
    if not idxls_value:
        return ''
    return f" ({idxls_value})"


@login_required
def traitement_retours_caissiere(request):
    """
    Vue principale pour le traitement des retours de tickets par la caissière
    Permet de scanner/saisir les numéros de tickets et les marquer comme retournés
    """
    # Statistiques des tickets en attente
    from django.db.models import Count, Sum, Q

    # Calculer le montant total (In + Out)
    lignes_attente = DiameXTemporaire.objects.filter(statut='en_attente')
    totaux = lignes_attente.aggregate(
        total_in=Sum('montant_in'),
        total_out=Sum('montant_out')
    )
    montant_total = (totaux['total_in'] or 0) + (totaux['total_out'] or 0)

    stats = {
        'en_attente': lignes_attente.count(),
        'envoye': DiameXTemporaire.objects.filter(statut='envoye').count(),
        'erreur': DiameXTemporaire.objects.filter(statut='erreur').count(),
        'montant_total_attente': montant_total,
    }

    # Derniers tickets traités
    derniers_tickets = DiameXTemporaire.objects.select_related(
        'planning_detail', 'created_by'
    ).order_by('-created_at')[:20]

    context = {
        'title': 'Traitement des retours - Caissière',
        'stats': stats,
        'derniers_tickets': derniers_tickets,
    }

    return render(request, 'billing/traitement_retours_caissiere.html', context)


@login_required
@require_http_methods(["POST"])
def api_scanner_ticket(request):
    """
    API pour scanner/saisir un numéro de ticket et récupérer ses informations
    """
    try:
        data = json.loads(request.body)
        numero_ticket = data.get('numero_ticket', '').strip()

        if not numero_ticket:
            return JsonResponse({
                'success': False,
                'error': 'Numéro de ticket requis'
            }, status=400)

        # Chercher le bon de livraison dans la nouvelle table BonLivraison
        bon_livraison = BonLivraison.objects.filter(
            numero_bon=numero_ticket
        ).select_related(
            'planning', 'planning__employe', 'planning__ouvrage',
            'designation', 'equipement', 'point_eau'
        ).first()

        # Si trouvé dans BonLivraison, le traiter
        if bon_livraison:
            # Vérifier si déjà retourné
            if bon_livraison.retour:
                return JsonResponse({
                    'success': False,
                    'error': f'Ticket {numero_ticket} déjà retourné le {bon_livraison.date_retour.strftime("%d/%m/%Y") if bon_livraison.date_retour else "date inconnue"}'
                }, status=400)

            # Vérifier si pas encore utilisé
            if not bon_livraison.utilise:
                return JsonResponse({
                    'success': False,
                    'error': f'Ticket {numero_ticket} pas encore utilisé par l\'agent'
                }, status=400)

            # Préparer les données du ticket (BonLivraison)
            ticket_data = {
                'numero_ticket': numero_ticket,
                'type_ticket': 'livraison',
                'bon_livraison_id': str(bon_livraison.id),
                'detail_id': None,  # Pas de PlanningDetail pour les livraisons
                'designation': bon_livraison.designation.nom if bon_livraison.designation else '',
                'designation_id': str(bon_livraison.designation.id) if bon_livraison.designation else None,
                'quantite': float(bon_livraison.quantite or 0),
                'prix_unitaire': 0,  # BonLivraison n'a pas de PU
                'montant': 0,  # BonLivraison n'a pas de montant
                'date_planning': bon_livraison.planning.date.strftime('%Y-%m-%d') if bon_livraison.planning else None,
                'employe': bon_livraison.planning.employe.surnom if bon_livraison.planning and bon_livraison.planning.employe else '',
                'ouvrage': bon_livraison.planning.ouvrage.nom_ouvrage if bon_livraison.planning and bon_livraison.planning.ouvrage else '',
                'fournisseur': None,
                'equipement': bon_livraison.equipement.nom if bon_livraison.equipement else None,
                'point_eau': bon_livraison.point_eau.idxls if bon_livraison.point_eau else None,
                'point_eau_nom': bon_livraison.point_eau.nomabonne if bon_livraison.point_eau else None,
                'magasin': bon_livraison.magasin or None,
            }

            # Les bons de livraison ne génèrent pas de ligne DiameX (workflow stock uniquement)
            return JsonResponse({
                'success': True,
                'ticket': ticket_data,
                'apercu_diamex': None
            })

        # Sinon, chercher dans PlanningDetail pour les avances et recettes
        # Essayer avec numero_bon_avance (CharField) pour les avances
        detail = PlanningDetail.objects.filter(
            numero_bon_avance=numero_ticket
        ).select_related(
            'planning', 'planning__employe', 'planning__ouvrage',
            'designation', 'fournisseur', 'equipement_constitutif', 'point_eau'
        ).first()

        if not detail and numero_ticket.isdigit():
            # Essayer avec numeroDiameX (IntegerField) seulement si c'est un nombre
            detail = PlanningDetail.objects.filter(
                numeroDiameX=int(numero_ticket)
            ).select_related(
                'planning', 'planning__employe', 'planning__ouvrage',
                'designation', 'fournisseur', 'equipement_constitutif', 'point_eau'
            ).first()

        if not detail:
            return JsonResponse({
                'success': False,
                'error': f'Ticket {numero_ticket} non trouvé'
            }, status=404)

        # Vérifier si déjà traité (retour = True)
        if detail.retour:
            return JsonResponse({
                'success': False,
                'error': f'Ticket {numero_ticket} déjà retourné le {detail.date_retour.strftime("%d/%m/%Y") if detail.date_retour else "date inconnue"}'
            }, status=400)

        # Vérifier si pas encore utilisé
        if not detail.utilise:
            return JsonResponse({
                'success': False,
                'error': f'Ticket {numero_ticket} pas encore utilisé par l\'agent'
            }, status=400)

        # Déterminer le type de ticket
        type_ticket = 'livraison'  # Par défaut
        if detail.designation:
            if detail.designation.type_avance_caissiere:
                type_avance = detail.designation.type_avance_caissiere.lower()
                if type_avance == 'recette':
                    type_ticket = 'recette'
                elif type_avance == 'avance':
                    type_ticket = 'avance'
                elif type_avance == 'bon de livraison':
                    type_ticket = 'livraison'

        # Préparer les données du ticket
        ticket_data = {
            'numero_ticket': numero_ticket,
            'type_ticket': type_ticket,
            'detail_id': str(detail.id),
            'designation': detail.designation.nom if detail.designation else '',
            'designation_id': str(detail.designation.id) if detail.designation else None,
            'quantite': float(detail.quantity or 0),
            'prix_unitaire': float(detail.pu or 0),
            'montant': float(detail.montant or 0),
            'date_planning': detail.planning.date.strftime('%Y-%m-%d') if detail.planning else None,
            'employe': detail.planning.employe.surnom if detail.planning and detail.planning.employe else '',
            'ouvrage': detail.planning.ouvrage.nom_ouvrage if detail.planning and detail.planning.ouvrage else '',
            'fournisseur': detail.fournisseur.nom_fournisseur if detail.fournisseur else None,
            'equipement': detail.equipement_constitutif.nom if detail.equipement_constitutif else None,
            'point_eau': detail.point_eau.idxls if detail.point_eau else None,
            'point_eau_nom': detail.point_eau.nomabonne if detail.point_eau else None,
        }

        # Récupérer TOUTES les lignes du même ticket pour l'aperçu
        if numero_ticket:
            toutes_lignes_apercu = PlanningDetail.objects.filter(
                numero_bon_avance=numero_ticket,
                utilise=True
            ).select_related('designation', 'fournisseur')
        else:
            toutes_lignes_apercu = [detail]

        # Préparer l'aperçu de la ligne DiameX qui sera créée
        # Note: Les bons de livraison ne génèrent pas de ligne DiameX (workflow stock uniquement)
        apercu_diamex = None
        if type_ticket in ['recette', 'avance']:
            import pytz
            tz_madagascar = pytz.timezone('Indian/Antananarivo')

            # Journal
            journal = "00PERS"
            if detail.planning and detail.planning.employe and detail.planning.employe.base:
                base = detail.planning.employe.base
                if base.journal_retour and hasattr(base.journal_retour, 'code') and base.journal_retour.code:
                    journal = base.journal_retour.code

            # Date (DateM sera calculé dans Access)
            date_aware = detail.planning.date if detail.planning else timezone.now()
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)

            date_rec = date_madagascar.date()

            # Description selon le type
            if type_ticket == 'recette':
                # Format: _Paiement forfaitaire_[Nom Ouvrage]_[Montant]
                nom_ouvrage = detail.planning.ouvrage.nom_ouvrage if detail.planning and detail.planning.ouvrage else "N/A"
                montant_str = str(detail.montant) if detail.montant is not None else "0"
                description = f"_Paiement forfaitaire_{nom_ouvrage}_{montant_str}{_build_forfaitaire_idxls_suffix(getattr(detail, 'point_eau', None))}"
                in_amount = float(detail.montant or 0)
                out_amount = 0
                cat = "748411"
            else:  # avance
                # Format: [NIF ou ISI] [PREST]_[Nom du fournisseur]_[Toutes les désignations]_[Montant TOTAL]
                # NIF ou ISI est la mention (pas le numéro), définie dans fournisseur.nif_ou_isi
                # Note: espace entre NIF/ISI et PREST, underscore pour le reste

                # Construire la partie NIF/ISI + PREST (avec espace)
                nif_isi_prest = ""
                if detail.fournisseur:
                    parts_nif_prest = []
                    if detail.fournisseur.nif_ou_isi:
                        parts_nif_prest.append(detail.fournisseur.nif_ou_isi)  # "NIF" ou "ISI"
                    if detail.fournisseur.prestation:
                        parts_nif_prest.append("PREST")
                    nif_isi_prest = " ".join(parts_nif_prest)  # Espace entre NIF et PREST

                # Nom du fournisseur
                nom_fournisseur = detail.fournisseur.nom_fournisseur if detail.fournisseur else ""

                # Récupérer TOUTES les désignations des lignes du ticket
                designations_list = []
                montant_total = 0
                for ligne in toutes_lignes_apercu:
                    if ligne.designation:
                        designations_list.append(ligne.designation.nom)
                    montant_total += float(ligne.montant if ligne.montant else 0)

                designations_str = "_".join(designations_list) if designations_list else (detail.designation.nom if detail.designation else "")

                # Formater le montant TOTAL avec séparateur de milliers et " Ar"
                if montant_total > 0:
                    montant_str = f"{int(montant_total):,} Ar".replace(",", " ")
                else:
                    montant_str = "0 Ar"

                # Assembler avec underscore (sauf pour la partie NIF PREST qui a déjà un espace)
                parts = [nif_isi_prest, nom_fournisseur, designations_str, montant_str]
                description = "_".join([p for p in parts if p])

                in_amount = 0
                out_amount = montant_total
                cat = detail.compte.compte if detail.compte else ""

            # PERS (surnom employé)
            pers = detail.planning.employe.surnom if detail.planning and detail.planning.employe else ""

            # Fournisseur IDxls (au lieu du nom)
            fournisseur_val = ""
            if detail.fournisseur:
                fournisseur_val = str(detail.fournisseur.idxls) if detail.fournisseur.idxls else ""

            # ACTIV (base DiameX)
            activ = ""
            if detail.planning and detail.planning.employe and detail.planning.employe.base:
                activ = detail.planning.employe.base.prog_diamex or ""

            apercu_diamex = {
                'numero_ticket': numero_ticket,
                'journal': journal,
                'rec': 0,  # Sera défini dans le prochain workflow
                'date_rec': date_rec.strftime('%d/%m/%Y'),
                'description': description,
                'in': in_amount,
                'out': out_amount,
                'cat': cat,
                'pers': pers,
                'fournisseur': fournisseur_val,  # IDxls du fournisseur
                'activ': activ,
            }

        return JsonResponse({
            'success': True,
            'ticket': ticket_data,
            'apercu_diamex': apercu_diamex
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Données JSON invalides'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def api_valider_retour_ticket(request):
    """
    API pour valider le retour d'un ticket :
    - Marquer le détail comme retourné
    - Créer une ligne dans DiameXTemporaire (table unifiée)
    - Pour les bons de livraison : impacter le stock
    - NOUVEAU: Supporter les PaiementForfaitaire (tickets PF-xxx)
    """
    try:
        data = json.loads(request.body)
        detail_id = data.get('detail_id')
        numero_ticket = data.get('numero_ticket')
        modifications_diamex = data.get('modifications_diamex', None)

        if not detail_id or not numero_ticket:
            return JsonResponse({
                'success': False,
                'error': 'ID de détail et numéro de ticket requis'
            }, status=400)

        # Détecter si c'est un PaiementForfaitaire (numéro commence par PF-)
        is_paiement_forfaitaire = numero_ticket.startswith('PF-')

        if is_paiement_forfaitaire:
            # === WORKFLOW PAIEMENT FORFAITAIRE ===
            try:
                paiement = PaiementForfaitaire.objects.select_related(
                    'point_eau', 'point_eau__ouvrage'
                ).get(id=detail_id)
            except PaiementForfaitaire.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Paiement forfaitaire introuvable'
                }, status=404)

            # Vérifier si déjà traité
            if paiement.numeroDiameX:
                return JsonResponse({
                    'success': False,
                    'error': 'Paiement déjà enregistré en comptabilité'
                }, status=400)

            # Préparer les données DiameX
            import pytz
            tz_madagascar = pytz.timezone('Indian/Antananarivo')

            # Date
            date_aware = paiement.date_facture if paiement.date_facture else timezone.now()
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)
            date_rec = date_madagascar.date()

            # Description: _Paiement forfaitaire_[Nom Ouvrage]_[Montant]
            nom_ouvrage = paiement.point_eau.ouvrage.nom_ouvrage if paiement.point_eau and paiement.point_eau.ouvrage else "N/A"
            montant_str = str(paiement.montant) if paiement.montant is not None else "0"
            description = f"_Paiement forfaitaire_{nom_ouvrage}_{montant_str}{_build_forfaitaire_idxls_suffix(getattr(paiement, 'point_eau', None))}"

            # In/Out
            in_amount = float(paiement.montant or 0)
            out_amount = 0

            # Cat (compte fixe pour paiements forfaitaires)
            cat = "748411"

            # Journal par défaut
            journal = "00PERS"

            # Créer la ligne DiameX
            ligne_diamex = DiameXTemporaire.objects.create(
                paiement_forfaitaire=paiement,
                type_transaction='recette',
                journal_code=journal,
                date_m=date_rec,
                rec=0,
                date_rec=date_rec,
                description=description,
                montant_in=in_amount,
                montant_out=out_amount,
                compte_code=cat,
                pers='',  # Pas d'employé pour paiements forfaitaires
                detail='',
                info='hydria paiement forfaitaire',
                scan='',
                prog=None,
                activ=None,
                fournisseur=None,
                statut='en_attente',
                created_by=request.user.employe if hasattr(request.user, 'employe') else None
            )

            # Générer un numéro DiameX temporaire (sera remplacé lors de l'export vers Access)
            numero_diamex_temp = f"TEMP-{ligne_diamex.id}"
            paiement.numeroDiameX = numero_diamex_temp
            paiement.baseDiameX = 'Django'  # Marqueur pour indiquer origine
            # Trace de l'encaissement caissière (cohérence avec le workflow d'encaissement forfaitaire)
            if not paiement.date_encaissement:
                paiement.date_encaissement = timezone.localdate()
                paiement.encaisse_par = request.user.employe if hasattr(request.user, 'employe') else None
            paiement.save()

            return JsonResponse({
                'success': True,
                'message': 'Paiement forfaitaire validé et envoyé vers DiameX',
                'ligne_diamex_id': str(ligne_diamex.id),
                'numero_diamex': numero_diamex_temp
            })

        # === WORKFLOW BON DE LIVRAISON ===
        # Vérifier si c'est un BonLivraison (bon_livraison_id fourni au lieu de detail_id)
        # Dans ce cas, detail_id sera None et on récupère l'ID depuis les données
        data_parsed = json.loads(request.body)
        bon_livraison_id = data_parsed.get('bon_livraison_id')

        if bon_livraison_id:
            # Traiter le bon de livraison
            try:
                bon = BonLivraison.objects.select_related(
                    'planning', 'planning__employe',
                    'designation', 'equipement', 'point_eau'
                ).get(id=bon_livraison_id)
            except BonLivraison.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Bon de livraison introuvable'
                }, status=404)

            # Vérifier si déjà retourné
            if bon.retour:
                return JsonResponse({
                    'success': False,
                    'error': 'Bon de livraison déjà retourné'
                }, status=400)

            # Marquer comme retourné (pas de ligne DiameX pour les livraisons)
            with transaction.atomic():
                bon.retour = True
                bon.date_retour = timezone.now()
                bon.save()

            return JsonResponse({
                'success': True,
                'message': f'Bon de livraison {numero_ticket} retourné avec succès',
                'ligne_diamex_id': None,  # Pas de ligne DiameX pour livraisons
                'stock_impact': None,
                'modifications_appliquees': False
            })

        # === WORKFLOW PLANNINGDETAIL (code existant) ===
        # Récupérer le détail principal
        detail = PlanningDetail.objects.select_related(
            'planning', 'planning__employe', 'planning__ouvrage',
            'designation', 'fournisseur', 'equipement_constitutif', 'point_eau'
        ).get(id=detail_id)

        # Vérifier à nouveau
        if detail.retour:
            return JsonResponse({
                'success': False,
                'error': 'Ticket déjà retourné'
            }, status=400)

        # Récupérer TOUTES les lignes du même ticket (même numero_bon_avance)
        # pour regrouper dans une seule ligne DiameX
        if numero_ticket:
            toutes_lignes_ticket = PlanningDetail.objects.filter(
                numero_bon_avance=numero_ticket,
                utilise=True
            ).select_related(
                'planning', 'planning__employe', 'planning__ouvrage',
                'designation', 'fournisseur', 'equipement_constitutif', 'point_eau'
            )
        else:
            toutes_lignes_ticket = [detail]

        # NOTE: Ne PAS marquer les lignes comme retournées ici!
        # Elles seront marquées APRÈS validation et création réussie de la ligne DiameX
        # pour éviter de bloquer le ticket si la validation échoue

        # Déterminer le type de ticket
        type_ticket = 'livraison'
        if detail.designation:
            if detail.designation.type_avance_caissiere:
                type_avance = detail.designation.type_avance_caissiere.lower()
                if 'recette' in type_avance:
                    type_ticket = 'recette'
                elif 'facture' in type_avance or 'depense' in type_avance:
                    type_ticket = 'depense'  # Facture/Dépense
                elif 'avance' in type_avance:
                    type_ticket = 'avance'  # Vraie avance remboursable
                elif 'livraison' in type_avance:
                    type_ticket = 'livraison'

        # Les bons de livraison ne créent PAS de ligne DiameX (workflow stock uniquement)
        ligne_diamex = None
        if type_ticket in ['recette', 'avance', 'depense']:
            # === PRÉPARER LES DONNÉES DIAMEX ===
            import pytz
            tz_madagascar = pytz.timezone('Indian/Antananarivo')

            # Journal
            journal = "00PERS"
            if detail.planning and detail.planning.employe and detail.planning.employe.base:
                # Relation directe : Employe -> Base
                base = detail.planning.employe.base
                if base.journal_retour and hasattr(base.journal_retour, 'code') and base.journal_retour.code:
                    journal = base.journal_retour.code

            # Date (DateM sera calculé dans Access)
            date_aware = detail.planning.date if detail.planning else timezone.now()
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)

            date_rec = date_madagascar.date()

            # Description selon le type
            if type_ticket == 'recette':
                # Format: _Paiement forfaitaire_[Nom Ouvrage]_[Montant]
                nom_ouvrage = detail.planning.ouvrage.nom_ouvrage if detail.planning and detail.planning.ouvrage else "N/A"
                montant_str = str(detail.montant) if detail.montant is not None else "0"
                description = f"_Paiement forfaitaire_{nom_ouvrage}_{montant_str}{_build_forfaitaire_idxls_suffix(getattr(detail, 'point_eau', None))}"

                # In/Out
                in_amount = detail.montant or 0
                out_amount = 0

                # Cat (compte)
                cat = "748411"  # Code fixe pour paiements forfaitaires

            elif type_ticket in ['avance', 'depense']:  # Avance ou Facture/Dépense
                # Format: [NIF ou ISI] [PREST]_[Nom du fournisseur]_[Toutes les désignations]_[Montant TOTAL]
                # NIF ou ISI est la mention (pas le numéro), définie dans fournisseur.nif_ou_isi
                # Note: espace entre NIF/ISI et PREST, underscore pour le reste

                # Construire la partie NIF/ISI + PREST (avec espace)
                nif_isi_prest = ""
                if detail.fournisseur:
                    parts_nif_prest = []
                    if detail.fournisseur.nif_ou_isi:
                        parts_nif_prest.append(detail.fournisseur.nif_ou_isi)  # "NIF" ou "ISI"
                    if detail.fournisseur.prestation:
                        parts_nif_prest.append("PREST")
                    nif_isi_prest = " ".join(parts_nif_prest)  # Espace entre NIF et PREST

                # Nom du fournisseur
                nom_fournisseur = detail.fournisseur.nom_fournisseur if detail.fournisseur else ""

                # Récupérer TOUTES les désignations des lignes du ticket (pas seulement 2)
                designations_list = []
                montant_total = 0
                for ligne in toutes_lignes_ticket:
                    if ligne.designation:
                        designations_list.append(ligne.designation.nom)
                    montant_total += ligne.montant if ligne.montant else 0

                designations_str = "_".join(designations_list) if designations_list else (detail.designation.nom if detail.designation else "")

                # Formater le montant TOTAL avec séparateur de milliers et " Ar"
                if montant_total > 0:
                    montant_str = f"{int(montant_total):,} Ar".replace(",", " ")
                else:
                    montant_str = "0 Ar"

                # Assemblage avec underscore (sauf pour la partie NIF PREST qui a déjà un espace)
                parts = [nif_isi_prest, nom_fournisseur, designations_str, montant_str]
                description = "_".join([p for p in parts if p])

                # In/Out (montant TOTAL)
                in_amount = 0
                out_amount = montant_total

                # Cat (compte depuis PlanningDetail)
                cat = detail.compte.compte if detail.compte else ""

            # PERS (surnom employé)
            pers = detail.planning.employe.surnom if detail.planning and detail.planning.employe else ""

            # Fournisseur IDxls (au lieu du nom)
            fournisseur_nom = None
            if detail.fournisseur:
                fournisseur_nom = str(detail.fournisseur.idxls) if detail.fournisseur.idxls else None

            # Programme DiameX (champ Prog dans Access) = Base DiameX (nom de la base)
            prog = None
            if detail.planning and detail.planning.employe and detail.planning.employe.base:
                # Relation directe : Employe -> Base
                base = detail.planning.employe.base
                if base.base_diamex:
                    prog = base.base_diamex  # ✅ Corrigé : Prog = base_diamex (pas prog_diamex)

            # ACTIV = Volet (champ ACTIV distinct de Prog dans Access)
            # Sera calculé plus bas avec les règles conditionnelles (NULL pour 00PERS)

            # DateM sera calculé dans Access (laisser vide)
            datem = ""

            # Récupérer le fournisseur si fourni
            fournisseur_obj = None
            fournisseur_idxls = None

            if modifications_diamex and modifications_diamex.get('fournisseur'):
                # Le frontend envoie l'idxls du fournisseur
                try:
                    fournisseur_idxls = int(modifications_diamex.get('fournisseur'))
                    fournisseur_obj = Fournisseur.objects.get(idxls=fournisseur_idxls)
                except (Fournisseur.DoesNotExist, ValueError, TypeError) as e:
                    print(f"⚠️ Fournisseur {modifications_diamex.get('fournisseur')} introuvable: {e}")
                    fournisseur_idxls = modifications_diamex.get('fournisseur')  # Garder la valeur pour validation
            elif detail.fournisseur:
                # Utiliser le fournisseur du détail si pas de modification
                fournisseur_obj = detail.fournisseur
                fournisseur_idxls = detail.fournisseur.idxls

            # === VALIDATION DES CHAMPS OBLIGATOIRES ===
            # Préparer les valeurs finales (avec modifications ou valeurs calculées)
            final_journal = modifications_diamex.get('journal') if modifications_diamex else journal
            final_compte = modifications_diamex.get('cat') if modifications_diamex else cat
            final_description = modifications_diamex.get('description') if modifications_diamex else description

            # Vérifier les champs obligatoires
            erreurs = []

            if not final_journal:
                erreurs.append("Journal comptable obligatoire")

            if not final_compte:
                erreurs.append("Compte comptable (Cat) obligatoire")

            if not final_description:
                erreurs.append("Description obligatoire")

            if not date_rec:
                erreurs.append("Date obligatoire")

            # Vérifier qu'au moins In ou Out est renseigné et > 0
            if float(in_amount) == 0 and float(out_amount) == 0:
                erreurs.append("Montant obligatoire (In ou Out doit être > 0)")

            # Vérifier fournisseur et activ selon les règles du compte
            compte_obj = None
            final_fournisseur_value = None  # Valeur finale à utiliser
            final_activ_value = None  # Valeur finale ACTIV (volet) à utiliser

            if final_compte:
                from apps.organization.models import Compte
                try:
                    compte_obj = Compte.objects.get(compte=final_compte)

                    # RÈGLE FOURNISSEUR
                    if compte_obj.fournisseur_obligatoire:
                        # Fournisseur OBLIGATOIRE - doit être renseigné
                        if not fournisseur_idxls:
                            erreurs.append(f"Fournisseur obligatoire pour le compte {final_compte}")
                        else:
                            # Vérifier que le fournisseur existe vraiment
                            if not fournisseur_obj:
                                erreurs.append(f"Fournisseur {fournisseur_idxls} introuvable dans la base de données")
                            else:
                                final_fournisseur_value = fournisseur_obj  # Conserver l'objet
                    else:
                        # Fournisseur NON obligatoire - DOIT être vide/null
                        final_fournisseur_value = None

                    # RÈGLE ACTIV (Volet)
                    if final_compte.startswith('00PERS'):
                        # Compte 00PERS → ACTIV DOIT être vide
                        final_activ_value = None
                    else:
                        # Autre compte → ACTIV = Volet de la Base de l'employé
                        if detail.planning and detail.planning.employe and detail.planning.employe.base:
                            final_activ_value = detail.planning.employe.base.volet or None
                        else:
                            # Prog/Volet est obligatoire pour tous les comptes (sauf 00PERS)
                            erreurs.append(f"ACTIV (Volet) obligatoire pour le compte {final_compte} mais employé sans base")
                            final_activ_value = None

                except Compte.DoesNotExist:
                    # Compte invalide, mais déjà vérifié plus haut
                    pass

            # Si des erreurs, retourner erreur au lieu de créer la ligne
            if erreurs:
                return JsonResponse({
                    'success': False,
                    'error': 'Champs obligatoires manquants',
                    'details': erreurs,
                    'message': 'Veuillez compléter les informations manquantes avant de valider le retour.'
                }, status=400)

            # Déterminer le champ info selon le type de ticket
            info_diamex = ''
            if type_ticket == 'recette':
                info_diamex = 'hydria paiement forfaitaire'
            elif type_ticket == 'depense':
                info_diamex = 'hydria depenses'
            elif type_ticket == 'avance':
                info_diamex = 'hydria avance'

            # Créer la ligne temporaire DiameX dans la table unifiée DiameXTemporaire
            # Utiliser les modifications si fournies, sinon les valeurs calculées avec règles métier
            ligne_diamex = DiameXTemporaire.objects.create(
                planning_detail=detail,
                type_transaction=type_ticket,  # 'avance' ou 'recette'
                # Colonnes DiameX - utiliser modifications si disponibles
                journal_code=modifications_diamex.get('journal') if modifications_diamex else journal,
                date_m=date_rec,  # DateM = date du ticket
                rec=modifications_diamex.get('rec') if modifications_diamex else 0,
                date_rec=date_rec,
                description=modifications_diamex.get('description') if modifications_diamex else description,
                montant_in=float(in_amount),
                montant_out=float(out_amount),
                compte_code=modifications_diamex.get('cat') if modifications_diamex else cat,
                pers=modifications_diamex.get('pers') if modifications_diamex else pers,
                detail='',  # Laisser vide, fournisseur est maintenant une ForeignKey
                info=info_diamex,
                scan='',  # Pas de scan pour les retours caissière
                prog=prog,  # ✅ Programme DiameX (base.prog_diamex)
                activ=final_activ_value,  # ✅ ACTIV = Volet (NULL pour 00PERS, base.volet pour autres)
                fournisseur=final_fournisseur_value,  # ✅ Utilise les règles métier : NULL si non obligatoire, ForeignKey si obligatoire
                statut='en_attente',
                created_by=request.user.employe if hasattr(request.user, 'employe') else None
            )

        # Pour les bons de livraison : confirmer le stock (la sortie a déjà été faite lors de la livraison terrain)
        stock_impact = None
        if type_ticket == 'livraison' and detail.equipement_constitutif:
            try:
                # Récupérer le stock pour affichage (pas de mouvement, juste confirmation)
                stock = Stock.objects.filter(equipement=detail.equipement_constitutif).first()

                if stock:
                    stock_impact = {
                        'equipement': detail.equipement_constitutif.nom,
                        'equipement_id': str(detail.equipement_constitutif.id),
                        'quantite_livree': float(detail.quantity or 0),
                        'stock_actuel': float(stock.quantite_actuelle),
                        'stock_id': str(stock.id),
                        'fournisseur': detail.fournisseur.nom_fournisseur if detail.fournisseur else None,
                        'confirmation': True  # Indique qu'il s'agit d'une confirmation, pas d'un mouvement
                    }

            except Exception as e:
                # Logger l'erreur mais ne pas bloquer le processus
                print(f"[WARNING] Erreur récupération stock: {e}")

        # === MARQUER LES LIGNES COMME RETOURNÉES ===
        # Marquer APRÈS validation et création réussie
        for ligne in toutes_lignes_ticket:
            ligne.retour = True
            ligne.date_retour = timezone.now()
            ligne.save()

        # === MISE À JOUR DU PRIX UNITAIRE DE LA DÉSIGNATION ===
        # Mettre à jour le prix unitaire et la date dans la table designations
        # à partir des données du PlanningDetail exporté
        # RÈGLE CRITICAL: Seulement pour les désignations de type "Avance"
        # (Pas pour "Bon de livraison" ni "Recette")
        if detail.designation and detail.pu:
            try:
                designation = detail.designation

                # Vérifier le type_avance_caissiere : seulement "Avance" (avec majuscule)
                if designation.type_avance_caissiere != 'Avance':
                    print(f"ℹ️ Prix unitaire NON mis à jour pour {designation.nom} (type: {designation.type_avance_caissiere}, seulement 'Avance' autorisé)")
                else:
                    date_planning = detail.planning.date.date() if detail.planning and detail.planning.date else timezone.now().date()

                    # Mettre à jour seulement si la date du planning est plus récente
                    # OU si la désignation n'a pas encore de prix
                    doit_mettre_a_jour = False

                    if designation.prix_unitaire is None or designation.date_prix is None:
                        # Pas de prix existant : mise à jour directe
                        doit_mettre_a_jour = True
                    elif date_planning >= designation.date_prix:
                        # Date du planning plus récente ou égale : mise à jour
                        doit_mettre_a_jour = True

                    if doit_mettre_a_jour:
                        designation.prix_unitaire = detail.pu
                        designation.date_prix = date_planning
                        designation.save()
                        print(f"✅ Prix unitaire mis à jour pour {designation.nom}: {detail.pu} Ar (date: {date_planning})")
                    else:
                        print(f"ℹ️ Prix unitaire NON mis à jour pour {designation.nom} (date existante {designation.date_prix} plus récente que {date_planning})")

            except Exception as e:
                # Logger l'erreur mais ne pas bloquer le processus
                print(f"⚠️ Erreur mise à jour prix unitaire désignation: {e}")

        # Message de retour
        message = f'Ticket {numero_ticket} retourné avec succès'
        if modifications_diamex:
            message += ' (avec modifications DiameX appliquées)'

        return JsonResponse({
            'success': True,
            'message': message,
            'ligne_diamex_id': str(ligne_diamex.id) if ligne_diamex else None,
            'stock_impact': stock_impact,
            'modifications_appliquees': bool(modifications_diamex)
        })

    except PlanningDetail.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Détail de planning non trouvé'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Données JSON invalides'
        }, status=400)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERREUR dans api_valider_retour_ticket: {error_trace}")
        return JsonResponse({
            'success': False,
            'error': f'Erreur: {str(e)}',
            'details': error_trace if request.user.is_staff else None
        }, status=500)


@login_required
def api_liste_lignes_diamex(request):
    """
    API pour récupérer la liste des lignes temporaires DiameX
    Filtrable par statut, type de transaction, date
    """
    try:
        # Filtres
        statut = request.GET.get('statut', '')
        type_transaction = request.GET.get('type_ticket', '')  # Garder le nom type_ticket pour compatibilité frontend
        date_debut = request.GET.get('date_debut', '')
        date_fin = request.GET.get('date_fin', '')

        # Query de base - DiameXTemporaire
        lignes = DiameXTemporaire.objects.select_related(
            'planning_detail', 'created_by', 'fournisseur'
        ).all()

        # Appliquer les filtres
        if statut:
            lignes = lignes.filter(statut=statut)
        if type_transaction:
            lignes = lignes.filter(type_transaction=type_transaction)
        if date_debut:
            lignes = lignes.filter(created_at__gte=date_debut)
        if date_fin:
            lignes = lignes.filter(created_at__lte=date_fin)

        # Limiter à 100 résultats
        lignes = lignes.order_by('-created_at')[:100]

        # Formater les résultats
        results = []
        for ligne in lignes:
            # Extraire numero_ticket depuis info (format: "Ticket BA-2025-XXXX")
            numero_ticket = ''
            if ligne.info and ligne.info.startswith('Ticket '):
                numero_ticket = ligne.info.replace('Ticket ', '')

            # Récupérer designation et montant depuis planning_detail
            designation = ligne.description or ''
            quantite = 0
            montant = ligne.montant_in if ligne.montant_in > 0 else ligne.montant_out

            if ligne.planning_detail:
                designation = ligne.planning_detail.designation.nom if ligne.planning_detail.designation else designation
                quantite = float(ligne.planning_detail.quantity or 0)
                montant_detail = float(ligne.planning_detail.montant or 0)
                if montant_detail > 0:
                    montant = montant_detail

            results.append({
                'id': ligne.id,
                'numero_ticket': numero_ticket,
                'type_ticket': ligne.get_type_transaction_display(),
                'designation': designation,
                'quantite': quantite,
                'montant': float(montant),
                'employe': ligne.created_by.surnom if ligne.created_by else '',
                'ouvrage': ligne.planning_detail.planning.ouvrage.nom_ouvrage if ligne.planning_detail and ligne.planning_detail.planning and ligne.planning_detail.planning.ouvrage else '',
                'statut': ligne.get_statut_display(),
                'date_traitement': ligne.created_at.strftime('%d/%m/%Y %H:%M'),
            })

        return JsonResponse({
            'success': True,
            'lignes': results,
            'total': lignes.count()
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur: {str(e)}'
        }, status=500)



@login_required
def api_details_en_attente_retour(request):
    """
    API pour récupérer les détails de planning utilisés mais pas encore retournés
    Groupés par type : livraison, avance, recette

    NOTE: Les "recettes" sont maintenant les PaiementForfaitaire payés en attente d'envoi DiameX
    """
    try:
        from django.db.models import Q

        # Récupérer tous les détails utilisés mais pas encore retournés (SAUF recettes)
        details = PlanningDetail.objects.filter(
            utilise=True,
            retour=False
        ).exclude(
            designation__type_avance_caissiere__iexact='recette'  # Exclure les recettes (migrées vers PaiementForfaitaire)
        ).select_related(
            'planning', 'planning__employe', 'planning__ouvrage',
            'designation', 'fournisseur', 'equipement_constitutif', 'point_eau'
        ).order_by('-planning__date')[:100]  # Limiter à 100 résultats

        # Grouper par type ET par numéro de ticket (éviter les doublons)
        livraisons = []
        avances = []
        recettes = []  # Maintenant depuis PaiementForfaitaire
        tickets_vus = set()  # Pour éviter les doublons

        for detail in details:
            # Déterminer le type et le numéro de ticket
            type_ticket = 'livraison'
            numero_ticket = ''

            if detail.designation and detail.designation.type_avance_caissiere:
                type_avance = detail.designation.type_avance_caissiere.lower()
                if type_avance == 'recette':
                    type_ticket = 'recette'
                    numero_ticket = detail.numero_bon_avance or detail.numeroDiameXAvance or detail.numeroDiameX or ''
                elif type_avance == 'avance':
                    type_ticket = 'avance'
                    numero_ticket = detail.numero_bon_avance or detail.numeroDiameXAvance or detail.numeroDiameX or ''
                elif 'livraison' in type_avance:
                    type_ticket = 'livraison'
                    numero_ticket = detail.numero_bon_livraison or detail.numeroDiameX or ''

            # Si pas de numéro attribué, utiliser les champs par défaut
            if not numero_ticket:
                numero_ticket = detail.numero_bon_livraison or detail.numero_bon_avance or detail.numeroDiameX or ''

            # Vérifier si ce ticket a déjà été ajouté
            ticket_key = f"{type_ticket}_{numero_ticket}"
            if ticket_key in tickets_vus:
                continue  # Ignorer les lignes en double du même ticket
            tickets_vus.add(ticket_key)

            # Pour les tickets avec plusieurs lignes, calculer le montant total et les désignations
            if type_ticket in ['avance', 'recette'] and numero_ticket:
                # Recharger depuis la DB pour avoir toutes les lignes du ticket du MÊME TYPE
                lignes_ticket = PlanningDetail.objects.filter(
                    numero_bon_avance=numero_ticket,
                    utilise=True,
                    retour=False,
                    designation__type_avance_caissiere__iexact=type_ticket  # Filtrer par type
                ).select_related('designation')
            else:
                lignes_ticket = [detail]

            montant_total = sum(float(ligne.montant or 0) for ligne in lignes_ticket)
            designations = [ligne.designation.nom for ligne in lignes_ticket if ligne.designation]
            nb_lignes = len(lignes_ticket)

            # Extraire année et mois pour le regroupement
            annee_mois = None
            mois_annee_display = None
            if detail.planning and detail.planning.date:
                annee_mois = detail.planning.date.strftime('%Y-%m')
                mois_annee_display = detail.planning.date.strftime('%B %Y').capitalize()

            # Construire l'objet détail
            detail_obj = {
                'id': str(detail.id),
                'numero_ticket': numero_ticket,
                'designation': ', '.join(designations[:3]) + (f' (+{len(designations)-3})' if len(designations) > 3 else ''),
                'nb_lignes': nb_lignes,
                'quantite': float(detail.quantity or 0),
                'prix_unitaire': float(detail.pu or 0),
                'montant': montant_total,
                'date_planning': detail.planning.date.strftime('%d/%m/%Y') if detail.planning else '',
                'employe': detail.planning.employe.surnom if detail.planning and detail.planning.employe else '',
                'ouvrage': detail.planning.ouvrage.nom_ouvrage if detail.planning and detail.planning.ouvrage else '',
                'fournisseur': detail.fournisseur.nom_fournisseur if detail.fournisseur else '',
                'equipement': detail.equipement_constitutif.nom if detail.equipement_constitutif else '',
                'point_eau': detail.point_eau.idxls if detail.point_eau else '',
                'point_eau_nom': detail.point_eau.nomabonne if detail.point_eau else '',
                'annee_mois': annee_mois,
                'mois_annee_display': mois_annee_display,
            }

            # Ajouter dans la bonne liste
            if type_ticket == 'livraison':
                livraisons.append(detail_obj)
            elif type_ticket == 'avance':
                avances.append(detail_obj)
            # Les recettes ne viennent plus de PlanningDetail

        # Récupérer les paiements forfaitaires payés en attente d'envoi DiameX
        paiements_forfaitaires = PaiementForfaitaire.objects.filter(
            paye=True,
            numeroDiameX__isnull=True  # Payé mais pas encore envoyé à DiameX
        ).select_related(
            'point_eau',
            'point_eau__ouvrage'
        ).order_by('-date_facture')[:100]

        for paiement in paiements_forfaitaires:
            # Extraire année et mois pour le regroupement
            annee_mois = paiement.date_facture.strftime('%Y-%m') if paiement.date_facture else None
            mois_annee_display = paiement.date_facture.strftime('%B %Y').capitalize() if paiement.date_facture else None

            # Générer un "numéro de ticket" basé sur le point d'eau et la date
            numero_ticket = f"PF-{paiement.point_eau.idxls or paiement.point_eau.code_point_eau or paiement.id}-{paiement.date_facture.strftime('%Y%m%d')}" if paiement.date_facture and paiement.point_eau else str(paiement.id)

            recettes.append({
                'id': str(paiement.id),
                'numero_ticket': numero_ticket,
                'designation': 'Paiement forfaitaire',
                'nb_lignes': 1,
                'quantite': float(paiement.quantite or 0),
                'prix_unitaire': float(paiement.prix_unitaire or 0),
                'montant': float(paiement.montant or 0),
                'date_planning': paiement.date_facture.strftime('%d/%m/%Y') if paiement.date_facture else '',
                'employe': '',  # Pas d'employé pour les paiements forfaitaires
                'ouvrage': paiement.point_eau.ouvrage.nom_ouvrage if paiement.point_eau and paiement.point_eau.ouvrage else '',
                'fournisseur': '',
                'equipement': '',
                'point_eau': paiement.point_eau.idxls if paiement.point_eau else '',
                'point_eau_nom': paiement.point_eau.nomabonne if paiement.point_eau else '',
                'annee_mois': annee_mois,
                'mois_annee_display': mois_annee_display,
                'is_paiement_forfaitaire': True  # Flag pour identifier le type dans le frontend
            })

        return JsonResponse({
            'success': True,
            'livraisons': livraisons,
            'avances': avances,
            'recettes': recettes,
            'total': {
                'livraisons': len(livraisons),
                'avances': len(avances),
                'recettes': len(recettes)
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur liste en attente: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_get_journaux(request):
    """API pour récupérer la liste des journaux"""
    try:
        from apps.organization.models import Journal

        journaux = Journal.objects.all().values('code', 'nom_journal')

        return JsonResponse({
            'success': True,
            'journaux': [{'code': j['code'], 'libelle': j['nom_journal']} for j in journaux]
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_get_fournisseurs(request):
    """API pour récupérer la liste des fournisseurs"""
    try:
        from .models import Fournisseur

        fournisseurs = Fournisseur.objects.filter(actif=True).values(
            'id', 'idxls', 'nom_fournisseur'
        ).order_by('nom_fournisseur')

        return JsonResponse({
            'success': True,
            'fournisseurs': list(fournisseurs)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_get_bases(request):
    """API pour récupérer la liste des bases (ACTIV)"""
    try:
        from apps.organization.models import Base

        bases = Base.objects.exclude(prog_diamex__isnull=True).exclude(prog_diamex='').values(
            'id', 'prog_diamex', 'nom_base'
        ).order_by('nom_base')

        return JsonResponse({
            'success': True,
            'bases': list(bases)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_get_comptes_par_designation(request):
    """API pour récupérer les comptes associés à une désignation"""
    try:
        data = json.loads(request.body)
        designation_id = data.get('designation_id')

        if not designation_id:
            return JsonResponse({
                'success': False,
                'error': 'ID de désignation requis'
            }, status=400)

        from apps.planning.models import DesignationCompte
        from apps.organization.models import Compte

        # Récupérer les comptes liés à cette désignation
        designation_comptes = DesignationCompte.objects.filter(
            designation_id=designation_id
        ).select_related('compte')

        comptes = []
        for dc in designation_comptes:
            if dc.compte:
                comptes.append({
                    'compte': dc.compte.compte,
                    'libelle': dc.compte.nom_compte if dc.compte.nom_compte else dc.compte.compte
                })

        return JsonResponse({
            'success': True,
            'comptes': comptes
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_derniers_tickets_traites(request):
    """
    API pour récupérer les derniers tickets traités (7 derniers jours)
    Groupés par date de traitement
    """
    try:
        from collections import defaultdict
        from datetime import timedelta

        # Récupérer les lignes DiameX des 7 derniers jours
        date_limite = timezone.now() - timedelta(days=7)

        lignes_diamex = DiameXTemporaire.objects.filter(
            created_at__gte=date_limite,
            type_transaction__in=['bon_livraison', 'avance', 'recette']
        ).select_related(
            'planning_detail',
            'planning_detail__planning',
            'planning_detail__planning__employe',
            'planning_detail__designation',
            'created_by'
        ).order_by('-created_at')[:100]

        # Regrouper par date de traitement
        tickets_par_date = defaultdict(lambda: {
            'lignes': [],
            'nb_lignes': 0,
            'nb_exportees': 0,
            'date_traitement': None
        })

        for ligne in lignes_diamex:
            date_key = ligne.created_at.date().strftime('%Y-%m-%d') if ligne.created_at else 'inconnu'

            # Extraire le numéro de ticket depuis info
            numero_ticket = ''
            if ligne.info and ligne.info.startswith('Ticket '):
                numero_ticket = ligne.info.replace('Ticket ', '')

            # Déterminer l'employé
            employe = ''
            if ligne.created_by:
                employe = ligne.created_by.surnom
            elif ligne.planning_detail and ligne.planning_detail.planning and ligne.planning_detail.planning.employe:
                employe = ligne.planning_detail.planning.employe.surnom

            # Ouvrage
            ouvrage = ''
            if ligne.planning_detail and ligne.planning_detail.planning and ligne.planning_detail.planning.ouvrage:
                ouvrage = ligne.planning_detail.planning.ouvrage.nom_ouvrage

            tickets_par_date[date_key]['date_traitement'] = ligne.created_at.date() if ligne.created_at else None
            tickets_par_date[date_key]['lignes'].append({
                'id': ligne.id,
                'numero_ticket': numero_ticket,
                'type_ticket': ligne.get_type_transaction_display(),
                'designation': ligne.description or '',
                'montant': float(ligne.montant_in if ligne.montant_in > 0 else ligne.montant_out),
                'employe': employe,
                'ouvrage': ouvrage,
                'statut': ligne.statut,
                'statut_display': ligne.get_statut_display(),
                'created_at': ligne.created_at.strftime('%d/%m/%Y %H:%M') if ligne.created_at else ''
            })
            tickets_par_date[date_key]['nb_lignes'] += 1
            if ligne.statut == 'exporte':
                tickets_par_date[date_key]['nb_exportees'] += 1

        # Convertir en liste
        tickets_list = []
        for date_key, data in tickets_par_date.items():
            tickets_list.append({
                'date_traitement': date_key,
                'date_traitement_display': data['date_traitement'].strftime('%d/%m/%Y') if data['date_traitement'] else date_key,
                'lignes': data['lignes'],
                'nb_lignes': data['nb_lignes'],
                'nb_exportees': data['nb_exportees'],
                'peut_annuler': data['nb_exportees'] == 0  # Peut annuler seulement si aucune ligne exportée
            })

        # Trier par date décroissante
        tickets_list.sort(key=lambda x: x['date_traitement'], reverse=True)

        return JsonResponse({
            'success': True,
            'tickets': tickets_list
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_annuler_tickets_date(request):
    """
    API pour annuler tous les tickets traités à une date donnée
    Protection: Ne supprime que les lignes avec statut != 'exporte'
    """
    try:
        data = json.loads(request.body)
        date_traitement = data.get('date_traitement')

        if not date_traitement:
            return JsonResponse({
                'success': False,
                'error': 'Date de traitement requise'
            }, status=400)

        # Convertir la date
        from datetime import datetime
        date_obj = datetime.strptime(date_traitement, '%Y-%m-%d').date()

        with transaction.atomic():
            # Récupérer les lignes de cette date
            lignes = DiameXTemporaire.objects.filter(
                created_at__date=date_obj,
                type_transaction__in=['bon_livraison', 'avance', 'recette']
            )

            # Vérifier s'il y a des lignes exportées
            nb_exportees = lignes.filter(statut='exporte').count()
            if nb_exportees > 0:
                return JsonResponse({
                    'success': False,
                    'error': f'Impossible d\'annuler : {nb_exportees} ticket(s) déjà exporté(s). Les tickets exportés ne peuvent pas être annulés.'
                }, status=400)

            # Récupérer les IDs des PlanningDetail associés
            planning_detail_ids = list(lignes.filter(
                planning_detail__isnull=False
            ).values_list('planning_detail_id', flat=True).distinct())

            nb_lignes = lignes.count()

            # Supprimer les lignes DiameX (seulement non exportées)
            lignes.delete()

            # Réinitialiser les PlanningDetail (retour=False pour qu'ils réapparaissent)
            nb_details = PlanningDetail.objects.filter(
                id__in=planning_detail_ids
            ).update(retour=False)

            return JsonResponse({
                'success': True,
                'message': f'{nb_lignes} ligne(s) DiameX supprimée(s), {nb_details} ticket(s) réinitialisé(s)',
                'nb_lignes': nb_lignes,
                'nb_details': nb_details
            })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Format JSON invalide'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
