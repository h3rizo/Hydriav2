from django.db import models
from apps.core.models import Base
from apps.employees.models import Employe
import uuid


# Import des modèles depuis l'app inventory qui les définit déjà
from apps.inventory.models import Category, Product, Stock, StockMovement


# Import du modèle Designation depuis planning
from apps.planning.models import Designation