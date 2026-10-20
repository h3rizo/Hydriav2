"""
Vues pour la gestion de l'impression des fiches de paie et export vers DiameX
"""
import json
import math
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Salaire
from apps.accounting.models import DiameXTemporaire


@csrf_exempt
@require_http_methods(["POST"])
def api_marquer_fiches_imprimees(request):
    """
    API pour marquer les fiches de paie comme imprimées et exporter vers DiameXTemporaire.

    Format attendu:
    {
        "salaire_ids": ["uuid1", "uuid2", ...],
        "mois": 1,
        "annee": 2025
    }

    Pour chaque salaire:
    1. Marque la fiche comme imprimée
    2. Crée une ligne dans DiameXTemporaire avec:
       - Description: [Préfixe du poste] [Nom complet]_Salaire_[Année] [Mois en 00]
       - compte_code (Cat): Compte salaire du poste
       - detail: Surnom de l'employé
       - activ: Volet de l'employé
       - montant_out: Salaire net arrondi
    """
    try:
        data = json.loads(request.body)
        salaire_ids = data.get('salaire_ids', [])
        mois = data.get('mois')
        annee = data.get('annee')

        if not salaire_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucun salaire fourni'
            }, status=400)

        if not mois or not annee:
            return JsonResponse({
                'success': False,
                'error': 'Mois et année requis'
            }, status=400)

        # Récupérer les salaires avec toutes les relations nécessaires
        salaires = Salaire.objects.filter(
            id__in=salaire_ids,
            fiche_imprimee=False  # Ne traiter que les fiches non imprimées
        ).select_related(
            'grille_salaire__contrat__employe__poste',
            'grille_salaire__contrat__employe__poste__compte_salaire'
        )

        nb_imprimes = 0
        nb_exportes = 0
        erreurs = []

        for salaire in salaires:
            try:
                # Récupérer les informations de l'employé
                employe = salaire.grille_salaire.contrat.employe
                poste = employe.poste

                # Validation: le poste doit avoir un compte_salaire
                if not poste or not poste.compte_salaire:
                    erreurs.append(f"{employe.nom_complet}: Pas de compte salaire défini pour le poste")
                    continue

                # Calcul du salaire net arrondi (arrondi supérieur à 100 Ar)
                salaire_net = salaire.salaire_net_paye if salaire.salaire_net_paye else Decimal('0')
                salaire_net_arrondi = Decimal(math.ceil(float(salaire_net) / 100) * 100)

                # Construction de la description
                # Format: _[Préfixe du poste] [Nom complet]_Salaire_[Année] [Mois en 00][_Prorata si applicable]
                prefixe = poste.prefixe if poste.prefixe else ''
                nom_complet = employe.nom_complet
                mois_format = f"{mois:02d}"

                # Vérifier si calcul au prorata
                est_prorata = salaire.grille_salaire.est_prorata if salaire.grille_salaire else False
                prorata_suffix = "_Prorata" if est_prorata else ""

                # Précéder la description par un underscore
                description = f"_{prefixe} {nom_complet}_Salaire_{annee} {mois_format}{prorata_suffix}"

                # Créer la ligne DiameXTemporaire
                DiameXTemporaire.objects.create(
                    salaire=salaire,  # Lien vers le salaire source
                    type_transaction='depense',  # Les salaires sont des dépenses
                    description=description,
                    compte_code=poste.compte_salaire.compte,  # Cat - utilise le champ 'compte' et non 'code_compte'
                    detail=employe.surnom if employe.surnom else employe.prenom,  # Detail
                    activ=employe.volet if employe.volet else '',  # ACTIV
                    montant_out=float(salaire_net_arrondi),  # Out
                    date_m=salaire.date_paiement,  # Date du mouvement
                    date_rec=salaire.date_paiement,  # Date de paiement dans dateRec
                    info='Hydria Salaires',  # Info fixe pour les salaires
                    statut='en_attente'  # En attente de validation
                )
                nb_exportes += 1

                # Marquer la fiche comme imprimée
                salaire.fiche_imprimee = True
                salaire.date_impression = timezone.now()
                salaire.save()
                nb_imprimes += 1

            except Exception as e:
                erreurs.append(f"{employe.nom_complet if employe else 'Inconnu'}: {str(e)}")

        message = f"{nb_imprimes} fiche(s) marquée(s) comme imprimée(s), {nb_exportes} ligne(s) exportée(s) vers DiameX"
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
