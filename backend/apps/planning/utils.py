"""
Utilitaires pour la gestion des plannings
"""
from django.utils import timezone
from .models import PlanningDetail


def generer_numero_bon(type_bon='livraison'):
    """
    Génère automatiquement un numéro de bon unique

    Args:
        type_bon (str): Type de bon - 'livraison', 'avance' ou 'facture'

    Returns:
        str: Numéro de bon au format TYPE-YYYY-NNN (ex: BL-2025-001)
    """
    # Définir le préfixe selon le type
    prefixes = {
        'livraison': 'BL',
        'avance': 'BA',
        'facture': 'F'
    }

    prefix = prefixes.get(type_bon, 'DOC')
    annee = timezone.now().year

    # Trouver le dernier numéro pour ce type et cette année
    field_name = f'numero_bon_{type_bon}' if type_bon in ['livraison', 'avance'] else 'numero_facture'

    # Filtre pour les bons de l'année en cours
    pattern = f'{prefix}-{annee}-%'

    derniers_bons = PlanningDetail.objects.filter(
        **{f'{field_name}__startswith': f'{prefix}-{annee}-'}
    ).values_list(field_name, flat=True).order_by(f'-{field_name}')

    # Pour les factures, vérifier aussi dans la table Releve
    dernier_numero = 0
    if type_bon == 'facture':
        from apps.billing.models import Releve

        # Chercher dans PlanningDetail
        if derniers_bons.exists():
            dernier_bon = derniers_bons.first()
            if dernier_bon:
                try:
                    parts = dernier_bon.split('-')
                    if len(parts) == 3:
                        dernier_numero = int(parts[2])
                except (ValueError, IndexError):
                    pass

        # Chercher aussi dans Releve
        derniers_releves = Releve.objects.filter(
            numero_facture__startswith=f'{prefix}-{annee}-'
        ).values_list('numero_facture', flat=True).order_by('-numero_facture')

        if derniers_releves.exists():
            dernier_releve = derniers_releves.first()
            if dernier_releve:
                try:
                    parts = dernier_releve.split('-')
                    if len(parts) == 3:
                        numero_releve = int(parts[2])
                        dernier_numero = max(dernier_numero, numero_releve)
                except (ValueError, IndexError):
                    pass
    else:
        # Pour les autres types, seulement PlanningDetail
        if derniers_bons.exists():
            dernier_bon = derniers_bons.first()
            if dernier_bon:
                try:
                    parts = dernier_bon.split('-')
                    if len(parts) == 3:
                        dernier_numero = int(parts[2])
                except (ValueError, IndexError):
                    pass

    # Incrémenter
    nouveau_numero = dernier_numero + 1

    # Formater avec zéro padding (3 chiffres)
    return f'{prefix}-{annee}-{nouveau_numero:03d}'
