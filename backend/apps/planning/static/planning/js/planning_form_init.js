(function () {
    document.addEventListener('DOMContentLoaded', function () {
        const activiteSelect = document.getElementById('activite');
        const typeSelect = document.getElementById('type_activite');
        const savedActiviteValue = activiteSelect.dataset.selectedValue || activiteSelect.value;

        console.log('Valeur activité sauvegardée:', savedActiviteValue);
        console.log('Valeur type activité actuelle:', typeSelect.value);

        if (savedActiviteValue) {
            const savedOption = activiteSelect.querySelector(`option[value="${savedActiviteValue}"]`);
            if (savedOption) {
                const typeId = savedOption.dataset.typeId;
                console.log('Type ID de l\'activité sauvegardée:', typeId);
                if (typeId && !typeSelect.value) {
                    typeSelect.value = typeId;
                }
            }
        }

        if (typeof window.filterActivites === 'function') {
            window.filterActivites();
        }
        const initialTypeId = typeSelect.value;
        if (initialTypeId && typeof window.loadDesignationsByActivite === 'function') {
            window.loadDesignationsByActivite(initialTypeId);
        }

        if (savedActiviteValue) {
            activiteSelect.value = savedActiviteValue;
            const selectedOption = activiteSelect.querySelector(`option[value="${savedActiviteValue}"]`);
            if (selectedOption) {
                selectedOption.style.display = '';
                console.log('Activité restaurée:', selectedOption.textContent);
            } else {
                console.warn('Option activité non trouvée pour ID:', savedActiviteValue);
            }
        }

        if (typeof window.updateTotal === 'function') {
            window.updateTotal();
        }

        const chefSelect = document.getElementById('employe');
        const participantsSelect = document.getElementById('participants');
        if (chefSelect && participantsSelect && !participantsSelect.disabled) {
            const ensureChefParticipant = () => {
                if (!chefSelect.value) {
                    return;
                }
                Array.from(participantsSelect.options).forEach(option => {
                    if (option.value === chefSelect.value) {
                        option.selected = true;
                    }
                });
            };

            chefSelect.addEventListener('change', ensureChefParticipant);
            ensureChefParticipant();
        }
        if (chefSelect) {
            chefSelect.addEventListener('change', window.updatePlanningQuickLinks);
            chefSelect.addEventListener('change', window.refreshActiviteOptionLabels);
            window.updatePlanningQuickLinks();
            window.refreshActiviteOptionLabels();
        } else {
            window.updatePlanningQuickLinks();
            window.refreshActiviteOptionLabels();
        }

        if (typeof window.bindOuvrageDependentListeners === 'function') {
            window.bindOuvrageDependentListeners();
        }
        if (typeof window.bindActiviteDependentListeners === 'function') {
            window.bindActiviteDependentListeners();
        }

        const datePlanningInput = document.querySelector('input[name="date_planning"]');
        const remarqueInput = document.querySelector('textarea[name="remarque"]');
        const ouvrageSearchInput = document.getElementById('ouvrage-search');
        const ouvrageHiddenInput = document.getElementById('ouvrage');
        const monthlyPreviewInputs = [
            chefSelect,
            datePlanningInput,
            activiteSelect,
            typeSelect,
            remarqueInput,
            ouvrageSearchInput,
            ouvrageHiddenInput,
        ];

        monthlyPreviewInputs.forEach(input => {
            if (!input) {
                return;
            }
            input.addEventListener('change', window.scheduleMonthlyPreviewRefresh);
            input.addEventListener('input', window.scheduleMonthlyPreviewRefresh);
        });
        window.scheduleMonthlyPreviewRefresh();

        const ouvrageInput = document.getElementById('ouvrage');
        if (ouvrageInput) {
            ouvrageInput.addEventListener('change', function () {
                document.querySelectorAll('.detail-row').forEach(row => {
                    const equipementSelect = row.querySelector('.equipement-select');
                    const pointEauSelect = row.querySelector('.point-eau-select');

                    if (equipementSelect && typeof window.loadEquipementsByOuvrage === 'function') {
                        window.loadEquipementsByOuvrage(ouvrageInput.value, [equipementSelect]);
                    }
                    if (pointEauSelect && typeof window.loadPointsEauByOuvrage === 'function') {
                        window.loadPointsEauByOuvrage(ouvrageInput.value, [pointEauSelect]);
                    }
                });
            });
        }

        const ouvrageId = document.getElementById('ouvrage').value;
        const typeActiviteId = document.getElementById('type_activite').value;

        if (ouvrageId) {
            if (typeof window.loadEquipementsByOuvrage === 'function') {
                window.loadEquipementsByOuvrage(ouvrageId);
            }
            if (typeof window.loadPointsEauByOuvrage === 'function') {
                window.loadPointsEauByOuvrage(ouvrageId);
            }
        }

        if (typeActiviteId && typeof window.loadDesignationsByActivite === 'function') {
            window.loadDesignationsByActivite(typeActiviteId);
        }

        document.querySelectorAll('.detail-row').forEach(row => {
            const designationSelect = row.querySelector('.designation-select');
            const compteSelect = row.querySelector('.compte-select');

            if (designationSelect && designationSelect.value && compteSelect && typeof window.loadComptesByDesignation === 'function') {
                window.loadComptesByDesignation(designationSelect.value, compteSelect);
            }

            const quantityInput = row.querySelector('.quantity-input');
            const puInput = row.querySelector('.pu-input');
            const montantInput = row.querySelector('.montant-input');

            if (quantityInput && quantityInput.dataset.original) {
                quantityInput.value = quantityInput.dataset.original;
            }
            if (puInput && puInput.dataset.original) {
                puInput.value = puInput.dataset.original;
            }
            if (montantInput && montantInput.dataset.original) {
                montantInput.value = montantInput.dataset.original;
            }
        });

        document.querySelectorAll('#avances-tbody .designation-select').forEach(select => {
            if (select.value && typeof window.handleDesignationChange === 'function') {
                window.handleDesignationChange(select);
            }
        });

        if (window.planningFormConfig && window.planningFormConfig.isValidatedPlanning) {
            const fieldsToDisable = [
                'type_activite',
                'activite',
                'ouvrage',
                'remarque'
            ];

            fieldsToDisable.forEach(fieldName => {
                const field = document.querySelector(`[name="${fieldName}"]`);
                if (field) {
                    field.disabled = true;
                    field.classList.add('opacity-50', 'cursor-not-allowed');
                }
            });

            const detailsInputs = document.querySelectorAll('#details-tbody input, #details-tbody select, #details-tbody button');
            detailsInputs.forEach(input => {
                input.disabled = true;
                input.classList.add('opacity-50', 'cursor-not-allowed');
            });

            const addButton = document.querySelector('button[onclick*="addRow"]');
            if (addButton) {
                addButton.style.display = 'none';
            }
        }

        if (typeof window.ensureVillagesDatalist === 'function') {
            window.ensureVillagesDatalist();
        }
        if (typeof window.bindAvanceAutocompleteSync === 'function') {
            window.bindAvanceAutocompleteSync();
        }
    });
})();
