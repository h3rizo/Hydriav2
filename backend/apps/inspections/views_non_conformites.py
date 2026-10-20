"""
Vues et APIs pour la gestion des non-conformités détaillées lors des inspections.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework import status as http_status
from django.http import JsonResponse
import json

from .models import NonConformite, ResultatInspectionComposant


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def api_creer_non_conformite(request):
    """
    API pour créer une non-conformité détaillée suite à un point de contrôle non conforme.

    Données attendues:
    - resultat_inspection_id: UUID du ResultatInspectionComposant
    - narratif_probleme: Description détaillée du problème
    - solution_detaillee: Solution proposée avec détails
    - materiaux_necessaires: Liste JSON des matériaux [{designation, quantite, unite}]
    - besoin_superviseur: Boolean
    - niveau_solution: mpikojakoja|st|social|projet
    - priorite: basse|moyenne|haute
    - echeance: immediat|3_mois|6_mois
    - cout_estime: Decimal (optionnel)
    """
    try:
        # Récupérer les données
        data = request.data
        resultat_id = data.get('resultat_inspection_id')

        if not resultat_id:
            return Response({
                'error': 'ID du résultat d\'inspection requis'
            }, status=http_status.HTTP_400_BAD_REQUEST)

        # Vérifier que le résultat existe
        try:
            resultat = ResultatInspectionComposant.objects.get(id=resultat_id)
        except ResultatInspectionComposant.DoesNotExist:
            return Response({
                'error': 'Résultat d\'inspection non trouvé'
            }, status=http_status.HTTP_404_NOT_FOUND)

        # Vérifier que le résultat est non conforme
        if resultat.conforme is True:
            return Response({
                'error': 'Impossible de créer une non-conformité pour un point conforme'
            }, status=http_status.HTTP_400_BAD_REQUEST)

        # Parser les matériaux (JSON)
        materiaux = data.get('materiaux_necessaires', [])
        if isinstance(materiaux, str):
            try:
                materiaux = json.loads(materiaux)
            except:
                materiaux = []

        # Gérer le boolean besoin_superviseur
        besoin_superviseur = data.get('besoin_superviseur', False)
        if isinstance(besoin_superviseur, str):
            besoin_superviseur = besoin_superviseur.lower() in ['true', '1', 'yes', 'oui']

        # Créer la non-conformité
        non_conformite = NonConformite.objects.create(
            resultat_inspection=resultat,
            narratif_probleme=data.get('narratif_probleme', ''),
            solution_detaillee=data.get('solution_detaillee', ''),
            materiaux_necessaires=materiaux,
            besoin_superviseur=besoin_superviseur,
            niveau_solution=data.get('niveau_solution', 'mpikojakoja'),
            priorite=data.get('priorite', 'moyenne'),
            echeance=data.get('echeance', '3_mois'),
            cout_estime=data.get('cout_estime') if data.get('cout_estime') else None,
            creee_par=request.user
        )

        # Générer automatiquement une action corrective
        action = non_conformite.generer_action_corrective()

        return Response({
            'success': True,
            'message': 'Non-conformité créée avec succès',
            'non_conformite_id': str(non_conformite.id),
            'action_corrective_id': str(action.id) if action else None
        })

    except Exception as e:
        import traceback
        return Response({
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=http_status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_get_non_conformite(request, resultat_id):
    """
    API pour récupérer les détails d'une non-conformité par son resultat_inspection_id.
    """
    try:
        non_conformite = NonConformite.objects.get(resultat_inspection_id=resultat_id)

        return Response({
            'success': True,
            'non_conformite': {
                'id': str(non_conformite.id),
                'narratif_probleme': non_conformite.narratif_probleme,
                'solution_detaillee': non_conformite.solution_detaillee,
                'materiaux_necessaires': non_conformite.materiaux_necessaires,
                'besoin_superviseur': non_conformite.besoin_superviseur,
                'niveau_solution': non_conformite.niveau_solution,
                'niveau_solution_display': non_conformite.get_niveau_solution_display(),
                'priorite': non_conformite.priorite,
                'priorite_display': non_conformite.get_priorite_display(),
                'echeance': non_conformite.echeance,
                'echeance_display': non_conformite.get_echeance_display(),
                'cout_estime': float(non_conformite.cout_estime) if non_conformite.cout_estime else None,
                'date_creation': non_conformite.date_creation.isoformat(),
            }
        })
    except NonConformite.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Non-conformité non trouvée'
        }, status=http_status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=http_status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@permission_classes([permissions.AllowAny])
def api_update_non_conformite(request, non_conformite_id):
    """
    API pour mettre à jour une non-conformité existante.
    """
    try:
        non_conformite = NonConformite.objects.get(id=non_conformite_id)

        # Mettre à jour les champs fournis
        data = request.data

        if 'narratif_probleme' in data:
            non_conformite.narratif_probleme = data['narratif_probleme']

        if 'solution_detaillee' in data:
            non_conformite.solution_detaillee = data['solution_detaillee']

        if 'materiaux_necessaires' in data:
            materiaux = data['materiaux_necessaires']
            if isinstance(materiaux, str):
                try:
                    materiaux = json.loads(materiaux)
                except:
                    materiaux = []
            non_conformite.materiaux_necessaires = materiaux

        if 'besoin_superviseur' in data:
            besoin_superviseur = data['besoin_superviseur']
            if isinstance(besoin_superviseur, str):
                besoin_superviseur = besoin_superviseur.lower() in ['true', '1', 'yes', 'oui']
            non_conformite.besoin_superviseur = besoin_superviseur

        if 'niveau_solution' in data:
            non_conformite.niveau_solution = data['niveau_solution']

        if 'priorite' in data:
            non_conformite.priorite = data['priorite']

        if 'echeance' in data:
            non_conformite.echeance = data['echeance']

        if 'cout_estime' in data:
            non_conformite.cout_estime = data['cout_estime'] if data['cout_estime'] else None

        non_conformite.save()

        return Response({
            'success': True,
            'message': 'Non-conformité mise à jour avec succès'
        })

    except NonConformite.DoesNotExist:
        return Response({
            'error': 'Non-conformité non trouvée'
        }, status=http_status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=http_status.HTTP_400_BAD_REQUEST)
