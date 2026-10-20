"""Import/Export Excel des demandes d'achat et des proformas.

Le template de demandes d'achat contient, en plus de la feuille de saisie, deux
feuilles de référence (Bases et Articles) listant les ID à reporter dans les
colonnes "ID Base" et "ID Article" pour permettre le rapprochement lors de
l'import, sans ambiguïté en cas de doublons de noms.

Le template de proformas est propre à une demande d'achat : une ligne par
article de la demande, avec des paires de colonnes (ID Fournisseur, Prix)
répétées pour saisir plusieurs devis en une seule fois (format matriciel,
comme le tableau comparatif).
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

from apps.billing.models import Fournisseur
from apps.planning.models import Designation

from .models import DemandeAchat, DemandeAchatItem, Proforma, ProformaItem
from .views import _bases_disponibles, _get_demande_or_404, _get_employe


HEADER_FILL = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def _style_header_row(ws, comments=None):
    for idx, cell in enumerate(ws[1]):
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center')
        if comments and idx < len(comments) and comments[idx]:
            cell.comment = Comment(comments[idx], "Hydria")


@login_required
def template_excel_demandes(request):
    """Génère le template Excel d'import des demandes d'achat, avec feuilles de référence."""
    wb = Workbook()

    # --- Feuille 1 : Saisie des demandes ---
    ws = wb.active
    ws.title = "Demandes"

    headers = [
        'Groupe*',
        'ID Base*',
        'Motif*',
        'ID Article*',
        'Quantité*',
        'Remarques',
    ]
    ws.append(headers)

    comments = [
        "Identifiant de regroupement (ex: 1, 2, 3...). Toutes les lignes ayant le même Groupe "
        "formeront UNE SEULE demande d'achat avec plusieurs articles.",
        "ID de la base demandeuse - voir colonne ID dans la feuille 'Bases'",
        "Motif de la demande - identique pour toutes les lignes d'un même Groupe",
        "ID de l'article demandé - voir colonne ID dans la feuille 'Articles'",
        "Quantité souhaitée pour cet article (nombre)",
        "Remarque libre pour cet article (optionnel)",
    ]
    _style_header_row(ws, comments)

    # Exemple : une demande (Groupe 1) avec 2 articles
    bases_disponibles = list(_bases_disponibles(request)[:1])
    designations_exemple = list(Designation.objects.filter(actif=True)[:2])

    exemple_base_id = str(bases_disponibles[0].id) if bases_disponibles else 'ID_BASE'
    exemple_article_1 = str(designations_exemple[0].id) if designations_exemple else 'ID_ARTICLE'
    exemple_article_2 = str(designations_exemple[1].id) if len(designations_exemple) > 1 else 'ID_ARTICLE'

    ws.append([1, exemple_base_id, "Remplacement matériel usé du réseau", exemple_article_1, 10, ''])
    ws.append([1, exemple_base_id, "Remplacement matériel usé du réseau", exemple_article_2, 4, 'Urgent'])

    ws.column_dimensions['A'].width = 10
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['C'].width = 45
    ws.column_dimensions['D'].width = 40
    ws.column_dimensions['E'].width = 12
    ws.column_dimensions['F'].width = 30

    # --- Feuille 2 : Référence des Bases ---
    ws_bases = wb.create_sheet("Bases")
    ws_bases.append(['ID Base', 'Nom de la base', 'Organisation'])
    _style_header_row(ws_bases)

    for base in _bases_disponibles(request).select_related('organisation'):
        ws_bases.append([
            str(base.id),
            base.nom_base,
            base.organisation.nom_organisation if base.organisation else '',
        ])

    ws_bases.column_dimensions['A'].width = 40
    ws_bases.column_dimensions['B'].width = 35
    ws_bases.column_dimensions['C'].width = 30

    # --- Feuille 3 : Référence des Articles (Désignations) ---
    ws_articles = wb.create_sheet("Articles")
    ws_articles.append(['ID Article', 'Nom', 'Type', 'Unité', 'Prix unitaire suggéré (Ar)'])
    _style_header_row(ws_articles)

    designations = Designation.objects.filter(actif=True).select_related('type_designation').order_by('nom')
    for designation in designations:
        ws_articles.append([
            str(designation.id),
            designation.nom,
            designation.type_designation.nom if designation.type_designation else '',
            designation.unite or '',
            float(designation.prix_unitaire) if designation.prix_unitaire else '',
        ])

    ws_articles.column_dimensions['A'].width = 40
    ws_articles.column_dimensions['B'].width = 45
    ws_articles.column_dimensions['C'].width = 25
    ws_articles.column_dimensions['D'].width = 12
    ws_articles.column_dimensions['E'].width = 22

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="template_import_demandes_achat.xlsx"'
    wb.save(response)
    return response


@login_required
def import_excel_demandes(request):
    """Importe des demandes d'achat depuis le fichier Excel généré par le template ci-dessus."""
    if request.method != 'POST':
        return redirect('procurement:demande_achat_list')

    fichier = request.FILES.get('fichier_excel')
    if not fichier:
        messages.error(request, "Veuillez sélectionner un fichier Excel.")
        return redirect('procurement:demande_achat_list')

    employe = _get_employe(request)
    if employe is None:
        messages.error(request, "Votre compte n'est lié à aucun employé, impossible d'importer des demandes.")
        return redirect('procurement:demande_achat_list')

    bases_autorisees = {str(b.id): b for b in _bases_disponibles(request)}
    designations_valides = set(
        str(pk) for pk in Designation.objects.filter(actif=True).values_list('id', flat=True)
    )

    try:
        wb = load_workbook(fichier, data_only=True)
        ws = wb['Demandes'] if 'Demandes' in wb.sheetnames else wb.active
    except Exception as exc:
        messages.error(request, f"Impossible de lire le fichier Excel : {exc}")
        return redirect('procurement:demande_achat_list')

    # Regrouper les lignes par colonne "Groupe"
    groupes = {}
    erreurs = []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row is None or all(cell in (None, '') for cell in row):
            continue

        groupe_raw, base_id, motif, article_id, quantite_raw, remarques = (list(row) + [None] * 6)[:6]

        if groupe_raw in (None, ''):
            erreurs.append(f"Ligne {row_idx} : colonne 'Groupe' vide, ligne ignorée.")
            continue

        groupe_cle = str(groupe_raw).strip()
        base_id = str(base_id).strip() if base_id else ''
        motif = str(motif).strip() if motif else ''
        article_id = str(article_id).strip() if article_id else ''

        if not base_id or not motif or not article_id:
            erreurs.append(f"Ligne {row_idx} (groupe {groupe_cle}) : Base, Motif ou Article manquant.")
            continue

        if base_id not in bases_autorisees:
            erreurs.append(f"Ligne {row_idx} (groupe {groupe_cle}) : ID Base '{base_id}' invalide ou hors de votre organisation.")
            continue

        if article_id not in designations_valides:
            erreurs.append(f"Ligne {row_idx} (groupe {groupe_cle}) : ID Article '{article_id}' invalide.")
            continue

        try:
            quantite = Decimal(str(quantite_raw).replace(',', '.'))
        except (InvalidOperation, TypeError):
            erreurs.append(f"Ligne {row_idx} (groupe {groupe_cle}) : quantité invalide.")
            continue

        if quantite <= 0:
            erreurs.append(f"Ligne {row_idx} (groupe {groupe_cle}) : quantité doit être positive.")
            continue

        groupe = groupes.setdefault(groupe_cle, {
            'base_id': base_id,
            'motif': motif,
            'items': [],
        })
        # Une demande importée doit être cohérente : même base et même motif pour toutes ses lignes
        if groupe['base_id'] != base_id:
            erreurs.append(f"Ligne {row_idx} (groupe {groupe_cle}) : la base diffère de la première ligne de ce groupe, ligne ignorée.")
            continue

        groupe['items'].append({
            'article_id': article_id,
            'quantite': quantite,
            'remarques': str(remarques).strip() if remarques else None,
        })

    if not groupes:
        messages.error(request, "Aucune ligne valide trouvée dans le fichier." + (" Détails : " + " / ".join(erreurs[:5]) if erreurs else ""))
        return redirect('procurement:demande_achat_list')

    demandes_creees = []
    with transaction.atomic():
        for groupe_cle, groupe in groupes.items():
            if not groupe['items']:
                continue
            demande = DemandeAchat.objects.create(
                base_id=groupe['base_id'],
                demandeur=employe,
                motif=groupe['motif'],
                statut='proformas',
            )
            for item in groupe['items']:
                DemandeAchatItem.objects.create(
                    demande=demande,
                    designation_id=item['article_id'],
                    quantite=item['quantite'],
                    remarques=item['remarques'],
                )
            demandes_creees.append(demande)

    if demandes_creees:
        messages.success(
            request,
            f"{len(demandes_creees)} demande(s) d'achat importée(s) avec succès : "
            + ', '.join(d.numero_demande for d in demandes_creees)
        )
    if erreurs:
        nb_affichees = 8
        detail = ' / '.join(erreurs[:nb_affichees])
        suffixe = f" (+{len(erreurs) - nb_affichees} autre(s) erreur(s))" if len(erreurs) > nb_affichees else ""
        messages.warning(request, f"{len(erreurs)} ligne(s) ignorée(s) : {detail}{suffixe}")

    return redirect('procurement:demande_achat_list')


