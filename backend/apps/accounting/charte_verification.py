"""
Fonctions de vérification des formats de charte comptable
"""
import re
from datetime import datetime


def verifier_charte_compte(description, charte_type, compte_code=None):
    """
    Vérifie si la description respecte la charte définie pour le compte

    Args:
        description: Description de la transaction
        charte_type: Type de charte ('allocation_familiale', 'baf', etc.)
        compte_code: Code du compte (pour info)

    Returns:
        dict avec 'conforme' (bool), 'erreurs' (list), 'details' (dict)
    """
    if not description:
        return {'conforme': False, 'erreurs': ['Description vide'], 'details': {}}

    erreurs = []
    details = {'type_charte': charte_type}

    # 1. ALLOCATION FAMILIALE (648200)
    # Format: __Allocation familiale employés__[Année] [Numéro du mois]
    # Accepte également:
    #   - Allocation familiale employés_[Année] [Numéro du mois]
    #   - un suffixe libre entre parenthèses
    #   - plusieurs mois séparés par "et" ou ","
    # Exemples:
    #   - "__Allocation familiale employés__2025 09" (un seul mois)
    #   - "__Allocation familiale employés__2025 09 et 10" (plusieurs mois)
    #   - "Allocation familiale employés_2026 06"
    #   - "Allocation familiale employés_2026 02 (30 000 Ar rendu à la CNaPS)"
    if charte_type == 'allocation_familiale':
        # Pattern flexible pour accepter les variantes historiques et un suffixe entre parenthèses
        pattern = r'^(?:__Allocation familiale employés__|Allocation familiale employés_)(\d{4})\s+(.+?)(?:\s*\([^)]*\))?$'
        match = re.match(pattern, description)

        if match:
            annee = match.group(1)
            mois_text = match.group(2).strip()
            details['annee'] = annee
            details['mois'] = mois_text

            # Extraire tous les nombres (mois) du texte
            # Exemple: "09 et 10" ou "09, 10" ou juste "09"
            mois_list = re.findall(r'\d{1,2}', mois_text)

            if not mois_list:
                erreurs.append('Aucun numéro de mois trouvé')
            else:
                # Vérifier que tous les mois sont valides
                for mois_str in mois_list:
                    try:
                        mois_int = int(mois_str)
                        if mois_int < 1 or mois_int > 12:
                            erreurs.append(f'Mois invalide: {mois_str} (doit être entre 1 et 12)')
                    except:
                        erreurs.append(f'Mois invalide: {mois_str}')
        else:
            erreurs.append('Format attendu: __Allocation familiale employés__[Année] [Numéro(s) du/des mois] ou Allocation familiale employés_[Année] [Numéro(s) du/des mois]')

    # 2. BAF (748100)
    # Format: __BAF__[Année] [Numéro du mois]
    # Accepte également plusieurs mois séparés par "et" ou ","
    # Exemples:
    #   - "__BAF__2025 09" (un seul mois)
    #   - "__BAF__2025 09 et 11" (plusieurs mois)
    elif charte_type == 'baf':
        # Pattern flexible pour accepter plusieurs mois
        pattern = r'^__BAF__(\d{4})\s+(.+)$'
        match = re.match(pattern, description)
        if not match:
            match = re.match(r'^BAF\s+CNaPS\s+(\d{4})\s+(.+)$', description, re.IGNORECASE)

        if match:
            annee = match.group(1)
            mois_text = match.group(2).strip()
            details['annee'] = annee
            details['mois'] = mois_text

            # Extraire tous les nombres (mois) du texte
            # Exemple: "09 et 11" ou "09, 11" ou juste "09"
            mois_list = re.findall(r'\d{1,2}', mois_text)

            if not mois_list:
                erreurs.append('Aucun numéro de mois trouvé')
            else:
                # Vérifier que tous les mois sont valides
                for mois_str in mois_list:
                    try:
                        mois_int = int(mois_str)
                        if mois_int < 1 or mois_int > 12:
                            erreurs.append(f'Mois invalide: {mois_str} (doit être entre 1 et 12)')
                    except:
                        erreurs.append(f'Mois invalide: {mois_str}')
        else:
            erreurs.append('Format attendu: __BAF__[Année] [Numéro(s) du/des mois]')

    # 3. INSTALLATION BP/BF (748201)
    # Format 1: [Type paiement]_[IDxls ou Ouvrage] (sans nom de personne)
    # Format 2: _[Nom personne]_[Type paiement]_[IDxls ou Ouvrage] (avec nom de personne)
    # Format 3: [Nom personne]_[Type paiement]_[IDxls]_[Ouvrage] (avec nom mais sans underscore initial)
    # Accepte à la fois BP (Borne Fontaine Payante) et BF (Borne Fontaine)
    # Pour identifier le point d'eau, il suffit soit du nom de l'ouvrage soit de l'IDxls (au moins un des deux)
    # Exemples:
    #   - "Paiement pour installation BP_78_Vohipeno" (avec IDxls et ouvrage)
    #   - "_RAVAOJANAHARY Hanta_Paiement pour installation BP_01_Antsahafilo" (avec IDxls et ouvrage)
    #   - "_RASOAZANAMALALA Edvige_Paiment pour installation BP_Ambato" (sans IDxls, juste ouvrage)
    #   - "_NABABANY_Paiement pour installation BF_5_Maroaomby" (BF avec IDxls et ouvrage)
    #   - "_Florine_Paiement pour installation BP (2ème tranche)_26_Sahivo" (texte entre parenthèses ignoré)
    #   - "RASOLONIAINA Harisoa Eliane_Paiement demande installation BP_101_Ankazondandy" (sans underscore initial, type "demande" sans "devis")
    elif charte_type == 'installation_bp':
        description_clean = re.sub(
            r'(Paiement\s+(?:demande\s+devis\s+installation|pour\s+(?:devis\s+)?installation)\s+B[PF])\s*\([^)]*\)',
            r'\1',
            description,
            flags=re.IGNORECASE,
        )
        parts = description_clean.split('_')

        # Détection du format selon si commence par underscore
        if description.startswith('_'):
            # Format avec nom: _[Nom]_[Type]_[IDxls ou Ouvrage]_[Ouvrage optionnel]
            if len(parts) < 3:
                erreurs.append('Format attendu: _[Nom]_[Type paiement]_[IDxls ou Ouvrage] ou [Type paiement]_[IDxls ou Ouvrage]')
            else:
                details['nom_personne'] = parts[1].strip()
                details['type_paiement'] = parts[2].strip()

                # parts[3] peut être soit IDxls soit le nom de l'ouvrage
                # Si parts[4] existe, alors parts[3] = IDxls et parts[4] = Ouvrage
                # Sinon parts[3] = Ouvrage (ou IDxls)
                if len(parts) >= 4:
                    details['idxls_pe'] = parts[3].strip()
                    details['ouvrage'] = parts[4].strip() if len(parts) > 4 else ''
                else:
                    # Seulement 3 parties: considérer parts[3] comme identifiant (peut être nom ou IDxls)
                    identifiant = parts[3].strip() if len(parts) > 3 else ''
                    # Si c'est un nombre, c'est probablement un IDxls
                    if identifiant.isdigit():
                        details['idxls_pe'] = identifiant
                        details['ouvrage'] = ''
                    else:
                        details['idxls_pe'] = ''
                        details['ouvrage'] = identifiant

                # Vérifier le type de paiement (accepte BP et BF)
                types_valides = [
                    'Paiement demande devis installation BP',
                    'Paiement demande installation BP',
                    'Paiement pour devis installation BP',
                    'Paiement pour installation BP',
                    'Paiment pour installation BP',  # Accepter la faute de frappe
                    'Paiement demande devis installation BF',
                    'Paiement demande installation BF',
                    'Paiement pour installation BF',
                    'Paiment pour installation BF'   # Accepter la faute de frappe
                ]
                if parts[2].strip() == 'Paiement devise BP':
                    pass
                elif parts[2].strip() not in types_valides:
                    erreurs.append(f'Type paiement invalide. Attendu: "Paiement pour installation BP/BF" ou "Paiement demande devis installation BP/BF"')

                # Vérifier qu'au moins un identifiant est présent (IDxls OU Ouvrage)
                if not details.get('idxls_pe') and not details.get('ouvrage'):
                    erreurs.append('Au moins un identifiant requis: IDxls ou nom de l\'ouvrage')
        else:
            # Deux variantes sans underscore initial:
            # - [Type]_[IDxls ou Ouvrage]_[Ouvrage optionnel]
            # - [Nom]_[Type]_[IDxls ou Ouvrage]_[Ouvrage optionnel]
            if len(parts) < 2:
                erreurs.append('Format attendu: _[Nom]_[Type paiement]_[IDxls ou Ouvrage] ou [Type paiement]_[IDxls ou Ouvrage]')
            else:
                types_valides = [
                    'Paiement demande devis installation BP',
                    'Paiement demande installation BP',
                    'Paiement pour devis installation BP',
                    'Paiement pour installation BP',
                    'Paiment pour installation BP',  # Accepter la faute de frappe
                    'Paiement demande devis installation BF',
                    'Paiement demande installation BF',
                    'Paiement pour devis installation BF',
                    'Paiement pour installation BF',
                    'Paiment pour installation BF'   # Accepter la faute de frappe
                ]

                if parts[0].strip() in types_valides:
                    details['type_paiement'] = parts[0].strip()
                    details['nom_personne'] = ''

                    # parts[1] peut être soit IDxls soit le nom de l'ouvrage
                    if len(parts) >= 3:
                        details['idxls_pe'] = parts[1].strip()
                        details['ouvrage'] = parts[2].strip()
                    else:
                        identifiant = parts[1].strip()
                        if identifiant.isdigit():
                            details['idxls_pe'] = identifiant
                            details['ouvrage'] = ''
                        else:
                            details['idxls_pe'] = ''
                            details['ouvrage'] = identifiant
                else:
                    details['nom_personne'] = parts[0].strip()
                    details['type_paiement'] = parts[1].strip() if len(parts) > 1 else ''

                    if len(parts) >= 4:
                        details['idxls_pe'] = parts[2].strip()
                        details['ouvrage'] = parts[3].strip()
                    else:
                        details['idxls_pe'] = parts[2].strip() if len(parts) > 2 else ''
                        details['ouvrage'] = parts[3].strip() if len(parts) > 3 else ''

                # Vérifier le type de paiement (accepte BP et BF)
                if details['type_paiement'] == 'Paiement devise BP':
                    pass
                elif details['type_paiement'] not in types_valides:
                    erreurs.append(f'Type paiement invalide. Attendu: "Paiement pour installation BP/BF" ou "Paiement demande devis installation BP/BF"')

                # Vérifier qu'au moins un identifiant est présent
                if not details.get('idxls_pe') and not details.get('ouvrage'):
                    erreurs.append('Au moins un identifiant requis: IDxls ou nom de l\'ouvrage')

    # 4. TAXE COMMUNALE (635201)
    # Format: Taxe Communale [Nom de commune] (avec ou sans underscore)
    # Exemples: "Taxe Communale Soavinandriana" ou "Taxe communale_Soavinandriana"
    elif charte_type == 'taxe_communale':
        # Accepter avec ou sans underscore
        pattern = r'^Taxe [Cc]ommunale[_ ](.+)$'
        match = re.match(pattern, description)

        if match:
            details['commune'] = match.group(1).strip()
            if not details['commune']:
                erreurs.append('Nom de commune manquant')
        else:
            erreurs.append('Format attendu: Taxe Communale [Nom de commune]')

    # 5. CARTES SOCIALES (748415)
    # Format: Cartes sociales [Nom de l'ouvrage] [Mois en format DD/MM/YYYY]
    # Exemple: "Cartes sociales Ambato 01/11/2025"
    elif charte_type == 'cartes_sociales':
        # Pattern non-greedy (.+?) pour capturer correctement le nom de l'ouvrage
        pattern = r'^Cartes sociales (.+?) (\d{2}/\d{2}/\d{4})$'
        match = re.match(pattern, description)

        if match:
            details['ouvrage'] = match.group(1).strip()
            date_str = match.group(2)
            details['date'] = date_str

            try:
                datetime.strptime(date_str, '%d/%m/%Y')
            except ValueError:
                erreurs.append(f'Date invalide: {date_str}')

            return {
                'conforme': len(erreurs) == 0,
                'erreurs': erreurs,
                'details': details
            }

        if match:
            details['ouvrage'] = match.group(1).strip()
            date_str = match.group(2)
            details['date'] = date_str

            # Vérifier le format de la date
            try:
                datetime.strptime(date_str, '%d/%m/%Y')
                # Vérifier que le jour est 01
                jour = date_str.split('/')[0]
                if jour != '01':
                    erreurs.append(f'Le jour doit être 01, trouvé: {jour}')
            except ValueError:
                erreurs.append(f'Date invalide: {date_str}')
        else:
            erreurs.append('Format attendu: Cartes sociales [Nom ouvrage] [01/MM/YYYY]')

    # 6. PAIEMENT AU VOLUME (707401)
    # Formats acceptes:
    # - Paiement au volume [Nom de l'ouvrage] [MM/YYYY]
    # - Paiement au volume [Nom de l'ouvrage] [JJ/MM/YYYY]
    # Suffixes optionnels acceptes et ignores:
    # - texte entre crochets en fin
    # - texte entre parentheses en fin, par ex. IDXls, liste d'IDXls, no facture, nb releves
    # Le mot "volume"/"Volume" est accepte indifferemment de la casse.
    # Exemples:
    #   "Paiement au volume Vohipeno 01/07/2025 [196300 split 2/2]"
    #   "Paiement au volume Avaratsena 19/06/2026 (8)"
    #   "Paiement au volume Avaratsena 19/06/2026 (8;12;15)"
    #   "Paiement au Volume Vohilengo AEPG 01/07/2026 (2 relevés)"
    elif charte_type == 'paiement_volume':
        # Nettoyer la description en supprimant:
        # - le texte entre crochets à la fin
        # - le suffixe optionnel entre parenthèses à la fin
        #   ex: "(123;456)" ou "(3 relevés)"
        description_clean = re.sub(r'\s*\[.*?\]\s*$', '', description).strip()
        description_clean = re.sub(r'\s*\([^()]*\)\s*$', '', description_clean).strip()

        match_mois = re.match(r'^Paiement au [Vv]olume (.+?) (\d{2}/\d{4})$', description_clean)
        if match_mois:
            details['ouvrage'] = match_mois.group(1).strip()
            date_str = match_mois.group(2)
            details['date'] = date_str

            try:
                mois_str, annee_str = date_str.split('/')
                mois_int = int(mois_str)
                annee_int = int(annee_str)
                if mois_int < 1 or mois_int > 12:
                    erreurs.append(f'Mois invalide: {mois_str}')
                details['mois'] = mois_int
                details['annee'] = annee_int
            except (ValueError, TypeError):
                erreurs.append(f'Date invalide: {date_str}')

            return {
                'conforme': len(erreurs) == 0,
                'erreurs': erreurs,
                'details': details
            }

        # Pattern non-greedy (.+?) pour capturer correctement le nom de l'ouvrage
        pattern = r'^Paiement au [Vv]olume (.+?) (\d{2}/\d{2}/\d{4})$'
        match = re.match(pattern, description_clean)

        if match:
            details['ouvrage'] = match.group(1).strip()
            date_str = match.group(2)
            details['date'] = date_str

            # Verifier le format de la date
            try:
                datetime.strptime(date_str, '%d/%m/%Y')
            except ValueError:
                erreurs.append(f'Date invalide: {date_str}')
        else:
            erreurs.append('Format attendu: Paiement au volume [Nom ouvrage] [JJ/MM/YYYY] ou [MM/YYYY], avec suffixe optionnel entre parenthèses')

    # 7. PAIEMENT FORFAITAIRE (748411)
    # Format: Paiement forfaitaire_U_[Quantité]_[Tarif]_[Liste PE (optionnel)]_[Nom de l'ouvrage]
    # ou avec suffixe IDXls optionnel entre parenthèses en fin de libellé: ...(1;2;3)
    # La liste de points d'eau ou le suffixe IDXls sont optionnels et ignorés pour la conformité.
    # Exemples:
    #   - "Paiement forfaitaire_U_3_75000_Avaratsena" (sans liste PE)
    #   - "Paiement forfaitaire_U_3_75000_BF3,BF4,BF5_Avaratsena" (avec liste PE)
    #   - "Paiement forfaitaire_U_3_75000_Avaratsena (1;2;3)" (avec suffixe IDXls)
    elif charte_type == 'paiement_forfaitaire':
        suffix_match = re.search(r'\(([^()]*)\)\s*$', description.strip())
        if suffix_match:
            raw_suffix = suffix_match.group(1).strip()
            idxls_parts = [part.strip() for part in raw_suffix.split(';') if part.strip()]
            if idxls_parts and all(part.isdigit() for part in idxls_parts):
                details['idxls_list'] = idxls_parts

        description_stripped = re.sub(r'\s*\([^()]*\)\s*$', '', description.strip()).strip()
        simple_match = re.match(r'^Paiement forfaitaire\s+(.+)$', description_stripped)
        if (
            not simple_match
            and description_stripped.startswith('Paiement forfaitaire_')
            and not description_stripped.startswith((
                'Paiement forfaitaire_U_',
                'Paiement forfaitaire_Fft_',
                'Paiement forfaitaire_fft_',
            ))
        ):
            simple_match = re.match(r'^Paiement forfaitaire_(.+)$', description_stripped)
        if simple_match:
            details['ouvrage'] = simple_match.group(1).strip()
            if not details.get('ouvrage'):
                erreurs.append('Nom de l\'ouvrage manquant')
            return {
                'conforme': len(erreurs) == 0,
                'erreurs': erreurs,
                'details': details
            }

        parts = description_stripped.split('_')

        if len(parts) < 5:
            erreurs.append('Format attendu: Paiement forfaitaire_U_[Quantité]_[Tarif]_[Ouvrage], avec liste PE optionnelle et suffixe IDXls optionnel en fin')
        elif len(parts) > 6:
            erreurs.append('Format trop long: maximum 6 parties attendues')
        else:
            if parts[0].strip() != 'Paiement forfaitaire':
                erreurs.append(f'Doit commencer par "Paiement forfaitaire", trouvé: "{parts[0]}"')

            details['unite'] = parts[1].strip()
            if parts[1].strip() != 'U':
                erreurs.append(f'Unité doit être "U", trouvé: "{parts[1].strip()}"')

            details['quantite'] = parts[2].strip()
            try:
                float(parts[2].strip())
            except:
                erreurs.append(f'Quantité invalide: "{parts[2].strip()}"')

            details['tarif'] = parts[3].strip()
            try:
                float(parts[3].strip().replace(' ', '').replace(',', ''))
            except:
                erreurs.append(f'Tarif invalide: "{parts[3].strip()}"')

            # Si 5 parties: parts[4] = Ouvrage
            # Si 6 parties: parts[4] = Liste PE (ignorée), parts[5] = Ouvrage
            if len(parts) == 5:
                details['ouvrage'] = parts[4].strip()
                details['liste_pe'] = ''  # Pas de liste
            else:  # len(parts) == 6
                details['liste_pe'] = parts[4].strip()  # Liste ignorée mais enregistrée
                details['ouvrage'] = parts[5].strip()

            if not details.get('ouvrage'):
                erreurs.append('Nom de l\'ouvrage manquant')

    # 8. INDEMNITÉ RBF/SAVON/PPMH/NETTOYAGE/BF (621102)
    # Format: _[Nom Employé]_[Type opération] [Code][détails]_[Ouvrage]
    # Variantes acceptées:
    #   - Avec underscore initial: "_RANIVOARISON_Indemnité..."
    #   - Sans underscore initial: "NONIE_Indemnité..."
    #   - Type opération: Indemnité, Nettoyage
    #   - Code: RBF, savon, PPMH, BF (Borne Fontaine)
    #   - Accepte "de" optionnel: "Indemnité de Savon" ou "Indemnité Savon"
    # Exemples:
    #   - "_RANIVOARISON Stephan Augustin_Indemnité savon_Ambalatenina II"
    #   - "_RAZAFIMANGA Francelette_Indemnité RBF10_2025_Manakambahiny 7 villages"
    #   - "_LAHADISON Jacquis_Indemnité savon_U_5_Ambalahady"
    #   - "_AH et RBF_Indemnité RBF_2025 03_Ambinanisahazahana"
    #   - "NONIE Egiptienne_Indemnité RBF3_2025_Andampy" (sans underscore initial)
    #   - "_RAZAFINDRAVAO_Indemnité PPMH_Trimestre_5000_Ar Ambohijatovo"
    #   - "RAMIADANA Francelette_Nettoyage BF3_Fft_20000_Vohipenohely"
    #   - "_ARMANDINE_Indemnité de Savon BF4_Fft_20000_pour gestion"
    elif charte_type == 'indemnite_rbf_savon':
        # Pattern flexible:
        # - Espaces et underscores optionnels au début
        # - [nom]_[Type opération: Indemnité/Nettoyage] (nom peut être absent, opération peut être absente)
        # - "de" optionnel
        # - [Code: RBF/RB/savon/PPMH/FPMH/PMH/BF]
        # - [reste]
        # Accepte: "_NOM_Indemnité RBF...", "Indemnité RBF_U_...", " _NOM_...", "NOM_Indemnité...", "Indemnité RBF...", "Savon_U_...", "Indemnité FPMH..."
        # L'underscore avant le type d'opération est maintenant optionnel
        # Le type d'opération (Indemnité/Nettoyage) est maintenant optionnel
        pattern = r'^\s*_?([^_]*?)_?\s*_?(Indemnit[ée]|Nettoyage)?(?:\s+de)?\s*(RBF?\d*|savon|PPMH|FPMH|PMH|BF)(.*)$'
        match = re.match(pattern, description, re.IGNORECASE)

        if match:
            nom_employe = match.group(1).strip() if match.group(1) else ''
            type_operation = match.group(2).strip() if match.group(2) else ''
            type_indemnite = match.group(3).strip()
            reste = match.group(4).strip()

            details['nom_employe'] = nom_employe if nom_employe else 'Non spécifié'
            details['type_operation'] = type_operation if type_operation else 'Non spécifié'
            details['type_indemnite'] = type_indemnite
            details['reste'] = reste

            # Ne plus exiger le nom de l'employé (certaines lignes n'en ont pas)

            # Vérifier qu'il y a bien un contenu après le type (ouvrage ou détails)
            # Pour Nettoyage BF, le reste peut être vide (juste "BF3_Fft_...")
            # Pour Indemnité, on accepte aussi un reste vide

            # Pour les indemnités savon avec U_, extraire l'IDxls
            if type_indemnite.lower() == 'savon' and '_U_' in reste.upper():
                # Format: _U_[idxls]_[montant]_[ouvrage] ou _U_[idxls]_[ouvrage]
                pattern_savon_u = r'_U_(\d+)_'
                match_savon = re.search(pattern_savon_u, reste, re.IGNORECASE)
                if match_savon:
                    details['idxls'] = match_savon.group(1)

            # Pour RBF ou BF avec numéro, extraire le numéro
            if type_indemnite.upper() in ['RBF', 'BF']:
                # Format possible: RBF[numéro] ou BF[numéro] ou RBF_[année] ou BF_[année]
                pattern_num = r'^(\d+)'  # RBF10, RBF1, BF3, etc.
                match_num = re.match(pattern_num, reste)
                if match_num:
                    details['numero_rbf'] = match_num.group(1)

            # Extraire l'année si présente (format: _[année] ou _[année] [mois])
            pattern_annee = r'_(\d{4})'
            match_annee = re.search(pattern_annee, reste)
            if match_annee:
                details['annee'] = match_annee.group(1)

                # Vérifier si mois présent
                pattern_mois = r'_\d{4}\s+(\d{2})'
                match_mois = re.search(pattern_mois, reste)
                if match_mois:
                    details['mois'] = match_mois.group(1)
        else:
            erreurs.append('Format attendu: _[Nom Employé]_[Indemnité/Nettoyage] [RBF/savon/BF][détails]_[Ouvrage]')

    # 9. INDEMNITÉ HORS ZONE / TERRAIN (625107 etc)
    # Format: _[Identité]_[Indemnité hors zone/terrain]_[Calcul/Montant]_[Reste]
    # Exemple: "_ADMIN TOTO Olivianne Wenda_Indemnité hors zone_4 x 30000 Ar_du 16 au 19/12/25 pour formation Tanà"
    elif charte_type in ['indemnite_hors_zone', 'indemnite_terrain']:
        # Pattern flexible pour capturer l'identité, le type, le calcul et le reste
        pattern = r'^_?(.*?)_?(Indemnit[ée]\s+(?:hors\s+zone|terrain))_+(.*?)_+(.*)$'
        match = re.match(pattern, description, re.IGNORECASE)

        if match:
            details['identité'] = match.group(1).strip()
            details['type_indemnité'] = match.group(2).strip()
            details['calcul'] = match.group(3).strip()
            details['reste'] = match.group(4).strip()
        else:
            # Essayer un format plus simple sans le reste à la fin
            pattern_simple = r'^_?(.*?)_?(Indemnit[ée]\s+(?:hors\s+zone|terrain))_+(.*)$'
            match_simple = re.match(pattern_simple, description, re.IGNORECASE)
            if match_simple:
                details['identité'] = match_simple.group(1).strip()
                details['type_indemnité'] = match_simple.group(2).strip()
                details['calcul'] = match_simple.group(3).strip()
            else:
                erreurs.append(f'Format attendu: _[Identité]_{charte_type.replace("_", " ").capitalize()}_[Calcul]_[Détails]')

    else:
        return {'conforme': True, 'erreurs': [], 'details': {'type_charte': 'aucune'}}

    conforme = len(erreurs) == 0
    return {'conforme': conforme, 'erreurs': erreurs, 'details': details}
