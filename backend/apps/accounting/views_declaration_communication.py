"""
Vues pour la génération de la déclaration de communication aux impôts.
Rassemble toutes les transactions avec NIF ou ISI, groupées par fournisseur et nature.
"""

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Q
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from decimal import Decimal
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from datetime import datetime
from io import BytesIO

from .models import BaseDiameX, ConfigDeclarationCommunication
from apps.billing.models import Fournisseur, AdresseFournisseurDistrict
from apps.organization.models import Base


def _get_fournisseur_location_data(fournisseur):
    adresse = (getattr(fournisseur, 'adresse', '') or '').strip()
    mapping = None
    if adresse:
        mapping = (
            AdresseFournisseurDistrict.objects
            .select_related('district__region__ex_province')
            .filter(adresse__iexact=adresse, actif=True)
            .first()
        )
    district = getattr(mapping, 'district', None)
    region = getattr(district, 'region', None) if district else None
    ex_province = getattr(region, 'ex_province', None) if region else None
    return {
        'district': district.nom_district if district else '',
        'ex_province': ex_province.nom_ex_province if ex_province else '',
    }


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_allowed_progs(user):
    if getattr(user, 'is_superuser', False):
        return None
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return []
    return list(
        Base.objects.filter(organisation_id=organisation_id)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )


