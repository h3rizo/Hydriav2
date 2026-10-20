# Script to add salary and social charges prediction functions

new_code = """

def calculer_previsions_salaires(annee, base=None, config=None):
    \"""Calcule les prévisions de salaires pour l'année entière.\"""
    from apps.employees.models import Employe, Contrat

    nb_created = 0
    nb_employes = 0

    employes_qs = Employe.objects.filter(date_debauchage__isnull=True).select_related('poste', 'poste__compte_salaire', 'base')

    if base:
        employes_qs = employes_qs.filter(base=base)

    for employe in employes_qs:
        contrat_actif = Contrat.objects.filter(employe=employe, date_fin__isnull=True).first()

        if not contrat_actif:
            continue

        salaire_net = contrat_actif.montant_salaire_net or Decimal('0')

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
                    source_calcul=f"Employe:{employe.id}|Contrat:{contrat_actif.id}"
                )
                nb_created += 1

            except Exception as e:
                logger.error(f"Erreur calcul salaire {employe.nom} mois {mois}: {str(e)}")
                continue

    return {'nb_created': nb_created, 'nb_employes': nb_employes}


def calculer_previsions_irsa(annee, base=None, config=None):
    \"""Calcule les prévisions IRSA pour l'année entière.\"""
    from apps.employees.models import Employe, Contrat

    nb_created = 0
    nb_employes = 0

    employes_qs = Employe.objects.filter(date_debauchage__isnull=True).select_related('poste', 'poste__compte_irsa', 'base')

    if base:
        employes_qs = employes_qs.filter(base=base)

    for employe in employes_qs:
        contrat_actif = Contrat.objects.filter(employe=employe, date_fin__isnull=True).first()

        if not contrat_actif:
            continue

        irsa = contrat_actif.montant_irsa or Decimal('0')

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
                    source_calcul=f"Employe:{employe.id}|Contrat:{contrat_actif.id}"
                )
                nb_created += 1

            except Exception as e:
                logger.error(f"Erreur calcul IRSA {employe.nom} mois {mois}: {str(e)}")
                continue

    return {'nb_created': nb_created, 'nb_employes': nb_employes}


def calculer_previsions_charges_sociales(annee, base=None, config=None):
    \"""Calcule les charges sociales trimestrielles (CNAPS, FMFP, Mutuelle).\"""
    from apps.employees.models import Salaire

    nb_created = 0
    trimestres = [
        (1, [(annee-1, 10), (annee-1, 11), (annee-1, 12)]),
        (4, [(annee, 1), (annee, 2), (annee, 3)]),
        (7, [(annee, 4), (annee, 5), (annee, 6)]),
        (10, [(annee, 7), (annee, 8), (annee, 9)])
    ]

    for mois_trim, mois_sources in trimestres:
        salaires_sources = Salaire.objects.filter(
            date_paiement__year__in=[annee-1, annee],
            date_paiement__month__in=[m for (a, m) in mois_sources]
        ).select_related('grille_salaire__contrat__employe', 'grille_salaire__contrat__employe__poste', 'grille_salaire__contrat__employe__base')

        if base:
            salaires_sources = salaires_sources.filter(grille_salaire__contrat__employe__base=base)

        employes_data = {}
        for salaire in salaires_sources:
            employe = salaire.grille_salaire.contrat.employe
            emp_id = str(employe.id)

            if emp_id not in employes_data:
                employes_data[emp_id] = {
                    'employe': employe,
                    'cnaps_total': Decimal('0'),
                    'fmfp_total': Decimal('0'),
                    'mutuelle_total': Decimal('0')
                }

            employes_data[emp_id]['cnaps_total'] += salaire.cnaps_paye or Decimal('0')
            employes_data[emp_id]['fmfp_total'] += salaire.fmfp_paye or Decimal('0')
            employes_data[emp_id]['mutuelle_total'] += salaire.mutuelle_sante_paye or Decimal('0')

        date_prevision = date(annee, mois_trim, 1)

        for emp_id, data in employes_data.items():
            employe = data['employe']

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

            base_obj = employe.base if employe.base else None
            activ = employe.volet if employe.volet else (base_obj.nom_base if base_obj else 'GLOBAL')
            detail_text = employe.surnom if employe.surnom else employe.prenom
            prefixe_poste = employe.poste.prefixe_designation if employe.poste else ''

            if data['cnaps_total'] > 0:
                try:
                    cat_cnaps = ''
                    if employe.poste and hasattr(employe.poste, 'compte_cnaps') and employe.poste.compte_cnaps:
                        cat_cnaps = employe.poste.compte_cnaps.compte

                    PrevisionBudget.objects.create(
                        date=date_prevision,
                        cat=cat_cnaps,
                        libelle=f"_{prefixe_poste} {employe.nom} {employe.prenom}_CNAPS_T{mois_trim//3+1}_{annee}",
                        in_amount=Decimal('0'),
                        out_amount=data['cnaps_total'],
                        activ=activ,
                        detail=detail_text,
                        designation='CNAPS',
                        quantite=Decimal('3'),
                        prix_unitaire=data['cnaps_total'] / Decimal('3'),
                        type_prevision='depense_cnaps',
                        base=base_obj,
                        ouvrage=ouvrage_obj,
                        district=district_obj,
                        commune=commune_obj,
                        annee=annee,
                        mois=mois_trim,
                        est_calculee_auto=True,
                        source_calcul=f"Employe:{employe.id}|Trimestre:{mois_trim}"
                    )
                    nb_created += 1
                except Exception as e:
                    logger.error(f"Erreur CNAPS {employe.nom} trim {mois_trim}: {str(e)}")

            if data['fmfp_total'] > 0:
                try:
                    cat_fmfp = ''
                    if employe.poste and hasattr(employe.poste, 'compte_fmfp') and employe.poste.compte_fmfp:
                        cat_fmfp = employe.poste.compte_fmfp.compte

                    PrevisionBudget.objects.create(
                        date=date_prevision,
                        cat=cat_fmfp,
                        libelle=f"_{prefixe_poste} {employe.nom} {employe.prenom}_FMFP_T{mois_trim//3+1}_{annee}",
                        in_amount=Decimal('0'),
                        out_amount=data['fmfp_total'],
                        activ=activ,
                        detail=detail_text,
                        designation='FMFP',
                        quantite=Decimal('3'),
                        prix_unitaire=data['fmfp_total'] / Decimal('3'),
                        type_prevision='depense_fmfp',
                        base=base_obj,
                        ouvrage=ouvrage_obj,
                        district=district_obj,
                        commune=commune_obj,
                        annee=annee,
                        mois=mois_trim,
                        est_calculee_auto=True,
                        source_calcul=f"Employe:{employe.id}|Trimestre:{mois_trim}"
                    )
                    nb_created += 1
                except Exception as e:
                    logger.error(f"Erreur FMFP {employe.nom} trim {mois_trim}: {str(e)}")

            if data['mutuelle_total'] > 0:
                try:
                    cat_mutuelle = ''
                    if employe.poste and hasattr(employe.poste, 'compte_mutuelle') and employe.poste.compte_mutuelle:
                        cat_mutuelle = employe.poste.compte_mutuelle.compte

                    PrevisionBudget.objects.create(
                        date=date_prevision,
                        cat=cat_mutuelle,
                        libelle=f"_{prefixe_poste} {employe.nom} {employe.prenom}_Mutuelle_{annee} T{mois_trim//3+1}",
                        in_amount=Decimal('0'),
                        out_amount=data['mutuelle_total'],
                        activ=activ,
                        detail=detail_text,
                        designation='Mutuelle Sante',
                        quantite=Decimal('3'),
                        prix_unitaire=data['mutuelle_total'] / Decimal('3'),
                        type_prevision='depense_mutuelle',
                        base=base_obj,
                        ouvrage=ouvrage_obj,
                        district=district_obj,
                        commune=commune_obj,
                        annee=annee,
                        mois=mois_trim,
                        est_calculee_auto=True,
                        source_calcul=f"Employe:{employe.id}|Trimestre:{mois_trim}"
                    )
                    nb_created += 1
                except Exception as e:
                    logger.error(f"Erreur Mutuelle {employe.nom} trim {mois_trim}: {str(e)}")

    return {'nb_created': nb_created}
"""

# Read existing file
with open('services_previsions.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Append new code
with open('services_previsions.py', 'w', encoding='utf-8') as f:
    f.write(content + new_code)

print("Functions added successfully!")
