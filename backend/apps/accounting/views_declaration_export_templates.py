"""
Export de la déclaration de communication aux impôts
avec utilisation des templates officiels de l'administration fiscale.

Génère 3 fichiers Excel distincts :
- Achats non destinés à la revente (AC)
- Achats immobilisés (AI)
- Sommes versées à des tiers / Prestations (PS)
"""

from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from decimal import Decimal
from datetime import datetime
import xlrd
import xlwt
from xlwt import Workbook, XFStyle, Borders, Pattern, Font as XlwtFont, Alignment as XlwtAlignment
import os
from io import BytesIO
import zipfile

from .models import BaseDiameX
from apps.billing.models import Fournisseur
from .views_declaration_communication import _scope_diamex_queryset, _get_fournisseur_location_data


# Chemins des templates
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '')
TEMPLATE_ACHATS = os.path.join(TEMPLATE_DIR, 'Canevas annexe Achats non destines a la revente (AC).xls')
TEMPLATE_ACHATS_IMMOBILISES = os.path.join(TEMPLATE_DIR, 'Canevas annexe Achats Immobilises (AI).xls')
TEMPLATE_PRESTATIONS = os.path.join(TEMPLATE_DIR, 'Canevas annexe Sommes versees a des tiers (PS).xls')


def copier_style_cellule(cell_rd, cell_wt):
    """Copie le style d'une cellule xlrd vers une cellule xlwt"""
    style = XFStyle()

    # Copier les bordures si présentes
    borders = Borders()
    borders.left = Borders.THIN
    borders.right = Borders.THIN
    borders.top = Borders.THIN
    borders.bottom = Borders.THIN
    style.borders = borders

    # Copier l'alignement
    alignment = XlwtAlignment()
    alignment.horz = XlwtAlignment.HORZ_LEFT
    alignment.vert = XlwtAlignment.VERT_CENTER
    style.alignment = alignment

    return style


def copier_feuille_template(template_path):
    """
    Copie une feuille Excel template (xlrd) vers un nouveau workbook (xlwt)
    en préservant les styles et les deux premières lignes d'en-tête
    """
    # Lire le template
    rb = xlrd.open_workbook(template_path, formatting_info=True)
    rs = rb.sheet_by_index(0)

    # Créer nouveau workbook
    wb = Workbook()
    ws = wb.add_sheet(rs.name)

    # Copier les 2 premières lignes (en-têtes)
    for row_idx in range(min(2, rs.nrows)):
        for col_idx in range(rs.ncols):
            cell_rd = rs.cell(row_idx, col_idx)

            # Écrire la valeur
            if cell_rd.value:
                ws.write(row_idx, col_idx, cell_rd.value)

    # Définir les largeurs de colonnes (approximatif)
    for col_idx in range(16):
        ws.col(col_idx).width = 4000  # ~15 caractères

    return wb, ws


