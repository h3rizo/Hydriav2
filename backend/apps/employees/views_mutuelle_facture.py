"""
Vue pour générer les factures Excel de Mutuelle Santé (AMIT et OSIEFSoVa)
"""
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter
import os
from datetime import datetime
from decimal import Decimal

from .models import PaiementMutuelleSante, PaiementMutuelleSanteDetail
from .utils_contrat import get_contrat_actif


def safe_write(ws, row, col, value):
    """Écrire dans une cellule en ignorant les cellules fusionnées"""
    cell = ws.cell(row=row, column=col)
    if not isinstance(cell, MergedCell):
        cell.value = value


@csrf_exempt
@require_http_methods(["POST"])
def generer_facture_mutuelle_sante(request, paiement_id):
    """
    Génère les factures Excel pour un paiement de mutuelle santé.
    Crée un fichier séparé pour AMIT et/ou OSIEFSoVa selon les données.
    """
    try:
        paiement = get_object_or_404(PaiementMutuelleSante, id=paiement_id)

        if paiement.statut != 'valide':
            return JsonResponse({
                'success': False,
                'error': 'Le paiement doit être validé avant de générer la facture'
            }, status=400)

        # Récupérer les détails par mutuelle
        details_amit = paiement.details.filter(mutuelle='AMIT').select_related('employe', 'employe__base')
        details_osiefsova = paiement.details.filter(mutuelle='OSIEFSoVa').select_related('employe', 'employe__base')

        fichiers_generes = []
        erreurs = []

        # Debug
        nb_amit = details_amit.count()
        nb_osie = details_osiefsova.count()
        print(f"[DEBUG] Détails AMIT: {nb_amit}, montant paiement: {paiement.montant_total_amit}")
        print(f"[DEBUG] Détails OSIEFSoVa: {nb_osie}, montant paiement: {paiement.montant_total_osiefsova}")

        # Recalculer les montants totaux depuis les détails
        total_amit_details = sum([d.total_trimestre for d in details_amit if d.total_trimestre], Decimal('0'))
        total_osie_details = sum([d.total_trimestre for d in details_osiefsova if d.total_trimestre], Decimal('0'))
        print(f"[DEBUG] Total AMIT depuis détails: {total_amit_details}")
        print(f"[DEBUG] Total OSIEFSoVa depuis détails: {total_osie_details}")

        # Générer facture AMIT si applicable (vérifier les détails)
        if details_amit.exists() and total_amit_details > 0:
            try:
                fichier_amit = generer_facture_amit(paiement, details_amit)
                fichiers_generes.append(('AMIT', fichier_amit))
            except Exception as e:
                erreurs.append(f"AMIT: {str(e)}")
                print(f"[ERROR] AMIT: {str(e)}")

        # Générer facture OSIEFSoVa si applicable (vérifier les détails)
        if details_osiefsova.exists() and total_osie_details > 0:
            try:
                fichier_osie = generer_facture_osiefsova(paiement, details_osiefsova)
                fichiers_generes.append(('OSIEFSoVa', fichier_osie))
            except Exception as e:
                erreurs.append(f"OSIEFSoVa: {str(e)}")
                print(f"[ERROR] OSIEFSoVa: {str(e)}")

        if not fichiers_generes:
            msg_detail = f"Aucune facture générée. AMIT: {nb_amit} employé(s), {total_amit_details} Ar | OSIEFSoVa: {nb_osie} employé(s), {total_osie_details} Ar"
            if erreurs:
                msg_detail += f"\n\nErreurs: {', '.join(erreurs)}"
            return JsonResponse({
                'success': False,
                'error': msg_detail,
                'erreurs': erreurs
            }, status=400)

        # Marquer comme facture générée
        paiement.facture_generee = True
        paiement.save()

        return JsonResponse({
            'success': True,
            'message': f'{len(fichiers_generes)} facture(s) générée(s) avec succès',
            'fichiers': [{'mutuelle': m, 'path': f} for m, f in fichiers_generes],
            'erreurs': erreurs
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def generer_facture_amit(paiement, details):
    """Génère la facture AMIT avec onglets 'recapitulatif' et 'detail'"""
    # Charger le modèle
    template_path = os.path.join(settings.BASE_DIR, 'Modele facture AMIT.xlsx')
    wb = load_workbook(template_path)

    # Onglet 0: BORDEREAU TRIMESTRIELLE (récapitulatif)
    ws_recap = wb.worksheets[0]

    # Onglet 1: DNS (détail)
    ws_detail = wb.worksheets[1]

    # Remplir le récapitulatif (BORDEREAU)
    # L10: Col1:Nom ou Raison sociale: | Col3:ONG SOAKOJA
    safe_write(ws_recap, 10, 3, paiement.organisation.nom_organisation)

    # L7: Col4:Période : 3° trimestre 2025
    trimestre_text = f"{paiement.trimestre}° trimestre {paiement.annee}"
    safe_write(ws_recap, 7, 4, f"Période : {trimestre_text}")

    # Effacer les données d'exemple dans le template (à partir de la ligne 15)
    # On garde les en-têtes (lignes 1-14) et on efface le reste
    # Ne PAS effacer les colonnes O, P, Q (conservent les en-têtes de cotisations)
    max_row = ws_detail.max_row
    if max_row >= 15:
        for row in range(15, max_row + 1):
            for col in range(1, 15):  # Colonnes A à N seulement (garde O, P, Q)
                cell = ws_detail.cell(row=row, column=col)
                if not isinstance(cell, MergedCell):
                    cell.value = None

    # Remplir les détails (DNS) - Ligne de départ: 15
    start_row = 15
    current_row = start_row

    for detail in details:
        employe = detail.employe

        # Col1:NOM | Col2:PRENOMS | Col3:N° CHEZ L'AMIT | Col4:Date de naissance
        safe_write(ws_detail, current_row, 1, employe.nom)
        safe_write(ws_detail, current_row, 2, employe.prenom or '')
        safe_write(ws_detail, current_row, 3, '')  # N° CHEZ L'AMIT - à remplir manuellement

        # Col4: Date de naissance (format datetime)
        if hasattr(employe, 'date_naissance') and employe.date_naissance:
            safe_write(ws_detail, current_row, 4, employe.date_naissance)

        # Col5:CIN | Col6:SEXE | Col7:DATE Entrée
        safe_write(ws_detail, current_row, 5, employe.numero_cin or '')
        safe_write(ws_detail, current_row, 6, employe.sexe or '')  # SEXE - à déterminer
        safe_write(ws_detail, current_row, 7, '')  # DATE Entrée - à déterminer

        # Col10:Temps de travail (vide)
        safe_write(ws_detail, current_row, 10, '')

        # Col11:Salaire mois 1 | Col12:Salaire mois 2 | Col13:Salaire mois 3
        # Utiliser le salaire brut de base depuis le contrat actif
        contrat = get_contrat_actif(employe)
        salaire_brut = float(contrat.salaire_brut_base) if contrat and contrat.salaire_brut_base else 0
        safe_write(ws_detail, current_row, 11, salaire_brut)
        safe_write(ws_detail, current_row, 12, salaire_brut)
        safe_write(ws_detail, current_row, 13, salaire_brut)

        # Col14:TOTAL SALAIRE (formule Excel)
        safe_write(ws_detail, current_row, 14, f"=K{current_row}+L{current_row}+M{current_row}")

        # Col15 (O): Cotisations part employé 1%
        safe_write(ws_detail, current_row, 15, f"=N{current_row}*1%")

        # Col16 (P): Cotisations part employeur 5%
        safe_write(ws_detail, current_row, 16, f"=N{current_row}*5%")

        # Col17 (Q): Total Cotisations 6%
        safe_write(ws_detail, current_row, 17, f"=O{current_row}+P{current_row}")

        current_row += 1

    # Ajouter la ligne TOTAL dynamique
    last_data_row = current_row - 1

    if last_data_row >= start_row:
        # Ligne TOTAL (une ligne après les données)
        total_row = last_data_row + 1

        # Col1: Label TOTAL
        safe_write(ws_detail, total_row, 1, "TOTAL")

        # Formules pour les totaux des salaires (colonnes K, L, M, N)
        # Col11 (K): Total salaires mois 1
        safe_write(ws_detail, total_row, 11, f"=SUM(K{start_row}:K{last_data_row})")

        # Col12 (L): Total salaires mois 2
        safe_write(ws_detail, total_row, 12, f"=SUM(L{start_row}:L{last_data_row})")

        # Col13 (M): Total salaires mois 3
        safe_write(ws_detail, total_row, 13, f"=SUM(M{start_row}:M{last_data_row})")

        # Col14 (N): Total général
        safe_write(ws_detail, total_row, 14, f"=SUM(N{start_row}:N{last_data_row})")

        # Col15 (O): Total cotisations employé 1%
        safe_write(ws_detail, total_row, 15, f"=SUM(O{start_row}:O{last_data_row})")

        # Col16 (P): Total cotisations employeur 5%
        safe_write(ws_detail, total_row, 16, f"=SUM(P{start_row}:P{last_data_row})")

        # Col17 (Q): Total général cotisations 6%
        safe_write(ws_detail, total_row, 17, f"=SUM(Q{start_row}:Q{last_data_row})")

        # Supprimer toutes les lignes après le TOTAL
        if total_row < ws_detail.max_row:
            ws_detail.delete_rows(total_row + 1, ws_detail.max_row - total_row)

    # Remplir le récapitulatif BORDEREAU TRIMESTRIELLE
    # E19: Total des salaires bruts de la déclaration
    if last_data_row >= start_row:
        # Référence vers le total de la colonne N (total salaires) de l'onglet DNS
        safe_write(ws_recap, 19, 5, f"=DNS!N{total_row}")

        # E21: Cotisation employeur 5% (E19 * 5%)
        safe_write(ws_recap, 21, 5, "=E19*5%")

        # E23: Cotisation employé 1% (E19 * 1%)
        safe_write(ws_recap, 23, 5, "=E19*1%")
    else:
        safe_write(ws_recap, 19, 5, 0)
        safe_write(ws_recap, 21, 5, 0)
        safe_write(ws_recap, 23, 5, 0)

    # Sauvegarder
    output_dir = os.path.join(settings.BASE_DIR, 'media', 'factures_mutuelle')
    os.makedirs(output_dir, exist_ok=True)

    filename = f'Facture_AMIT_{paiement.organisation.nom_organisation}_T{paiement.trimestre}_{paiement.annee}.xlsx'
    output_path = os.path.join(output_dir, filename)
    wb.save(output_path)

    return output_path


def generer_facture_osiefsova(paiement, details):
    """Génère la facture OSIEFSoVa avec onglets 'recapitulatif' et 'detail'"""
    # Charger le modèle
    template_path = os.path.join(settings.BASE_DIR, 'Modèle facture OSIEFSoVa.xlsx')
    wb = load_workbook(template_path)

    # Onglet 0: BORDEREAU SKJ (récapitulatif)
    ws_recap = wb.worksheets[0]

    # Onglet 1: SKJ 3T (détail)
    ws_detail = wb.worksheets[1]

    # Remplir le récapitulatif (BORDEREAU SKJ)
    # L10: Col1:Nom ou Raison sociale: | Col3:ONG SOAKOJA
    safe_write(ws_recap, 10, 3, paiement.organisation.nom_organisation)

    # L7: Col4:PERIODE: | Col5:3° trimestre 2025
    trimestre_text = f"{paiement.trimestre}° trimestre {paiement.annee}"
    safe_write(ws_recap, 7, 5, trimestre_text)

    # Effacer les données d'exemple dans le template (à partir de la ligne 15)
    # On garde les en-têtes (lignes 1-14) et on efface le reste
    # Inclure toutes les colonnes jusqu'à S
    max_row = ws_detail.max_row
    if max_row >= 15:
        for row in range(15, max_row + 1):
            for col in range(1, 20):  # Colonnes A à S (élargi pour tout effacer)
                cell = ws_detail.cell(row=row, column=col)
                if not isinstance(cell, MergedCell):
                    cell.value = None

    # Remplir les détails (SKJ 3T) - Ligne de départ: 15
    start_row = 15
    current_row = start_row

    for detail in details:
        employe = detail.employe

        # Col1:NOM ET PRENOMS
        nom_complet = f"{employe.nom}  {employe.prenom}" if employe.prenom else employe.nom
        safe_write(ws_detail, current_row, 1, nom_complet)

        # Col2:Date de naissance
        if hasattr(employe, 'date_naissance') and employe.date_naissance:
            safe_write(ws_detail, current_row, 2, employe.date_naissance)

        # Col3:CIN | Col4:SEXE
        safe_write(ws_detail, current_row, 3, employe.numero_cin or '')
        safe_write(ws_detail, current_row, 4, '')  # SEXE - à déterminer

        # Col5:DATE Entrée (vide)
        safe_write(ws_detail, current_row, 5, '')

        # Col7:Salaire Juillet | Col8:Salaire Août | Col9:Salaire Sept
        # Utiliser le salaire brut de base depuis le contrat actif
        contrat = get_contrat_actif(employe)
        salaire_brut = float(contrat.salaire_brut_base) if contrat and contrat.salaire_brut_base else 0
        safe_write(ws_detail, current_row, 7, salaire_brut)
        safe_write(ws_detail, current_row, 8, salaire_brut)
        safe_write(ws_detail, current_row, 9, salaire_brut)

        # Col10:Avantages ou autres (vide)
        safe_write(ws_detail, current_row, 10, '')

        # Col11:Temps de travail (vide)
        safe_write(ws_detail, current_row, 11, '')

        # Col12:TOTAL SALAIRE (formule Excel)
        safe_write(ws_detail, current_row, 12, f"=G{current_row}+H{current_row}+I{current_row}")

        # Col13:Cotisations part employé 1% (formule Excel)
        safe_write(ws_detail, current_row, 13, f"=L{current_row}*1%")

        # Col14:Cotisations part employeur 5% (formule Excel)
        safe_write(ws_detail, current_row, 14, f"=L{current_row}*5%")

        # Col15 (O): Total cotisations (M + N)
        safe_write(ws_detail, current_row, 15, f"=M{current_row}+N{current_row}")

        current_row += 1

    # Ajouter la ligne TOTAL
    # Calculer la dernière ligne de données
    last_data_row = current_row - 1

    if last_data_row >= start_row:
        # Ligne TOTAL (une ligne après les données)
        total_row = last_data_row + 1

        # Col1 (A): Label TOTAL
        safe_write(ws_detail, total_row, 1, "TOTAL")

        # Formules pour les totaux (colonnes L, M, N, O)
        # Col12 (L): Total des salaires
        safe_write(ws_detail, total_row, 12, f"=SUM(L{start_row}:L{last_data_row})")

        # Col13 (M): Total cotisations employé 1%
        safe_write(ws_detail, total_row, 13, f"=SUM(M{start_row}:M{last_data_row})")

        # Col14 (N): Total cotisations employeur 5%
        safe_write(ws_detail, total_row, 14, f"=SUM(N{start_row}:N{last_data_row})")

        # Col15 (O): Total général cotisations (M + N)
        safe_write(ws_detail, total_row, 15, f"=SUM(O{start_row}:O{last_data_row})")

        # Supprimer toutes les lignes après le TOTAL
        if total_row < ws_detail.max_row:
            ws_detail.delete_rows(total_row + 1, ws_detail.max_row - total_row)

    # Remplir le récapitulatif BORDEREAU SKJ avec les valeurs de SKJ 3T
    # G17: Nombre d'employés
    nb_employes = details.count()
    safe_write(ws_recap, 17, 7, nb_employes)

    # G19: Total des salaires (somme de la colonne L de SKJ 3T)
    if last_data_row >= start_row:
        # Utiliser une formule qui référence l'autre onglet
        safe_write(ws_recap, 19, 7, f"='SKJ 3T'!L{total_row}")
    else:
        safe_write(ws_recap, 19, 7, 0)

    # Sauvegarder
    output_dir = os.path.join(settings.BASE_DIR, 'media', 'factures_mutuelle')
    os.makedirs(output_dir, exist_ok=True)

    filename = f'Facture_OSIEFSoVa_{paiement.organisation.nom_organisation}_T{paiement.trimestre}_{paiement.annee}.xlsx'
    output_path = os.path.join(output_dir, filename)
    wb.save(output_path)

    return output_path


@csrf_exempt
@require_http_methods(["GET"])
def telecharger_facture_mutuelle(request, paiement_id, mutuelle_type):
    """
    Permet de télécharger une facture générée
    mutuelle_type: 'amit' ou 'osiefsova'
    """
    try:
        paiement = get_object_or_404(PaiementMutuelleSante, id=paiement_id)

        if not paiement.facture_generee:
            return JsonResponse({
                'success': False,
                'error': 'Aucune facture générée pour ce paiement'
            }, status=404)

        # Construire le chemin du fichier
        mutuelle_label = 'AMIT' if mutuelle_type.lower() == 'amit' else 'OSIEFSoVa'
        filename = f'Facture_{mutuelle_label}_{paiement.organisation.nom_organisation}_T{paiement.trimestre}_{paiement.annee}.xlsx'
        file_path = os.path.join(settings.BASE_DIR, 'media', 'factures_mutuelle', filename)

        if not os.path.exists(file_path):
            return JsonResponse({
                'success': False,
                'error': f'Fichier {mutuelle_label} introuvable'
            }, status=404)

        # Retourner le fichier
        response = FileResponse(open(file_path, 'rb'), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
