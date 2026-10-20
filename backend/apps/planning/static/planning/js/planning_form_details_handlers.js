(function () {
    function getPlanningFormConfig() {
        return window.planningFormConfig || {};
    }

    function getEditableAvanceDesignationsData() {
        return window.editableAvanceDesignationsData || [];
    }

    function isStaffUser() {
        return Boolean(getPlanningFormConfig().isStaffUser);
    }

    function ensureRowPointBDatalist(row) {
        let datalist = row.querySelector('.point-b-datalist');
        if (datalist) {
            return datalist;
        }
        datalist = document.createElement('datalist');
        datalist.className = 'point-b-datalist';
        datalist.id = `point-b-options-${Math.random().toString(36).slice(2, 10)}`;
        row.appendChild(datalist);
        return datalist;
    }

    function handleEquipementChange(selectElement) {
        const row = selectElement.closest('tr');
        const pointEauSelect = row.querySelector('.point-eau-select');

        if (selectElement.value) {
            pointEauSelect.value = '';
            pointEauSelect.disabled = true;
        } else {
            pointEauSelect.disabled = false;
        }
    }

    function handlePointEauChange(selectElement) {
        const row = selectElement.closest('tr');
        const equipementSelect = row.querySelector('.equipement-select');
        const designationSelect = row.querySelector('.designation-select');
        const puInput = row.querySelector('.pu-input');

        if (selectElement.value) {
            equipementSelect.value = '';
            equipementSelect.disabled = true;

            const selectedDesignation = designationSelect.options[designationSelect.selectedIndex];
            const designationNom = selectedDesignation ? selectedDesignation.textContent.toLowerCase() : '';
            const typeAvance = selectedDesignation ? selectedDesignation.dataset.typeAvance : '';

            if (typeAvance === 'recette' || designationNom.includes('paiement forfaitaire')) {
                const selectedPE = selectElement.options[selectElement.selectedIndex];
                const tarif = parseFloat(selectedPE.dataset.tarif) || 0;
                puInput.value = tarif.toFixed(2);
                if (typeof window.calculateMontant === 'function') {
                    window.calculateMontant(puInput);
                }
            }
        } else {
            equipementSelect.disabled = false;
        }
    }

    function handleDesignationChange(selectElement) {
        const row = selectElement.closest('tr');
        const selectedOption = selectElement.options[selectElement.selectedIndex];

        if (!selectedOption || !selectedOption.value) return;

        const designationData = getEditableAvanceDesignationsData().find(
            designation => String(designation.id || '') === String(selectedOption.value || '')
        ) || null;

        const typeAvance = String(
            designationData ? (designationData.type_avance_caissiere || '') : (selectedOption.dataset.typeAvance || '')
        ).toLowerCase();
        const prixUnitaire = designationData
            ? (parseFloat(designationData.prix_unitaire) || 0)
            : (parseFloat(selectedOption.dataset.prixUnitaire) || 0);
        const posteAcheteur = designationData
            ? (designationData.poste_acheteur || '')
            : (selectedOption.dataset.posteAcheteur || '');
        const concerneLivraison = designationData
            ? Boolean(designationData.concerne_livraison)
            : selectedOption.dataset.concerneLivraison === 'true';
        const nomDesignation = selectedOption.textContent.toLowerCase();

        const quantityInput = row.querySelector('.quantity-input');
        const puInput = row.querySelector('.pu-input');
        const montantInput = row.querySelector('.montant-input');
        const compteSelect = row.querySelector('.compte-select');
        const trajetCheckbox = row.querySelector('.trajet-checkbox');
        const trajetSelect = row.querySelector('.trajet-select');
        const pointEauSelect = row.querySelector('.point-eau-select');
        const acheteurInput = row.querySelector('input[name="avance_acheteur[]"]');

        if (puInput && !concerneLivraison && !Number.isNaN(prixUnitaire)) {
            puInput.value = prixUnitaire.toFixed(2);
        }

        if (acheteurInput && posteAcheteur) {
            acheteurInput.value = posteAcheteur;
        }

        if (typeof window.loadComptesByDesignation === 'function') {
            window.loadComptesByDesignation(selectedOption.value, compteSelect);
        }

        if (typeAvance === 'avance') {
            quantityInput.value = '1';

            puInput.readOnly = true;
            puInput.classList.add('bg-base-200', 'cursor-not-allowed');

            if (typeof window.calculateMontant === 'function') {
                window.calculateMontant(quantityInput);
            }

            if (nomDesignation.includes('frais de déplacement') || nomDesignation.includes('deplacement')) {
                if (trajetSelect) {
                    trajetSelect.required = true;
                    trajetSelect.disabled = false;
                    trajetSelect.value = '';
                } else if (trajetCheckbox) {
                    trajetCheckbox.checked = true;
                    trajetCheckbox.required = true;
                    if (typeof window.handleTrajetChange === 'function') {
                        window.handleTrajetChange(trajetCheckbox);
                    }
                }
                if (row.querySelector('.point-a-select')) {
                    row.querySelector('.point-a-select').disabled = true;
                }
                if (row.querySelector('.point-b-select')) {
                    row.querySelector('.point-b-select').disabled = true;
                }
                if (row.querySelector('.transport-select')) {
                    row.querySelector('.transport-select').disabled = true;
                }
            } else {
                if (trajetSelect) {
                    trajetSelect.required = false;
                    trajetSelect.disabled = true;
                    trajetSelect.value = '';
                }
                if (trajetCheckbox) {
                    trajetCheckbox.required = false;
                }
            }
        } else if (typeAvance === 'recette') {
            pointEauSelect.required = true;

            if (pointEauSelect.value) {
                const selectedPE = pointEauSelect.options[pointEauSelect.selectedIndex];
                const tarif = parseFloat(selectedPE.dataset.tarif) || 0;
                puInput.value = tarif.toFixed(2);
                if (typeof window.calculateMontant === 'function') {
                    window.calculateMontant(puInput);
                }
            }
        } else if (typeAvance === 'bon_livraison' || concerneLivraison) {
            quantityInput.value = '';
            puInput.value = '';
            montantInput.value = '0.00';
            puInput.readOnly = true;
            puInput.classList.add('bg-base-200', 'cursor-not-allowed');
        } else {
            puInput.readOnly = false;
            puInput.classList.remove('bg-base-200', 'cursor-not-allowed');
        }
    }

    function handleTrajetChange(checkbox) {
        const row = checkbox.closest('tr');
        const pointASelect = row.querySelector('.point-a-select');
        const pointBSelect = row.querySelector('.point-b-select');
        const transportSelect = row.querySelector('.transport-select');
        const trajetSelect = row.querySelector('.trajet-select');

        if (checkbox.checked) {
            pointASelect.disabled = false;
            pointBSelect.disabled = false;
            transportSelect.disabled = false;
        } else {
            pointASelect.disabled = true;
            pointASelect.value = '';
            pointBSelect.disabled = true;
            pointBSelect.value = '';
            transportSelect.disabled = true;
            transportSelect.value = '';
            if (trajetSelect) trajetSelect.value = '';
        }
    }

    function handleTrajetModeChange(selectElement) {
        const row = selectElement.closest('tr');
        const pointASelect = row.querySelector('.point-a-autocomplete');
        const pointBSelect = row.querySelector('.point-b-autocomplete');
        const pointAHidden = row.querySelector('.point-a-select');
        const pointBHidden = row.querySelector('.point-b-select');
        const transportSelect = row.querySelector('.transport-select');
        if (!selectElement.value) {
            pointASelect.disabled = true;
            pointASelect.value = '';
            if (pointAHidden) pointAHidden.value = '';
            pointBSelect.disabled = true;
            pointBSelect.value = '';
            if (pointBHidden) pointBHidden.value = '';
            transportSelect.disabled = true;
            transportSelect.innerHTML = '<option value="">-</option>';
            return;
        }
        pointASelect.disabled = false;
        pointBSelect.disabled = true;
        pointBSelect.value = '';
        if (pointBHidden) pointBHidden.value = '';
        transportSelect.disabled = true;
        transportSelect.innerHTML = '<option value="">-</option>';
        proposerTrajet(row);
    }

    function handlePointAAutocomplete(input) {
        const row = input.closest('tr');
        const hidden = row.querySelector('.point-a-select');
        const pointBInput = row.querySelector('.point-b-autocomplete');
        const pointBHidden = row.querySelector('.point-b-select');
        hidden.value = resolveLieu(input);
        if (!hidden.value) {
            pointBInput.disabled = true;
            pointBInput.value = '';
            pointBHidden.value = '';
            return;
        }
        pointBInput.disabled = false;
        pointBInput.value = '';
        pointBHidden.value = '';
        handlePointAChange(hidden);
    }

    function handlePointBAutocomplete(input) {
        const row = input.closest('tr');
        const hidden = row.querySelector('.point-b-select');
        hidden.value = resolveLieu(input);
        if (hidden.value) {
            handlePointBChange(hidden);
        }
    }

    function handlePointAChange(selectElement) {
        const row = selectElement.closest('tr');
        const pointBHidden = row.querySelector('.point-b-select');
        const pointBInput = row.querySelector('.point-b-autocomplete');
        const transportSelect = row.querySelector('.transport-select');
        const puInput = row.querySelector('.pu-input');
        const trajetSelect = row.querySelector('.trajet-select');
        const pointAId = selectElement.value;
        const datalist = ensureRowPointBDatalist(row);

        if (!pointAId) {
            if (pointBInput) {
                pointBInput.value = '';
                pointBInput.disabled = true;
            }
            if (pointBHidden) {
                pointBHidden.value = '';
                delete pointBHidden.dataset.transport;
                delete pointBHidden.dataset.prixUnitaire;
            }
            if (datalist) {
                datalist.innerHTML = '';
            }
            if (transportSelect) {
                transportSelect.innerHTML = '<option value="">-</option>';
                transportSelect.value = '';
                transportSelect.disabled = true;
            }
            if (puInput) puInput.value = '0';
            return;
        }

        const deplacementsData = window.deplacementsData || [];
        const trajet = trajetSelect ? trajetSelect.value : '';
        const matches = trajet === 'retour'
            ? deplacementsData.filter(dep => dep.point_b_id === pointAId)
            : deplacementsData.filter(dep => dep.point_a_id === pointAId);
        const pointBOptions = matches.filter(dep => dep.point_b_id && dep.point_b_nom);

        if (pointBInput) {
            pointBInput.value = '';
            pointBInput.disabled = false;   // l'arrivée n'est plus limitée aux trajets déjà tarifés
            pointBInput.setAttribute('list', datalist.id);
        }
        if (pointBHidden) {
            pointBHidden.value = '';
            delete pointBHidden.dataset.transport;
            delete pointBHidden.dataset.prixUnitaire;
        }
        if (datalist) {
            const seen = new Set();
            datalist.innerHTML = '';
            pointBOptions.forEach(dep => {
                const label = String(dep.point_b_nom || '').trim();
                if (!label || seen.has(label.toLowerCase())) {
                    return;
                }
                seen.add(label.toLowerCase());
                const option = document.createElement('option');
                option.value = label;
                datalist.appendChild(option);
            });
        }

        if (transportSelect) {
            transportSelect.innerHTML = '<option value="">-</option>';
            const transportsTarifes = [...new Set(pointBOptions.map(dep => dep.moyen_transport).filter(Boolean))];
            const transports = transportsTarifes.length ? transportsTarifes : ['taxi-brousse', 'pirogue', 'bac'];
            transports.forEach(t => {
                const option = document.createElement('option');
                option.value = t;
                option.textContent = t === 'taxi-brousse' ? 'Taxi' : (t === 'pirogue' ? 'Pirogue' : 'Bac');
                transportSelect.appendChild(option);
            });
            transportSelect.disabled = false;
        }
    }

    function handlePointBChange(selectElement) {
        const row = selectElement.closest('tr');
        const transportSelect = row.querySelector('.transport-select');
        const puInput = row.querySelector('.pu-input');
        const trajetSelect = row.querySelector('.trajet-select');
        const pointAHidden = row.querySelector('.point-a-select');
        const pointBInput = row.querySelector('.point-b-autocomplete');
        const typedLabel = pointBInput ? pointBInput.value : '';
        const pointAId = pointAHidden ? pointAHidden.value : '';
        const trajet = trajetSelect ? trajetSelect.value : '';
        const deplacementsData = window.deplacementsData || [];
        const normalizedLabel = String(typedLabel || '').trim().toLowerCase();

        const match = deplacementsData.find(dep => {
            if (!normalizedLabel) {
                return false;
            }
            const depPointA = String(dep.point_a_id || '');
            const depPointB = String(dep.point_b_id || '');
            const depLabel = String(dep.point_b_nom || '').trim().toLowerCase();
            if (trajet === 'retour') {
                return String(dep.point_b_id || '') === String(pointAId || '') && depLabel === normalizedLabel;
            }
            return depPointA === String(pointAId || '') && depLabel === normalizedLabel;
        });

        if (!match) {
            delete selectElement.dataset.transport;
            delete selectElement.dataset.prixUnitaire;
            if (selectElement.value) {
                // Village reconnu mais trajet absent de la table des prix : on le garde, le tarif sera
                // proposé (prix habituel dans un autre sens) ou à renseigner.
                if (transportSelect) {
                    transportSelect.disabled = false;
                    const presents = new Set([...transportSelect.options].map(o => o.value));
                    [['taxi-brousse', 'Taxi'], ['pirogue', 'Pirogue'], ['bac', 'Bac']].forEach(([v, l]) => {
                        if (presents.has(v)) return;
                        const o = document.createElement('option');
                        o.value = v;
                        o.textContent = l;
                        transportSelect.appendChild(o);
                    });
                    if (!transportSelect.value) transportSelect.value = 'taxi-brousse';   // cas le plus courant
                }
                afficherInfoTrajet(row);
                return;
            }
            if (transportSelect) {
                transportSelect.value = '';
            }
            if (puInput) {
                puInput.value = '0.00';
                if (typeof window.calculateMontant === 'function') {
                    window.calculateMontant(puInput);
                }
            }
            return;
        }

        selectElement.value = trajet === 'retour' ? (match.point_a_id || '') : (match.point_b_id || '');
        selectElement.dataset.transport = match.moyen_transport || '';
        selectElement.dataset.prixUnitaire = match.prix_unitaire || 0;
        const transport = selectElement.dataset.transport || '';
        const prix = parseFloat(selectElement.dataset.prixUnitaire || 0) || 0;
        if (transportSelect && transport) {
            transportSelect.disabled = false;
            transportSelect.innerHTML = '<option value="">-</option>';
            const opt = document.createElement('option');
            opt.value = transport;
            opt.textContent = transport === 'taxi-brousse' ? 'Taxi' : (transport === 'pirogue' ? 'Pirogue' : 'Bac');
            opt.selected = true;
            transportSelect.appendChild(opt);
        }
        if (puInput) {
            puInput.value = prix.toFixed(2);
            if (typeof window.calculateMontant === 'function') {
                window.calculateMontant(puInput);
            }
        }
        afficherInfoTrajet(row);
    }

    function handleTransportChange(selectElement) {
        const row = selectElement.closest('tr');
        const pointASelect = row.querySelector('.point-a-select');
        const pointBSelect = row.querySelector('.point-b-select');

        // On ne réinitialise plus l'arrivée : on rafraîchit seulement l'information (prix habituel, durée).
        if (selectElement.value && pointASelect.value && pointBSelect.value) {
            afficherInfoTrajet(row, true);
        }
    }

    // ---- Aide à la saisie : trajet proposé, distance, durée et prix habituel -----------------------------

    function resolveLieu(input) {
        if (input.dataset.villageId && input.dataset.villageNom === input.value) return input.dataset.villageId;
        return typeof window.resolveVillageIdFromLabel === 'function' ? window.resolveVillageIdFromLabel(input.value) : '';
    }

    function setLieu(input, hidden, village) {
        input.disabled = false;
        input.value = village.nom;
        input.dataset.villageId = village.id;
        input.dataset.villageNom = village.nom;
        hidden.value = village.id;
    }

    function zoneDe(row, classe, apres) {
        let zone = row.querySelector('.' + classe);
        if (!zone) {
            zone = document.createElement('div');
            zone.className = classe + ' text-xs mt-1';
            apres.appendChild(zone);
        }
        return zone;
    }

    function fmtDuree(min) {
        const h = Math.floor(min / 60), m = Math.round(min % 60);
        return h ? h + ' h ' + String(m).padStart(2, '0') : m + ' min';
    }

    /** Affiche sous le point B : distance et durée par la route, prix habituel, et alerte si l'écart est grand. */
    async function afficherInfoTrajet(row, majPrix) {
        const cfg = window.planningFormConfig || {};
        const aHidden = row.querySelector('.point-a-select'), bHidden = row.querySelector('.point-b-select');
        const bInput = row.querySelector('.point-b-autocomplete');
        if (!aHidden || !bHidden || !bInput || !cfg.apiPrixDeplacementUrl) return;
        const zone = zoneDe(row, 'trajet-info', bInput.closest('td'));
        if (!aHidden.value || !bHidden.value) { zone.textContent = ''; return; }
        const moyen = (row.querySelector('.transport-select') || {}).value || 'taxi-brousse';
        const jeton = String(Math.random());
        row.dataset.infoJeton = jeton;
        try {
            const r = await fetch(cfg.apiPrixDeplacementUrl + '?point_a_id=' + encodeURIComponent(aHidden.value) +
                                  '&point_b_id=' + encodeURIComponent(bHidden.value) + '&moyen_transport=' + encodeURIComponent(moyen));
            const d = await r.json();
            if (row.dataset.infoJeton !== jeton) return;   // une saisie plus récente a pris le relais
            const parts = [];
            if (d.distance_route_km != null) {
                let texte = String(d.distance_route_km).replace('.', ',') + ' km · ' + fmtDuree(d.duree_route_min) + ' estimées';
                if (d.part_sentier_pct >= 50) texte += ' (' + d.part_sentier_pct + ' % de sentier ou à pied)';
                parts.push(texte);
            }
            const puInput = row.querySelector('.pu-input');
            let classe = 'text-base-content/70';
            if (d.prix_unitaire != null) {
                parts.push('tarif habituel ' + Number(d.prix_unitaire).toLocaleString('fr-FR') + ' Ar' + (d.date_prix ? ' (' + d.date_prix.split('-').reverse().join('/') + ')' : ''));
                const saisi = puInput ? parseFloat(puInput.value || '0') : 0;
                if (puInput && (!saisi || majPrix === true && !saisi)) {
                    puInput.value = Number(d.prix_unitaire).toFixed(2);
                    if (typeof window.calculateMontant === 'function') window.calculateMontant(puInput);
                } else if (saisi > 0 && (saisi > 1.5 * d.prix_unitaire || saisi < 0.5 * d.prix_unitaire)) {
                    parts.push('⚠ ton prix s\'écarte de ' + Math.round((saisi / d.prix_unitaire - 1) * 100) + ' %');
                    classe = 'text-warning';
                }
            } else {
                parts.push('⚠ tarif inconnu : à renseigner');
                classe = 'text-warning';
            }
            zone.className = 'trajet-info text-xs mt-1 ' + classe;
            zone.textContent = parts.join(' · ');
        } catch (e) { zone.textContent = ''; }
    }

    /** Propose le trajet de la ligne d'après l'ouvrage du planning (arrivée) et la base de l'agent (départ). */
    async function proposerTrajet(row) {
        const cfg = window.planningFormConfig || {};
        const trajet = (row.querySelector('.trajet-select') || {}).value;
        const aInput = row.querySelector('.point-a-autocomplete');
        const zone = zoneDe(row, 'trajet-suggestion', aInput.closest('td'));
        zone.replaceChildren();
        const ouvrage = document.getElementById('ouvrage');
        if (!trajet || !cfg.apiTrajetSuggereUrl || !ouvrage || !ouvrage.value) return;
        const employe = document.getElementById('employe');
        try {
            const r = await fetch(cfg.apiTrajetSuggereUrl + '?ouvrage_id=' + encodeURIComponent(ouvrage.value) +
                                  '&employe_id=' + encodeURIComponent(employe ? employe.value : ''));
            const d = await r.json();
            if (!d.success || !d.arrivee) return;
            if ((row.querySelector('.trajet-select') || {}).value !== trajet) return;
            const depart = d.depart_base && d.depart_base.village;
            const [va, vb] = trajet === 'retour' ? [d.arrivee, depart] : [depart, d.arrivee];
            const bouton = document.createElement('button');
            bouton.type = 'button';
            bouton.className = 'btn btn-xs btn-outline btn-info';
            bouton.textContent = '💡 ' + (va ? va.nom : '?') + ' → ' + (vb ? vb.nom : '?');
            bouton.title = "Trajet proposé d'après l'ouvrage du planning" + (depart ? " et la base de l'agent" : ' (base non localisée : choisis l\'autre village)');
            bouton.onclick = () => appliquerTrajet(row, va, vb);
            zone.appendChild(bouton);
        } catch (e) { /* suggestion facultative */ }
    }

    function appliquerTrajet(row, va, vb) {
        const aInput = row.querySelector('.point-a-autocomplete'), aHidden = row.querySelector('.point-a-select');
        const bInput = row.querySelector('.point-b-autocomplete'), bHidden = row.querySelector('.point-b-select');
        if (va) {
            setLieu(aInput, aHidden, va);
            handlePointAChange(aHidden);      // prépare les choix d'arrivée (efface B : on le remplit ensuite)
        }
        if (vb) {
            setLieu(bInput, bHidden, vb);
            handlePointBChange(bHidden);      // prix habituel s'il existe, sinon information « tarif inconnu »
        } else {
            bInput.disabled = false;
            bInput.focus();
        }
        const zone = row.querySelector('.trajet-suggestion');
        if (zone) zone.replaceChildren();
    }

    window.handleEquipementChange = handleEquipementChange;
    window.handlePointEauChange = handlePointEauChange;
    window.handleDesignationChange = handleDesignationChange;
    window.handleTrajetChange = handleTrajetChange;
    window.handleTrajetModeChange = handleTrajetModeChange;
    window.handlePointAAutocomplete = handlePointAAutocomplete;
    window.handlePointBAutocomplete = handlePointBAutocomplete;
    window.handlePointAChange = handlePointAChange;
    window.handlePointBChange = handlePointBChange;
    window.handleTransportChange = handleTransportChange;
    window.resolveVillageIdFromInput = resolveLieu;
    window.afficherInfoTrajet = afficherInfoTrajet;
    window.proposerTrajet = proposerTrajet;
})();
