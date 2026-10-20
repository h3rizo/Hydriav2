from decimal import Decimal, InvalidOperation
import datetime

from django import template
from django.core.exceptions import ObjectDoesNotExist

register = template.Library()


def _coerce_decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

@register.simple_tag
def make_date(day, month, year):
    """
    Crée un objet datetime.date à partir du jour, du numéro du mois et de l'année.
    Utilisé comme tag : {% make_date jour mois_data.numero annee %}
    """
    if day is None or month is None or year is None:
        return None

    try:
        # Assurez-vous que les valeurs sont des entiers valides
        day_int = int(day)
        month_int = int(month)
        year_int = int(year)
        return datetime.date(year_int, month_int, day_int)
    except (ValueError, TypeError):
        return None
    

@register.filter(name='intcomma')
def intcomma(value):
    """
    Formate un nombre avec des séparateurs de milliers (espaces).
    Exemple: 1234567 -> 1 234 567
    """
    try:
        value = int(value)
        return f"{value:,}".replace(',', ' ')
    except (ValueError, TypeError):
        return value


@register.filter(name='intcomma_zero_blank')
def intcomma_zero_blank(value):
    """
    Formate un entier avec separateur de milliers mais masque les valeurs egales a 0.
    """
    numeric_value = _coerce_decimal(value)
    if numeric_value is not None:
        if numeric_value == 0:
            return ''
        return intcomma(int(numeric_value))
    return value


@register.filter(name='float0_zero_blank')
def float0_zero_blank(value):
    """
    Formate un nombre sans decimales avec separateur de milliers, mais masque les 0.
    """
    numeric_value = _coerce_decimal(value)
    if numeric_value is None:
        return value
    if numeric_value == 0:
        return ''
    formatted = f"{numeric_value:,.0f}"
    return formatted.replace(',', ' ')


@register.filter(name='percent_zero_blank')
def percent_zero_blank(value):
    """
    Retourne un pourcentage entier et masque les 0.
    """
    numeric_value = _coerce_decimal(value)
    if numeric_value is None:
        return value
    if numeric_value == 0:
        return ''
    return f"{int(numeric_value)}%"

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Récupère un élément d'un dictionnaire par sa clé.
    Utilisé pour accéder à dictionary[key] dans les templates.
    Exemple: {{ my_dict|get_item:my_key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def sum_quantite(paiements):
    """Calcule la somme des champs 'quantite' d'une liste de paiements."""
    # Assurez-vous que 'quantite' est un float ou peut être converti
    return sum(float(p.get('quantite', 0) or 0) for p in paiements)


@register.filter
def join_idxls(paiements):
    """Joint les champs 'idxls' (points d'eau) d'une liste de paiements en une seule chaîne."""
    # Sépare les idxls par une virgule et tronque si la liste est très longue
    idxl_list = [str(p.get('idxls', '')) for p in paiements]
    joined = ', '.join(idxl_list)
    return joined if len(joined) < 30 else joined[:27] + '...' # Troncature pour l'affichage


@register.filter
def check_paye(paiements):
    """Vérifie si tous les paiements du groupe sont payés (pour la couleur de la carte)."""
    # Retourne True si TOUS les paiements sont marqués comme 'paye'
    # S'il y en a au moins un qui n'est pas payé, la carte sera marquée 'non-paye' (False)
    return all(p.get('paye', False) for p in paiements)


@register.filter
def get_nested_attribute(obj, attr_string):
    """
    Accède à un attribut imbriqué en toute sécurité, gérant les méthodes 
    (comme .all) et les indexations (comme .0).
    Exemple d'utilisation : |get_nested_attribute:"pointeau_set.all.0.parcelle.commune"
    """
    attrs = attr_string.split('.')
    current = obj
    
    for attr in attrs:
        try:
            # Gérer l'indexation (e.g., '.0' ou '.1')
            if attr.isdigit():
                index = int(attr)
                if isinstance(current, (list, tuple)):
                    current = current[index]
                elif hasattr(current, '__getitem__'): # Peut-être une QuerySet qui supporte l'indexation
                    current = current[index]
                else:
                    return None
            
            # Gérer l'appel de méthode (e.g., '.all')
            elif hasattr(current, attr) and callable(getattr(current, attr)):
                current = getattr(current, attr)()
            
            # Gérer les attributs simples (relation ou champ)
            else:
                current = getattr(current, attr)
                
            if current is None:
                return None
        except (AttributeError, IndexError, TypeError, ObjectDoesNotExist):
            # Si un attribut ou index n'existe pas, on arrête et retourne None
            return None
            
    return current

# N'oubliez pas le filtre de couleur :
@register.filter
def get_commune_color(commune_name):
    # ... (Le code de ce filtre reste le même que dans la réponse précédente)
    import hashlib
    if not commune_name or commune_name == "N/D": return '#aaaaaa' 
    hash_object = hashlib.sha1(commune_name.encode('utf-8'))
    hex_dig = hash_object.hexdigest()
    return '#' + hex_dig[:6]


@register.filter
def get_day_of_week(date_obj):
    """
    Retourne le nom du jour de la semaine (e.g., 'Samedi' ou un index pour la vérification).
    (L'implémentation exacte dépend de votre logique).
    """
    if date_obj is None:
        return None
    
    # Exemple simple (si vous utilisez le module datetime)
    # 0 = Lundi, 6 = Dimanche
    # return date_obj.weekday() 
    
    # Si vous voulez le nom du jour :
    jours = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    return jours[date_obj.weekday()]

# Le filtre 'is_weekend' doit aussi exister et utiliser le résultat de 'get_day_of_week' :
@register.filter
def is_weekend(day_name):
    """Vérifie si le jour est un samedi ou un dimanche."""
    return day_name in ['Samedi', 'Dimanche'] 
    # Ou si get_day_of_week retourne un index :
    # return day_index in [5, 6]


@register.filter
def is_ferie(date_obj, jours_feries_list):
    """
    Vérifie si date_obj est présent dans la liste des jours fériés fournie.
    """
    if date_obj is None or jours_feries_list is None:
        return False
        
    # La vérification se fait sur le format de date (date_obj doit être comparable aux éléments de la liste)
    # Si jours_feries_list contient des objets date:
    return date_obj in jours_feries_list

    # Si jours_feries_list contient des chaînes de caractères (ex: '2025-01-01'):
    # return date_obj.strftime('%Y-%m-%d') in jours_feries_list
@register.filter(name='multiply')
def multiply(value, arg):
    """Multiplie la valeur par l'argument."""
    try:
        val = _coerce_decimal(value)
        a = _coerce_decimal(arg)
        if val is not None and a is not None:
            return val * a
    except Exception:
        return 0
    return 0
