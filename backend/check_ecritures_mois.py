#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Vérifier la répartition des écritures par mois"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models_partie_double import EcriturePartieDouble
from django.db.models import Count
from django.db.models.functions import TruncMonth

ecritures_par_mois = EcriturePartieDouble.objects.annotate(
    mois=TruncMonth('date')
).values('mois').annotate(total=Count('id')).order_by('mois')

print('=== REPARTITION PAR MOIS ===')
for em in ecritures_par_mois:
    if em['mois']:
        print(f"{em['mois'].strftime('%Y-%m')}: {em['total']} ecritures")
    else:
        print(f"NULL: {em['total']} ecritures")

print(f'\nTotal: {EcriturePartieDouble.objects.count()} ecritures')
