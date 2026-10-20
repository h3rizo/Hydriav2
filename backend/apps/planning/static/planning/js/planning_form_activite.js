(function () {
    function getPlanningFormConfig() {
        return window.planningFormConfig || {};
    }

    function getEditableAvanceDesignationsData() {
        return window.editableAvanceDesignationsData || [];
    }

    function populateAvanceDesignationSelects(selectElements) {
        selectElements.forEach(select => {
            const currentValue = select.value;
            select.innerHTML = '<option value="">Selectionner</option>';

            getEditableAvanceDesignationsData().forEach(des => {
                const option = document.createElement('option');
                option.value = des.id;
                option.textContent = des.nom;
                option.dataset.typeAvance = 'avance';
                option.dataset.prixUnitaire = des.prix_unitaire || 0;
                option.dataset.posteAcheteur = des.poste_acheteur || '';
                option.dataset.concerneLivraison = des.concerne_livraison ? 'true' : 'false';
                if (des.id === currentValue) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            if (select.value && typeof window.handleDesignationChange === 'function') {
                window.handleDesignationChange(select);
            }
        });
    }

    function clearDesignationSelects() {
        document.querySelectorAll('.designation-select').forEach(select => {
            select.innerHTML = '<option value="">Selectionner</option>';
        });
    }

    function filterActivites() {
        const typeSelect = document.getElementById('type_activite');
        const employeSelect = document.getElementById('employe');
        const activiteSelect = document.getElementById('activite');
        if (!typeSelect || !activiteSelect) {
            return;
        }

        const selectedTypeId = typeSelect.value;
        const selectedPosteId = typeof window.getEmployePosteId === 'function'
            ? window.getEmployePosteId(employeSelect ? employeSelect.value : '')
            : '';

        const currentValue = activiteSelect.value;
        const options = Array.from(activiteSelect.querySelectorAll('option'));
        let isCurrentValueValid = false;

        options.forEach(option => {
            if (option.value === '') {
                option.style.display = '';
                return;
            }

            const allowedForType = !selectedTypeId || option.dataset.typeId === selectedTypeId;
            const allowedForPoste = typeof window.isFicheAllowedForPoste === 'function'
                ? window.isFicheAllowedForPoste(option.value, selectedPosteId)
                : true;

            if (allowedForType && allowedForPoste) {
                option.style.display = '';
                if (option.value === currentValue) {
                    isCurrentValueValid = true;
                }
            } else {
                option.style.display = 'none';
            }
        });

        if (!isCurrentValueValid && currentValue !== '') {
            activiteSelect.value = '';
        }

        if (selectedTypeId) {
            loadDesignationsByActivite(selectedTypeId);
        } else {
            clearDesignationSelects();
        }

        if (typeof window.refreshActiviteOptionLabels === 'function') {
            window.refreshActiviteOptionLabels();
        }
    }

    async function loadDesignationsByActivite(typeActiviteId) {
        if (!typeActiviteId) {
            return;
        }

        try {
            populateAvanceDesignationSelects(
                Array.from(document.querySelectorAll('select[name="avance_designation_id[]"]'))
            );
        } catch (error) {
            console.error('Erreur lors du chargement des designations:', error);
        }
    }

    async function loadComptesByDesignation(designationId, selectElement) {
        if (!selectElement) {
            return;
        }
        if (!designationId) {
            selectElement.innerHTML = '<option value="">Selectionner</option>';
            return;
        }

        const config = getPlanningFormConfig();
        if (!config.apiComptesByDesignationUrl) {
            return;
        }

        try {
            const response = await fetch(`${config.apiComptesByDesignationUrl}?designation_id=${designationId}`);
            const data = await response.json();

            const currentValue = selectElement.value;
            selectElement.innerHTML = '<option value="">Selectionner</option>';

            (data.comptes || []).forEach((compte, index) => {
                const option = document.createElement('option');
                option.value = compte.id;
                option.textContent = `${compte.code} - ${compte.nom}`;

                if (!currentValue && index === 0) {
                    option.selected = true;
                } else if (compte.id === currentValue) {
                    option.selected = true;
                }

                selectElement.appendChild(option);
            });
        } catch (error) {
            console.error('Erreur lors du chargement des comptes:', error);
        }
    }

    function bindActiviteDependentListeners() {
        const typeActiviteSelect = document.getElementById('type_activite');
        if (typeActiviteSelect) {
            typeActiviteSelect.addEventListener('change', function () {
                filterActivites();
            });
        }

        const activiteSelect = document.getElementById('activite');
        if (activiteSelect) {
            activiteSelect.addEventListener('change', function () {
                const typeActiviteId = document.getElementById('type_activite')?.value;
                if (typeActiviteId) {
                    loadDesignationsByActivite(typeActiviteId);
                } else {
                    clearDesignationSelects();
                }
            });
        }

        const employeSelect = document.getElementById('employe');
        if (employeSelect) {
            employeSelect.addEventListener('change', function () {
                filterActivites();
            });
        }
    }

    window.populateAvanceDesignationSelects = populateAvanceDesignationSelects;
    window.filterActivites = filterActivites;
    window.loadDesignationsByActivite = loadDesignationsByActivite;
    window.loadComptesByDesignation = loadComptesByDesignation;
    window.bindActiviteDependentListeners = bindActiviteDependentListeners;
})();
