(function () {
    function getPlanningFormConfig() {
        return window.planningFormConfig || {};
    }

    function getOuvragesData() {
        return window.ouvragesData || [];
    }

    function normalizeText(value) {
        return String(value || '').trim().toLowerCase();
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function buildOuvrageOptionHtml(ouvrage) {
        const ouvrageId = escapeHtml(ouvrage.id || '');
        const ouvrageNom = escapeHtml(ouvrage.nom || '');
        return `
            <div
                class="p-2 hover:bg-base-200 cursor-pointer border-b border-base-300 last:border-b-0"
                data-ouvrage-option="1"
                data-ouvrage-id="${ouvrageId}"
                data-ouvrage-nom="${ouvrageNom}"
            >
                ${ouvrageNom}
            </div>
        `;
    }

    function findMatchingOuvrageByName(name) {
        const normalizedName = normalizeText(name);
        if (!normalizedName) {
            return null;
        }

        return getOuvragesData().find(o => normalizeText(o.nom) === normalizedName) || null;
    }

    function syncOuvrageSelectionFromSearchInput() {
        const ouvrageInput = document.getElementById('ouvrage');
        const ouvrageSearchInput = document.getElementById('ouvrage-search');
        if (!ouvrageInput || !ouvrageSearchInput) {
            return;
        }

        const searchValue = ouvrageSearchInput.value.trim();
        if (!searchValue) {
            ouvrageInput.value = '';
            return;
        }

        const matchedOuvrage = findMatchingOuvrageByName(searchValue);
        if (matchedOuvrage) {
            ouvrageInput.value = matchedOuvrage.id;
            ouvrageSearchInput.value = matchedOuvrage.nom || searchValue;
            return;
        }

        const currentSelection = getOuvragesData().find(o => String(o.id) === String(ouvrageInput.value || ''));
        if (!currentSelection || normalizeText(currentSelection.nom) !== normalizeText(searchValue)) {
            ouvrageInput.value = '';
        }
    }

    function filterOuvragesList() {
        const searchInput = document.getElementById('ouvrage-search');
        const ouvragesList = document.getElementById('ouvrages-list');
        if (!searchInput || !ouvragesList) {
            return;
        }

        const searchTerm = searchInput.value.toLowerCase();
        if (searchTerm.length < 1) {
            ouvragesList.classList.add('hidden');
            return;
        }

        const filteredOuvrages = getOuvragesData().filter(o =>
            (o.nom || '').toLowerCase().includes(searchTerm)
        );

        if (filteredOuvrages.length === 0) {
            ouvragesList.innerHTML = '<div class="p-4 text-sm text-base-content/70">Aucun ouvrage trouve</div>';
        } else {
            ouvragesList.innerHTML = filteredOuvrages.map(buildOuvrageOptionHtml).join('');
        }

        ouvragesList.classList.remove('hidden');
    }

    function showOuvragesList() {
        const ouvragesList = document.getElementById('ouvrages-list');
        const searchInput = document.getElementById('ouvrage-search');
        if (!ouvragesList || !searchInput) {
            return;
        }

        if (searchInput.value.length >= 1) {
            filterOuvragesList();
        } else {
            ouvragesList.innerHTML = getOuvragesData().map(buildOuvrageOptionHtml).join('');
            ouvragesList.classList.remove('hidden');
        }
    }

    function selectOuvrage(id, nom) {
        const ouvrageInput = document.getElementById('ouvrage');
        const ouvrageSearchInput = document.getElementById('ouvrage-search');
        const ouvragesList = document.getElementById('ouvrages-list');
        if (!ouvrageInput || !ouvrageSearchInput || !ouvragesList) {
            return;
        }

        ouvrageSearchInput.value = nom;
        ouvrageInput.value = id;
        ouvragesList.classList.add('hidden');

        loadEquipementsByOuvrage(id);
        loadPointsEauByOuvrage(id);

        ouvrageInput.dispatchEvent(new Event('change'));
    }

    function resolveOuvrageId(ouvrageInputOrId) {
        if (typeof ouvrageInputOrId === 'string') {
            return ouvrageInputOrId.trim();
        }
        if (
            ouvrageInputOrId &&
            typeof ouvrageInputOrId.value === 'string' &&
            ouvrageInputOrId.tagName === 'INPUT' &&
            ouvrageInputOrId.type === 'hidden'
        ) {
            return ouvrageInputOrId.value.trim();
        }
        const ouvrageField = document.getElementById('ouvrage');
        return ouvrageField && ouvrageField.value ? ouvrageField.value.trim() : '';
    }

    function populateEquipementSelects(equipements, selectElements) {
        selectElements.forEach(select => {
            const currentValue = select.value;
            select.innerHTML = '<option value="">-</option>';

            (equipements || []).forEach(equip => {
                const option = document.createElement('option');
                option.value = equip.id;
                option.textContent = equip.nom;
                if (equip.id === currentValue) {
                    option.selected = true;
                }
                select.appendChild(option);
            });
        });
    }

    function getPointEauOptionLabel(pointEau, selectElement) {
        if (selectElement && selectElement.closest('.paiement-row')) {
            return pointEau.forfaitaire_label || pointEau.nom_abonne || pointEau.nom || pointEau.idxls || '-';
        }
        return pointEau.nom || pointEau.nom_abonne || pointEau.idxls || '-';
    }

    function populatePointEauSelects(pointsEau, selectElements) {
        selectElements.forEach(select => {
            const currentValue = select.value;
            select.innerHTML = '<option value="">-</option>';

            (pointsEau || []).forEach(pe => {
                const option = document.createElement('option');
                option.value = pe.id;
                option.textContent = getPointEauOptionLabel(pe, select);
                option.dataset.tarif = pe.tarif || 0;
                if (pe.id === currentValue) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            if (select.value && select.closest('.paiement-row') && typeof window.handlePaiementPointEauChange === 'function') {
                window.handlePaiementPointEauChange(select);
            }
        });
    }

    async function loadEquipementsByOuvrage(ouvrageInputOrId, targetSelects = null) {
        const ouvrageId = resolveOuvrageId(ouvrageInputOrId);
        const selectElements = targetSelects || document.querySelectorAll('.equipement-select');
        if (!ouvrageId) {
            populateEquipementSelects([], Array.from(selectElements));
            return;
        }

        const config = getPlanningFormConfig();
        if (!config.apiEquipementsByOuvrageUrl) {
            return;
        }

        try {
            const response = await fetch(`${config.apiEquipementsByOuvrageUrl}?ouvrage_id=${ouvrageId}`);
            const data = await response.json();
            populateEquipementSelects(data.equipements || [], Array.from(selectElements));
        } catch (error) {
            console.error('Erreur lors du chargement des equipements:', error);
        }
    }

    async function loadPointsEauByOuvrage(ouvrageInputOrId, targetSelects = null) {
        const ouvrageId = resolveOuvrageId(ouvrageInputOrId);
        const selectElements = targetSelects || document.querySelectorAll('.point-eau-select');
        if (!ouvrageId) {
            populatePointEauSelects([], Array.from(selectElements));
            return;
        }

        const config = getPlanningFormConfig();
        if (!config.apiPointsEauByOuvrageUrl) {
            return;
        }

        try {
            const response = await fetch(`${config.apiPointsEauByOuvrageUrl}?ouvrage_id=${ouvrageId}`);
            const data = await response.json();
            populatePointEauSelects(data.points_eau || [], Array.from(selectElements));
        } catch (error) {
            console.error("Erreur lors du chargement des points d'eau:", error);
        }
    }

    function bindOuvrageDependentListeners() {
        const ouvrageInput = document.getElementById('ouvrage');
        if (ouvrageInput) {
            ouvrageInput.addEventListener('change', function () {
                const ouvrageId = this.value;
                if (ouvrageId) {
                    loadEquipementsByOuvrage(ouvrageId);
                    loadPointsEauByOuvrage(ouvrageId);
                } else {
                    document.querySelectorAll('.equipement-select').forEach(select => {
                        select.innerHTML = '<option value="">-</option>';
                    });
                    document.querySelectorAll('.point-eau-select').forEach(select => {
                        select.innerHTML = '<option value="">-</option>';
                    });
                }
            });
        }

        const ouvrageSearchInput = document.getElementById('ouvrage-search');
        if (ouvrageSearchInput) {
            ouvrageSearchInput.addEventListener('input', function () {
                const ouvrageInputField = document.getElementById('ouvrage');
                if (!ouvrageInputField) {
                    return;
                }

                const currentSelection = getOuvragesData().find(
                    o => String(o.id) === String(ouvrageInputField.value || '')
                );
                if (!currentSelection || normalizeText(currentSelection.nom) !== normalizeText(this.value)) {
                    ouvrageInputField.value = '';
                }
            });

            ouvrageSearchInput.addEventListener('blur', syncOuvrageSelectionFromSearchInput);
        }

        const planningForm = document.getElementById('planningForm');
        if (planningForm) {
            planningForm.addEventListener('submit', syncOuvrageSelectionFromSearchInput);
        }

        document.addEventListener('click', function (event) {
            const ouvragesList = document.getElementById('ouvrages-list');
            const searchInput = document.getElementById('ouvrage-search');
            if (!ouvragesList || !searchInput) {
                return;
            }
            const optionElement = event.target.closest('[data-ouvrage-option="1"]');
            if (optionElement && ouvragesList.contains(optionElement)) {
                selectOuvrage(
                    optionElement.getAttribute('data-ouvrage-id') || '',
                    optionElement.getAttribute('data-ouvrage-nom') || ''
                );
                return;
            }
            if (!ouvragesList.contains(event.target) && event.target !== searchInput) {
                ouvragesList.classList.add('hidden');
            }
        });
    }

    window.filterOuvragesList = filterOuvragesList;
    window.showOuvragesList = showOuvragesList;
    window.selectOuvrage = selectOuvrage;
    window.resolveOuvrageId = resolveOuvrageId;
    window.populateEquipementSelects = populateEquipementSelects;
    window.populatePointEauSelects = populatePointEauSelects;
    window.loadEquipementsByOuvrage = loadEquipementsByOuvrage;
    window.loadPointsEauByOuvrage = loadPointsEauByOuvrage;
    window.bindOuvrageDependentListeners = bindOuvrageDependentListeners;
    window.syncOuvrageSelectionFromSearchInput = syncOuvrageSelectionFromSearchInput;
})();
