"""
Export des paiements CNaPS/FMFP vers DiameXTemporaire
Similaire au workflow IRSA mais avec 2 lignes par employé (CNaPS + FMFP)
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal
import math

from .models import PaiementCNaPSFMFP
from apps.accounting.models import DiameXTemporaire


@login_required
@require_http_methods(["POST"])
def api_marquer_cnaps_fmfp_imprime(request, paiement_id):
    """Marque le paiement CNaPS/FMFP comme imprimé et exporte vers DiameXTemporaire"""
    try:
        paiement = PaiementCNaPSFMFP.objects.select_related('organisation').get(id=paiement_id)
        
        # Vérifier les droits
        if hasattr(request.user, 'employe') and request.user.employe:
            if request.user.employe.base and request.user.employe.base.organisation:
                if paiement.organisation != request.user.employe.base.organisation:
                    return JsonResponse({
                        'success': False,
                        'error': 'Vous n\'avez pas accès à ce paiement'
                    }, status=403)
        
        # Vérifier que la facture a été générée
        if not paiement.facture_generee:
            return JsonResponse({
                'success': False,
                'error': 'La facture doit d\'abord être générée avant de marquer comme imprimée'
            }, status=400)
        
        # Marquer comme imprimé
        paiement.facture_imprimee = True
        paiement.date_impression = timezone.now()
        paiement.save()
        
        # Exporter vers DiameXTemporaire
        details = paiement.details.select_related('employe', 'employe__poste').all()
        
        nb_exportes = 0
        erreurs = []
        
        trimestre_labels = {1: '1er trimestre', 2: '2e trimestre', 3: '3e trimestre', 4: '4e trimestre'}
        periode_label = f"{trimestre_labels[paiement.trimestre]} {paiement.annee}"
        
        for detail in details:
            employe = detail.employe
            poste = employe.poste if employe else None

            # Validation préalable : vérifier que le poste et le compte existent
            if not employe:
                erreurs.append(f"Détail {detail.id}: Aucun employé associé")
                continue

            if not poste:
                erreurs.append(f"{detail.employe_nom_complet}: Aucun poste assigné (requis pour compte CNaPS/FMFP)")
                continue

            if not hasattr(poste, 'compte_cnaps_fmfp_sante') or not poste.compte_cnaps_fmfp_sante:
                erreurs.append(f"{detail.employe_nom_complet} ({poste.nom_poste}): Compte CNaPS/FMFP non défini pour ce poste")
                continue

            # Préfixe du poste pour la description
            prefixe_poste = poste.prefixe_designation if hasattr(poste, 'prefixe_designation') else ''

            # === LIGNE CNaPS ===
            try:
                # Créer la description : _[Préfixe] [Nom complet]_Charge CNaPS_[Période]
                description_cnaps = f"_{prefixe_poste} {detail.employe_nom_complet}_Charge CNaPS_{periode_label}"

                # Montant CNaPS (pas d'arrondi)
                montant_cnaps = detail.total_cnaps

                # Créer la ligne DiameX CNaPS
                DiameXTemporaire.objects.create(
                    description=description_cnaps,
                    compte_code=poste.compte_cnaps_fmfp_sante.compte,
                    detail=employe.surnom if hasattr(employe, 'surnom') and employe.surnom else employe.prenom,
                    activ=employe.volet if hasattr(employe, 'volet') and employe.volet else '',
                    montant_out=montant_cnaps,
                    date_m=paiement.date_paiement,
                    info='Hydria CNaPS',
                    type_transaction='depense',
                    statut='en_attente',
                    paiement_cnaps_fmfp=paiement
                )
                nb_exportes += 1

            except Exception as e:
                erreurs.append(f"{detail.employe_nom_complet} CNaPS: {str(e)}")

            # === LIGNE FMFP ===
            try:
                # Créer la description : _[Préfixe] [Nom complet]_Charge FMFP_[Période]
                description_fmfp = f"_{prefixe_poste} {detail.employe_nom_complet}_Charge FMFP_{periode_label}"

                # Montant FMFP (pas d'arrondi)
                montant_fmfp = detail.total_fmfp

                # Créer la ligne DiameX FMFP
                DiameXTemporaire.objects.create(
                    description=description_fmfp,
                    compte_code=poste.compte_cnaps_fmfp_sante.compte,
                    detail=employe.surnom if hasattr(employe, 'surnom') and employe.surnom else employe.prenom,
                    activ=employe.volet if hasattr(employe, 'volet') and employe.volet else '',
                    montant_out=montant_fmfp,
                    date_m=paiement.date_paiement,
                    info='Hydria FMFP',
                    type_transaction='depense',
                    statut='en_attente',
                    paiement_cnaps_fmfp=paiement
                )
                nb_exportes += 1

            except Exception as e:
                erreurs.append(f"{detail.employe_nom_complet} FMFP: {str(e)}")
        
        message = f"{paiement.details.count()} employé(s), {nb_exportes} ligne(s) exportée(s) vers DiameX"
        if erreurs:
            message += f", {len(erreurs)} erreur(s)"
        
        return JsonResponse({
            'success': True,
            'message': message,
            'nb_employes': paiement.details.count(),
            'nb_exportes': nb_exportes,
            'erreurs': erreurs
        })
        
    except PaiementCNaPSFMFP.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement CNaPS/FMFP introuvable'
        }, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
