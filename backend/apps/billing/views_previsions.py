"""
Vues pour la gestion des prévisions budgétaires.
"""
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.db.models import Sum
from datetime import datetime
from decimal import Decimal
import json
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from .models_previsions import PrevisionBudget, ConfigurationPrevision
from .services_previsions import (
    recalculer_previsions_annee,
    get_resume_previsions
)
from apps.organization.models import Base, Ouvrage, Compte
from apps.geography.models import District, Commune
from .models import PointEau
from django.views.decorators.csrf import csrf_exempt
import re


@login_required
def previsions_budget_page(request):
    """
    Page principale d'affichage des prévisions budgétaires.
    """
    # Récupérer l'année courante ou celle demandée
    annee = int(request.GET.get('annee', datetime.now().year))
    mois = request.GET.get('mois')
    if mois:
        mois = int(mois)

    # Récupérer les bases pour le filtre
    bases = Base.objects.all().order_by('nom_base')

    # Récupérer les districts pour le filtre
    districts = District.objects.all().order_by('nom_district')

    # Récupérer la configuration active
    try:
        config = ConfigurationPrevision.objects.get(annee_reference=annee, actif=True)
    except ConfigurationPrevision.DoesNotExist:
        config = None

    # Récupérer les comptes avec codes à 5 chiffres pour le dropdown
    comptes = Compte.objects.all()
    comptes_5_chiffres = [
        {'code': c.compte, 'libelle': c.nom_compte}
        for c in comptes
        if re.match(r'^\d{5}', c.compte)
    ]
    comptes_5_chiffres_sorted = sorted(comptes_5_chiffres, key=lambda x: x['code'])

    context = {
        'annee': annee,
        'mois': mois,
        'bases': bases,
        'districts': districts,
        'config': config,
        'comptes': comptes_5_chiffres_sorted,
        # Années disponibles (5 années autour de l'année courante)
        'annees': range(annee - 2, annee + 3)
    }

    return render(request, 'billing/previsions_budget.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def api_previsions_list(request):
    """
    API pour récupérer la liste des prévisions avec filtres (GET)
    ou créer une prévision manuelle (POST).
    """
    # Création d'une prévision manuelle
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            # Valider les données
            annee = int(data.get('annee'))
            mois = int(data.get('mois'))
            type_prevision = data.get('type_prevision')
            libelle = data.get('libelle')
            cat = data.get('cat')
            quantite = data.get('quantite')
            prix_unitaire = data.get('prix_unitaire')
            in_amount = Decimal(str(data.get('in_amount', 0)))
            out_amount = Decimal(str(data.get('out_amount', 0)))

            if not libelle:
                return JsonResponse({
                    'success': False,
                    'error': 'Le libellé est obligatoire'
                }, status=400)

            # Créer la prévision
            from datetime import date
            prevision = PrevisionBudget.objects.create(
                annee=annee,
                mois=mois,
                date=date(annee, mois, 1),
                type_prevision=type_prevision,
                cat=cat,
                libelle=libelle,
                detail=data.get('detail', libelle),
                quantite=Decimal(str(quantite)) if quantite is not None else None,
                prix_unitaire=Decimal(str(prix_unitaire)) if prix_unitaire is not None else None,
                in_amount=in_amount,
                out_amount=out_amount,
                est_calculee_auto=False,
                source_calcul='Manuel'
            )

            return JsonResponse({
                'success': True,
                'message': 'Prévision créée avec succès',
                'prevision_id': str(prevision.id)
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

    # Récupération de la liste (GET)
    try:
        # Filtres
        annee = int(request.GET.get('annee', datetime.now().year))
        mois = request.GET.get('mois')
        base_id = request.GET.get('base_id')
        type_prevision = request.GET.get('type')
        district_id = request.GET.get('district_id')
        commune_id = request.GET.get('commune_id')
        ouvrage_id = request.GET.get('ouvrage_id')
        est_calculee_auto = request.GET.get('est_calculee_auto')

        # Requête de base
        queryset = PrevisionBudget.objects.filter(annee=annee).select_related(
            'base', 'ouvrage', 'district', 'commune'
        )

        # Appliquer les filtres
        if mois:
            queryset = queryset.filter(mois=int(mois))
        if base_id and base_id != 'all':
            queryset = queryset.filter(base_id=base_id)
        if type_prevision and type_prevision != 'all':
            # Support pour plusieurs types séparés par virgule
            if ',' in type_prevision:
                types = type_prevision.split(',')
                queryset = queryset.filter(type_prevision__in=types)
            else:
                queryset = queryset.filter(type_prevision=type_prevision)
        if district_id and district_id != 'all':
            queryset = queryset.filter(district_id=district_id)
        if commune_id and commune_id != 'all':
            queryset = queryset.filter(commune_id=commune_id)
        if ouvrage_id and ouvrage_id != 'all':
            queryset = queryset.filter(ouvrage_id=ouvrage_id)
        if est_calculee_auto is not None:
            # Convertir la chaîne en booléen
            queryset = queryset.filter(est_calculee_auto=(est_calculee_auto.lower() == 'true'))

        # Trier par date
        queryset = queryset.order_by('date', 'type_prevision', 'libelle')

        # Convertir en liste de dictionnaires
        previsions = []
        for prev in queryset:
            previsions.append({
                'id': str(prev.id),
                'date': prev.date.isoformat(),
                'mois': prev.mois,
                'cat': prev.cat or '',
                'libelle': prev.libelle,
                'in_amount': float(prev.in_amount),
                'out_amount': float(prev.out_amount),
                'activ': prev.activ or '',
                'detail': prev.detail or '',
                'quantite': float(prev.quantite) if prev.quantite else None,
                'prix_unitaire': float(prev.prix_unitaire) if prev.prix_unitaire else None,
                'type_prevision': prev.type_prevision,
                'type_prevision_display': prev.get_type_prevision_display(),
                'est_calculee_auto': prev.est_calculee_auto,
                'base_nom': prev.base.nom_base if prev.base else '',
                'ouvrage': prev.ouvrage.nom_ouvrage if prev.ouvrage else '',
                'district': prev.district.nom_district if prev.district else '',
                'commune': prev.commune.nom_commune if prev.commune else '',
                'created_at': prev.created_at.isoformat() if prev.created_at else None,
            })

        # Calculer les totaux
        totaux = queryset.aggregate(
            total_in=Sum('in_amount'),
            total_out=Sum('out_amount')
        )

        return JsonResponse({
            'success': True,
            'previsions': previsions,
            'total_in': float(totaux['total_in'] or 0),
            'total_out': float(totaux['total_out'] or 0),
            'solde': float((totaux['total_in'] or 0) - (totaux['total_out'] or 0)),
            'count': len(previsions)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_recalculer_previsions(request):
    """
    API pour recalculer les prévisions automatiques pour une année.
    """
    try:
        data = json.loads(request.body)
        annee = int(data.get('annee', datetime.now().year))
        base_id = data.get('base_id')

        # Récupérer la base si spécifiée
        base = None
        if base_id and base_id != 'all':
            base = Base.objects.get(id=base_id)

        # Lancer le recalcul
        stats = recalculer_previsions_annee(annee, base)

        return JsonResponse({
            'success': True,
            'message': f"{stats['creees']} prévisions calculées pour {annee}",
            'stats': stats
        })

    except Base.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Base introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_resume_previsions(request):
    """
    API pour obtenir un résumé des prévisions (totaux par type).
    """
    try:
        annee = int(request.GET.get('annee', datetime.now().year))
        mois = request.GET.get('mois')
        base_id = request.GET.get('base_id')

        if mois:
            mois = int(mois)

        base = None
        if base_id and base_id != 'all':
            base = Base.objects.get(id=base_id)

        resume = get_resume_previsions(annee, mois, base)

        # Convertir Decimal en float pour JSON
        resume_json = {
            k: float(v) for k, v in resume.items()
        }

        return JsonResponse({
            'success': True,
            'resume': resume_json
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_update_configuration(request):
    """
    API pour mettre à jour la configuration des prévisions.
    """
    try:
        data = json.loads(request.body)
        annee = int(data.get('annee', datetime.now().year))

        # Récupérer ou créer la configuration
        config, created = ConfigurationPrevision.objects.get_or_create(
            annee_reference=annee,
            actif=True,
            defaults={
                'created_by': request.user.employe if hasattr(request.user, 'employe') else None
            }
        )

        # Mettre à jour les champs
        if 'nb_nouveaux_pe_prevus' in data:
            config.nb_nouveaux_pe_prevus = int(data['nb_nouveaux_pe_prevus'])
        if 'tarif_nouveau_pe_trimestre' in data:
            config.tarif_nouveau_pe_trimestre = float(data['tarif_nouveau_pe_trimestre'])
        if 'nb_mois_moyenne_volumetrique' in data:
            config.nb_mois_moyenne_volumetrique = int(data['nb_mois_moyenne_volumetrique'])

        config.save()

        return JsonResponse({
            'success': True,
            'message': 'Configuration mise à jour avec succès',
            'created': created
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["DELETE"])
def api_delete_prevision(request, prevision_id):
    """
    API pour supprimer une prévision (seulement les manuelles).
    """
    try:
        prevision = PrevisionBudget.objects.get(id=prevision_id)

        # Empêcher la suppression des prévisions auto
        if prevision.est_calculee_auto:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de supprimer une prévision calculée automatiquement. Utilisez le recalcul.'
            }, status=403)

        prevision.delete()

        return JsonResponse({
            'success': True,
            'message': 'Prévision supprimée avec succès'
        })

    except PrevisionBudget.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Prévision introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_communes_by_district(request):
    """API pour récupérer les communes d'un district."""
    try:
        district_id = request.GET.get('district_id')

        if not district_id or district_id == 'all':
            communes = Commune.objects.all().order_by('nom_commune')
        else:
            communes = Commune.objects.filter(
                fokontany__village__parcelle__pointeau__ouvrage__isnull=False
            ).filter(
                district_id=district_id
            ).distinct().order_by('nom_commune')

        communes_list = [
            {'id': str(c.id), 'nom': c.nom_commune}
            for c in communes
        ]

        return JsonResponse({
            'success': True,
            'communes': communes_list
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_ouvrages_by_commune(request):
    """API pour récupérer les ouvrages d'une commune."""
    try:
        commune_id = request.GET.get('commune_id')

        if not commune_id or commune_id == 'all':
            ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')
        else:
            ouvrages = Ouvrage.objects.filter(
                pointeau__parcelle__village__fokontany__commune_id=commune_id
            ).distinct().order_by('nom_ouvrage')

        ouvrages_list = [
            {'id': str(o.id), 'nom': o.nom_ouvrage}
            for o in ouvrages[:200]  # Limite pour performance
        ]

        return JsonResponse({
            'success': True,
            'ouvrages': ouvrages_list
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def recap_previsions_budget(request):
    """
    Page de récapitulatif des prévisions budgétaires groupées par type.
    Affiche les totaux sans colonne Date, avec le nombre d'ouvrages et points d'eau concernés.
    """
    annee = int(request.GET.get('annee', datetime.now().year))

    # Récupérer les bases et districts pour les filtres
    bases = Base.objects.all().order_by('nom_base')
    districts = District.objects.all().order_by('nom_district')

    context = {
        'annee': annee,
        'bases': bases,
        'districts': districts,
        'annees': range(annee - 2, annee + 3)
    }

    return render(request, 'billing/recap_previsions_budget.html', context)


@login_required
@require_http_methods(["GET"])
def api_recap_previsions(request):
    """
    API pour récupérer le récapitulatif des prévisions groupées par type.
    Retourne les totaux avec le nombre d'ouvrages et points d'eau concernés.
    """
    try:
        # Filtres
        annee = int(request.GET.get('annee', datetime.now().year))
        base_id = request.GET.get('base_id')
        district_id = request.GET.get('district_id')
        commune_id = request.GET.get('commune_id')
        type_id = request.GET.get('type_id')

        # Requête de base
        queryset = PrevisionBudget.objects.filter(annee=annee)

        # Appliquer les filtres
        if base_id and base_id != 'all':
            queryset = queryset.filter(base_id=base_id)
        if district_id and district_id != 'all':
            queryset = queryset.filter(district_id=district_id)
        if commune_id and commune_id != 'all':
            queryset = queryset.filter(commune_id=commune_id)
        if type_id and type_id != 'all':
            queryset = queryset.filter(type_prevision=type_id)

        # Grouper par district, commune et type de prévision
        from django.db.models import Q

        types_prevision = [
            'recette_forfaitaire',
            'recette_volumetrique',
            'recette_nouveau_pe',
            'depense_bon_livraison',
            'depense_avance'
        ]

        recap = []

        # Obtenir toutes les combinaisons district/commune présentes dans les prévisions
        combinaisons = queryset.values('district_id', 'commune_id').distinct()

        for combo in combinaisons:
            district_id_combo = combo['district_id']
            commune_id_combo = combo['commune_id']

            # Récupérer les noms
            district_nom = None
            commune_nom = None

            if district_id_combo:
                from apps.geography.models import District
                district = District.objects.filter(id=district_id_combo).first()
                if district:
                    district_nom = district.nom_district

            if commune_id_combo:
                from apps.geography.models import Commune
                commune = Commune.objects.filter(id=commune_id_combo).first()
                if commune:
                    commune_nom = commune.nom_commune

            # Filtrer les prévisions pour cette combinaison
            previsions_combo = queryset.filter(
                district_id=district_id_combo,
                commune_id=commune_id_combo
            )

            # Pour chaque type de prévision dans cette combinaison
            for type_prev in types_prevision:
                previsions_type = previsions_combo.filter(type_prevision=type_prev)

                if not previsions_type.exists():
                    continue

                # Calculer les totaux
                totaux = previsions_type.aggregate(
                    total_in=Sum('in_amount'),
                    total_out=Sum('out_amount')
                )

                # Compter les ouvrages distincts
                # IMPORTANT: Utiliser set() car .distinct() sur values_list() peut avoir des doublons
                ouvrages_ids = set(previsions_type.filter(
                    ouvrage__isnull=False
                ).values_list('ouvrage_id', flat=True))
                nb_ouvrages = len(ouvrages_ids)

                # Compter les points d'eau liés à ces ouvrages
                nb_points_eau = 0
                if nb_ouvrages > 0:
                    nb_points_eau = PointEau.objects.filter(
                        ouvrage_id__in=ouvrages_ids
                    ).count()

                # Obtenir le libellé du type
                type_display = dict(PrevisionBudget.TYPE_CHOICES).get(
                    type_prev, type_prev
                )

                recap.append({
                    'type': type_prev,
                    'type_display': type_display,
                    'district_nom': district_nom or 'N/A',
                    'commune_nom': commune_nom or 'N/A',
                    'total_in': float(totaux['total_in'] or 0),
                    'total_out': float(totaux['total_out'] or 0),
                    'nb_ouvrages': nb_ouvrages,
                    'nb_points_eau': nb_points_eau,
                    'nb_lignes': previsions_type.count()
                })

        # Calculer les totaux généraux
        # IMPORTANT: Calculer directement depuis queryset (pas somme des lignes recap)
        # car une même prévision peut apparaître dans plusieurs lignes du recap
        # (une par district/commune), ce qui multiplierait les montants

        # Totaux des montants (depuis queryset, pas recap)
        totaux_montants = queryset.aggregate(
            total_in=Sum('in_amount'),
            total_out=Sum('out_amount')
        )

        # Ouvrages distincts
        # IMPORTANT: Utiliser set() car .distinct() sur values_list() peut avoir des doublons
        ouvrages_distincts_ids = set(queryset.filter(
            ouvrage__isnull=False
        ).values_list('ouvrage_id', flat=True))

        total_ouvrages_distincts = len(ouvrages_distincts_ids)

        # Points d'eau distincts
        total_points_eau_distincts = 0
        if total_ouvrages_distincts > 0:
            total_points_eau_distincts = PointEau.objects.filter(
                ouvrage_id__in=ouvrages_distincts_ids
            ).count()

        totaux_generaux = {
            'total_recettes': float(totaux_montants['total_in'] or 0),  # Depuis queryset
            'total_depenses': float(totaux_montants['total_out'] or 0),  # Depuis queryset
            'total_ouvrages': total_ouvrages_distincts,
            'total_points_eau': total_points_eau_distincts,
        }
        totaux_generaux['solde'] = totaux_generaux['total_recettes'] - totaux_generaux['total_depenses']

        return JsonResponse({
            'success': True,
            'recap': recap,
            'totaux': totaux_generaux,
            'annee': annee
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def export_previsions_excel(request):
    """
    Exporte les prévisions budgétaires vers un fichier Excel.
    Applique les mêmes filtres que la vue récapitulative.
    """
    try:
        # Récupérer les paramètres de filtrage
        annee = int(request.GET.get('annee', datetime.now().year))
        base_id = request.GET.get('base_id')
        district_id = request.GET.get('district_id')
        commune_id = request.GET.get('commune_id')
        type_id = request.GET.get('type_id')

        # Construire le queryset avec les filtres
        queryset = PrevisionBudget.objects.filter(
            annee=annee,
            est_calculee_auto=True
        ).select_related('base', 'district', 'commune', 'ouvrage')

        # Appliquer les filtres
        if base_id and base_id != 'all':
            queryset = queryset.filter(base_id=base_id)
        if district_id and district_id != 'all':
            queryset = queryset.filter(district_id=district_id)
        if commune_id and commune_id != 'all':
            queryset = queryset.filter(commune_id=commune_id)
        if type_id and type_id != 'all':
            queryset = queryset.filter(type_prevision=type_id)

        # Trier par district, commune, type
        queryset = queryset.order_by('district__nom_district', 'commune__nom_commune', 'type_prevision', 'date')

        # Créer le classeur Excel
        wb = Workbook()
        ws = wb.active
        ws.title = f"Prévisions {annee}"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        center_align = Alignment(horizontal='center', vertical='center')
        right_align = Alignment(horizontal='right', vertical='center')

        # En-têtes
        headers = [
            'Date', 'District', 'Commune', 'Base', 'Ouvrage', 'Type',
            'Désignation', 'Cat', 'Libellé', 'Detail', 'Quantité', 'Prix unitaire',
            'Recettes (In)', 'Dépenses (Out)', 'Activ'
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
            cell.alignment = center_align

        # Données
        row_num = 2
        total_in = 0
        total_out = 0

        for prevision in queryset:
            # Date au format DD/MM/YYYY
            if prevision.date:
                ws.cell(row=row_num, column=1, value=prevision.date)
                ws.cell(row=row_num, column=1).number_format = 'DD/MM/YYYY'
            else:
                ws.cell(row=row_num, column=1, value='')

            ws.cell(row=row_num, column=2, value=prevision.district.nom_district if prevision.district else '')
            ws.cell(row=row_num, column=3, value=prevision.commune.nom_commune if prevision.commune else '')
            ws.cell(row=row_num, column=4, value=prevision.base.nom_base if prevision.base else '')
            ws.cell(row=row_num, column=5, value=prevision.ouvrage.nom_ouvrage if prevision.ouvrage else '')
            ws.cell(row=row_num, column=6, value=dict(PrevisionBudget.TYPE_CHOICES).get(prevision.type_prevision, ''))

            # Désignation (vérifier qu'elle existe bien)
            designation_value = prevision.designation if prevision.designation else ''
            ws.cell(row=row_num, column=7, value=designation_value)

            ws.cell(row=row_num, column=8, value=prevision.cat or '')
            ws.cell(row=row_num, column=9, value=prevision.libelle or '')
            ws.cell(row=row_num, column=10, value=prevision.detail or '')

            # Quantité
            if prevision.quantite:
                cell_qty = ws.cell(row=row_num, column=11, value=float(prevision.quantite))
                cell_qty.number_format = '#,##0.00'
                cell_qty.alignment = right_align
            else:
                ws.cell(row=row_num, column=11, value='')

            # Prix unitaire
            if prevision.prix_unitaire:
                cell_pu = ws.cell(row=row_num, column=12, value=float(prevision.prix_unitaire))
                cell_pu.number_format = '#,##0.00'
                cell_pu.alignment = right_align
            else:
                ws.cell(row=row_num, column=12, value='')

            # Montants
            cell_in = ws.cell(row=row_num, column=13, value=float(prevision.in_amount))
            cell_in.number_format = '#,##0.00'
            cell_in.alignment = right_align

            cell_out = ws.cell(row=row_num, column=14, value=float(prevision.out_amount))
            cell_out.number_format = '#,##0.00'
            cell_out.alignment = right_align

            ws.cell(row=row_num, column=15, value=prevision.activ or '')

            # Bordures
            for col in range(1, 16):
                ws.cell(row=row_num, column=col).border = border

            total_in += float(prevision.in_amount)
            total_out += float(prevision.out_amount)
            row_num += 1

        # Ligne de totaux
        if row_num > 2:
            total_row = row_num
            ws.cell(row=total_row, column=1, value='TOTAL')
            ws.cell(row=total_row, column=1).font = Font(bold=True)

            cell_total_in = ws.cell(row=total_row, column=13, value=total_in)
            cell_total_in.font = Font(bold=True)
            cell_total_in.number_format = '#,##0.00'
            cell_total_in.alignment = right_align
            cell_total_in.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

            cell_total_out = ws.cell(row=total_row, column=14, value=total_out)
            cell_total_out.font = Font(bold=True)
            cell_total_out.number_format = '#,##0.00'
            cell_total_out.alignment = right_align
            cell_total_out.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

            # Solde
            ws.cell(row=total_row + 1, column=1, value='SOLDE')
            ws.cell(row=total_row + 1, column=1).font = Font(bold=True)

            solde = total_in - total_out
            cell_solde = ws.cell(row=total_row + 1, column=13, value=solde)
            cell_solde.font = Font(bold=True)
            cell_solde.number_format = '#,##0.00'
            cell_solde.alignment = right_align

            # Couleur selon positif/négatif
            if solde >= 0:
                cell_solde.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
            else:
                cell_solde.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

        # Ajuster les largeurs de colonnes (ajout de Quantité et Prix unitaire)
        column_widths = [12, 20, 20, 15, 25, 25, 30, 10, 40, 30, 12, 15, 15, 15, 15]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = width

        # Convertir en tableau structuré Excel
        if row_num > 2:  # Si on a des données
            from openpyxl.worksheet.table import Table, TableStyleInfo

            # Définir la plage du tableau (sans les lignes de totaux)
            data_end_row = row_num - 1  # Ligne avant les totaux
            table_ref = f"A1:O{data_end_row}"  # 15 colonnes (A à O)

            # Créer le tableau structuré
            tab = Table(displayName="Previsions", ref=table_ref)

            # Style du tableau
            style = TableStyleInfo(
                name="TableStyleMedium9",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False
            )
            tab.tableStyleInfo = style

            # Ajouter le tableau à la feuille
            ws.add_table(tab)

        # Créer l'onglet TCD (Tableau Croisé Dynamique - Récapitulatif)
        if row_num > 2:
            ws_tcd = wb.create_sheet(title="TCD Récapitulatif")

            # En-têtes du TCD
            tcd_headers = ['Type de Prévision', 'District', 'Commune', 'Nb Lignes', 'Recettes', 'Dépenses', 'Solde']
            for col_num, header in enumerate(tcd_headers, 1):
                cell = ws_tcd.cell(row=1, column=col_num)
                cell.value = header
                cell.fill = header_fill
                cell.font = header_font
                cell.border = border
                cell.alignment = center_align

            # Récupérer les données groupées
            from django.db.models import Sum, Count

            # Réappliquer les filtres sur le queryset
            tcd_queryset = PrevisionBudget.objects.filter(
                annee=annee,
                est_calculee_auto=True
            )
            if base_id and base_id != 'all':
                tcd_queryset = tcd_queryset.filter(base_id=base_id)
            if district_id and district_id != 'all':
                tcd_queryset = tcd_queryset.filter(district_id=district_id)
            if commune_id and commune_id != 'all':
                tcd_queryset = tcd_queryset.filter(commune_id=commune_id)
            if type_id and type_id != 'all':
                tcd_queryset = tcd_queryset.filter(type_prevision=type_id)

            # Grouper par type, district, commune
            tcd_data = tcd_queryset.values(
                'type_prevision',
                'district__nom_district',
                'commune__nom_commune'
            ).annotate(
                nb_lignes=Count('id'),
                total_recettes=Sum('in_amount'),
                total_depenses=Sum('out_amount')
            ).order_by('type_prevision', 'district__nom_district', 'commune__nom_commune')

            # Remplir les données du TCD
            tcd_row = 2
            tcd_total_lignes = 0
            tcd_total_recettes = 0
            tcd_total_depenses = 0

            for data in tcd_data:
                ws_tcd.cell(row=tcd_row, column=1, value=dict(PrevisionBudget.TYPE_CHOICES).get(data['type_prevision'], ''))
                ws_tcd.cell(row=tcd_row, column=2, value=data['district__nom_district'] or '')
                ws_tcd.cell(row=tcd_row, column=3, value=data['commune__nom_commune'] or '')
                ws_tcd.cell(row=tcd_row, column=4, value=data['nb_lignes'])

                recettes = float(data['total_recettes'] or 0)
                depenses = float(data['total_depenses'] or 0)
                solde = recettes - depenses

                cell_recettes = ws_tcd.cell(row=tcd_row, column=5, value=recettes)
                cell_recettes.number_format = '#,##0.00'
                cell_recettes.alignment = right_align

                cell_depenses = ws_tcd.cell(row=tcd_row, column=6, value=depenses)
                cell_depenses.number_format = '#,##0.00'
                cell_depenses.alignment = right_align

                cell_solde = ws_tcd.cell(row=tcd_row, column=7, value=solde)
                cell_solde.number_format = '#,##0.00'
                cell_solde.alignment = right_align

                # Bordures
                for col in range(1, 8):
                    ws_tcd.cell(row=tcd_row, column=col).border = border

                tcd_total_lignes += data['nb_lignes']
                tcd_total_recettes += recettes
                tcd_total_depenses += depenses
                tcd_row += 1

            # Ligne de totaux du TCD
            if tcd_row > 2:
                ws_tcd.cell(row=tcd_row, column=1, value='TOTAL GÉNÉRAL')
                ws_tcd.cell(row=tcd_row, column=1).font = Font(bold=True)

                ws_tcd.cell(row=tcd_row, column=4, value=tcd_total_lignes)
                ws_tcd.cell(row=tcd_row, column=4).font = Font(bold=True)

                cell_total_rec = ws_tcd.cell(row=tcd_row, column=5, value=tcd_total_recettes)
                cell_total_rec.font = Font(bold=True)
                cell_total_rec.number_format = '#,##0.00'
                cell_total_rec.alignment = right_align
                cell_total_rec.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

                cell_total_dep = ws_tcd.cell(row=tcd_row, column=6, value=tcd_total_depenses)
                cell_total_dep.font = Font(bold=True)
                cell_total_dep.number_format = '#,##0.00'
                cell_total_dep.alignment = right_align
                cell_total_dep.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

                tcd_solde = tcd_total_recettes - tcd_total_depenses
                cell_total_solde = ws_tcd.cell(row=tcd_row, column=7, value=tcd_solde)
                cell_total_solde.font = Font(bold=True)
                cell_total_solde.number_format = '#,##0.00'
                cell_total_solde.alignment = right_align

                if tcd_solde >= 0:
                    cell_total_solde.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                else:
                    cell_total_solde.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

            # Ajuster les largeurs de colonnes du TCD
            tcd_widths = [30, 20, 20, 12, 15, 15, 15]
            for i, width in enumerate(tcd_widths, 1):
                ws_tcd.column_dimensions[get_column_letter(i)].width = width

        # Générer le fichier
        filename = f"Previsions_Budget_{annee}"
        if type_id and type_id != 'all':
            filename += f"_{type_id}"
        filename += ".xlsx"

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response

    except Exception as e:
        return HttpResponse(f"Erreur lors de l'export: {str(e)}", status=500)


@login_required
def depenses_recurrentes_page(request):
    """
    Page de gestion des dépenses récurrentes auto-générées.
    Permet à l'utilisateur de consulter et supprimer manuellement
    les prévisions de dépenses récurrentes.
    """
    annee = int(request.GET.get('annee', datetime.now().year))

    # Comptes concernés
    comptes_recurrents = [
        ('602', 'Achats stockés'),
        ('606', 'Achats non stockés'),
        ('615', 'Entretien et réparations'),
        ('623100', 'Publicité'),
        ('626222', 'Téléphone'),
        ('626320', 'Internet mobile'),
        ('626321', 'Internet fixe'),
        ('627203', 'Frais bancaires'),
        ('627204', 'Frais MVola/transferts'),
        ('631104', 'IRI'),
    ]

    context = {
        'annee': annee,
        'comptes_recurrents': comptes_recurrents,
    }

    return render(request, 'billing/depenses_recurrentes_management.html', context)


@login_required
@csrf_exempt
@require_http_methods(["GET"])
def api_depenses_recurrentes_list(request):
    """
    API pour récupérer la liste des dépenses récurrentes avec filtres.
    """
    try:
        annee = int(request.GET.get('annee', datetime.now().year))
        mois = request.GET.get('mois')
        compte_code = request.GET.get('compte')

        # Récupérer les prévisions de type depense_recurrente
        previsions = PrevisionBudget.objects.filter(
            type_prevision='depense_recurrente',
            annee=annee
        )

        # Filtrer par mois si fourni
        if mois:
            previsions = previsions.filter(mois=int(mois))

        # Filtrer par compte si fourni
        if compte_code:
            previsions = previsions.filter(cat=compte_code)

        # Préparer les données pour le frontend
        data = []
        for prev in previsions.order_by('date', 'cat'):
            data.append({
                'id': str(prev.id),
                'date': prev.date.strftime('%Y-%m-%d'),
                'mois': prev.mois,
                'compte': prev.cat,
                'libelle': prev.libelle,
                'detail': prev.detail,
                'montant': float(prev.out_amount),
                'source_calcul': prev.source_calcul,
            })

        # Statistiques
        stats = {
            'total_previsions': len(data),
            'montant_total': sum([d['montant'] for d in data]),
        }

        return JsonResponse({
            'success': True,
            'previsions': data,
            'stats': stats
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_depense_recurrente(request):
    """
    API pour supprimer une prévision de dépense récurrente.
    """
    try:
        data = json.loads(request.body)
        prevision_id = data.get('prevision_id')

        if not prevision_id:
            return JsonResponse({
                'success': False,
                'error': 'ID de prévision manquant'
            }, status=400)

        # Récupérer et vérifier que c'est bien une dépense récurrente
        try:
            prevision = PrevisionBudget.objects.get(
                id=prevision_id,
                type_prevision='depense_recurrente'
            )
        except PrevisionBudget.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Prévision non trouvée ou type incorrect'
            }, status=404)

        # Sauvegarder les infos pour le message
        compte = prevision.cat
        libelle = prevision.libelle
        mois = prevision.mois
        montant = float(prevision.out_amount)

        # Supprimer
        prevision.delete()

        return JsonResponse({
            'success': True,
            'message': f'Prévision supprimée : {libelle} (Compte {compte}) - Mois {mois} - {montant:,.0f} Ar'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_depenses_recurrentes_batch(request):
    """
    API pour supprimer plusieurs prévisions de dépenses récurrentes d'un coup.
    """
    try:
        data = json.loads(request.body)
        prevision_ids = data.get('prevision_ids', [])

        if not prevision_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucune prévision sélectionnée'
            }, status=400)

        # Supprimer toutes les prévisions
        nb_deleted = PrevisionBudget.objects.filter(
            id__in=prevision_ids,
            type_prevision='depense_recurrente'
        ).delete()[0]

        return JsonResponse({
            'success': True,
            'message': f'{nb_deleted} prévision(s) supprimée(s)',
            'nb_deleted': nb_deleted
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