# ---------------------------------------------------------------------------
# Import/Export Excel des proformas (format matriciel : articles en lignes,
# paires de colonnes ID Fournisseur / Prix répétées pour chaque devis)
# ---------------------------------------------------------------------------

NB_COLONNES_FOURNISSEUR_EXEMPLE = 3  # Nombre de paires (ID Fournisseur, Prix) pré-générées dans le template


@login_required
def template_excel_proformas(request, demande_id):
    """Génère le template Excel d'import de proformas pour une demande d'achat donnée."""
    demande = _get_demande_or_404(request, demande_id, DemandeAchat.objects.prefetch_related('items__designation'))

    items = list(demande.items.all())
    if not items:
        messages.error(request, "Cette demande d'achat ne contient aucun article, impossible de générer le template.")
        return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    wb = Workbook()
    ws = wb.active
    ws.title = "Proformas"

    fixed_headers = ['ID Article*', 'Désignation (info)', 'Quantité demandée (info)']
    fournisseur_headers = []
    for i in range(1, NB_COLONNES_FOURNISSEUR_EXEMPLE + 1):
        fournisseur_headers += [f'ID Fournisseur {i}', f'Prix {i}']
    headers = fixed_headers + fournisseur_headers
    ws.append(headers)

    comments = [
        "Ne pas modifier - identifie l'article de la demande d'achat (seule colonne réellement utilisée à l'import avec les colonnes Fournisseur/Prix)",
        "Information seule, pour vous repérer - non lue à l'import",
        "Quantité déjà fixée dans la demande d'achat - information seule pour vous repérer pendant la saisie des prix, non lue à l'import. Pour la modifier, éditez la demande d'achat.",
    ]
    for i in range(1, NB_COLONNES_FOURNISSEUR_EXEMPLE + 1):
        comments += [
            f"ID du fournisseur {i} - voir feuille 'Fournisseurs'. Identique sur toutes les lignes pour ce fournisseur.",
            f"Prix unitaire proposé par le fournisseur {i} pour cet article (laisser vide si non proposé)",
        ]
    _style_header_row(ws, comments)

    fournisseurs_devis = list(
        Fournisseur.objects.filter(actif=True, devis=True).order_by('nom_fournisseur')
    )
    fournisseurs_deja_soumis = set(str(pk) for pk in demande.proformas.values_list('fournisseur_id', flat=True))
    fournisseurs_disponibles = [f for f in fournisseurs_devis if str(f.id) not in fournisseurs_deja_soumis]

    for item in items:
        row = [str(item.designation_id), item.designation.nom, float(item.quantite)]
        for i in range(NB_COLONNES_FOURNISSEUR_EXEMPLE):
            fournisseur_id = str(fournisseurs_disponibles[i].id) if i < len(fournisseurs_disponibles) else ''
            row += [fournisseur_id, '']
        ws.append(row)

    ws.column_dimensions['A'].width = 40
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['C'].width = 20
    col_letters = [chr(ord('D') + i) for i in range(len(fournisseur_headers))]
    for letter in col_letters:
        ws.column_dimensions[letter].width = 20

    # --- Feuille de référence : Fournisseurs disponibles (devis=True, actifs) ---
    ws_fournisseurs = wb.create_sheet("Fournisseurs")
    ws_fournisseurs.append(['ID Fournisseur', 'Nom', 'Téléphone', 'Email', 'Déjà soumis pour cette demande'])
    _style_header_row(ws_fournisseurs)

    for fournisseur in fournisseurs_devis:
        ws_fournisseurs.append([
            str(fournisseur.id),
            fournisseur.nom_fournisseur,
            fournisseur.telephone or '',
            fournisseur.email or '',
            'Oui' if str(fournisseur.id) in fournisseurs_deja_soumis else 'Non',
        ])

    ws_fournisseurs.column_dimensions['A'].width = 40
    ws_fournisseurs.column_dimensions['B'].width = 35
    ws_fournisseurs.column_dimensions['C'].width = 18
    ws_fournisseurs.column_dimensions['D'].width = 30
    ws_fournisseurs.column_dimensions['E'].width = 28

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="template_proformas_{demande.numero_demande}.xlsx"'
    wb.save(response)
    return response


