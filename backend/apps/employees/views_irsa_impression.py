"""
Vues pour la gestion de l'impression des factures IRSA et export vers DiameX
"""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import PaiementIRSA, PaiementIRSADetail
from apps.accounting.models import DiameXTemporaire


@csrf_exempt
@require_http_methods(["POST"])
def api_marquer_irsa_imprime(request):
    """
    API pour marquer les factures IRSA comme imprimées et exporter vers DiameXTemporaire.

    Format attendu:
    {
        "paiement_ids": ["uuid1", "uuid2", ...],
        "mois": 1,
        "annee": 2025
    }

    Pour chaque paiement IRSA:
    1. Marque la facture comme imprimée
    2. Pour chaque détail (employé), crée une ligne dans DiameXTemporaire avec:
       - Description: [Préfixe du poste] [Nom complet]_IRSA_[Année] [Mois en 00]
       - compte_code (Cat): Compte IRSA du poste
       - detail: Surnom de l'employé
       - activ: Volet de l'employé
       - montant_out: Montant IRSA exact (SANS arrondi)
       - date_m: Date de paiement IRSA
    """
    try:
        data = json.loads(request.body)
        paiement_ids = data.get('paiement_ids', [])
        mois = data.get('mois')
        annee = data.get('annee')

        if not paiement_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucun paiement IRSA fourni'
            }, status=400)

        if not mois or not annee:
            return JsonResponse({
                'success': False,
                'error': 'Mois et année requis'
            }, status=400)

        # Récupérer les paiements IRSA avec toutes les relations nécessaires
        paiements = PaiementIRSA.objects.filter(
            id__in=paiement_ids,
            facture_imprimee=False  # Ne traiter que les factures non imprimées
        ).prefetch_related('details__salaire__grille_salaire__contrat__employe__poste__compte_irsa')

        nb_imprimes = 0
        nb_exportes = 0
        erreurs = []

        for paiement in paiements:
            try:
                # Récupérer tous les détails IRSA de ce paiement
                details = paiement.details.select_related(
                    'salaire__grille_salaire__contrat__employe',
                    'salaire__grille_salaire__contrat__employe__poste',
                    'salaire__grille_salaire__contrat__employe__poste__compte_irsa'
                ).all()

                for detail in details:
                    try:
                        # Récupérer les informations de l'employé
                        salaire = detail.salaire
                        if not salaire or not salaire.grille_salaire or not salaire.grille_salaire.contrat:
                            erreurs.append(f"{detail.employe_nom_complet}: Données salariales incomplètes")
                            continue

                        employe = salaire.grille_salaire.contrat.employe
                        poste = employe.poste

                        # Validation: le poste doit avoir un compte_irsa
                        if not poste or not poste.compte_irsa:
                            erreurs.append(f"{employe.nom_complet}: Pas de compte IRSA défini pour le poste")
                            continue

                        # Montant IRSA exact (SANS arrondi - contrairement aux salaires)
                        montant_irsa = detail.montant_irsa if detail.montant_irsa else Decimal('0')

                        # Construction de la description
                        # Format: [Préfixe du poste] [Nom complet]_IRSA_[Année] [Mois en 00]
                        prefixe = poste.prefixe if poste.prefixe else ''
                        nom_complet = employe.nom_complet
                        mois_format = f"{mois:02d}"

                        # Précéder la description par un underscore
                        description = f"_{prefixe} {nom_complet}_IRSA_{annee} {mois_format}"

                        # Créer la ligne DiameXTemporaire
                        DiameXTemporaire.objects.create(
                            paiement_irsa=paiement,  # Lien vers le paiement IRSA source
                            type_transaction='depense',  # Les IRSA sont des dépenses
                            description=description,
                            compte_code=poste.compte_irsa.compte,  # Cat - utilise le champ 'compte'
                            detail=employe.surnom if employe.surnom else employe.prenom,  # Detail
                            activ=employe.volet if employe.volet else '',  # ACTIV
                            montant_out=float(montant_irsa),  # Out - montant exact SANS arrondi
                            date_m=paiement.date_paiement,  # Date du mouvement
                            date_rec=paiement.date_paiement,  # Date de paiement dans dateRec
                            info='Hydria IRSA',  # Info fixe pour les IRSA
                            statut='en_attente'  # En attente de validation
                        )
                        nb_exportes += 1

                    except Exception as e:
                        erreurs.append(f"{detail.employe_nom_complet}: {str(e)}")

                # Marquer la facture comme imprimée (après tous les détails)
                paiement.facture_imprimee = True
                paiement.date_impression = timezone.now()
                paiement.save()
                nb_imprimes += 1

            except Exception as e:
                org_nom = paiement.organisation.nom_organisation if paiement.organisation else 'Inconnu'
                erreurs.append(f"{org_nom} ({mois:02d}/{annee}): {str(e)}")

        message = f"{nb_imprimes} facture(s) marquée(s) comme imprimée(s), {nb_exportes} ligne(s) exportée(s) vers DiameX"
        if erreurs:
            message += f" ({len(erreurs)} erreur(s))"

        return JsonResponse({
            'success': True,
            'message': message,
            'nb_imprimes': nb_imprimes,
            'nb_exportes': nb_exportes,
            'erreurs': erreurs
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Format JSON invalide'
        }, status=400)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        }, status=500)