def generer_donnees_declaration(annee, user=None):
    """
    Génère les données de déclaration regroupées par type d'opération.

    Returns:
        dict avec 3 clés : 'Achat', 'Achats immobilisé', 'Prestation'
        Chaque valeur est une liste de dictionnaires de données
    """
    # Récupérer toutes les transactions de l'année commençant par NIF ou ISI
    transactions_qs = BaseDiameX.objects.all()
    if user is not None:
        transactions_qs = _scope_diamex_queryset(transactions_qs, user)
    transactions = transactions_qs.filter(
        date_m__year=annee,
        description__iregex=r'^(NIF|ISI)(_| PREST)'  # Commence par NIF_ ou ISI_ ou "NIF PREST" ou "ISI PREST"
    ).select_related('compte__nature_declaration').prefetch_related('compte')

    groupes = {}

    for transaction in transactions:
        fournisseur_id = transaction.fournisseur
        if not fournisseur_id:
            continue

        try:
            fournisseur = Fournisseur.objects.get(idxls=fournisseur_id)
        except Fournisseur.DoesNotExist:
            fournisseur = None

        nature = None
        nature_nom = "Non classé"
        if transaction.compte and transaction.compte.nature_declaration:
            nature = transaction.compte.nature_declaration
            nature_nom = nature.nom

        cle = f"{fournisseur_id}_{nature_nom}"

        if cle not in groupes:
            location_data = _get_fournisseur_location_data(fournisseur) if fournisseur else {
                'district': '',
                'ex_province': '',
            }
            groupes[cle] = {
                'nif': fournisseur.numero_nif if fournisseur else '',
                'stat': fournisseur.numero_stat if fournisseur else '',
                'cin': fournisseur.cin if fournisseur else '',
                'date_cin': fournisseur.date_cin.strftime('%d/%m/%Y') if (fournisseur and fournisseur.date_cin) else '',
                'lieu_cin': fournisseur.lieu_cin if fournisseur else '',
                'nature_autre': '',  # Pas utilisé
                'reference': '',  # Pas dans Fournisseur
                'nif_representant': '',  # Pas dans Fournisseur
                'nom': fournisseur.nom_fournisseur if fournisseur else f"Fournisseur {fournisseur_id}",
                'adresse': fournisseur.adresse if fournisseur else '',
                'ville': location_data['district'],
                'district': location_data['district'],
                'province': location_data['ex_province'],
                'pays': 'Madagascar',
                'nature': nature_nom,
                'montant_comptabilise': Decimal('0'),
                'montant_verse': Decimal('0'),
                'type_operation': '',
                'type_numero': ''
            }

        montant = Decimal(str(transaction.montant_out))
        groupes[cle]['montant_comptabilise'] += montant
        groupes[cle]['montant_verse'] += montant

        # Déterminer le type d'opération (ORDRE DE PRIORITÉ)
        description = transaction.description.upper()
        if nature_nom.lower() == 'outillage':
            groupes[cle]['type_operation'] = 'Achats immobilisé'
        elif 'PREST' in description:
            groupes[cle]['type_operation'] = 'Prestation'
        else:
            groupes[cle]['type_operation'] = 'Achat'

        # Déterminer le type de numéro
        if description.startswith('NIF'):
            groupes[cle]['type_numero'] = 'NIF'
        elif description.startswith('ISI'):
            groupes[cle]['type_numero'] = 'ISI'

    resultats = list(groupes.values())
    resultats.sort(key=lambda x: (x['nom'], x['nature']))

    # Séparer par type d'opération
    donnees_par_type = {
        'Achat': [],
        'Achats immobilisé': [],
        'Prestation': []
    }

    for resultat in resultats:
        type_op = resultat['type_operation']
        if type_op in donnees_par_type:
            donnees_par_type[type_op].append(resultat)

    return donnees_par_type


def ecrire_donnees_dans_feuille(ws, donnees, debut_ligne=2):
    """
    Écrit les données dans une feuille Excel à partir de la ligne spécifiée.

    Mapping des colonnes (0-indexed) :
    0 - NIF
    1 - NUMERO STATISTIQUE
    2 - CIN
    3 - DATE CIN
    4 - LIEU DE DELIVRANCE CIN
    5 - NATURE (autre)
    6 - REFERENCE
    7 - NIFONLINE DU REPRESENTANT
    8 - RAISON SOCIALE / NOM COMMERCIAL
    9 - ADRESSE
    10 - VILLE
    11 - EX-PROVINCE
    12 - PAYS
    13 - NATURE DES ACHATS/SERVICES
    14 - COMPTABILISEES
    15 - VERSEES
    """
    style_data = XFStyle()
    borders = Borders()
    borders.left = Borders.THIN
    borders.right = Borders.THIN
    borders.top = Borders.THIN
    borders.bottom = Borders.THIN
    style_data.borders = borders

    # Style pour les montants (alignement à droite)
    style_montant = XFStyle()
    style_montant.borders = borders
    alignment = XlwtAlignment()
    alignment.horz = XlwtAlignment.HORZ_RIGHT
    style_montant.alignment = alignment
    style_montant.num_format_str = '#,##0.00'

    current_row = debut_ligne

    for data in donnees:
        ws.write(current_row, 0, data['nif'], style_data)
        ws.write(current_row, 1, data['stat'], style_data)
        ws.write(current_row, 2, data['cin'], style_data)
        ws.write(current_row, 3, data['date_cin'], style_data)
        ws.write(current_row, 4, data['lieu_cin'], style_data)
        ws.write(current_row, 5, data['nature_autre'], style_data)
        ws.write(current_row, 6, data['reference'], style_data)
        ws.write(current_row, 7, data['nif_representant'], style_data)
        ws.write(current_row, 8, data['nom'], style_data)
        ws.write(current_row, 9, data['adresse'], style_data)
        ws.write(current_row, 10, data['ville'], style_data)
        ws.write(current_row, 11, data['province'], style_data)
        ws.write(current_row, 12, data['pays'], style_data)
        ws.write(current_row, 13, data['nature'], style_data)
        ws.write(current_row, 14, float(data['montant_comptabilise']), style_montant)
        ws.write(current_row, 15, float(data['montant_verse']), style_montant)

        current_row += 1

    return current_row