@login_required
def import_excel_proformas(request, demande_id):
    """Importe un ou plusieurs proformas depuis le fichier Excel matriciel généré ci-dessus."""
    demande = _get_demande_or_404(request, demande_id, DemandeAchat.objects.prefetch_related('items__designation'))

    if request.method != 'POST':
        return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    if demande.statut in ('termine', 'annule'):
        messages.error(request, "Cette demande d'achat n'accepte plus de nouveaux proformas.")
        return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    fichier = request.FILES.get('fichier_excel')
    if not fichier:
        messages.error(request, "Veuillez sélectionner un fichier Excel.")
        return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    items_par_designation = {str(item.designation_id): item for item in demande.items.all()}
    fournisseurs_valides = {
        str(pk): pk for pk in Fournisseur.objects.filter(actif=True, devis=True).values_list('id', flat=True)
    }
    fournisseurs_deja_soumis = set(str(pk) for pk in demande.proformas.values_list('fournisseur_id', flat=True))

    try:
        wb = load_workbook(fichier, data_only=True)
        ws = wb['Proformas'] if 'Proformas' in wb.sheetnames else wb.active
    except Exception as exc:
        messages.error(request, f"Impossible de lire le fichier Excel : {exc}")
        return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    header_row = [cell.value for cell in ws[1]]
    if len(header_row) < 5:
        messages.error(request, "Format de fichier invalide : colonnes de fournisseurs manquantes.")
        return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    # Repérer dynamiquement les paires de colonnes (ID Fournisseur X, Prix X) à partir de la 4e colonne
    nb_colonnes_fixes = 3
    nb_paires = (len(header_row) - nb_colonnes_fixes) // 2

    # prix_par_fournisseur[fournisseur_id][article_id] = prix
    prix_par_fournisseur = {}
    erreurs = []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row is None or all(cell in (None, '') for cell in row):
            continue

        article_id = str(row[0]).strip() if row[0] else ''
        if not article_id or article_id not in items_par_designation:
            erreurs.append(f"Ligne {row_idx} : ID Article '{article_id}' introuvable dans cette demande.")
            continue

        for pair_idx in range(nb_paires):
            col_fournisseur = nb_colonnes_fixes + pair_idx * 2
            col_prix = col_fournisseur + 1
            if col_prix >= len(row):
                continue

            fournisseur_id_raw = row[col_fournisseur]
            prix_raw = row[col_prix]

            if not fournisseur_id_raw or prix_raw in (None, ''):
                continue

            fournisseur_id = str(fournisseur_id_raw).strip()
            if fournisseur_id not in fournisseurs_valides:
                erreurs.append(f"Ligne {row_idx}, colonne fournisseur {pair_idx + 1} : ID Fournisseur '{fournisseur_id}' invalide (inactif ou sans flag Devis).")
                continue

            try:
                prix = Decimal(str(prix_raw).replace(',', '.'))
            except InvalidOperation:
                erreurs.append(f"Ligne {row_idx}, colonne fournisseur {pair_idx + 1} : prix invalide.")
                continue

            if prix < 0:
                erreurs.append(f"Ligne {row_idx}, colonne fournisseur {pair_idx + 1} : prix négatif ignoré.")
                continue

            prix_par_fournisseur.setdefault(fournisseur_id, {})[article_id] = prix

    if not prix_par_fournisseur:
        detail = " Détails : " + " / ".join(erreurs[:5]) if erreurs else ""
        messages.error(request, "Aucun prix valide trouvé dans le fichier." + detail)
        return redirect('procurement:demande_achat_detail', demande_id=demande.id)

    proformas_crees = []
    proformas_ignores = []
    with transaction.atomic():
        for fournisseur_id, prix_articles in prix_par_fournisseur.items():
            if fournisseur_id in fournisseurs_deja_soumis:
                proformas_ignores.append(fournisseur_id)
                continue

            proforma = Proforma.objects.create(
                demande_achat=demande,
                fournisseur_id=fournisseur_id,
            )
            for article_id, prix in prix_articles.items():
                ProformaItem.objects.create(
                    proforma=proforma,
                    demande_item=items_par_designation[article_id],
                    prix_unitaire=prix,
                )
            proformas_crees.append(proforma)

        if proformas_crees and demande.statut == 'brouillon':
            demande.statut = 'proformas'
            demande.save(update_fields=['statut'])

    if proformas_crees:
        messages.success(
            request,
            f"{len(proformas_crees)} proforma(s) importé(s) avec succès : "
            + ', '.join(p.fournisseur.nom_fournisseur for p in proformas_crees)
        )
    if proformas_ignores:
        noms = Fournisseur.objects.filter(id__in=proformas_ignores).values_list('nom_fournisseur', flat=True)
        messages.warning(
            request,
            f"{len(proformas_ignores)} fournisseur(s) déjà soumis pour cette demande, ignoré(s) : " + ', '.join(noms)
            + " (modifiez leur proforma existant plutôt que de les réimporter)."
        )
    if erreurs:
        nb_affichees = 8
        detail = ' / '.join(erreurs[:nb_affichees])
        suffixe = f" (+{len(erreurs) - nb_affichees} autre(s) erreur(s))" if len(erreurs) > nb_affichees else ""
        messages.warning(request, f"{len(erreurs)} ligne(s)/cellule(s) ignorée(s) : {detail}{suffixe}")

    return redirect('procurement:demande_achat_detail', demande_id=demande.id)