def _scope_diamex_queryset(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    allowed_progs = _get_allowed_progs(user)
    if not allowed_progs:
        return queryset.none()
    return queryset.filter(prog__in=allowed_progs)


@login_required
def declaration_communication(request):
    """Page principale de génération de la déclaration de communication"""
    # Récupérer les années disponibles
    annees = _scope_diamex_queryset(BaseDiameX.objects.all(), request.user).filter(
        date_m__isnull=False
    ).dates('date_m', 'year', order='DESC')

    annees_list = [d.year for d in annees]

    context = {
        'annees': annees_list,
        'annee_actuelle': datetime.now().year
    }

    return render(request, 'accounting/declaration_communication.html', context)


@login_required
@require_http_methods(["GET"])
def api_generer_declaration(request):
    """
    API pour générer les données de la déclaration de communication.
    Filtre les transactions commençant par NIF ou ISI, groupe par fournisseur et nature.
    """
    try:
        annee = int(request.GET.get('annee', datetime.now().year))

        # Récupérer toutes les transactions de l'année commençant par NIF ou ISI
        transactions = _scope_diamex_queryset(BaseDiameX.objects.all(), request.user).filter(
            date_m__year=annee,
            description__iregex=r'^(NIF|ISI)(_| PREST)'  # Commence par NIF_ ou ISI_ ou "NIF PREST" ou "ISI PREST"
        ).select_related('compte__nature_declaration').prefetch_related('compte')

        # Dictionnaire pour grouper par fournisseur + nature
        groupes = {}

        for transaction in transactions:
            # Récupérer le fournisseur via le champ fournisseur de BaseDiameX
            fournisseur_id = transaction.fournisseur
            if not fournisseur_id:
                continue

            # Essayer de récupérer le fournisseur de la table Fournisseur
            try:
                fournisseur = Fournisseur.objects.get(idxls=fournisseur_id)
            except Fournisseur.DoesNotExist:
                # Si le fournisseur n'existe pas, créer une entrée avec ID uniquement
                fournisseur = None

            # Récupérer la nature de déclaration depuis le compte
            nature = None
            nature_nom = "Non classé"
            if transaction.compte and transaction.compte.nature_declaration:
                nature = transaction.compte.nature_declaration
                nature_nom = nature.nom

            # Clé unique: fournisseur_id + nature
            cle = f"{fournisseur_id}_{nature_nom}"

            if cle not in groupes:
                location_data = _get_fournisseur_location_data(fournisseur) if fournisseur else {
                    'district': '',
                    'ex_province': '',
                }
                groupes[cle] = {
                    'fournisseur_id': fournisseur_id,
                    'nif': fournisseur.numero_nif if fournisseur else '',
                    'stat': fournisseur.numero_stat if fournisseur else '',
                    'cin': fournisseur.cin if fournisseur else '',
                    'date_cin': fournisseur.date_cin.strftime('%d/%m/%Y') if (fournisseur and fournisseur.date_cin) else '',
                    'lieu_cin': fournisseur.lieu_cin if fournisseur else '',  # À ajouter au modèle Fournisseur si nécessaire
                    'nom': fournisseur.nom_fournisseur if fournisseur else f"Fournisseur {fournisseur_id}",
                    'adresse': fournisseur.adresse if fournisseur else '',
                    'ville': '',
                    'district': location_data['district'],
                    'ex_province': location_data['ex_province'],
                    'pays': 'Madagascar',  # Par défaut
                    'nature': nature_nom,
                    'montant_comptabilise': Decimal('0'),
                    'montant_verse': Decimal('0'),
                    'type_operation': '',  # Achat ou Prestation
                    'type_numero': ''  # NIF ou ISI
                }

            # Ajouter le montant (Out = dépense)
            montant = Decimal(str(transaction.montant_out))
            groupes[cle]['montant_comptabilise'] += montant
            groupes[cle]['montant_verse'] += montant  # Montant versé = Montant comptabilisé

            # Déterminer le type d'opération (Achat, Prestation ou Achats immobilisé)
            description = transaction.description.upper()
            if nature_nom.lower() == 'outillage':
                groupes[cle]['type_operation'] = 'Achats immobilisé'
            elif 'PREST' in description:
                groupes[cle]['type_operation'] = 'Prestation'
            else:
                groupes[cle]['type_operation'] = 'Achat'

            # Déterminer le type de numéro (NIF ou ISI)
            if description.startswith('NIF'):
                groupes[cle]['type_numero'] = 'NIF'
            elif description.startswith('ISI'):
                groupes[cle]['type_numero'] = 'ISI'

        # Convertir en liste
        resultats = list(groupes.values())

        # Convertir les Decimal en float pour la sérialisation JSON
        for resultat in resultats:
            resultat['montant_comptabilise'] = float(resultat['montant_comptabilise'])
            resultat['montant_verse'] = float(resultat['montant_verse'])

        # Trier par nom de fournisseur puis par nature
        resultats.sort(key=lambda x: (x['nom'], x['nature']))

        return JsonResponse({
            'success': True,
            'annee': annee,
            'total_lignes': len(resultats),
            'data': resultats
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_export_declaration_excel(request):
    """
    Exporte la déclaration de communication en fichier Excel.
    """
    try:
        annee = int(request.GET.get('annee', datetime.now().year))

        # Générer les données (même logique que api_generer_declaration)
        transactions = _scope_diamex_queryset(BaseDiameX.objects.all(), request.user).filter(
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
                    'lieu_cin': '',
                    'nom': fournisseur.nom_fournisseur if fournisseur else f"Fournisseur {fournisseur_id}",
                    'adresse': fournisseur.adresse if fournisseur else '',
                    'ville': '',
                    'district': location_data['district'],
                    'ex_province': location_data['ex_province'],
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

            description = transaction.description.upper()
            if nature_nom.lower() == 'outillage':
                groupes[cle]['type_operation'] = 'Achats immobilisé'
            elif 'PREST' in description:
                groupes[cle]['type_operation'] = 'Prestation'
            else:
                groupes[cle]['type_operation'] = 'Achat'

            if description.startswith('NIF'):
                groupes[cle]['type_numero'] = 'NIF'
            elif description.startswith('ISI'):
                groupes[cle]['type_numero'] = 'ISI'

        resultats = list(groupes.values())
        resultats.sort(key=lambda x: (x['nom'], x['nature']))

        # Créer le fichier Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Déclaration {annee}"

        # Styles
        header_font = Font(bold=True, size=11, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            "Numéro NIF",
            "Numéro STAT",
            "Numéro CIN",
            "Date CIN",
            "Lieu de délivrance CIN",
            "Nom fournisseur",
            "Adresse",
            "District",
            "Ex-province",
            "Pays",
            "Nature",
            "Montant comptabilisé (Ar)",
            "Montant versé (Ar)",
            "Achat ou Prestation",
            "ISI ou NIF"
        ]

        # Écrire les en-têtes
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border

        # Écrire les données
        for row_idx, ligne in enumerate(resultats, start=2):
            ws.cell(row=row_idx, column=1, value=ligne['nif']).border = thin_border
            ws.cell(row=row_idx, column=2, value=ligne['stat']).border = thin_border
            ws.cell(row=row_idx, column=3, value=ligne['cin']).border = thin_border
            ws.cell(row=row_idx, column=4, value=ligne['date_cin']).border = thin_border
            ws.cell(row=row_idx, column=5, value=ligne['lieu_cin']).border = thin_border
            ws.cell(row=row_idx, column=6, value=ligne['nom']).border = thin_border
            ws.cell(row=row_idx, column=7, value=ligne['adresse']).border = thin_border
            ws.cell(row=row_idx, column=8, value=ligne['district']).border = thin_border
            ws.cell(row=row_idx, column=9, value=ligne['ex_province']).border = thin_border
            ws.cell(row=row_idx, column=10, value=ligne['pays']).border = thin_border
            ws.cell(row=row_idx, column=11, value=ligne['nature']).border = thin_border

            # Montants avec format numérique
            cell_comptabilise = ws.cell(row=row_idx, column=12, value=float(ligne['montant_comptabilise']))
            cell_comptabilise.number_format = '#,##0.00'
            cell_comptabilise.border = thin_border

            cell_verse = ws.cell(row=row_idx, column=13, value=float(ligne['montant_verse']))
            cell_verse.number_format = '#,##0.00'
            cell_verse.border = thin_border

            ws.cell(row=row_idx, column=14, value=ligne['type_operation']).border = thin_border
            ws.cell(row=row_idx, column=15, value=ligne['type_numero']).border = thin_border

        # Ajuster les largeurs de colonnes
        column_widths = {
            1: 15,  # NIF
            2: 18,  # STAT
            3: 15,  # CIN
            4: 12,  # Date CIN
            5: 20,  # Lieu CIN
            6: 40,  # Nom
            7: 50,  # Adresse
            8: 20,  # Ville
            9: 20,  # Province
            10: 15,  # Pays
            11: 20,  # Nature
            12: 20,  # Montant comptabilisé
            13: 18,  # Montant versé
            14: 18,  # Type opération
            15: 12   # Type numéro
        }

        for col_idx, width in column_widths.items():
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

        # Figer la première ligne
        ws.freeze_panes = "A2"

        # Sauvegarder dans un buffer
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        # Créer la réponse
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"Declaration_Communication_{annee}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
