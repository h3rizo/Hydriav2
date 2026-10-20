"""
Vues pour l'intégration MVola (Mobile Money)
Gère les paiements de factures d'eau via MVola
"""

import json
import logging
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings

from apps.billing.models import Releve

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def initier_paiement_mvola(request):
    """
    Initie un paiement MVola pour une facture d'eau

    POST /api/paiement/mvola/initier/
    Body: {
        "releve_id": "uuid",
        "montant": "12500",
        "numero_mvola": "0341234567"
    }
    """
    try:
        data = json.loads(request.body)
        releve_id = data.get('releve_id')
        montant = data.get('montant')
        numero_mvola = data.get('numero_mvola')

        # Validation des données
        if not all([releve_id, montant, numero_mvola]):
            return JsonResponse({
                'success': False,
                'error': 'Données manquantes'
            }, status=400)

        # Vérifier que le relevé existe et appartient bien à l'utilisateur
        try:
            releve = Releve.objects.select_related(
                'point_eau',
                'point_eau__ouvrage'
            ).get(id=releve_id)

            # Vérifier que l'utilisateur est bien client de ce point d'eau
            if not hasattr(request.user, 'client'):
                return JsonResponse({
                    'success': False,
                    'error': 'Vous devez être connecté en tant que client'
                }, status=403)

            if request.user.client.point_eau_id != releve.point_eau_id:
                return JsonResponse({
                    'success': False,
                    'error': 'Cette facture ne vous appartient pas'
                }, status=403)

            # Vérifier que la facture n'est pas déjà payée
            if releve.numeroDiameX:
                return JsonResponse({
                    'success': False,
                    'error': 'Cette facture est déjà payée'
                }, status=400)

        except Releve.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Facture non trouvée'
            }, status=404)

        # Vérifier que le montant correspond
        montant_decimal = Decimal(str(montant))
        if releve.montant != montant_decimal:
            return JsonResponse({
                'success': False,
                'error': f'Le montant ne correspond pas. Attendu: {releve.montant} Ar'
            }, status=400)

        # TODO: Intégrer avec l'API MVola réelle
        # Pour l'instant, on simule le processus

        # Configuration MVola (à mettre dans settings.py en production)
        MVOLA_API_KEY = getattr(settings, 'MVOLA_API_KEY', None)
        MVOLA_MERCHANT_ID = getattr(settings, 'MVOLA_MERCHANT_ID', None)

        if not MVOLA_API_KEY:
            logger.warning("MVOLA_API_KEY non configurée - mode simulation")

            # Mode simulation pour le développement
            # En production, appeler l'API MVola ici
            transaction_ref = f"MVOLA_{timezone.now().strftime('%Y%m%d%H%M%S')}_{releve_id[:8]}"

            # Enregistrer la tentative de paiement (créer un modèle PaiementMVola si nécessaire)
            logger.info(f"Simulation paiement MVola - Relevé: {releve_id}, Montant: {montant}, Numéro: {numero_mvola}, Ref: {transaction_ref}")

            return JsonResponse({
                'success': True,
                'message': 'Paiement initié avec succès. Veuillez confirmer sur votre téléphone.',
                'transaction_ref': transaction_ref,
                'simulation': True
            })
        else:
            # TODO: Code réel d'intégration MVola API
            # import requests
            #
            # mvola_api_url = "https://api.mvola.mg/v1/payment"
            # headers = {
            #     'Authorization': f'Bearer {MVOLA_API_KEY}',
            #     'Content-Type': 'application/json'
            # }
            # payload = {
            #     'merchant_id': MVOLA_MERCHANT_ID,
            #     'customer_phone': numero_mvola,
            #     'amount': str(montant),
            #     'reference': f"FACTURE_{releve_id}",
            #     'description': f"Facture d'eau du {releve.datereleve.strftime('%d/%m/%Y')}"
            # }
            #
            # response = requests.post(mvola_api_url, json=payload, headers=headers)
            # response_data = response.json()
            #
            # if response.status_code == 200 and response_data.get('status') == 'success':
            #     return JsonResponse({
            #         'success': True,
            #         'message': 'Paiement initié avec succès',
            #         'transaction_ref': response_data.get('transaction_id')
            #     })
            # else:
            #     return JsonResponse({
            #         'success': False,
            #         'error': response_data.get('message', 'Erreur lors de l\'initiation du paiement')
            #     }, status=400)

            pass

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Format JSON invalide'
        }, status=400)
    except Exception as e:
        logger.error(f"Erreur lors de l'initiation du paiement MVola: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Une erreur s\'est produite lors du traitement'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def callback_mvola(request):
    """
    Webhook pour recevoir les confirmations de paiement de MVola

    POST /api/paiement/mvola/callback/

    Ce endpoint sera appelé par MVola pour confirmer le paiement
    """
    try:
        data = json.loads(request.body)

        # Vérifier la signature MVola pour sécuriser le webhook
        # TODO: Implémenter la vérification de signature

        transaction_ref = data.get('transaction_ref')
        status = data.get('status')
        releve_id = data.get('reference', '').replace('FACTURE_', '')

        if status == 'success' and releve_id:
            try:
                releve = Releve.objects.get(id=releve_id)

                # Marquer la facture comme payée
                releve.numeroDiameX = transaction_ref
                releve.baseDiameX = 'MVOLA'
                releve.save()

                logger.info(f"Paiement MVola confirmé - Relevé: {releve_id}, Ref: {transaction_ref}")

                # TODO: Envoyer notification au client
                # TODO: Créer entrée dans DiameXTemporaire si nécessaire

                return JsonResponse({
                    'success': True,
                    'message': 'Paiement confirmé'
                })
            except Releve.DoesNotExist:
                logger.error(f"Relevé non trouvé pour callback MVola: {releve_id}")
                return JsonResponse({
                    'success': False,
                    'error': 'Relevé non trouvé'
                }, status=404)
        else:
            logger.warning(f"Callback MVola avec statut: {status}")
            return JsonResponse({
                'success': False,
                'error': 'Paiement non confirmé'
            }, status=400)

    except Exception as e:
        logger.error(f"Erreur lors du traitement du callback MVola: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Erreur lors du traitement'
        }, status=500)
