(function () {
    function getEditableAvanceDesignationsData() {
        const dedicatedList = window.editableAvanceDesignationsData || [];
        if (dedicatedList.length > 0) {
            return dedicatedList;
        }
        const allDesignations = window.designationsData || [];
        return allDesignations.filter(designation => Boolean(designation.is_generic_planning_avance));
    }

    function getDeplacementDefaultDesignation() {
        return window.deplacementDefaultDesignation || {};
    }

    function getComptesData() {
        return window.comptesData || [];
    }

    function getMagasinsData() {
        return window.magasinsData || [];
    }

    function isStaffUser() {
        return Boolean((window.planningFormConfig || {}).isStaffUser);
    }

    function populateAvanceDesignationSelects(selectElements) {
        const elements = Array.from(selectElements || []);
        const designations = getEditableAvanceDesignationsData();

        elements.forEach(select => {
            if (!select) {
                return;
            }

            const currentValue = select.value;
            select.innerHTML = '<option value="">Selectionner</option>';

            designations.forEach(designation => {
                const option = document.createElement('option');
                option.value = designation.id || '';
                option.textContent = designation.nom || '';
                option.dataset.typeAvance = String(designation.type_avance_caissiere || '').toLowerCase();
                option.dataset.prixUnitaire = designation.prix_unitaire || 0;
                option.dataset.posteAcheteur = designation.poste_acheteur || '';
                option.dataset.concerneLivraison = designation.concerne_livraison ? 'true' : 'false';
                if (String(designation.id) === String(currentValue || '')) {
                    option.selected = true;
                }
                select.appendChild(option);
            });
        });
    }

    async function addAvanceRow() {
        const tbody = document.getElementById('avances-tbody');
        const typeActiviteId = document.getElementById('type_activite')?.value;

        if (!typeActiviteId) {
            alert("Veuillez d'abord selectionner une activite");
            return;
        }

        const newRow = document.createElement('tr');
        newRow.className = 'avance-row';
        newRow.innerHTML = `
            <td class="relative">
                <select name="avance_equipement_id[]" class="select select-bordered select-sm w-32 equipement-select" onchange="handleEquipementChange(this)">
                    <option value="">-</option>
                </select>
                <span class="loading loading-spinner loading-xs equipement-loading hidden absolute right-1 top-2"></span>
            </td>
            <td class="relative">
                <select name="avance_point_eau_id[]" class="select select-bordered select-sm w-32 point-eau-select" onchange="handlePointEauChange(this)">
                    <option value="">-</option>
                </select>
                <span class="loading loading-spinner loading-xs point-eau-loading hidden absolute right-1 top-2"></span>
            </td>
            <td>
                <select name="avance_designation_id[]" class="select select-bordered select-sm w-48 designation-select" onchange="handleDesignationChange(this); syncDesignationRowMeta(this);">
                    <option value="">Selectionner</option>
                </select>
            </td>
            <td>
                <input type="number" name="avance_quantity[]" class="input input-bordered input-sm w-20 quantity-input" step="0.01" value="1" onchange="calculateMontant(this)">
            </td>
            <td>
                <input type="number" name="avance_pu[]" class="input input-bordered input-sm w-24 pu-input" step="0.01" onchange="calculateMontant(this)">
            </td>
            <td>
                <input type="number" name="avance_montant[]" class="input input-bordered input-sm w-24 montant-input" step="0.01" readonly>
            </td>
            <td>
                <select name="avance_compte_id[]" class="select select-bordered select-sm w-32 compte-select">
                    <option value="">-</option>
                    ${getComptesData().map(c => `<option value="${c.id}">${(c.nom || '').substring(0, 15)}</option>`).join('')}
                </select>
            </td>
            <td>
                <input type="text" name="avance_acheteur[]" class="input input-bordered input-sm w-24">
            </td>
            <td>
                <button type="button" class="btn btn-ghost btn-xs text-error" onclick="removeAvanceRow(this)">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
            </td>
        `;

        tbody.appendChild(newRow);

        const ouvrageId = document.getElementById('ouvrage')?.value || '';
        const equipementSelect = newRow.querySelector('.equipement-select');
        const pointEauSelect = newRow.querySelector('.point-eau-select');
        const designationSelect = newRow.querySelector('.designation-select');
        const quantityInput = newRow.querySelector('.quantity-input');
        const puInput = newRow.querySelector('.pu-input');
        const acheteurInput = newRow.querySelector('input[name="avance_acheteur[]"]');

        if (ouvrageId) {
            if (equipementSelect && typeof window.loadEquipementsByOuvrage === 'function') {
                window.loadEquipementsByOuvrage(ouvrageId, [equipementSelect]);
            }
            if (pointEauSelect && typeof window.loadPointsEauByOuvrage === 'function') {
                window.loadPointsEauByOuvrage(ouvrageId, [pointEauSelect]);
            }
        }

        if (typeof window.populateAvanceDesignationSelects === 'function') {
            window.populateAvanceDesignationSelects([designationSelect]);
        }

        designationSelect.addEventListener('change', function () {
            const selectedOption = this.options[this.selectedIndex];
            if (selectedOption && selectedOption.value) {
                const prixUnitaire = parseFloat(selectedOption.dataset.prixUnitaire) || 0;
                puInput.value = prixUnitaire.toFixed(2);
                puInput.readOnly = true;
                puInput.classList.add('bg-base-200', 'cursor-not-allowed');

                acheteurInput.value = selectedOption.dataset.posteAcheteur || '';
                if (typeof window.calculateMontant === 'function') {
                    window.calculateMontant(quantityInput);
                }
            }
        });

        updateTotalAvances();
        return;
    }

    function addDeplacementRow() {
        const tbody = document.getElementById('deplacements-tbody');
        const defaultDesignation = getDeplacementDefaultDesignation();
        const defaultDesignationId = defaultDesignation.id || '';
        const defaultPu = Number(defaultDesignation.prix_unitaire || 0);
        const defaultAcheteur = defaultDesignation.poste_acheteur || '';
        const newRow = document.createElement('tr');
        newRow.className = 'deplacement-row';
        newRow.innerHTML = `
            <td>
                <input type="hidden" name="avance_designation_id[]" value="${defaultDesignationId}">
                <input type="hidden" name="avance_quantity[]" class="quantity-input" value="1">
                <select name="avance_trajet[]" class="select select-bordered select-sm w-24 trajet-select" onchange="handleTrajetModeChange(this)">
                    <option value="">-</option>
                    <option value="aller">Aller</option>
                    <option value="retour">Retour</option>
                </select>
            </td>
            <td>
                <input type="text" class="input input-bordered input-sm w-32 point-a-autocomplete" list="villages-autocomplete" placeholder="Village..." oninput="handlePointAAutocomplete(this)" disabled>
                <input type="hidden" name="avance_point_a_id[]" class="point-a-select">
            </td>
            <td>
                <input type="text" class="input input-bordered input-sm w-32 point-b-autocomplete" list="villages-autocomplete" placeholder="Village..." oninput="handlePointBAutocomplete(this)" disabled>
                <input type="hidden" name="avance_point_b_id[]" class="point-b-select">
            </td>
            <td>
                <select name="avance_moyen_transport[]" class="select select-bordered select-sm w-24 transport-select" onchange="handleTransportChange(this)" disabled>
                    <option value="">-</option>
                </select>
            </td>
            <td>
                <input type="number" name="avance_pu[]" class="input input-bordered input-sm w-24 pu-input" step="0.01" value="${defaultPu.toFixed(2)}" onchange="calculateMontant(this)">
            </td>
            <td>
                <input type="number" name="avance_montant[]" class="input input-bordered input-sm w-24 montant-input" step="0.01" value="${defaultPu.toFixed(2)}" readonly>
            </td>
            <td>
                <input type="text" name="avance_acheteur[]" class="input input-bordered input-sm w-24" value="${defaultAcheteur}">
            </td>
            <td>
                <select name="avance_compte_id[]" class="select select-bordered select-sm w-32 compte-select">
                    <option value="">-</option>
                    ${getComptesData().map(c => `<option value="${c.id}">${(c.nom || '').substring(0, 15)}</option>`).join('')}
                </select>
            </td>
            <td><span class="badge badge-warning badge-sm">En cours</span></td>
            <td>
                <button type="button" class="btn btn-ghost btn-xs text-error" onclick="removeAvanceRow(this)">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
            </td>
        `;
        tbody.appendChild(newRow);
        const puInput = newRow.querySelector('.pu-input');
        if (puInput && typeof window.calculateMontant === 'function') {
            window.calculateMontant(puInput);
        }
        updateTotalAvances();
    }

    function removeAvanceRow(button) {
        const tbody = document.getElementById('avances-tbody');
        const row = button.closest('tr');

        if (tbody.querySelectorAll('tr').length > 0) {
            row.remove();
            updateTotalAvances();
        }
    }

    function updateTotalAvances() {
        const montants = document.querySelectorAll('#avances-tbody .montant-input, #deplacements-tbody .montant-input');
        let total = 0;

        montants.forEach(input => {
            total += parseFloat(input.value) || 0;
        });

        const totalElement = document.getElementById('total-avances');
        if (totalElement) {
            totalElement.textContent = total.toFixed(2);
        }
    }

    async function addLivraisonRow() {
        const tbody = document.getElementById('livraisons-tbody');
        const typeActiviteId = document.getElementById('type_activite')?.value;

        if (!typeActiviteId) {
            alert("Veuillez d'abord selectionner une activite");
            return;
        }

        const newRow = document.createElement('tr');
        newRow.className = 'livraison-row';
        newRow.innerHTML = `
            <td class="relative">
                <select name="livraison_equipement_id[]" class="select select-bordered select-sm w-32">
                    <option value="">-</option>
                </select>
            </td>
            <td class="relative">
                <select name="livraison_point_eau_id[]" class="select select-bordered select-sm w-32">
                    <option value="">-</option>
                </select>
            </td>
            <td>
                <select name="livraison_designation_id[]" class="select select-bordered select-sm w-48 livraison-designation-select">
                    <option value="">Chargement...</option>
                </select>
            </td>
            <td>
                <input type="number" name="livraison_quantity[]" class="input input-bordered input-sm w-20" step="0.01" value="1">
            </td>
            <td>
                <select name="livraison_magasin[]" class="select select-bordered select-sm w-32">
                    <option value="">-</option>
                    ${getMagasinsData().map((mag, index) => `<option value="${mag.nom}" ${index === 0 ? 'selected' : ''}>${(mag.nom || '').substring(0, 20)}</option>`).join('')}
                </select>
            </td>
            <td>
                <button type="button" class="btn btn-ghost btn-xs text-error" onclick="removeLivraisonRow(this)">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
            </td>
        `;
        tbody.appendChild(newRow);

        const designationSelect = newRow.querySelector('.livraison-designation-select');
        if (typeof window.loadEquipementsByOuvrage === 'function') {
            const ouvrageId = document.getElementById('ouvrage')?.value || '';
            const equipementSelect = newRow.querySelector('select[name="livraison_equipement_id[]"]');
            if (ouvrageId && equipementSelect) {
                window.loadEquipementsByOuvrage(ouvrageId, [equipementSelect]);
            }
        }
        if (typeof window.loadPointsEauByOuvrage === 'function') {
            const ouvrageId = document.getElementById('ouvrage')?.value || '';
            const pointEauSelect = newRow.querySelector('select[name="livraison_point_eau_id[]"]');
            if (ouvrageId && pointEauSelect) {
                window.loadPointsEauByOuvrage(ouvrageId, [pointEauSelect]);
            }
        }

        try {
            const allDesignations = getEditableAvanceDesignationsData();
            designationSelect.innerHTML = '<option value="">Selectionner</option>';
            allDesignations
                .filter(des => des.type_avance_caissiere === 'Bon de livraison')
                .forEach(des => {
                    const option = document.createElement('option');
                    option.value = des.id;
                    option.textContent = des.nom;
                    designationSelect.appendChild(option);
                });
        } catch (error) {
            console.error('Erreur lors du chargement des designations:', error);
            designationSelect.innerHTML = '<option value="">Erreur de chargement</option>';
        }

        updateLivraisonsCount();
    }

    function removeLivraisonRow(button) {
        const tbody = document.getElementById('livraisons-tbody');
        const row = button.closest('tr');

        if (tbody.querySelectorAll('tr').length > 0) {
            row.remove();
            updateLivraisonsCount();
        }
    }

    function updateLivraisonsCount() {
        const count = document.querySelectorAll('#livraisons-tbody tr').length;
        const countElement = document.getElementById('livraisons-count');
        if (countElement) {
            countElement.textContent = count;
        }
    }

    function addPaiementRow() {
        const tbody = document.getElementById('paiements-tbody');
        const ouvrageId = document.getElementById('ouvrage')?.value || '';
        if (!ouvrageId) {
            alert("Veuillez d'abord selectionner un ouvrage");
            return;
        }
        const newRow = document.createElement('tr');
        newRow.className = 'paiement-row';
        newRow.innerHTML = `
            <td>
                <select name="paiement_point_eau_id[]" class="select select-bordered select-sm w-56 point-eau-select" onchange="handlePaiementPointEauChange(this)">
                    <option value="">-</option>
                </select>
            </td>
            <td>
                <input type="date" name="paiement_date_facture[]" class="input input-bordered input-sm w-36">
            </td>
            <td>
                <input type="number" name="paiement_quantite[]" class="input input-bordered input-sm w-20 paiement-quantite-input" step="1" min="0" value="1" oninput="updatePaiementMontant(this)">
            </td>
            <td>
                <input type="number" name="paiement_prix_unitaire[]" class="input input-bordered input-sm w-24 paiement-prix-input bg-base-200 cursor-not-allowed" step="0.01" value="0" oninput="updatePaiementMontant(this)" readonly>
            </td>
            <td>
                <input type="number" name="paiement_montant[]" class="input input-bordered input-sm w-24 paiement-montant-input" step="0.01" value="0" readonly>
            </td>
            <td>
                <select name="paiement_paye[]" class="select select-bordered select-sm w-20" onchange="handlePaiementPayeChange(this)">
                    <option value="0" selected>Non</option>
                    <option value="1">Oui</option>
                </select>
            </td>
            <td>
                <button type="button" class="btn btn-ghost btn-xs text-error" onclick="removePaiementRow(this)">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
            </td>
        `;
        tbody.appendChild(newRow);
        const pointEauSelect = newRow.querySelector('.point-eau-select');
        if (typeof window.loadPointsEauByOuvrage === 'function' && pointEauSelect) {
            window.loadPointsEauByOuvrage(ouvrageId, [pointEauSelect]);
        }
        updatePaiementsCount();
    }

    function removePaiementRow(button) {
        const tbody = document.getElementById('paiements-tbody');
        const row = button.closest('tr');

        if (tbody.querySelectorAll('tr').length > 0) {
            row.remove();
            updatePaiementsCount();
        }
    }

    function updatePaiementsCount() {
        const count = document.querySelectorAll('#paiements-tbody tr').length;
        const countElement = document.getElementById('paiements-count');
        if (countElement) {
            countElement.textContent = count;
        }
    }

    function updatePaiementMontant(input) {
        const row = input.closest('tr');
        const quantiteInput = row.querySelector('.paiement-quantite-input');
        const prixInput = row.querySelector('.paiement-prix-input');
        const montantInput = row.querySelector('.paiement-montant-input');
        const quantite = parseFloat(quantiteInput.value) || 0;
        const prix = parseFloat(prixInput.value) || 0;
        montantInput.value = (quantite * prix).toFixed(2);
    }

    function handlePaiementPointEauChange(selectElement) {
        const row = selectElement.closest('tr');
        const selectedOption = selectElement.options[selectElement.selectedIndex];
        const tarif = selectedOption ? parseFloat(selectedOption.dataset.tarif) || 0 : 0;
        const prixInput = row.querySelector('.paiement-prix-input');
        if (prixInput) {
            prixInput.value = tarif.toFixed(2);
            prixInput.readOnly = true;
            prixInput.classList.add('bg-base-200', 'cursor-not-allowed');
        }
        updatePaiementMontant(selectElement);
    }

    function handlePaiementPayeChange(selectElement) {
        const row = selectElement.closest('tr');
        const isPaye = selectElement.value === '1';
        const datePaiementInput = row.querySelector('input[name="paiement_date_paiement[]"]');
        if (isPaye && datePaiementInput && !datePaiementInput.value) {
            const dateFactureInput = row.querySelector('input[name="paiement_date_facture[]"]');
            if (dateFactureInput && dateFactureInput.value) {
                datePaiementInput.value = dateFactureInput.value;
            } else {
                const today = new Date();
                const month = String(today.getMonth() + 1).padStart(2, '0');
                const day = String(today.getDate()).padStart(2, '0');
                datePaiementInput.value = `${today.getFullYear()}-${month}-${day}`;
            }
        }
    }

    window.addAvanceRow = addAvanceRow;
    window.populateAvanceDesignationSelects = populateAvanceDesignationSelects;
    window.addDeplacementRow = addDeplacementRow;
    window.removeAvanceRow = removeAvanceRow;
    window.updateTotalAvances = updateTotalAvances;
    window.addLivraisonRow = addLivraisonRow;
    window.removeLivraisonRow = removeLivraisonRow;
    window.updateLivraisonsCount = updateLivraisonsCount;
    window.addPaiementRow = addPaiementRow;
    window.removePaiementRow = removePaiementRow;
    window.updatePaiementsCount = updatePaiementsCount;
    window.updatePaiementMontant = updatePaiementMontant;
    window.handlePaiementPointEauChange = handlePaiementPointEauChange;
    window.handlePaiementPayeChange = handlePaiementPayeChange;
})();
