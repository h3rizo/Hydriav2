import re

# Lire le fichier services_previsions.py
with open('services_previsions.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fonction correcte calculer_previsions_salaires
new_calculer_salaires = '''def calculer_previsions_salaires(annee, base=None, config=None):
    """Calcule les previsions de salaires pour l'annee entiere."""
    from apps.employees.models import Employe, GrilleSalaire
    from django.db.models import Q

    nb_created = 0
    nb_employes = 0

    employes_qs = Employe.objects.filter(date_debauchage__isnull=True).select_related('poste', 'poste__compte_salaire', 'base')

    if base:
        employes_qs = employes_qs.filter(base=base)

    for employe in employes_qs:
        # Recuperer la derniere grille de salaire pour cet employe
        derniere_grille = GrilleSalaire.objects.filter(
            contrat__employe=employe
        ).order_by('-date_salaire').first()

        if not derniere_grille or not derniere_grille.salaire_net:
            continue

        salaire_net = derniere_grille.salaire_net or Decimal('0')

        if salaire_net == 0:
            continue

        nb_employes += 1

        district_obj = None
        commune_obj = None
        ouvrage_obj = None

        if hasattr(employe, 'organisation') and employe.organisation:
            from apps.billing.models import ModaliteGestion, PointEau

            modalite = ModaliteGestion.objects.filter(gestionnaire=employe.organisation, date_fin__isnull=True).select_related('ouvrage').first()

            if modalite and modalite.ouvrage:
                ouvrage_obj = modalite.ouvrage

                point_eau = PointEau.objects.filter(ouvrage=ouvrage_obj).select_related('parcelle__village__fokontany__commune__district').first()

                if point_eau and point_eau.parcelle:
                    parcelle = point_eau.parcelle
                    if parcelle.village and parcelle.village.fokontany:
                        fokontany = parcelle.village.fokontany
                        if fokontany.commune:
                            commune_obj = fokontany.commune
                            if commune_obj.district:
                                district_obj = commune_obj.district

        for mois in range(1, 13):
            try:
                date_prevision = date(annee, mois, 1)

                base_obj = employe.base if employe.base else None
                activ = base_obj.nom_base if base_obj else 'GLOBAL'

                cat = ''
                if employe.poste and employe.poste.compte_salaire:
                    cat = employe.poste.compte_salaire.code_compte

                prefixe_poste = employe.poste.prefixe_designation if employe.poste else ''
                libelle = f"{prefixe_poste} {employe.nom} {employe.prenom}_Salaire_{annee} {mois:02d}"

                detail_text = employe.surnom if employe.surnom else employe.prenom

                PrevisionBudget.objects.create(
                    date=date_prevision,
                    cat=cat,
                    libelle=libelle,
                    in_amount=Decimal('0'),
                    out_amount=salaire_net,
                    activ=activ,
                    detail=detail_text,
                    designation='Salaire',
                    quantite=Decimal('1'),
                    prix_unitaire=salaire_net,
                    type_prevision='depense_salaires',
                    base=base_obj,
                    ouvrage=ouvrage_obj,
                    district=district_obj,
                    commune=commune_obj,
                    annee=annee,
                    mois=mois,
                    est_calculee_auto=True,
                    source_calcul=f"Employe:{employe.id}|GrilleSalaire:{derniere_grille.id}"
                )
                nb_created += 1

            except Exception as e:
                logger.error(f"Erreur calcul salaire {employe.nom} mois {mois}: {str(e)}")
                continue

    return {'nb_created': nb_created, 'nb_employes': nb_employes}'''

# Fonction correcte calculer_previsions_irsa
new_calculer_irsa = '''

def calculer_previsions_irsa(annee, base=None, config=None):
    """Calcule les previsions IRSA pour l'annee entiere."""
    from apps.employees.models import Employe, GrilleSalaire
    from django.db.models import Q

    nb_created = 0
    nb_employes = 0

    employes_qs = Employe.objects.filter(date_debauchage__isnull=True).select_related('poste', 'poste__compte_irsa', 'base')

    if base:
        employes_qs = employes_qs.filter(base=base)

    for employe in employes_qs:
        # Recuperer la derniere grille de salaire pour cet employe
        derniere_grille = GrilleSalaire.objects.filter(
            contrat__employe=employe
        ).order_by('-date_salaire').first()

        if not derniere_grille or not derniere_grille.irsa:
            continue

        irsa = derniere_grille.irsa or Decimal('0')

        if irsa == 0:
            continue

        nb_employes += 1

        district_obj = None
        commune_obj = None
        ouvrage_obj = None

        if hasattr(employe, 'organisation') and employe.organisation:
            from apps.billing.models import ModaliteGestion, PointEau

            modalite = ModaliteGestion.objects.filter(gestionnaire=employe.organisation, date_fin__isnull=True).select_related('ouvrage').first()

            if modalite and modalite.ouvrage:
                ouvrage_obj = modalite.ouvrage

                point_eau = PointEau.objects.filter(ouvrage=ouvrage_obj).select_related('parcelle__village__fokontany__commune__district').first()

                if point_eau and point_eau.parcelle:
                    parcelle = point_eau.parcelle
                    if parcelle.village and parcelle.village.fokontany:
                        fokontany = parcelle.village.fokontany
                        if fokontany.commune:
                            commune_obj = fokontany.commune
                            if commune_obj.district:
                                district_obj = commune_obj.district

        for mois in range(1, 13):
            try:
                date_prevision = date(annee, mois, 1)

                base_obj = employe.base if employe.base else None
                activ = employe.volet if employe.volet else (base_obj.nom_base if base_obj else 'GLOBAL')

                cat = ''
                if employe.poste and employe.poste.compte_irsa:
                    cat = employe.poste.compte_irsa.compte

                prefixe_poste = employe.poste.prefixe_designation if employe.poste else ''
                libelle = f"_{prefixe_poste} {employe.nom} {employe.prenom}_IRSA_{annee} {mois:02d}"

                detail_text = employe.surnom if employe.surnom else employe.prenom

                PrevisionBudget.objects.create(
                    date=date_prevision,
                    cat=cat,
                    libelle=libelle,
                    in_amount=Decimal('0'),
                    out_amount=irsa,
                    activ=activ,
                    detail=detail_text,
                    designation='IRSA',
                    quantite=Decimal('1'),
                    prix_unitaire=irsa,
                    type_prevision='depense_irsa',
                    base=base_obj,
                    ouvrage=ouvrage_obj,
                    district=district_obj,
                    commune=commune_obj,
                    annee=annee,
                    mois=mois,
                    est_calculee_auto=True,
                    source_calcul=f"Employe:{employe.id}|GrilleSalaire:{derniere_grille.id}"
                )
                nb_created += 1

            except Exception as e:
                logger.error(f"Erreur calcul IRSA {employe.nom} mois {mois}: {str(e)}")
                continue

    return {'nb_created': nb_created, 'nb_employes': nb_employes}'''

# Supprimer les anciennes fonctions et ajouter les nouvelles
# Trouver calculer_previsions_salaires
pattern_salaires = r'def calculer_previsions_salaires\(.*?\n.*?return \{[^\}]*\}'
content = re.sub(pattern_salaires, new_calculer_salaires, content, flags=re.DOTALL)

# Trouver calculer_previsions_irsa
pattern_irsa = r'def calculer_previsions_irsa\(.*?\n.*?return \{[^\}]*\}'
content = re.sub(pattern_irsa, new_calculer_irsa, content, flags=re.DOTALL)

# Ecrire le fichier modifie
with open('services_previsions.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fonctions corrigees - utilisation de GrilleSalaire au lieu de Contrat")
