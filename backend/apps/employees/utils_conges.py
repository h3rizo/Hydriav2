"""
Fonctions utilitaires pour la gestion des conges et absences
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import DatabaseError, OperationalError, ProgrammingError


DEFAULT_JOURS_FERIES = {
    2025: [
        (date(2025, 1, 1), "Jour de l'An"),
        (date(2025, 3, 29), "Commemoration des martyrs de 1947"),
        (date(2025, 3, 31), "Lundi de Paques"),
        (date(2025, 5, 1), "Fete du Travail"),
        (date(2025, 5, 19), "Lundi de Pentecote"),
        (date(2025, 6, 26), "Fete de l'Independance"),
        (date(2025, 8, 15), "Assomption"),
        (date(2025, 11, 1), "Toussaint"),
        (date(2025, 12, 25), "Noel"),
    ],
    2026: [
        (date(2026, 1, 1), "Jour de l'An"),
        (date(2026, 3, 20), "Jour ferie exceptionnel"),
        (date(2026, 3, 29), "Commemoration des martyrs de 1947"),
        (date(2026, 4, 6), "Lundi de Paques"),
        (date(2026, 5, 1), "Fete du Travail"),
        (date(2026, 5, 14), "Ascension"),
        (date(2026, 5, 25), "Lundi de Pentecote"),
        (date(2026, 5, 27), "Aid-el-filtr"),
        (date(2026, 6, 26), "Fete de l'Independance"),
        (date(2026, 8, 15), "Assomption"),
        (date(2026, 11, 1), "Toussaint"),
        (date(2026, 12, 25), "Noel"),
    ],
}


def _get_default_records_for_year(annee):
        return [
            {
                'id': None,
                'date': holiday_date,
                'nom': holiday_name,
                'description': '',
                'actif': True,
                'type_jour': 'officiel',
            }
        for holiday_date, holiday_name in DEFAULT_JOURS_FERIES.get(annee, [])
    ]


def get_jours_feries_records(annee):
    """
    Retourne les jours feries d'une annee avec leurs metadonnees.

    Priorite:
    1. Base de donnees (CRUD utilisateur)
    2. Fallback interne si la table n'existe pas encore
    """
    try:
        from .models_conges import JourFerie

        records = list(
            JourFerie.objects.filter(
                actif=True,
                date__year=annee,
            )
            .order_by('date')
            .values('id', 'date', 'nom', 'description', 'actif', 'type_jour')
        )
        if records:
            return records
    except (DatabaseError, OperationalError, ProgrammingError):
        pass
    except Exception:
        pass

    return _get_default_records_for_year(annee)


def get_jours_feries(annee):
    """
    Retourne la liste des jours feries pour une annee donnee.
    """
    return [record['date'] for record in get_jours_feries_records(annee)]


def get_jour_ferie_label(date_obj):
    """
    Retourne le nom du jour ferie pour une date donnee.
    """
    if not date_obj:
        return 'Jour ferie'

    for record in get_jours_feries_records(date_obj.year):
        if record['date'] == date_obj:
            return record['nom'] or 'Jour ferie'
    return 'Jour ferie'


def est_jour_ferie(date_obj):
    """
    Verifie si une date est un jour ferie.
    """
    if not date_obj:
        return False
    return date_obj in get_jours_feries(date_obj.year)


def get_type_jour_ferie(date_obj):
    """
    Retourne le type d'un jour ferie ('officiel' ou 'decret') pour une date donnee.
    Retourne None si la date n'est pas un jour ferie.
    """
    if not date_obj:
        return None
    for record in get_jours_feries_records(date_obj.year):
        if record['date'] == date_obj:
            return record.get('type_jour') or 'officiel'
    return None


def est_weekend(date_obj):
    """
    Verifie si une date tombe un weekend (samedi ou dimanche)
    """
    return date_obj.weekday() in [5, 6]


def est_journalier(employe):
    """
    Verifie si un employe a un contrat de type journalier
    """
    contrat = employe.contrats.filter(fin_contrat__isnull=True).first()

    if not contrat:
        return False

    return contrat.type_contrat == 'journalier'


def valider_dates_repos(employe, date_debut, date_fin):
    """
    Valide que les dates de repos respectent les regles selon le type de contrat.
    """
    if est_journalier(employe):
        return True

    current_date = date_debut
    while current_date <= date_fin:
        if not est_weekend(current_date):
            raise ValueError(
                f"Pour les employes non-journaliers, les repos ne peuvent etre places "
                f"que le samedi ou le dimanche. La date {current_date.strftime('%d/%m/%Y')} "
                f"n'est pas autorisee."
            )
        current_date += timedelta(days=1)

    return True


def valider_dates_jour_ferie(date_debut, date_fin):
    """
    Valide que les dates sont bien des jours feries officiels.
    """
    current_date = date_debut
    while current_date <= date_fin:
        if not est_jour_ferie(current_date):
            raise ValueError(
                f"La date {current_date.strftime('%d/%m/%Y')} n'est pas un jour ferie officiel. "
                f"Les jours feries ne peuvent etre places que sur des dates officielles."
            )
        current_date += timedelta(days=1)

    return True


def calculer_nb_jours(date_debut, date_fin, est_demi_journee=False):
    """
    Calcule le nombre de jours entre deux dates avec support des demi-journees
    """
    nb_jours_total = (date_fin - date_debut).days + 1

    if est_demi_journee:
        return Decimal('0.5')
    return Decimal(str(nb_jours_total))