@login_required
@require_http_methods(["GET"])
def api_export_declaration_templates(request):
    """
    Exporte la déclaration de communication en 3 fichiers Excel
    basés sur les templates officiels de l'administration fiscale.

    Retourne un fichier ZIP contenant les 3 fichiers Excel.
    """
    try:
        annee = int(request.GET.get('annee', datetime.now().year))

        # Générer les données groupées par type
        donnees_par_type = generer_donnees_declaration(annee, request.user)

        # Créer un buffer pour le fichier ZIP
        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:

            # 1. FICHIER ACHATS (AC)
            if donnees_par_type['Achat']:
                wb_achats, ws_achats = copier_feuille_template(TEMPLATE_ACHATS)
                ecrire_donnees_dans_feuille(ws_achats, donnees_par_type['Achat'])

                # Sauvegarder dans un buffer
                buffer_achats = BytesIO()
                wb_achats.save(buffer_achats)
                buffer_achats.seek(0)

                # Ajouter au ZIP
                zip_file.writestr(
                    f'Declaration_Achats_{annee}.xls',
                    buffer_achats.getvalue()
                )

            # 2. FICHIER ACHATS IMMOBILISÉS (AI)
            if donnees_par_type['Achats immobilisé']:
                wb_ai, ws_ai = copier_feuille_template(TEMPLATE_ACHATS_IMMOBILISES)
                ecrire_donnees_dans_feuille(ws_ai, donnees_par_type['Achats immobilisé'])

                buffer_ai = BytesIO()
                wb_ai.save(buffer_ai)
                buffer_ai.seek(0)

                zip_file.writestr(
                    f'Declaration_Achats_Immobilises_{annee}.xls',
                    buffer_ai.getvalue()
                )

            # 3. FICHIER PRESTATIONS (PS)
            if donnees_par_type['Prestation']:
                wb_prest, ws_prest = copier_feuille_template(TEMPLATE_PRESTATIONS)
                ecrire_donnees_dans_feuille(ws_prest, donnees_par_type['Prestation'])

                buffer_prest = BytesIO()
                wb_prest.save(buffer_prest)
                buffer_prest.seek(0)

                zip_file.writestr(
                    f'Declaration_Prestations_{annee}.xls',
                    buffer_prest.getvalue()
                )

        # Retourner le ZIP
        zip_buffer.seek(0)

        response = HttpResponse(
            zip_buffer.getvalue(),
            content_type='application/zip'
        )
        response['Content-Disposition'] = f'attachment; filename="Declaration_Communication_{annee}.zip"'

        return response

    except Exception as e:
        import traceback
        return HttpResponse(
            f"Erreur lors de l'export : {str(e)}\n\n{traceback.format_exc()}",
            status=500,
            content_type='text/plain'
        )
