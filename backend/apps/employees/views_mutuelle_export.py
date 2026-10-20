"""
Export des paiements de mutuelle santé vers DiameX (Access)
"""
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json

from .models import PaiementMutuelleSante
from apps.accounting.models import DiameXTemporaire


@csrf_exempt
@require_http_methods(["POST"])
def api_exporter_mutuelle_diamex(request, paiement_id):
    """
    API pour exporter un paiement de mutuelle santé vers DiameX
    Crée des lignes dans DiameXTemporaire avec les libellés Charge AMIT ou Charge OSIEFSoVa
    """
    try:
        paiement = get_object_or_404(PaiementMutuelleSante, id=paiement_id)

        if paiement.statut == 'brouillon':
            return JsonResponse({
                'success': False,
                'error': 'Le paiement doit être validé avant export'
            }, status=400)

        if paiement.statut == 'exporte':
            return JsonResponse({
                'success': False,
                'error': 'Ce paiement a déjà été exporté'
            }, status=400)

        if not paiement.facture_generee:
            return JsonResponse({
                'success': False,
                'error': 'La facture doit être générée avant export'
            }, status=400)

        # Récupérer les détails par mutuelle
        details_amit = paiement.details.filter(mutuelle='AMIT')
        details_osiefsova = paiement.details.filter(mutuelle='OSIEFSoVa')

        lignes_creees = 0
        erreurs = []

        # Export AMIT
        if details_amit.exists() and paiement.montant_total_amit > 0:
            try:
                # Récupérer le compte depuis le poste (compte_cnaps_fmfp_sante)
                # On utilise le premier employé pour trouver le compte
                premier_employe_amit = details_amit.first().employe
                compte_code = None

                if premier_employe_amit and premier_employe_amit.poste and premier_employe_amit.poste.compte_cnaps_fmfp_sante:
                    compte_code = premier_employe_amit.poste.compte_cnaps_fmfp_sante.compte

                if not compte_code:
                    erreurs.append("AMIT: Compte CNAPS/FMFP/Santé non défini pour le poste")
                else:
                    # Créer la ligne DiameX pour AMIT
                    # Format Description: "Charge AMIT {Organisation} T{Trimestre}/{Année}"
                    description = f"Charge AMIT {paiement.organisation.nom_organisation} T{paiement.trimestre}/{paiement.annee}"

                    ligne_amit = DiameXTemporaire.objects.create(
                        description=description,
                        compte_code=compte_code,
                        montant_out=paiement.montant_total_amit,
                        date_mouvement=None,  # À définir lors de l'export final
                        info='Hydria Mutuelle Santé',
                        type_operation='depense',
                        statut='en_attente',
                        paiement_mutuelle_sante=paiement
                    )

                    lignes_creees += 1

            except Exception as e:
                erreurs.append(f"AMIT: {str(e)}")

        # Export OSIEFSoVa
        if details_osiefsova.exists() and paiement.montant_total_osiefsova > 0:
            try:
                # Récupérer le compte depuis le poste
                premier_employe_osiefsova = details_osiefsova.first().employe
                compte_code = None

                if premier_employe_osiefsova and premier_employe_osiefsova.poste and premier_employe_osiefsova.poste.compte_cnaps_fmfp_sante:
                    compte_code = premier_employe_osiefsova.poste.compte_cnaps_fmfp_sante.compte

                if not compte_code:
                    erreurs.append("OSIEFSoVa: Compte CNAPS/FMFP/Santé non défini pour le poste")
                else:
                    # Créer la ligne DiameX pour OSIEFSoVa
                    description = f"Charge OSIEFSoVa {paiement.organisation.nom_organisation} T{paiement.trimestre}/{paiement.annee}"

                    ligne_osiefsova = DiameXTemporaire.objects.create(
                        description=description,
                        compte_code=compte_code,
                        montant_out=paiement.montant_total_osiefsova,
                        date_mouvement=None,
                        info='Hydria Mutuelle Santé',
                        type_operation='depense',
                        statut='en_attente',
                        paiement_mutuelle_sante=paiement
                    )

                    lignes_creees += 1

            except Exception as e:
                erreurs.append(f"OSIEFSoVa: {str(e)}")

        if lignes_creees > 0:
            # Marquer comme exporté
            paiement.statut = 'exporte'
            paiement.save()

        message = f'{lignes_creees} ligne(s) exportée(s) vers DiameX'
        if erreurs:
            message += f' (avec {len(erreurs)} erreur(s))'

        return JsonResponse({
            'success': lignes_creees > 0,
            'message': message,
            'nb_lignes': lignes_creees,
            'erreurs': erreurs
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_enregistrer_diamex_mutuelle(request, paiement_id):
    """
    API pour enregistrer les numéros DiameX récupérés depuis Access
    L'ID et Prog récupérés sont stockés dans DiameXSante et BaseDiameXSante
    """
    try:
        data = json.loads(request.body)
        paiement = get_object_or_404(PaiementMutuelleSante, id=paiement_id)

        # Numéros DiameX AMIT
        numero_diamex_amit = data.get('numero_diamex_amit', '').strip()
        base_diamex_amit = data.get('base_diamex_amit', '').strip()

        # Numéros DiameX OSIEFSoVa
        numero_diamex_osiefsova = data.get('numero_diamex_osiefsova', '').strip()
        base_diamex_osiefsova = data.get('base_diamex_osiefsova', '').strip()

        # Mettre à jour le paiement
        if numero_diamex_amit:
            paiement.numero_diamex_amit = numero_diamex_amit
        if base_diamex_amit:
            paiement.base_diamex_amit = base_diamex_amit

        if numero_diamex_osiefsova:
            paiement.numero_diamex_osiefsova = numero_diamex_osiefsova
        if base_diamex_osiefsova:
            paiement.base_diamex_osiefsova = base_diamex_osiefsova

        paiement.save()

        return JsonResponse({
            'success': True,
            'message': 'Numéros DiameX enregistrés avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
