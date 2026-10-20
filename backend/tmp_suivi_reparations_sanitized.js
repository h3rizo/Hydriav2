
const defaultOrganisationFilter = 'null';

let currentFilters = {
    organisation: 'null',
    region_id: 'all',
    district_id: 'all',
    commune_id: 'all',
    employe_id: 'all',
    recherche: '',
    statut: 'all',  // Filtre de statut de réparation
    grading: 'all',  // Filtre de grading
    annee: 'null'
};

let allOuvrages = [];  // Stocker tous les ouvrages pour filtrage côté client
let currentModalReparations = [];  // Réparations chargées dans le modal "Voir"
let currentFilteredOuvrages = [];  // Ouvrages après filtres client
let allScopedReparations = [];  // Réparations du périmètre courant pour la vue Suite à donner
let editRepairPhotosData = [];  // Photos preuve du modal d'édition

let currentView = 'suite'; // Vue par défaut: suite à donner

const designationAvanceNameToId = {
    
    "null": "null",
    
};
const designationAvanceIdToName = {
    
    "null": "null",
    
};
const designationAvanceIdToPu = {
    
    "null": "null",
    
};
const designationBonNameToId = {
    
    "null": "null",
    
};
const designationBonIdToName = {
    
    "null": "null",
    
};
const pointEauxList = [
    
    {
        id: "null",
        name: "null",
        ouvrage_id: "null",
    },
    
];
const equipementsList = [
    
    {
        id: "null",
        name: "null",
        ouvrage_id: "null",
    },
    
];
const magasinsList = [
    
    {
        value: "null",
        label: "null (null)"
    },
    
];

function normalizeText(value) {
    return (value || '')
        .toString()
        .trim()
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '');
}

function classifyRepairFicheClient(fiche) {
    const typeName = normalizeText(fiche?.type_activites_nom || '');
    const ficheLabel = normalizeText(fiche?.tache || '');
    const combined = `${typeName} ${ficheLabel}`.trim();

    if (
        combined.includes('habilitation')
        && !combined.includes('preparation')
    ) {
        return 'rehabilitation';
    }

    if (
        combined.includes('paration')
        && !combined.includes('preparation')
        && !combined.includes('au cas ou')
    ) {
        return 'reparation';
    }

    if (combined.includes('panne')) {
        return 'panne';
    }

    return '';
}

function buildRepairFicheOptionsHtml(fiches) {
    const groups = new Map();
    const sortedFiches = [...fiches].sort((a, b) => {
        const typeCompare = (a.type_activites_nom || '').localeCompare(b.type_activites_nom || '', 'fr', { sensitivity: 'base' });
        if (typeCompare !== 0) {
            return typeCompare;
        }
        return (a.tache || '').localeCompare(b.tache || '', 'fr', { sensitivity: 'base' });
    });

    sortedFiches.forEach((fiche) => {
        const groupLabel = fiche.type_activites_nom || 'Sans type';
        if (!groups.has(groupLabel)) {
            groups.set(groupLabel, []);
        }
        groups.get(groupLabel).push(fiche);
    });

    let html = '<option value="">-- Sélectionner --</option>';
    groups.forEach((groupFiches, groupLabel) => {
        html += `<optgroup label="${groupLabel}">`;
        groupFiches.forEach((fiche) => {
            const optionLabel = `${fiche.tache || ''}${fiche.type_activites_nom ? ` - ${fiche.type_activites_nom}` : ''}`;
            html += `<option value="${fiche.id}">${optionLabel}</option>`;
        });
        html += '</optgroup>';
    });

    return html;
}

function renderRepairFicheOptions(selectId, fiches, selectedValue = '') {
    const select = document.getElementById(selectId);
    if (!select) return;

    const html = buildRepairFicheOptionsHtml(fiches);
    select.innerHTML = html;
    select.dataset.originalHtml = html;
    if (selectedValue) {
        select.value = selectedValue;
    }
}

async function refreshRepairFicheOptions(selectId, searchId, selectedValue = '') {
    const select = document.getElementById(selectId);
    if (!select) return;

    try {
        const response = await fetch('/plannings/crud/api/fiches-poste/', { cache: 'no-store' });
        if (!response.ok) {
            return;
        }

        const data = await response.json();
        const repairFiches = (Array.isArray(data) ? data : []).filter((fiche) =>
            ['reparation', 'rehabilitation', 'panne'].includes(classifyRepairFicheClient(fiche))
        );

        renderRepairFicheOptions(selectId, repairFiches, selectedValue);

        const search = document.getElementById(searchId);
        if (search) {
            search.value = '';
        }
    } catch (error) {
        console.error('Erreur chargement fiches de poste:', error);
    }
}

function filterFichePosteOptions(selectId, searchId) {
    const select = document.getElementById(selectId);
    const search = document.getElementById(searchId);
    if (!select || !search) return;

    if (!select.dataset.originalHtml) {
        select.dataset.originalHtml = select.innerHTML;
    }

    const query = normalizeText(search.value);
    const previousValue = select.value;

    if (!query) {
        select.innerHTML = select.dataset.originalHtml;
        if (previousValue) {
            select.value = previousValue;
        }
        return;
    }

    const parser = document.createElement('template');
    parser.innerHTML = `<select>${select.dataset.originalHtml}</select>`;
    const sourceSelect = parser.content.firstElementChild;
    const filteredSelect = document.createElement('select');

    Array.from(sourceSelect.children).forEach((child) => {
        if (child.tagName === 'OPTION') {
            const matches = normalizeText(child.textContent).includes(query) || child.value === '';
            if (matches) {
                filteredSelect.appendChild(child.cloneNode(true));
            }
            return;
        }

        if (child.tagName === 'OPTGROUP') {
            const matchingOptions = Array.from(child.children).filter((option) =>
                normalizeText(option.textContent).includes(query)
            );
            if (matchingOptions.length) {
                const optgroup = document.createElement('optgroup');
                optgroup.label = child.label;
                matchingOptions.forEach((option) => optgroup.appendChild(option.cloneNode(true)));
                filteredSelect.appendChild(optgroup);
            }
        }
    });

    select.innerHTML = filteredSelect.innerHTML || '<option value="">Aucune fiche trouvée</option>';
    if (previousValue) {
        select.value = previousValue;
    }
}

function initFichePosteSearch(selectId, searchId) {
    const select = document.getElementById(selectId);
    const search = document.getElementById(searchId);
    if (!select || !search) return;

    if (!select.dataset.originalHtml) {
        select.dataset.originalHtml = select.innerHTML;
    }

    search.addEventListener('input', () => filterFichePosteOptions(selectId, searchId));
}

function resetFichePosteSearch(selectId, searchId) {
    const select = document.getElementById(selectId);
    const search = document.getElementById(searchId);
    if (!select || !search) return;

    search.value = '';
    if (select.dataset.originalHtml) {
        const currentValue = select.value;
        select.innerHTML = select.dataset.originalHtml;
        if (currentValue) {
            select.value = currentValue;
        }
    }
}

function resolveDesignationIdInMap(value, nameToIdMap) {
    const normalized = normalizeText(value);
    if (!normalized) return '';
    const exactEntry = Object.entries(nameToIdMap).find(([name]) => normalizeText(name) === normalized);
    if (exactEntry) return exactEntry[1];
    const starts = Object.entries(nameToIdMap).filter(([name]) => normalizeText(name).startsWith(normalized));
    if (starts.length === 1) return starts[0][1];
    return '';
}

function findPointEauByName(value, ouvrageId = '') {
    const normalized = normalizeText(value);
    if (!normalized) return null;
    const matches = pointEauxList.filter(item => {
        if (ouvrageId && item.ouvrage_id && item.ouvrage_id !== ouvrageId) return false;
        return normalizeText(item.name) === normalized || normalizeText(item.name).startsWith(normalized);
    });
    return matches.length === 1 ? matches[0] : null;
}

function findEquipementByName(value, ouvrageId = '') {
    const normalized = normalizeText(value);
    if (!normalized) return null;
    const matches = equipementsList.filter(item => {
        if (ouvrageId && item.ouvrage_id && item.ouvrage_id !== ouvrageId) return false;
        return normalizeText(item.name) === normalized || normalizeText(item.name).startsWith(normalized);
    });
    return matches.length === 1 ? matches[0] : null;
}

function populateRepairTargetSelects(prefix, selectedPointEauId = '', selectedEquipementId = '') {
    const ouvrageId = document.getElementById(`${prefix}-ouvrage-id`)?.value || '';
    const pointSelect = document.getElementById(`${prefix}-point-eau-id`);
    const equipSelect = document.getElementById(`${prefix}-equipement-id`);
    if (!pointSelect || !equipSelect) return;

    const points = pointEauxList
        .filter(item => !ouvrageId || !item.ouvrage_id || item.ouvrage_id === ouvrageId)
        .sort((a, b) => (a.name || '').localeCompare(b.name || '', 'fr', { sensitivity: 'base' }));
    pointSelect.innerHTML = `<option value="">-- Sélectionner un point d'eau --</option>`
        + points.map(item => `<option value="${item.id}">${item.name}</option>`).join('');
    pointSelect.value = selectedPointEauId || '';

    const equipements = equipementsList
        .filter(item => !ouvrageId || !item.ouvrage_id || item.ouvrage_id === ouvrageId)
        .sort((a, b) => (a.name || '').localeCompare(b.name || '', 'fr', { sensitivity: 'base' }));
    equipSelect.innerHTML = '<option value="">-- Sélectionner un équipement --</option>'
        + equipements.map(item => `<option value="${item.id}">${item.name}</option>`).join('');
    equipSelect.value = selectedEquipementId || '';
}

function updateRepairTargetVisibility(prefix) {
    const type = document.getElementById(`${prefix}-target-type`)?.value || '';
    const pointWrapper = document.getElementById(`${prefix}-point-eau-wrapper`);
    const equipWrapper = document.getElementById(`${prefix}-equipement-wrapper`);
    const pointSelect = document.getElementById(`${prefix}-point-eau-id`);
    const equipSelect = document.getElementById(`${prefix}-equipement-id`);

    if (pointWrapper) {
        const showPoint = type === 'point_eau';
        pointWrapper.classList.toggle('hidden', !showPoint);
        pointWrapper.style.display = showPoint ? '' : 'none';
    }
    if (equipWrapper) {
        const showEquip = type === 'equipement';
        equipWrapper.classList.toggle('hidden', !showEquip);
        equipWrapper.style.display = showEquip ? '' : 'none';
    }

    if (type === 'point_eau' && equipSelect) {
        equipSelect.value = '';
    }
    if (type === 'equipement' && pointSelect) {
        pointSelect.value = '';
    }
    if (!type) {
        if (pointSelect) pointSelect.value = '';
        if (equipSelect) equipSelect.value = '';
    }
}

function initRepairTargetFields(prefix) {
    const typeSelect = document.getElementById(`${prefix}-target-type`);
    const pointSelect = document.getElementById(`${prefix}-point-eau-id`);
    const equipSelect = document.getElementById(`${prefix}-equipement-id`);
    if (!typeSelect || !pointSelect || !equipSelect) return;

    typeSelect.addEventListener('change', () => updateRepairTargetVisibility(prefix));
    pointSelect.addEventListener('change', () => {
        if (pointSelect.value) {
            typeSelect.value = 'point_eau';
            equipSelect.value = '';
            updateRepairTargetVisibility(prefix);
        }
    });
    equipSelect.addEventListener('change', () => {
        if (equipSelect.value) {
            typeSelect.value = 'equipement';
            pointSelect.value = '';
            updateRepairTargetVisibility(prefix);
        }
    });

    populateRepairTargetSelects(prefix);
    updateRepairTargetVisibility(prefix);
}

function setRepairTargetFields(prefix, targetType = '', pointEauId = '', equipementId = '') {
    populateRepairTargetSelects(prefix, pointEauId, equipementId);
    const typeSelect = document.getElementById(`${prefix}-target-type`);
    if (typeSelect) {
        typeSelect.value = targetType || '';
    }
    updateRepairTargetVisibility(prefix);
}

function getRepairTargetPayload(prefix) {
    const targetType = document.getElementById(`${prefix}-target-type`)?.value || '';
    const pointEauId = document.getElementById(`${prefix}-point-eau-id`)?.value || '';
    const equipementId = document.getElementById(`${prefix}-equipement-id`)?.value || '';
    return {
        targetType,
        pointEauId: targetType === 'point_eau' ? pointEauId : '',
        equipementId: targetType === 'equipement' ? equipementId : '',
    };
}

function designationInputHtml(prefix, mode, data = {}) {
    const idToNameMap = mode === 'bon' ? designationBonIdToName : designationAvanceIdToName;
    const designationName = data.designation_nom || idToNameMap[data.designation_id] || '';
    const datalistId = mode === 'bon' ? 'designation-datalist-bon' : 'designation-datalist-avance';
    return `
        <input type="hidden" class="${prefix}-designation-id" value="${data.designation_id || ''}">
        <input type="text" list="${datalistId}" class="input input-bordered input-xs w-full ${prefix}-designation-name" value="${designationName}" placeholder="Rechercher désignation...">
    `;
}

function attachDesignationAutocomplete(tr, prefix, mode) {
    const input = tr.querySelector(`.${prefix}-designation-name`);
    const hidden = tr.querySelector(`.${prefix}-designation-id`);
    if (!input || !hidden) return;
    const nameToIdMap = mode === 'bon' ? designationBonNameToId : designationAvanceNameToId;
    const sync = () => {
        hidden.value = resolveDesignationIdInMap(input.value, nameToIdMap);
        if (prefix === 'detail') {
            const puField = tr.querySelector('.detail-pu');
            if (puField) {
                puField.value = designationAvanceIdToPu[hidden.value] || 0;
            }
        }
    };
    input.addEventListener('input', sync);
    input.addEventListener('change', sync);
    input.addEventListener('blur', sync);
}

function addDetailRow(prefix, data = {}) {
    const tbody = document.getElementById(`${prefix}-details-rows`);
    if (!tbody) return;

    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td>
            <input type="hidden" class="detail-id" value="${data.detail_id || ''}">
            ${designationInputHtml('detail', 'avance', data)}
        </td>
        <td><input type="number" class="input input-bordered input-xs w-20 min-w-20 detail-quantity" min="0" step="0.01" value="${data.quantity ?? ''}"></td>
        <td><input type="number" class="input input-bordered input-xs w-24 min-w-24 detail-pu bg-base-300" min="0" step="0.01" value="${data.pu ?? 0}" readonly></td>
        <td><button type="button" class="btn btn-xs btn-error" onclick="removeDetailRow(this)"><i class="fas fa-trash"></i></button></td>
    `;
    tbody.appendChild(tr);
    attachDesignationAutocomplete(tr, 'detail', 'avance');
    const designationId = data.designation_id || '';
    if (designationId) {
        const puField = tr.querySelector('.detail-pu');
        if (puField) {
            puField.value = designationAvanceIdToPu[designationId] || data.pu || 0;
        }
    }
}

function addBonRow(prefix, data = {}) {
    const tbody = document.getElementById(`${prefix}-bons-rows`);
    if (!tbody) return;
    const tr = document.createElement('tr');
    const selectedMagasin = (data.magasin || '').trim();
    const magasinOptions = ['<option value="">-- Sélectionner --</option>']
        .concat(magasinsList.map(m => `<option value="${m.value}" ${m.value === selectedMagasin ? 'selected' : ''}>${m.label}</option>`))
        .join('');

    tr.innerHTML = `
        <td>
            <input type="hidden" class="bon-id" value="${data.bon_id || data.id || ''}">
            ${designationInputHtml('bon', 'bon', data)}
        </td>
        <td><input type="number" class="input input-bordered input-xs w-20 min-w-20 bon-quantity" min="0" step="0.01" value="${data.quantite ?? ''}"></td>
        <td><select class="select select-bordered select-xs w-44 bon-magasin">${magasinOptions}</select></td>
        <td><button type="button" class="btn btn-xs btn-error" onclick="removeBonRow(this)"><i class="fas fa-trash"></i></button></td>
    `;
    tbody.appendChild(tr);
    attachDesignationAutocomplete(tr, 'bon', 'bon');
}

function removeDetailRow(btn) {
    const tbody = btn.closest('tbody');
    btn.closest('tr')?.remove();
    if (tbody && tbody.querySelectorAll('tr').length === 0) {
        const prefix = tbody.id.startsWith('edit-') ? 'edit' : 'add';
        addDetailRow(prefix);
    }
}

function removeBonRow(btn) {
    const tbody = btn.closest('tbody');
    btn.closest('tr')?.remove();
    if (tbody && tbody.querySelectorAll('tr').length === 0) {
        const prefix = tbody.id.startsWith('edit-') ? 'edit' : 'add';
        addBonRow(prefix);
    }
}

function resetDetailRows(prefix, rows = []) {
    const tbody = document.getElementById(`${prefix}-details-rows`);
    if (!tbody) return;
    tbody.innerHTML = '';
    if (rows.length === 0) {
        addDetailRow(prefix);
        return;
    }
    rows.forEach(row => addDetailRow(prefix, row));
}

function resetBonRows(prefix, rows = []) {
    const tbody = document.getElementById(`${prefix}-bons-rows`);
    if (!tbody) return;
    tbody.innerHTML = '';
    if (rows.length === 0) {
        addBonRow(prefix);
        return;
    }
    rows.forEach(row => addBonRow(prefix, row));
}

function collectDetailRows(prefix) {
    const tbody = document.getElementById(`${prefix}-details-rows`);
    if (!tbody) return [];
    const rows = [];
    tbody.querySelectorAll('tr').forEach(tr => {
        const designationId = tr.querySelector('.detail-designation-id')?.value || resolveDesignationIdInMap(
            tr.querySelector('.detail-designation-name')?.value || '',
            designationAvanceNameToId
        );
        if (!designationId) return;
        rows.push({
            detail_id: tr.querySelector('.detail-id')?.value || null,
            designation_id: designationId,
            quantity: tr.querySelector('.detail-quantity')?.value || 0,
            pu: tr.querySelector('.detail-pu')?.value || 0,
        });
    });
    return rows;
}

function collectBonRows(prefix) {
    const tbody = document.getElementById(`${prefix}-bons-rows`);
    if (!tbody) return [];
    const rows = [];
    tbody.querySelectorAll('tr').forEach(tr => {
        const designationId = tr.querySelector('.bon-designation-id')?.value || resolveDesignationIdInMap(
            tr.querySelector('.bon-designation-name')?.value || '',
            designationBonNameToId
        );
        if (!designationId) return;
        rows.push({
            bon_id: tr.querySelector('.bon-id')?.value || null,
            designation_id: designationId,
            quantite: tr.querySelector('.bon-quantity')?.value || 0,
            magasin: tr.querySelector('.bon-magasin')?.value || '',
        });
    });
    return rows;
}

function hasUnresolvedDesignation(prefix) {
    const detailRows = document.querySelectorAll(`#${prefix}-details-rows tr`);
    for (const tr of detailRows) {
        const name = tr.querySelector('.detail-designation-name')?.value?.trim() || '';
        const id = tr.querySelector('.detail-designation-id')?.value || '';
        if (name && !id) return true;
    }

    const bonRows = document.querySelectorAll(`#${prefix}-bons-rows tr`);
    for (const tr of bonRows) {
        const name = tr.querySelector('.bon-designation-name')?.value?.trim() || '';
        const id = tr.querySelector('.bon-designation-id')?.value || '';
        if (name && !id) return true;
    }
    return false;
}

// Charger les options de filtres (région, district, commune)
async function loadFilterOptions() {
    const organisationSelect = document.getElementById('filter-organisation');
    const organisation = organisationSelect ? organisationSelect.value : (currentFilters.organisation || defaultOrganisationFilter || 'all');
    currentFilters.organisation = organisation;
    const annee = document.getElementById('filter-annee').value || currentFilters.annee || 'all';
    const region_id = document.getElementById('filter-region').value;
    const district_id = document.getElementById('filter-district').value;
    const commune_id = document.getElementById('filter-commune').value;
    const employeSelect = document.getElementById('filter-employe');
    const currentEmploye = employeSelect ? (employeSelect.value || 'all') : (currentFilters.employe_id || 'all');

    try {
        const url = `?organisation=${encodeURIComponent(organisation)}&annee=${encodeURIComponent(annee)}&region_id=${encodeURIComponent(region_id)}&district_id=${encodeURIComponent(district_id)}&commune_id=${encodeURIComponent(commune_id)}`;
        const response = await fetch(url);
        const data = await response.json();

        if (data.success) {
            // Mettre à jour les regions
            const regionSelect = document.getElementById('filter-region');
            const currentRegion = regionSelect.value;
            regionSelect.innerHTML = '<option value="all">Toutes les régions</option>';
            data.regions.forEach(r => {
                regionSelect.innerHTML += `<option value="${r.id}" ${r.id === currentRegion ? 'selected' : ''}>${r.nom}</option>`;
            });

            // Mettre à jour les districts
            const districtSelect = document.getElementById('filter-district');
            const currentDistrict = districtSelect.value;
            districtSelect.innerHTML = '<option value="all">Tous les districts</option>';
            data.districts.forEach(d => {
                districtSelect.innerHTML += `<option value="${d.id}" ${d.id === currentDistrict ? 'selected' : ''}>${d.nom}</option>`;
            });

            // Mettre à jour les communes
            const communeSelect = document.getElementById('filter-commune');
            const currentCommune = communeSelect.value;
            communeSelect.innerHTML = '<option value="all">Toutes les communes</option>';
            data.communes.forEach(c => {
                communeSelect.innerHTML += `<option value="${c.id}" ${c.id === currentCommune ? 'selected' : ''}>${c.nom}</option>`;
            });

            if (employeSelect) {
                employeSelect.innerHTML = '<option value="all">Tous les employés responsables</option>';
                let selectedEmployeId = 'all';
                (data.employes || []).forEach((employe) => {
                    const isSelected = employe.id === currentEmploye;
                    if (isSelected) {
                        selectedEmployeId = employe.id;
                    }
                    employeSelect.innerHTML += `<option value="${employe.id}" ${isSelected ? 'selected' : ''}>${employe.nom}</option>`;
                });
                employeSelect.value = selectedEmployeId;
                currentFilters.employe_id = selectedEmployeId;
            }
        }
    } catch (error) {
        console.error('Erreur chargement options filtres:', error);
    }
}

// Event listeners pour filtres en cascade
document.addEventListener('DOMContentLoaded', function() {
    initRepairTargetFields('add');
    initRepairTargetFields('edit');
    resetDetailRows('add');
    resetDetailRows('edit');
    resetBonRows('add');
    resetBonRows('edit');
    initFichePosteSearch('add-fiche-poste', 'add-fiche-poste-search');
    initFichePosteSearch('edit-fiche-poste', 'edit-fiche-poste-search');

    // Forcer l'affichage par défaut sur la vue Suite à donner avant le premier chargement
    switchView(currentView);

    // Charger les options de filtres au démarrage
    loadFilterOptions();

    // Charger les ouvrages au démarrage
    loadOuvrages();

    // Toggle du modal "Voir réparations": afficher uniquement les non terminées
    const modalToggle = document.getElementById('view-toggle-non-terminees');
    if (modalToggle) {
        modalToggle.addEventListener('change', applyViewReparationsToggle);
    }

    // Quand la région change, recharger districts et communes
    document.getElementById('filter-region').addEventListener('change', loadFilterOptions);

    // Quand le district change, recharger les communes
    document.getElementById('filter-district').addEventListener('change', loadFilterOptions);

    // Quand la commune change, recharger la liste des employés responsables
    document.getElementById('filter-commune').addEventListener('change', loadFilterOptions);

    // Quand l'organisation change, recharger les options géographiques
    const organisationFilter = document.getElementById('filter-organisation');
    if (organisationFilter) {
        organisationFilter.addEventListener('change', loadFilterOptions);
    }

    // Quand l'année change, recalculer aussi les options géographiques
    const anneeFilter = document.getElementById('filter-annee');
    if (anneeFilter) {
        anneeFilter.addEventListener('change', loadFilterOptions);
    }
});

// Changer de vue (cards, table ou communes)
function switchView(viewType) {
    currentView = viewType;

    // Toggle button states
    const btnCards = document.getElementById('btn-view-cards');
    const btnTable = document.getElementById('btn-view-table');
    const btnCommunes = document.getElementById('btn-view-communes');
    const btnSuite = document.getElementById('btn-view-suite');
    if (btnCards) btnCards.classList.toggle('btn-active', viewType === 'cards');
    if (btnTable) btnTable.classList.toggle('btn-active', viewType === 'table');
    if (btnCommunes) btnCommunes.classList.toggle('btn-active', viewType === 'communes');
    if (btnSuite) btnSuite.classList.toggle('btn-active', viewType === 'suite');

    // Toggle view containers (explicit add/remove)
    const viewCards = document.getElementById('view-cards');
    const viewTable = document.getElementById('view-table');
    const viewCommunes = document.getElementById('view-communes');
    const viewSuite = document.getElementById('view-suite');

    if (viewCards) {
        viewCards.classList[viewType === 'cards' ? 'remove' : 'add']('hidden');
        viewCards.style.display = viewType === 'cards' ? '' : 'none';
    }
    if (viewTable) {
        viewTable.classList[viewType === 'table' ? 'remove' : 'add']('hidden');
        viewTable.style.display = viewType === 'table' ? '' : 'none';
    }
    if (viewCommunes) {
        viewCommunes.classList[viewType === 'communes' ? 'remove' : 'add']('hidden');
        viewCommunes.style.display = viewType === 'communes' ? '' : 'none';
    }
    if (viewSuite) {
        viewSuite.classList[viewType === 'suite' ? 'remove' : 'add']('hidden');
        viewSuite.style.display = viewType === 'suite' ? '' : 'none';
    }
    if (viewType === 'communes' && typeof displayOuvragesCommunes === 'function') {
        displayOuvragesCommunes(allOuvrages || []);
    }
    if (viewType === 'suite' && typeof renderSuiteADonner === 'function') {
        renderSuiteADonner();
    }
}

// Charger les statistiques
async function loadStats() {
    const params = new URLSearchParams(currentFilters);

    try {
        const url = `?${params}`;
        const response = await fetch(url);

        if (!response.ok) {
            console.error('Erreur chargement stats:', response.status);
            return;
        }

        const data = await response.json();

        if (data.success && data.stats) {
            // Mettre à jour les valeurs affichées
            document.getElementById('stat-signalees').textContent = data.stats.signalees;
            document.getElementById('stat-planifiees').textContent = data.stats.planifiees;
            document.getElementById('stat-en-cours').textContent = data.stats.en_cours;
            document.getElementById('stat-terminees').textContent = data.stats.terminees;
            document.getElementById('stat-validees').textContent = data.stats.validees;
        }
    } catch (error) {
        console.error('Erreur chargement stats:', error);
    }
}

// Charger les statistiques de grading
async function loadGradingStats() {
    const params = new URLSearchParams(currentFilters);

    try {
        const url = `?${params}`;
        const response = await fetch(url);

        if (!response.ok) {
            console.error('Erreur chargement stats grading:', response.status);
            return;
        }

        const data = await response.json();

        if (data.success && data.stats) {
            const stats = data.stats;
            const total = (stats.grade_a || 0) + (stats.grade_b || 0) + (stats.grade_b_panne || 0) + (stats.grade_c || 0) + (stats.grade_d || 0) + (stats.grade_d_panne || 0);

            // Mettre à jour les nombres
            const gradingA = stats.grade_a || 0;
            const gradingB = stats.grade_b || 0;
            const gradingBPanne = stats.grade_b_panne || 0;
            const gradingC = stats.grade_c || 0;
            const gradingD = stats.grade_d || 0;
            const gradingDPanne = stats.grade_d_panne || 0;

            const statA = document.getElementById('stat-grading-a');
            const statB = document.getElementById('stat-grading-b');
            const statBPanne = document.getElementById('stat-grading-b-panne');
            const statC = document.getElementById('stat-grading-c');
            const statD = document.getElementById('stat-grading-d');
            const statDPanne = document.getElementById('stat-grading-d-panne');

            if (statA) statA.textContent = gradingA;
            if (statB) statB.textContent = gradingB;
            if (statBPanne) statBPanne.textContent = gradingBPanne;
            if (statC) statC.textContent = gradingC;
            if (statD) statD.textContent = gradingD;
            if (statDPanne) statDPanne.textContent = gradingDPanne;

            // Afficher le total des ouvrages
            const totalOuvrages = document.getElementById('total-ouvrages');
            if (totalOuvrages) totalOuvrages.textContent = total;

            // Masquer/afficher les lignes de répartition selon leur valeur
            const rowA = document.getElementById('row-grading-a');
            const rowB = document.getElementById('row-grading-b');
            const rowBPanne = document.getElementById('row-grading-b-panne');
            const rowC = document.getElementById('row-grading-c');
            const rowD = document.getElementById('row-grading-d');
            const rowDPanne = document.getElementById('row-grading-d-panne');

            if (rowA) rowA.style.display = gradingA === 0 ? 'none' : 'block';
            if (rowB) rowB.style.display = gradingB === 0 ? 'none' : 'block';
            if (rowBPanne) rowBPanne.style.display = gradingBPanne === 0 ? 'none' : 'block';
            if (rowC) rowC.style.display = gradingC === 0 ? 'none' : 'block';
            if (rowD) rowD.style.display = gradingD === 0 ? 'none' : 'block';
            if (rowDPanne) rowDPanne.style.display = gradingDPanne === 0 ? 'none' : 'block';

            // Masquer/afficher les barres de pourcentage selon leur valeur
            const barRowA = document.getElementById('bar-row-grading-a');
            const barRowB = document.getElementById('bar-row-grading-b');
            const barRowBPanne = document.getElementById('bar-row-grading-b-panne');
            const barRowC = document.getElementById('bar-row-grading-c');
            const barRowD = document.getElementById('bar-row-grading-d');
            const barRowDPanne = document.getElementById('bar-row-grading-d-panne');

            if (barRowA) barRowA.style.display = gradingA === 0 ? 'none' : 'block';
            if (barRowB) barRowB.style.display = gradingB === 0 ? 'none' : 'block';
            if (barRowBPanne) barRowBPanne.style.display = gradingBPanne === 0 ? 'none' : 'block';
            if (barRowC) barRowC.style.display = gradingC === 0 ? 'none' : 'block';
            if (barRowD) barRowD.style.display = gradingD === 0 ? 'none' : 'block';
            if (barRowDPanne) barRowDPanne.style.display = gradingDPanne === 0 ? 'none' : 'block';

            // Calculer et afficher les pourcentages
            if (total > 0) {
                const pctA = Math.round(gradingA * 100 / total);
                const pctB = Math.round(gradingB * 100 / total);
                const pctBPanne = Math.round(gradingBPanne * 100 / total);
                const pctC = Math.round(gradingC * 100 / total);
                const pctD = Math.round(gradingD * 100 / total);
                const pctDPanne = Math.round(gradingDPanne * 100 / total);

                const pctAEl = document.getElementById('pct-grading-a');
                const pctBEl = document.getElementById('pct-grading-b');
                const pctBPanneEl = document.getElementById('pct-grading-b-panne');
                const pctCEl = document.getElementById('pct-grading-c');
                const pctDEl = document.getElementById('pct-grading-d');
                const pctDPanneEl = document.getElementById('pct-grading-d-panne');

                if (pctAEl) pctAEl.textContent = pctA + '%';
                if (pctBEl) pctBEl.textContent = pctB + '%';
                if (pctBPanneEl) pctBPanneEl.textContent = pctBPanne + '%';
                if (pctCEl) pctCEl.textContent = pctC + '%';
                if (pctDEl) pctDEl.textContent = pctD + '%';
                if (pctDPanneEl) pctDPanneEl.textContent = pctDPanne + '%';

                const barA = document.getElementById('bar-grading-a');
                const barB = document.getElementById('bar-grading-b');
                const barBPanne = document.getElementById('bar-grading-b-panne');
                const barC = document.getElementById('bar-grading-c');
                const barD = document.getElementById('bar-grading-d');
                const barDPanne = document.getElementById('bar-grading-d-panne');

                if (barA) barA.style.width = pctA + '%';
                if (barB) barB.style.width = pctB + '%';
                if (barBPanne) barBPanne.style.width = pctBPanne + '%';
                if (barC) barC.style.width = pctC + '%';
                if (barD) barD.style.width = pctD + '%';
                if (barDPanne) barDPanne.style.width = pctDPanne + '%';
            }
        }
    } catch (error) {
        console.error('Erreur chargement stats grading:', error);
    }
}

// Charger la liste des ouvrages
async function loadOuvrages() {
    const params = new URLSearchParams(currentFilters);

    try {
        // Charger les stats en parallèle
        loadStats();
        loadGradingStats();

        const url = `?${params}`;
        console.log('[DEBUG] Chargement des ouvrages:', url);

        const response = await fetch(url);

        // Vérifier si la réponse est OK avant de parser JSON
        if (!response.ok) {
            const text = await response.text();
            console.error('[DEBUG] Erreur serveur:', response.status, text.substring(0, 500));
            throw new Error(`Erreur serveur (${response.status})`);
        }

        const data = await response.json();

        console.log('[DEBUG] Réponse API:', data);
        console.log('[DEBUG] Nombre ouvrages reçus:', data.ouvrages ? data.ouvrages.length : 0);

        if (data.success) {
            if (data.message) {
                console.warn('[DEBUG] Message API:', data.message);
            }
            // Stocker tous les ouvrages pour filtrage côté client
            allOuvrages = data.ouvrages || [];
            // Filtrer et afficher selon le statut actuel
            filterAndDisplayOuvrages();
            await loadSuiteADonner();
        } else {
            console.error('[DEBUG] Échec API');
            alert('Erreur lors du chargement des ouvrages');
        }
    } catch (error) {
        console.error('[DEBUG] Erreur réseau:', error);
        alert('Erreur réseau: ' + error.message);
    }
}

// Grouper les ouvrages par District puis par Commune
function groupOuvragesByLocation(ouvrages) {
    const grouped = {};

    ouvrages.forEach(ouvrage => {
        // Utiliser le district de l'API ou extraire de la commune
        const district = ouvrage.district || 'District inconnu';
        const commune = ouvrage.commune || 'Commune inconnue';

        if (!grouped[district]) {
            grouped[district] = {};
        }

        if (!grouped[district][commune]) {
            grouped[district][commune] = [];
        }

        grouped[district][commune].push(ouvrage);
    });

    return grouped;
}

// Compter les ouvrages par type de grading
function countGradings(ouvrages) {
    const counts = {
        b: 0,
        b_panne: 0,
        d: 0,
        d_panne: 0
    };

    ouvrages.forEach(ouvrage => {
        const grading = ouvrage.grading || '';
        const gradingLower = grading.toLowerCase();

        if (gradingLower.includes('b (panne)') || gradingLower.includes('b panne')) {
            counts.b_panne++;
        } else if (gradingLower.includes('grading b')) {
            counts.b++;
        } else if (gradingLower.includes('d (panne)') || gradingLower.includes('d panne')) {
            counts.d_panne++;
        } else if (gradingLower.includes('grading d')) {
            counts.d++;
        }
    });

    return counts;
}

// Fonction helper pour obtenir le badge de grading
function getGradingBadge(grading) {
    if (!grading) return '';

    const badgeClassMap = {
        'A': 'badge-success',
        'B': 'badge-warning',
        'B_panne': 'badge-warning',
        'D': 'badge-error',
        'D_panne': 'badge-error',
        'C': 'badge-info'
    };

    const iconMap = {
        'A': 'fa-check-circle',
        'B': 'fa-wrench',
        'B_panne': 'fa-exclamation-triangle',
        'D': 'fa-tools',
        'D_panne': 'fa-exclamation-circle',
        'C': 'fa-info-circle'
    };

    const labelMap = {
        'A': 'Grading A',
        'B': 'Grading B',
        'B_panne': 'Grading B Panne',
        'D': 'Grading D',
        'D_panne': 'Grading D Panne',
        'C': 'Grading C'
    };

    const badgeClass = badgeClassMap[grading] || 'badge-ghost';
    const icon = iconMap[grading] || 'fa-question';
    const label = labelMap[grading] || grading;

    return `<span class="badge ${badgeClass} badge-sm">
        <i class="fas ${icon} mr-1"></i>${label}
    </span>`;
}

// Afficher les ouvrages (appelle les deux fonctions de rendu)
// Filtrer les ouvrages selon le statut de réparation sélectionné
function filterAndDisplayOuvrages() {
    let ouvrages = allOuvrages;

    // Si un statut spécifique est sélectionné, filtrer les ouvrages
    if (currentFilters.statut !== 'all') {
        ouvrages = allOuvrages.filter(ouvrage => {
            const stats = ouvrage.reparations_stats;
            if (!stats) return false;

            // Vérifier si l'ouvrage a des réparations avec ce statut
            switch (currentFilters.statut) {
                case 'signalee':
                    return stats.signalee > 0;
                case 'planifiee':
                    return stats.planifiee > 0;
                case 'en_cours':
                    return stats.en_cours > 0;
                case 'terminee':
                    return stats.terminee > 0;
                case 'validee':
                    return stats.validee > 0;
                default:
                    return true;
            }
        });
    }

    console.log('[DEBUG] Ouvrages après filtrage statut:', ouvrages.length);
    currentFilteredOuvrages = ouvrages;
    displayOuvrages(ouvrages);
}

function formatDebitValue(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '-';
    }
    return `${Number(value).toFixed(3)} L/s`;
}

function getDebitBadgeMarkup(debit) {
    if (!debit || !debit.has_measure) {
        return '<span class="badge badge-ghost badge-sm">Débit non saisi</span>';
    }

    const valueLabel = formatDebitValue(debit.debit_l_s);
    const thresholdLabel = debit.threshold_l_s !== null && debit.threshold_l_s !== undefined
        ? `Seuil ${Number(debit.threshold_l_s).toFixed(3)} L/s`
        : 'Seuil indisponible';

    if (debit.is_alert) {
        return `<span class="badge badge-error badge-sm" title="${thresholdLabel}">${valueLabel} sous seuil</span>`;
    }

    if (debit.threshold_l_s !== null && debit.threshold_l_s !== undefined) {
        return `<span class="badge badge-success badge-sm" title="${thresholdLabel}">${valueLabel}</span>`;
    }

    return `<span class="badge badge-info badge-sm">${valueLabel}</span>`;
}

function getDebitDetailMarkup(debit) {
    if (!debit || !debit.has_measure) {
        return `<div class="text-xs text-base-content/60">Aucune mesure de débit source</div>`;
    }

    const thresholdText = debit.threshold_l_s !== null && debit.threshold_l_s !== undefined
        ? `Seuil ${Number(debit.threshold_l_s).toFixed(3)} L/s`
        : 'Seuil indisponible';
    const deltaText = debit.delta_vs_prev === null || debit.delta_vs_prev === undefined
        ? ''
        : ` • Δ ${Number(debit.delta_vs_prev).toFixed(3)} L/s`;
    const dateText = debit.date_visite ? ` • ${formatDateForDisplay(debit.date_visite)}` : '';

    return `
        <div class="flex items-center gap-2 flex-wrap">
            ${getDebitBadgeMarkup(debit)}
            <span class="text-xs text-base-content/60">${thresholdText}${deltaText}${dateText}</span>
            ${debit.page_url ? `<a href="${debit.page_url}" class="link link-primary text-xs">Ouvrir</a>` : ''}
        </div>
    `;
}

function renderDebitSummaryStats(ouvrages) {
    const totalEl = document.getElementById('stat-debit-sources');
    const alertEl = document.getElementById('stat-debit-alertes');
    const okEl = document.getElementById('stat-debit-ok');
    const missingEl = document.getElementById('stat-debit-missing');
    if (!totalEl || !alertEl || !okEl || !missingEl) {
        return;
    }

    let measured = 0;
    let alerts = 0;
    let ok = 0;
    let missing = 0;

    (ouvrages || []).forEach((ouvrage) => {
        const debit = ouvrage.debit_source || null;
        if (!debit || !debit.has_measure) {
            missing += 1;
            return;
        }
        measured += 1;
        if (debit.is_alert) {
            alerts += 1;
        } else {
            ok += 1;
        }
    });

    totalEl.textContent = measured;
    alertEl.textContent = alerts;
    okEl.textContent = ok;
    missingEl.textContent = missing;
}

function displayOuvrages(ouvrages) {
    console.log('[DEBUG] displayOuvrages appelé avec', ouvrages.length, 'ouvrage(s)');
    renderDebitSummaryStats(ouvrages);
    displayOuvragesCards(ouvrages);
    displayOuvragesTable(ouvrages);
    displayOuvragesCommunes(ouvrages);
    renderSuiteADonner();
    switchView(currentView);
}

// Afficher les ouvrages en cartes (groupés par District et Commune)
function displayOuvragesCards(ouvrages) {
    const container = document.getElementById('view-cards');
    console.log('[DEBUG] displayOuvragesCards - container trouvé:', container !== null);
    console.log('[DEBUG] displayOuvragesCards - nombre ouvrages:', ouvrages.length);

    if (ouvrages.length === 0) {
        container.innerHTML = `
            <div class="col-span-full text-center py-8 text-base-content/50">
                <i class="fas fa-inbox text-4xl mb-2"></i>
                <p>Aucun ouvrage trouvé avec les filtres appliqués</p>
            </div>
        `;
        return;
    }

    // Grouper par District et Commune
    const grouped = groupOuvragesByLocation(ouvrages);

    // Reconstruire le container avec structure de groupement
    container.innerHTML = '';
    container.classList.remove('grid', 'grid-cols-1', 'md:grid-cols-2', 'lg:grid-cols-3', 'gap-4');
    container.classList.add('space-y-6');

    // Parcourir les districts (triés alphabétiquement)
    Object.keys(grouped).sort().forEach((district, districtIndex) => {
        // Créer section District
        const districtSection = document.createElement('div');
        districtSection.className = 'space-y-4';

        const districtId = `district-cards-${districtIndex}`;

        // Compter les gradings pour ce district
        const districtOuvrages = Object.values(grouped[district]).flat();
        const districtGradings = countGradings(districtOuvrages);

        // Header District (cliquable pour plier/déplier)
        const districtHeader = document.createElement('div');
        districtHeader.className = 'bg-primary text-primary-content px-4 py-3 rounded-lg cursor-pointer hover:opacity-90 transition-opacity';
        districtHeader.innerHTML = `
            <h3 class="text-lg font-bold flex items-center justify-between">
                <span>
                    <i id="icon-${districtId}" class="fas fa-chevron-right mr-2 transition-transform"></i>
                    <i class="fas fa-map-marked-alt mr-2"></i>
                    District: ${district}
                    <span class="badge badge-neutral ml-2">
                        ${districtOuvrages.length} ouvrage(s)
                    </span>
                </span>
                <span class="flex gap-2">
                    ${districtGradings.b > 0 ? `<span class="badge badge-success badge-sm">B: ${districtGradings.b}</span>` : ''}
                    ${districtGradings.b_panne > 0 ? `<span class="badge badge-error badge-sm">B panne: ${districtGradings.b_panne}</span>` : ''}
                    ${districtGradings.d > 0 ? `<span class="badge badge-warning badge-sm">D: ${districtGradings.d}</span>` : ''}
                    ${districtGradings.d_panne > 0 ? `<span class="badge badge-error badge-sm">D panne: ${districtGradings.d_panne}</span>` : ''}
                </span>
            </h3>
        `;
        districtHeader.onclick = () => toggleSection(districtId);
        districtSection.appendChild(districtHeader);

        // Container pour les communes (pliable)
        const districtContent = document.createElement('div');
        districtContent.id = districtId;
        districtContent.className = 'space-y-4 hidden';

        // Parcourir les communes du district (triées alphabétiquement)
        Object.keys(grouped[district]).sort().forEach((commune, communeIndex) => {
            const communeOuvrages = grouped[district][commune];
            const communeId = `commune-cards-${districtIndex}-${communeIndex}`;

            // Compter les gradings pour cette commune
            const communeGradings = countGradings(communeOuvrages);

            // Header Commune (cliquable pour plier/déplier)
            const communeHeader = document.createElement('div');
            communeHeader.className = 'bg-secondary text-secondary-content px-4 py-2 rounded-md ml-4 cursor-pointer hover:opacity-90 transition-opacity';
            communeHeader.innerHTML = `
                <h4 class="font-semibold flex items-center justify-between">
                    <span>
                        <i id="icon-${communeId}" class="fas fa-chevron-right mr-2 transition-transform"></i>
                        <i class="fas fa-map-marker-alt mr-2"></i>
                        Commune: ${commune}
                        <span class="badge badge-ghost badge-sm ml-2">${communeOuvrages.length} ouvrage(s)</span>
                    </span>
                    <span class="flex gap-2">
                        ${communeGradings.b > 0 ? `<span class="badge badge-success badge-sm">B: ${communeGradings.b}</span>` : ''}
                        ${communeGradings.b_panne > 0 ? `<span class="badge badge-error badge-sm">B panne: ${communeGradings.b_panne}</span>` : ''}
                        ${communeGradings.d > 0 ? `<span class="badge badge-warning badge-sm">D: ${communeGradings.d}</span>` : ''}
                        ${communeGradings.d_panne > 0 ? `<span class="badge badge-error badge-sm">D panne: ${communeGradings.d_panne}</span>` : ''}
                    </span>
                </h4>
            `;
            communeHeader.onclick = () => toggleSection(communeId);
            districtContent.appendChild(communeHeader);

            // Grid des cartes pour cette commune (pliable)
            const communeGrid = document.createElement('div');
            communeGrid.id = communeId;
            communeGrid.className = 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 ml-8 mt-2 hidden';

            communeOuvrages.forEach(ouvrage => {
                const stats = ouvrage.reparations_stats;
                const totalRep = stats.total;

                // Déterminer la couleur du badge et de la bordure selon l'état des réparations
                let repBadgeClass = 'badge-ghost';
                let borderClass = '';
                let statusIcon = '';

                if (totalRep > 0) {
                    // Compter réparations terminées/validées
                    const reparationsTerminees = (stats.terminee || 0) + (stats.validee || 0);
                    const reparationsEnCours = totalRep - reparationsTerminees;

                    if (reparationsEnCours === 0 && reparationsTerminees > 0) {
                        // Toutes terminées
                        repBadgeClass = 'badge-success';
                        borderClass = 'border-l-4 border-success';
                        statusIcon = '<i class="fas fa-check-circle text-success"></i>';
                    } else if (stats.signalee > 0) {
                        // Au moins une signalée
                        repBadgeClass = 'badge-error';
                        borderClass = 'border-l-4 border-error';
                        statusIcon = '<i class="fas fa-exclamation-circle text-error"></i>';
                    } else if (stats.en_cours > 0) {
                        // En cours
                        repBadgeClass = 'badge-info';
                        borderClass = 'border-l-4 border-info';
                        statusIcon = '<i class="fas fa-tools text-info"></i>';
                    } else if (stats.terminee > 0) {
                        // Terminées non validées
                        repBadgeClass = 'badge-success';
                        borderClass = 'border-l-4 border-success';
                        statusIcon = '<i class="fas fa-check-circle text-success"></i>';
                    }
                }

                const card = document.createElement('div');
                card.className = `card bg-base-100 shadow-md hover:shadow-lg transition-shadow ${borderClass}`;
                card.innerHTML = `
                    <div class="card-body">
                        <h2 class="card-title justify-between">
                            <span>
                                <i class="fas fa-building text-primary"></i>
                                ${ouvrage.nom}
                            </span>
                            ${statusIcon}
                        </h2>

                        <div class="space-y-2">
                            <div class="flex items-center gap-2 flex-wrap">
                                <span class="badge badge-ghost badge-sm">${ouvrage.type}</span>
                                <span class="badge badge-primary badge-sm">${ouvrage.modalite || 'Non défini'}</span>
                                ${getGradingBadge(ouvrage.grading)}
                                ${ouvrage.est_saisonnier ? '<span class="badge badge-warning badge-sm"><i class="fas fa-snowflake mr-1"></i>Saisonnier</span>' : ''}
                            </div>

                            ${ouvrage.village ? `
                                <div class="text-sm text-base-content/70">
                                    <i class="fas fa-map-marker-alt mr-1"></i>
                                    ${ouvrage.village}
                                    ${ouvrage.fokontany ? `<span class="text-xs"> • ${ouvrage.fokontany}</span>` : ''}
                                </div>
                            ` : ''}

                            <div class="flex items-center gap-2 flex-wrap">
                                <i class="fas fa-wrench text-warning"></i>
                                <span class="badge ${repBadgeClass}">${totalRep} réparation${totalRep > 1 ? 's' : ''}</span>
                                ${stats.signalee > 0 ? `<span class="badge badge-error badge-xs">${stats.signalee} à faire</span>` : ''}
                                ${stats.en_cours > 0 ? `<span class="badge badge-info badge-xs">${stats.en_cours} en cours</span>` : ''}
                                ${stats.terminee > 0 ? `<span class="badge badge-success badge-xs">${stats.terminee} terminée${stats.terminee > 1 ? 's' : ''}</span>` : ''}
                                ${stats.validee > 0 ? `<span class="badge badge-primary badge-xs">${stats.validee} validée${stats.validee > 1 ? 's' : ''}</span>` : ''}
                            </div>

                            ${getDebitDetailMarkup(ouvrage.debit_source)}
                        </div>

                        <div class="card-actions justify-end mt-4">
                            <button onclick="openAddReparation('${ouvrage.id}', '${ouvrage.nom.replace(/'/g, "\\'")}')"
                                    class="btn btn-success btn-sm">
                                <i class="fas fa-plus mr-1"></i>Ajouter
                            </button>
                            ${totalRep > 0 ? `
                                <button onclick="viewReparations('${ouvrage.id}', '${ouvrage.nom.replace(/'/g, "\\'")}')"
                                        class="btn btn-info btn-sm">
                                    <i class="fas fa-eye mr-1"></i>Voir (${totalRep})
                                </button>
                            ` : ''}
                        </div>
                    </div>
                `;
                communeGrid.appendChild(card);
            });

            // Ajouter le grid de la commune au container du district
            districtContent.appendChild(communeGrid);
        });

        // Ajouter le container des communes à la section district
        districtSection.appendChild(districtContent);

        // Ajouter la section district au container principal
        container.appendChild(districtSection);
    });
}

// Afficher les ouvrages dans le tableau (groupés par District et Commune)
function displayOuvragesTable(ouvrages) {
    const tbody = document.getElementById('ouvrages-table');

    if (ouvrages.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center py-8 text-base-content/50">
                    Aucun ouvrage trouvé avec les filtres appliqués
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = '';

    // Grouper par District et Commune
    const grouped = groupOuvragesByLocation(ouvrages);

    // Parcourir les districts (triés alphabétiquement)
    Object.keys(grouped).sort().forEach((district, districtIndex) => {
        const districtId = `district-table-${districtIndex}`;

        // Compter les gradings pour ce district
        const districtOuvrages = Object.values(grouped[district]).flat();
        const districtGradings = countGradings(districtOuvrages);

        // Ligne header District (cliquable)
        const districtRow = document.createElement('tr');
        districtRow.className = 'bg-primary text-primary-content cursor-pointer hover:opacity-90';
        districtRow.onclick = () => toggleSection(districtId);
        districtRow.innerHTML = `
            <td colspan="7" class="font-bold py-3">
                <div class="flex items-center justify-between">
                    <span>
                        <i id="icon-${districtId}" class="fas fa-chevron-right mr-2 transition-transform"></i>
                        <i class="fas fa-map-marked-alt mr-2"></i>
                        District: ${district}
                        <span class="badge badge-neutral ml-2">
                            ${districtOuvrages.length} ouvrage(s)
                        </span>
                    </span>
                    <span class="flex gap-2">
                        ${districtGradings.b > 0 ? `<span class="badge badge-success badge-sm">B: ${districtGradings.b}</span>` : ''}
                        ${districtGradings.b_panne > 0 ? `<span class="badge badge-error badge-sm">B panne: ${districtGradings.b_panne}</span>` : ''}
                        ${districtGradings.d > 0 ? `<span class="badge badge-warning badge-sm">D: ${districtGradings.d}</span>` : ''}
                        ${districtGradings.d_panne > 0 ? `<span class="badge badge-error badge-sm">D panne: ${districtGradings.d_panne}</span>` : ''}
                    </span>
                </div>
            </td>
        `;
        tbody.appendChild(districtRow);

        // Parcourir les communes du district (triées alphabétiquement)
        Object.keys(grouped[district]).sort().forEach((commune, communeIndex) => {
            const communeOuvrages = grouped[district][commune];
            const communeId = `commune-table-${districtIndex}-${communeIndex}`;

            // Compter les gradings pour cette commune
            const communeGradings = countGradings(communeOuvrages);

            // Ligne header Commune (cliquable)
            const communeRow = document.createElement('tr');
            communeRow.className = 'bg-secondary text-secondary-content cursor-pointer hover:opacity-90 hidden';
            communeRow.dataset.districtGroup = districtId;
            communeRow.onclick = () => toggleSection(communeId);
            communeRow.innerHTML = `
                <td colspan="7" class="font-semibold py-2 pl-8">
                    <div class="flex items-center justify-between">
                        <span>
                            <i id="icon-${communeId}" class="fas fa-chevron-right mr-2 transition-transform"></i>
                            <i class="fas fa-map-marker-alt mr-2"></i>
                            Commune: ${commune}
                            <span class="badge badge-ghost badge-sm ml-2">${communeOuvrages.length} ouvrage(s)</span>
                        </span>
                        <span class="flex gap-2">
                            ${communeGradings.b > 0 ? `<span class="badge badge-success badge-sm">B: ${communeGradings.b}</span>` : ''}
                            ${communeGradings.b_panne > 0 ? `<span class="badge badge-error badge-sm">B panne: ${communeGradings.b_panne}</span>` : ''}
                            ${communeGradings.d > 0 ? `<span class="badge badge-warning badge-sm">D: ${communeGradings.d}</span>` : ''}
                            ${communeGradings.d_panne > 0 ? `<span class="badge badge-error badge-sm">D panne: ${communeGradings.d_panne}</span>` : ''}
                        </span>
                    </div>
                </td>
            `;
            tbody.appendChild(communeRow);

            // Lignes des ouvrages de la commune
            communeOuvrages.forEach(ouvrage => {
                const stats = ouvrage.reparations_stats;
                const totalRep = stats.total;

                // Déterminer statut et style de la ligne
                let repBadge = '';
                let rowClass = 'hover';
                let statusBadges = '';

                if (totalRep > 0) {
                    // Compter réparations terminées/validées
                    const reparationsTerminees = (stats.terminee || 0) + (stats.validee || 0);
                    const reparationsEnCours = totalRep - reparationsTerminees;

                    if (reparationsEnCours === 0 && reparationsTerminees > 0) {
                        // Toutes terminées - ligne verte
                        repBadge = `<span class="badge badge-success">${totalRep}</span>`;
                        rowClass = 'hover bg-success/10';
                        statusBadges = `<div class="flex gap-1 flex-wrap justify-center">
                            ${stats.terminee > 0 ? `<span class="badge badge-success badge-xs">${stats.terminee} terminée${stats.terminee > 1 ? 's' : ''}</span>` : ''}
                            ${stats.validee > 0 ? `<span class="badge badge-primary badge-xs">${stats.validee} validée${stats.validee > 1 ? 's' : ''}</span>` : ''}
                        </div>`;
                    } else if (stats.signalee > 0) {
                        // Au moins une signalée - ligne rouge
                        repBadge = `<span class="badge badge-error">${totalRep}</span>`;
                        rowClass = 'hover bg-error/10';
                        statusBadges = `<div class="flex gap-1 flex-wrap justify-center">
                            <span class="badge badge-error badge-xs">${stats.signalee} à faire</span>
                            ${stats.en_cours > 0 ? `<span class="badge badge-info badge-xs">${stats.en_cours} en cours</span>` : ''}
                            ${stats.terminee > 0 ? `<span class="badge badge-success badge-xs">${stats.terminee} terminée${stats.terminee > 1 ? 's' : ''}</span>` : ''}
                        </div>`;
                    } else if (stats.en_cours > 0) {
                        // En cours - ligne bleue
                        repBadge = `<span class="badge badge-info">${totalRep}</span>`;
                        rowClass = 'hover bg-info/10';
                        statusBadges = `<div class="flex gap-1 flex-wrap justify-center">
                            <span class="badge badge-info badge-xs">${stats.en_cours} en cours</span>
                            ${stats.terminee > 0 ? `<span class="badge badge-success badge-xs">${stats.terminee} terminée${stats.terminee > 1 ? 's' : ''}</span>` : ''}
                        </div>`;
                    } else {
                        repBadge = `<span class="badge badge-ghost">${totalRep}</span>`;
                    }
                } else {
                    repBadge = `<span class="badge badge-ghost">0</span>`;
                }

                const row = document.createElement('tr');
                row.className = `${rowClass} hidden`;
                row.dataset.districtGroup = districtId;
                row.dataset.communeGroup = communeId;
                row.innerHTML = `
                    <td class="font-semibold pl-12">${ouvrage.nom}</td>
                    <td>
                        <div class="flex flex-col gap-1">
                            <span class="badge badge-ghost badge-sm">${ouvrage.type}</span>
                            ${ouvrage.est_saisonnier ? '<span class="badge badge-warning badge-sm"><i class="fas fa-snowflake mr-1"></i>Saisonnier</span>' : ''}
                        </div>
                    </td>
                    <td class="text-sm">
                        ${ouvrage.village ? `<div>${ouvrage.village}</div>` : ''}
                        ${ouvrage.fokontany ? `<div class="text-xs text-base-content/70">${ouvrage.fokontany}</div>` : ''}
                    </td>
                    <td><span class="badge badge-primary badge-sm">${ouvrage.modalite || 'Non défini'}</span></td>
                    <td class="text-center">
                        <div class="flex flex-col gap-1 items-center">
                            ${getGradingBadge(ouvrage.grading)}
                            ${getDebitBadgeMarkup(ouvrage.debit_source)}
                        </div>
                    </td>
                    <td class="text-center">
                        ${repBadge}
                        ${statusBadges}
                    </td>
                    <td class="text-center">
                        <div class="flex gap-1 justify-center">
                            <button onclick="openAddReparation('${ouvrage.id}', '${ouvrage.nom.replace(/'/g, "\\'")}')"
                                    class="btn btn-success btn-xs" title="Ajouter réparation">
                                <i class="fas fa-plus"></i>
                            </button>
                            ${totalRep > 0 ? `
                                <button onclick="viewReparations('${ouvrage.id}', '${ouvrage.nom.replace(/'/g, "\\'")}')"
                                        class="btn btn-info btn-xs" title="Voir réparations">
                                    <i class="fas fa-eye"></i>
                                </button>
                            ` : ''}
                        </div>
                    </td>
                `;
                tbody.appendChild(row);
            });
        });
    });
}

function displayOuvragesCommunes(ouvrages) {
    const tbody = document.getElementById('communes-table');
    if (!tbody) return;
    const table = tbody.closest('table');
    const headerRow = table ? table.querySelector('thead tr') : null;

    if (ouvrages.length === 0) {
        if (headerRow) {
            headerRow.innerHTML = `
                <th>Commune</th>
                <th class="text-center">Ouvrages</th>
                <th class="text-center">A</th>
                <th class="text-center">B</th>
                <th class="text-center">B (panne)</th>
                <th class="text-center">C</th>
                <th class="text-center">D</th>
                <th class="text-center">D (panne)</th>
                <th class="text-center">Réparations terminées</th>
                <th class="text-center">Réparations non terminées</th>
            `;
        }
        tbody.innerHTML = `
            <tr>
                <td colspan="10" class="text-center py-8 text-base-content/50">
                    <i class="fas fa-inbox text-4xl mb-2"></i>
                    <p>Aucune commune trouvée</p>
                </td>
            </tr>
        `;
        return;
    }

    const regions = {};
    ouvrages.forEach(ouvrage => {
        const region = ouvrage.region || ouvrage.region_nom || ouvrage.region_name || ouvrage.district_region || 'Région inconnue';
        const district = ouvrage.district || ouvrage.district_nom || ouvrage.district_name || 'District inconnu';
        const commune = ouvrage.commune || 'Commune inconnue';

        if (!regions[region]) regions[region] = {};
        if (!regions[region][district]) regions[region][district] = {};
        if (!regions[region][district][commune]) {
            regions[region][district][commune] = {
                ouvrages: 0,
                a: 0,
                b: 0,
                b_panne: 0,
                c: 0,
                d: 0,
                d_panne: 0,
                terminees: 0,
                non_terminees: 0
            };
        }

        const stats = ouvrage.reparations_stats || {};
        const totalRep = stats.total || (stats.signalee || 0) + (stats.planifiee || 0) + (stats.en_cours || 0) + (stats.terminee || 0) + (stats.validee || 0);
        const terminees = (stats.terminee || 0) + (stats.validee || 0);
        const nonTerminees = Math.max(0, totalRep - terminees);

        const grading = (ouvrage.grading || '').toLowerCase();
        const bucket = regions[region][district][commune];
        if (grading.includes('grading a') || grading === 'a') bucket.a += 1;
        else if (grading.includes('b (panne)') || grading.includes('b panne')) bucket.b_panne += 1;
        else if (grading.includes('grading b') || grading === 'b') bucket.b += 1;
        else if (grading.includes('grading c') || grading === 'c') bucket.c += 1;
        else if (grading.includes('d (panne)') || grading.includes('d panne')) bucket.d_panne += 1;
        else if (grading.includes('grading d') || grading === 'd') bucket.d += 1;

        bucket.ouvrages += 1;
        bucket.terminees += terminees;
        bucket.non_terminees += nonTerminees;
    });

    const metricColumns = [
        { key: 'ouvrages', label: 'Ouvrages' },
        { key: 'a', label: 'A' },
        { key: 'b', label: 'B' },
        { key: 'b_panne', label: 'B (panne)' },
        { key: 'c', label: 'C' },
        { key: 'd', label: 'D' },
        { key: 'd_panne', label: 'D (panne)' },
        { key: 'terminees', label: 'Réparations terminées' },
        { key: 'non_terminees', label: 'Réparations non terminées' }
    ];

    const visibleMetricKeys = [];
    metricColumns.forEach(col => {
        let hasValue = false;
        Object.values(regions).forEach(districtsObj => {
            Object.values(districtsObj).forEach(communesObj => {
                Object.values(communesObj).forEach(stats => {
                    if ((stats[col.key] || 0) > 0) {
                        hasValue = true;
                    }
                });
            });
        });
        if (hasValue || col.key === 'ouvrages') {
            visibleMetricKeys.push(col.key);
        }
    });

    if (headerRow) {
        const headerCells = ['<th>Commune</th>'];
        metricColumns.forEach(col => {
            if (visibleMetricKeys.includes(col.key)) {
                headerCells.push(`<th class="text-center">${col.label}</th>`);
            }
        });
        headerRow.innerHTML = headerCells.join('');
    }

    const totalColumns = 1 + visibleMetricKeys.length;
    const fmt = (v) => (v && v !== 0 ? v : '');
    const rows = [];
    const grandTotal = {
        ouvrages: 0,
        a: 0,
        b: 0,
        b_panne: 0,
        c: 0,
        d: 0,
        d_panne: 0,
        terminees: 0,
        non_terminees: 0
    };
    let regionIndex = 0;

    Object.keys(regions).sort().forEach(region => {
        const regionId = `region-table-${regionIndex}`;
        rows.push(`
            <tr class="bg-base-200 font-semibold cursor-pointer" onclick="toggleSection('${regionId}')">
                <td colspan="${totalColumns}">
                    <i id="icon-${regionId}" class="fas fa-chevron-right mr-2 transition-transform"></i>
                    <i class="fas fa-map mr-2 text-primary"></i>${region}
                </td>
            </tr>
        `);

        let districtIndex = 0;
        Object.keys(regions[region]).sort().forEach(district => {
            const districtId = `district-table-${regionIndex}-${districtIndex}`;
            rows.push(`
                <tr class="bg-base-100 font-semibold cursor-pointer hidden" data-region-group="${regionId}" onclick="toggleSection('${districtId}')">
                    <td colspan="${totalColumns}" class="pl-6">
                        <i id="icon-${districtId}" class="fas fa-chevron-right mr-2 transition-transform"></i>
                        <i class="fas fa-map-marker-alt mr-2 text-secondary"></i>${district}
                    </td>
                </tr>
            `);

            Object.keys(regions[region][district]).sort().forEach(commune => {
                const c = regions[region][district][commune];
                grandTotal.ouvrages += c.ouvrages || 0;
                grandTotal.a += c.a || 0;
                grandTotal.b += c.b || 0;
                grandTotal.b_panne += c.b_panne || 0;
                grandTotal.c += c.c || 0;
                grandTotal.d += c.d || 0;
                grandTotal.d_panne += c.d_panne || 0;
                grandTotal.terminees += c.terminees || 0;
                grandTotal.non_terminees += c.non_terminees || 0;
                const cells = [];
                if (visibleMetricKeys.includes('ouvrages')) cells.push(`<td class="text-center">${fmt(c.ouvrages)}</td>`);
                if (visibleMetricKeys.includes('a')) cells.push(`<td class="text-center">${fmt(c.a)}</td>`);
                if (visibleMetricKeys.includes('b')) cells.push(`<td class="text-center">${fmt(c.b)}</td>`);
                if (visibleMetricKeys.includes('b_panne')) cells.push(`<td class="text-center">${fmt(c.b_panne)}</td>`);
                if (visibleMetricKeys.includes('c')) cells.push(`<td class="text-center">${fmt(c.c)}</td>`);
                if (visibleMetricKeys.includes('d')) cells.push(`<td class="text-center">${fmt(c.d)}</td>`);
                if (visibleMetricKeys.includes('d_panne')) cells.push(`<td class="text-center">${fmt(c.d_panne)}</td>`);
                if (visibleMetricKeys.includes('terminees')) cells.push(`<td class="text-center">${fmt(c.terminees)}</td>`);
                if (visibleMetricKeys.includes('non_terminees')) cells.push(`<td class="text-center">${fmt(c.non_terminees)}</td>`);

                rows.push(`
                    <tr class="hidden" data-region-group="${regionId}" data-district-group="${districtId}">
                        <td class="pl-10">${commune}</td>
                        ${cells.join('')}
                    </tr>
                `);
            });
            districtIndex += 1;
        });
        regionIndex += 1;
    });

    const grandTotalCells = [];
    if (visibleMetricKeys.includes('ouvrages')) grandTotalCells.push(`<td class="text-center font-bold">${fmt(grandTotal.ouvrages)}</td>`);
    if (visibleMetricKeys.includes('a')) grandTotalCells.push(`<td class="text-center font-bold">${fmt(grandTotal.a)}</td>`);
    if (visibleMetricKeys.includes('b')) grandTotalCells.push(`<td class="text-center font-bold">${fmt(grandTotal.b)}</td>`);
    if (visibleMetricKeys.includes('b_panne')) grandTotalCells.push(`<td class="text-center font-bold">${fmt(grandTotal.b_panne)}</td>`);
    if (visibleMetricKeys.includes('c')) grandTotalCells.push(`<td class="text-center font-bold">${fmt(grandTotal.c)}</td>`);
    if (visibleMetricKeys.includes('d')) grandTotalCells.push(`<td class="text-center font-bold">${fmt(grandTotal.d)}</td>`);
    if (visibleMetricKeys.includes('d_panne')) grandTotalCells.push(`<td class="text-center font-bold">${fmt(grandTotal.d_panne)}</td>`);
    if (visibleMetricKeys.includes('terminees')) grandTotalCells.push(`<td class="text-center font-bold">${fmt(grandTotal.terminees)}</td>`);
    if (visibleMetricKeys.includes('non_terminees')) grandTotalCells.push(`<td class="text-center font-bold">${fmt(grandTotal.non_terminees)}</td>`);

    rows.push(`
        <tr class="bg-base-200 font-bold border-t-2 border-primary">
            <td>Grand total</td>
            ${grandTotalCells.join('')}
        </tr>
    `);

    tbody.innerHTML = rows.join('');
}

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

function escapeJsString(value) {
    return (value == null ? '' : String(value))
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/\r?\n/g, ' ');
}

function normalizeRepairPhotosPayload(value) {
    if (!Array.isArray(value)) {
        return [];
    }

    return value
        .filter((item) => item && typeof item === 'object' && typeof item.data === 'string' && item.data.startsWith('data:image/'))
        .map((item, index) => ({
            id: item.id || `photo-${Date.now()}-${index}-${Math.random().toString(16).slice(2)}`,
            name: item.name || `photo-${index + 1}.jpg`,
            data: item.data,
            size: Number(item.size) || 0,
            originalSize: Number(item.originalSize) || 0,
            type: item.type || 'image/jpeg',
            date: item.date || new Date().toISOString()
        }));
}

function renderRepairPhotoProofs(photos, photoCount) {
    const normalizedPhotos = normalizeRepairPhotosPayload(photos);
    const totalPhotos = Number(photoCount) || normalizedPhotos.length;
    if (!normalizedPhotos.length && !totalPhotos) {
        return '';
    }

    if (!normalizedPhotos.length) {
        return `
            <div class="mt-3">
                <span class="badge badge-accent badge-sm">
                    <i class="fas fa-camera mr-1"></i>${totalPhotos} photo${totalPhotos > 1 ? 's' : ''} preuve
                </span>
            </div>
        `;
    }

    return `
        <div class="mt-3">
            <div class="flex items-center gap-2 mb-2">
                <span class="text-xs font-semibold text-base-content/80">Photos preuve</span>
                <span class="badge badge-accent badge-sm">${totalPhotos}</span>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
                ${normalizedPhotos.slice(0, 4).map((photo) => `
                    <a href="${photo.data}" target="_blank" rel="noopener" class="block">
                        <img
                            src="${photo.data}"
                            alt="${escapeHtml(photo.name || 'Photo preuve')}"
                            class="w-full h-24 object-cover rounded-lg border border-base-300"
                            loading="lazy">
                    </a>
                `).join('')}
            </div>
        </div>
    `;
}

function setEditRepairPhotos(photos) {
    editRepairPhotosData = normalizeRepairPhotosPayload(photos);
    renderEditRepairPhotosGallery();
}

function renderEditRepairPhotosGallery() {
    const gallery = document.getElementById('edit-photos-gallery');
    if (!gallery) return;

    if (!editRepairPhotosData.length) {
        gallery.innerHTML = `
            <div class="col-span-full rounded-lg border border-dashed border-base-300 bg-base-100 py-6 text-center text-xs text-base-content/60">
                <i class="fas fa-images text-2xl mb-2 block"></i>
                Aucune photo preuve ajoutée
            </div>
        `;
        return;
    }

    gallery.innerHTML = editRepairPhotosData.map((photo) => `
        <div class="relative group">
            <img
                src="${photo.data}"
                alt="${escapeHtml(photo.name || 'Photo preuve')}"
                class="w-full h-28 object-cover rounded-lg border border-base-300"
                loading="lazy">
            <button
                type="button"
                onclick="removeEditRepairPhoto('${escapeJsString(String(photo.id))}')"
                class="absolute top-1 right-1 btn btn-xs btn-error btn-circle opacity-0 group-hover:opacity-100 transition-opacity"
                title="Supprimer cette photo">
                <i class="fas fa-times"></i>
            </button>
            <div class="absolute bottom-0 left-0 right-0 rounded-b-lg bg-black/60 px-2 py-1 text-[11px] text-white">
                ${escapeHtml(photo.name || 'Photo')} ${photo.size ? `• ${(photo.size / 1024).toFixed(0)} KB` : ''}
            </div>
        </div>
    `).join('');
}

function selectEditRepairPhoto() {
    const input = document.getElementById('edit-photo-input');
    if (!input) return;
    input.removeAttribute('capture');
    input.click();
}

function captureEditRepairPhoto() {
    const input = document.getElementById('edit-photo-input');
    if (!input) return;
    input.setAttribute('capture', 'environment');
    input.click();
}

function compressEditRepairPhoto(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = function(event) {
            const image = new Image();
            image.onload = function() {
                const canvas = document.createElement('canvas');
                const context = canvas.getContext('2d');
                if (!context) {
                    reject(new Error('Canvas non disponible'));
                    return;
                }

                const maxWidth = 1200;
                const maxHeight = 1200;
                let width = image.width || 0;
                let height = image.height || 0;

                if (width > maxWidth || height > maxHeight) {
                    const ratio = Math.min(maxWidth / width, maxHeight / height);
                    width = Math.round(width * ratio);
                    height = Math.round(height * ratio);
                }

                canvas.width = width;
                canvas.height = height;
                context.drawImage(image, 0, 0, width, height);

                const compressedDataUrl = canvas.toDataURL('image/jpeg', 0.8);
                const compressedSize = Math.round((compressedDataUrl.length - 'data:image/jpeg;base64,'.length) * 3 / 4);

                resolve({
                    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
                    name: file.name || 'photo.jpg',
                    data: compressedDataUrl,
                    size: compressedSize,
                    originalSize: file.size || compressedSize,
                    type: 'image/jpeg',
                    date: new Date().toISOString()
                });
            };
            image.onerror = function() {
                reject(new Error(`Impossible de lire l'image ${file.name || ''}`.trim()));
            };
            image.src = event.target?.result || '';
        };
        reader.onerror = function() {
            reject(new Error(`Impossible de lire le fichier ${file.name || ''}`.trim()));
        };
        reader.readAsDataURL(file);
    });
}

async function handleEditRepairPhotoSelected(event) {
    const files = Array.from(event?.target?.files || []);
    if (!files.length) return;

    try {
        for (const file of files) {
            if (!file.type.startsWith('image/')) {
                continue;
            }
            const compressedPhoto = await compressEditRepairPhoto(file);
            editRepairPhotosData.push(compressedPhoto);
        }
        renderEditRepairPhotosGallery();
    } catch (error) {
        alert(error.message || 'Erreur lors de la préparation des photos');
    } finally {
        if (event?.target) {
            event.target.value = '';
            event.target.removeAttribute('capture');
        }
    }
}

function removeEditRepairPhoto(photoId) {
    editRepairPhotosData = editRepairPhotosData.filter((photo) => String(photo.id) !== String(photoId));
    renderEditRepairPhotosGallery();
}

renderEditRepairPhotosGallery();

function getOuvrageMetaMap() {
    return new Map((allOuvrages || []).map((ouvrage) => [ouvrage.id, ouvrage]));
}

function classifyRepairFamilyForRep(rep) {
    return classifyRepairFicheClient({
        type_activites_nom: rep?.type_activite_nom || '',
        tache: rep?.fiche_poste_nom || rep?.activite_nom || rep?.description || ''
    });
}

function getRepairFamilyLabel(family) {
    if (family === 'rehabilitation') return 'Réhabilitation';
    if (family === 'panne') return 'Panne';
    return 'Réparation';
}

function getManualPriorityMeta(priorityKey) {
    const meta = {
        critique: { key: 'critique', label: 'Critique', badgeClass: 'badge-error', sortRank: 4, score: 100 },
        haute: { key: 'haute', label: 'Haute', badgeClass: 'badge-warning', sortRank: 3, score: 75 },
        normale: { key: 'normale', label: 'Normale', badgeClass: 'badge-info', sortRank: 2, score: 50 },
        basse: { key: 'basse', label: 'Basse', badgeClass: 'badge-ghost', sortRank: 1, score: 10 }
    };
    return meta[priorityKey] || null;
}

function normalizeGradingKey(grading) {
    const normalized = normalizeText(grading);
    if (!normalized) return '';

    if (normalized.includes('panne')) {
        if (normalized.includes('grading d') || normalized === 'd' || normalized.includes(' d')) return 'd_panne';
        if (normalized.includes('grading b') || normalized === 'b' || normalized.includes(' b')) return 'b_panne';
        return 'panne';
    }
    if (normalized.includes('grading d') || normalized === 'd') return 'd';
    if (normalized.includes('grading c') || normalized === 'c') return 'c';
    if (normalized.includes('grading b') || normalized === 'b') return 'b';
    if (normalized.includes('grading a') || normalized === 'a') return 'a';
    return normalized;
}

function formatDateForDisplay(isoDate) {
    if (!isoDate) return '-';
    const parts = isoDate.split('-');
    if (parts.length !== 3) return isoDate;
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

function getOverdueDays(isoDate) {
    if (!isoDate) return 0;
    const target = new Date(`${isoDate}T00:00:00`);
    if (Number.isNaN(target.getTime())) return 0;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diffMs = today.getTime() - target.getTime();
    return diffMs > 0 ? Math.floor(diffMs / 86400000) : 0;
}

function computeSuitePriority(rep, ouvrageMeta) {
    const manualPriority = getManualPriorityMeta(rep?.priorite_suivi);
    if (manualPriority) {
        return {
            ...manualPriority,
            overdueDays: getOverdueDays(rep?.date_prevue),
            reasons: ['priorité manuelle'],
            source: 'manual'
        };
    }

    const family = classifyRepairFamilyForRep(rep);
    const gradingKey = normalizeGradingKey(ouvrageMeta?.grading || '');
    const overdueDays = getOverdueDays(rep?.date_prevue);
    const reasons = [];
    let score = 0;

    if (family === 'rehabilitation') {
        score += 30;
        reasons.push('réhabilitation');
    } else if (family === 'panne') {
        score += 28;
        reasons.push('panne');
    } else {
        score += 20;
        reasons.push('réparation');
    }

    if (gradingKey === 'd_panne' || gradingKey === 'b_panne' || gradingKey === 'panne') {
        score += 40;
        reasons.push('ouvrage en panne');
    } else if (gradingKey === 'd') {
        score += 26;
        reasons.push('grading D');
    } else if (gradingKey === 'c') {
        score += 16;
        reasons.push('grading C');
    } else if (gradingKey === 'b') {
        score += 12;
        reasons.push('grading B');
    }

    if (rep?.statut === 'en_cours') {
        score += 18;
        reasons.push('déjà en cours');
    } else {
        score += 8;
        reasons.push('planifiée');
    }

    if (overdueDays > 0) {
        score += Math.min(overdueDays, 25);
        reasons.push(`retard ${overdueDays}j`);
    }

    if (!rep?.assigne_a?.id) {
        score += 10;
        reasons.push('non assignée');
    }

    if (!(rep?.suite_a_donner || '').trim()) {
        score += 4;
        reasons.push('suite à cadrer');
    }

    let key = 'normale';
    let label = 'Normale';
    let badgeClass = 'badge-info';
    let sortRank = 1;

    if (score >= 72) {
        key = 'critique';
        label = 'Critique';
        badgeClass = 'badge-error';
        sortRank = 3;
    } else if (score >= 44) {
        key = 'haute';
        label = 'Haute';
        badgeClass = 'badge-warning';
        sortRank = 2;
    }

    return {
        key: key,
        label: label,
        badgeClass: badgeClass,
        score: score,
        sortRank: sortRank,
        overdueDays: overdueDays,
        reasons: reasons,
        source: 'auto'
    };
}

async function loadSuiteADonner() {
    const tbody = document.getElementById('suite-table');
    const summary = document.getElementById('suite-priority-summary');
    if (!tbody || !summary) return;

    if (currentView === 'suite') {
        summary.innerHTML = '<span class="badge badge-ghost">Chargement...</span>';
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center py-8">
                    <span class="loading loading-spinner loading-md text-primary"></span>
                    <p class="mt-2">Chargement des priorités...</p>
                </td>
            </tr>
        `;
    }

    const params = new URLSearchParams();
    params.set('summary', '1');
    params.set('limit', '500');

    if (currentFilters.organisation && currentFilters.organisation !== 'all') {
        params.set('organisation', currentFilters.organisation);
    }
    if (currentFilters.region_id && currentFilters.region_id !== 'all') {
        params.set('region', currentFilters.region_id);
    }
    if (currentFilters.district_id && currentFilters.district_id !== 'all') {
        params.set('district', currentFilters.district_id);
    }
    if (currentFilters.commune_id && currentFilters.commune_id !== 'all') {
        params.set('commune', currentFilters.commune_id);
    }
    if (currentFilters.annee && currentFilters.annee !== 'all') {
        params.set('annee', currentFilters.annee);
    }

    try {
        const url = `?${params.toString()}`;
        const response = await fetch(url);
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || `Erreur serveur (${response.status})`);
        }

        allScopedReparations = Array.isArray(data.reparations) ? data.reparations : [];
        renderSuiteADonner();
    } catch (error) {
        allScopedReparations = [];
        summary.innerHTML = '<span class="badge badge-error">Erreur</span>';
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center py-8 text-error">
                    Impossible de charger la vue Suite à donner: ${escapeHtml(error.message)}
                </td>
            </tr>
        `;
    }
}

function renderSuiteADonner() {
    const tbody = document.getElementById('suite-table');
    const summary = document.getElementById('suite-priority-summary');
    if (!tbody || !summary) return;

    const ouvrageMetaMap = getOuvrageMetaMap();
    const filteredOuvrageIds = new Set((currentFilteredOuvrages || []).map((ouvrage) => ouvrage.id));
    const priorityFilter = document.getElementById('suite-priority-filter')?.value || 'all';

    const compareSuiteEntries = (a, b) => (
        b.priority.sortRank - a.priority.sortRank
        || b.priority.score - a.priority.score
        || b.priority.overdueDays - a.priority.overdueDays
        || (a.date_prevue || '9999-12-31').localeCompare(b.date_prevue || '9999-12-31')
        || (a.ouvrage_nom || '').localeCompare(b.ouvrage_nom || '', 'fr', { sensitivity: 'base' })
        || (a.fiche_poste_nom || a.activite_nom || a.description || '').localeCompare(
            b.fiche_poste_nom || b.activite_nom || b.description || '',
            'fr',
            { sensitivity: 'base' }
        )
    );

    const repairItems = (allScopedReparations || [])
        .filter((rep) => {
            if (!rep || !rep.ouvrage_id || isReparationTerminee(rep)) {
                return false;
            }
            if (!filteredOuvrageIds.has(rep.ouvrage_id)) {
                return false;
            }
            const family = classifyRepairFamilyForRep(rep);
            return ['reparation', 'rehabilitation', 'panne'].includes(family);
        })
        .map((rep) => {
            const ouvrageMeta = ouvrageMetaMap.get(rep.ouvrage_id) || {};
            const priority = computeSuitePriority(rep, ouvrageMeta);
            return {
                ...rep,
                family: classifyRepairFamilyForRep(rep),
                ouvrageMeta: ouvrageMeta,
                priority: priority
            };
        });

    const groupedByOuvrage = new Map();
    repairItems.forEach((item) => {
        const current = groupedByOuvrage.get(item.ouvrage_id);
        if (!current) {
            groupedByOuvrage.set(item.ouvrage_id, {
                ouvrage_id: item.ouvrage_id,
                ouvrage_nom: item.ouvrage_nom,
                ouvrageMeta: item.ouvrageMeta,
                interventions: [item]
            });
            return;
        }
        current.interventions.push(item);
    });

    const baseItems = Array.from(groupedByOuvrage.values()).map((group) => {
        const interventions = [...group.interventions].sort(compareSuiteEntries);
        const representative = interventions[0];
        const uniqueAssignees = Array.from(new Set(
            interventions
                .map((item) => item.assigne_a?.surnom || '')
                .filter(Boolean)
        ));
        const suiteTexts = interventions
            .map((item) => (item.suite_a_donner || '').trim())
            .filter(Boolean);

        return {
            ...representative,
            representative: representative,
            ouvrage_id: group.ouvrage_id,
            ouvrage_nom: group.ouvrage_nom,
            ouvrageMeta: group.ouvrageMeta,
            interventions: interventions,
            total_interventions: interventions.length,
            assignees_label: uniqueAssignees.length === 0
                ? 'Non assigné'
                : uniqueAssignees.length === 1
                    ? uniqueAssignees[0]
                    : `${uniqueAssignees[0]} +${uniqueAssignees.length - 1}`,
            suite_a_donner: representative.suite_a_donner || suiteTexts[0] || '',
        };
    });

    const counts = {
        total: baseItems.length,
        critique: baseItems.filter((item) => item.priority.key === 'critique').length,
        haute: baseItems.filter((item) => item.priority.key === 'haute').length,
        normale: baseItems.filter((item) => item.priority.key === 'normale').length,
        basse: baseItems.filter((item) => item.priority.key === 'basse').length
    };

    summary.innerHTML = `
        <span class="badge badge-outline">Ouvrages: ${counts.total}</span>
        <span class="badge badge-error">Critique: ${counts.critique}</span>
        <span class="badge badge-warning">Haute: ${counts.haute}</span>
        <span class="badge badge-info">Normale: ${counts.normale}</span>
        <span class="badge badge-ghost">Basse: ${counts.basse}</span>
    `;

    const items = baseItems
        .filter((item) => priorityFilter === 'all' || item.priority.key === priorityFilter)
        .sort(compareSuiteEntries);

    if (!items.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center py-8 text-base-content/50">
                    Aucun ouvrage avec réparation ou réhabilitation non terminée à prioriser avec les filtres courants.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = items.map((item) => {
        const ouvrageMeta = item.ouvrageMeta || {};
        const localParts = [
            ouvrageMeta.commune || '',
            ouvrageMeta.district || ''
        ].filter(Boolean);
        const localLabel = localParts.length ? localParts.join(' • ') : 'Localisation non définie';
        const assignation = item.assignees_label || 'Non assigné';
        const debitMarkup = getDebitDetailMarkup(ouvrageMeta.debit_source);
        const overdueBadge = item.priority.overdueDays > 0
            ? `<span class="badge badge-error badge-sm">Retard ${item.priority.overdueDays}j</span>`
            : '<span class="badge badge-ghost badge-sm">À l\'heure</span>';
        const suiteLabel = (item.suite_a_donner || '').trim()
            ? escapeHtml(item.suite_a_donner)
            : '<span class="text-base-content/50">À renseigner</span>';
        const remarqueLabel = (item.representative?.remarque || item.remarque || '').trim()
            ? `<div class="text-xs text-base-content/70 whitespace-pre-wrap">Remarque: ${escapeHtml(item.representative?.remarque || item.remarque || '')}</div>`
            : '';
        const ouvrageNomJs = escapeJsString(item.ouvrage_nom || 'Ouvrage');
        const descriptionJs = escapeJsString(item.representative?.description || item.description || item.fiche_poste_nom || 'Réparation');
        const representativeId = item.representative?.id || item.id;

        return `
            <tr>
                <td>
                    <div class="flex flex-col gap-1">
                        <span class="badge ${item.priority.badgeClass}">${item.priority.label}</span>
                        <span class="text-xs text-base-content/60">${escapeHtml(item.priority.reasons.slice(0, 3).join(' • '))}</span>
                        <span class="text-xs ${item.priority.source === 'manual' ? 'text-warning' : 'text-base-content/50'}">
                            ${item.priority.source === 'manual' ? 'Manuelle' : 'Automatique'}
                        </span>
                    </div>
                </td>
                <td>
                    <div class="font-semibold">${escapeHtml(item.ouvrage_nom || 'Sans ouvrage')}</div>
                    <div class="text-xs text-base-content/60">${getGradingBadge(ouvrageMeta.grading || '')}</div>
                </td>
                <td class="text-sm">
                    ${escapeHtml(localLabel)}
                    <div class="mt-1">${debitMarkup}</div>
                </td>
                <td>
                    <div class="flex flex-col gap-1">
                        <span class="font-medium">${escapeHtml(item.representative?.fiche_poste_nom || item.representative?.activite_nom || item.representative?.description || 'Réparation')}</span>
                        ${remarqueLabel}
                        <div class="flex flex-wrap gap-1">
                            <span class="badge badge-outline badge-sm">${escapeHtml(getRepairFamilyLabel(item.family))}</span>
                            ${ouvrageMeta.modalite ? `<span class="badge badge-primary badge-sm">${escapeHtml(ouvrageMeta.modalite)}</span>` : ''}
                            <span class="badge badge-secondary badge-sm">${item.total_interventions} intervention${item.total_interventions > 1 ? 's' : ''}</span>
                            ${(item.representative?.photo_count || item.photo_count) ? `<span class="badge badge-accent badge-sm"><i class="fas fa-camera mr-1"></i>${item.representative?.photo_count || item.photo_count}</span>` : ''}
                        </div>
                    </div>
                </td>
                <td>${getStatusBadge(item.representative?.statut_display || item.statut_display)}</td>
                <td>
                    <div class="flex flex-col gap-1">
                        <span>${escapeHtml(formatDateForDisplay(item.representative?.date_prevue || item.date_prevue))}</span>
                        ${overdueBadge}
                    </div>
                </td>
                <td>${escapeHtml(assignation)}</td>
                <td class="max-w-xs">
                    <div class="text-sm whitespace-pre-wrap">${suiteLabel}</div>
                </td>
                <td class="text-center">
                    <div class="flex flex-wrap justify-center gap-1">
                        <button onclick="viewReparations('${item.ouvrage_id}', '${ouvrageNomJs}')" class="btn btn-ghost btn-xs" title="Voir l'ouvrage">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button onclick="openEditReparation('${representativeId}')" class="btn btn-info btn-xs" title="Modifier l'intervention prioritaire">
                            <i class="fas fa-pen"></i>
                        </button>
                        <button onclick="marquerTerminee('${representativeId}', '${descriptionJs}')" class="btn btn-success btn-xs" title="Marquer terminée l'intervention prioritaire">
                            <i class="fas fa-check"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function findRepairRecord(planningId) {
    return (currentModalReparations || []).find((rep) => rep.id === planningId)
        || (allScopedReparations || []).find((rep) => rep.id === planningId)
        || null;
}

async function refreshRepairViewsAfterMutation(planningId) {
    const rep = findRepairRecord(planningId);
    await loadOuvrages();

    const modal = document.getElementById('modalViewReparations');
    if (modal && modal.open && rep && rep.ouvrage_id) {
        await viewReparations(rep.ouvrage_id, rep.ouvrage_nom || document.getElementById('view-ouvrage-nom')?.textContent || 'Ouvrage');
    }
}

// Ouvrir modal d'ajout de réparation
async function openAddReparation(ouvrageId, ouvrageNom) {
    document.getElementById('add-ouvrage-id').value = ouvrageId;
    document.getElementById('add-ouvrage-nom').value = ouvrageNom;
    document.getElementById('formAddReparation').reset();
    document.getElementById('add-ouvrage-id').value = ouvrageId;
    document.getElementById('add-ouvrage-nom').value = ouvrageNom;
    await refreshRepairFicheOptions('add-fiche-poste', 'add-fiche-poste-search');
    resetFichePosteSearch('add-fiche-poste', 'add-fiche-poste-search');
    setRepairTargetFields('add', '', '', '');
    resetDetailRows('add');
    resetBonRows('add');
    document.getElementById('add-validation').checked = false;
    document.getElementById('modalAddReparation').showModal();
}

// Soumettre le formulaire d'ajout
document.getElementById('formAddReparation').addEventListener('submit', async function(e) {
    e.preventDefault();

    const ouvrageId = document.getElementById('add-ouvrage-id').value;
    const fichePosteId = document.getElementById('add-fiche-poste').value;
    const dateStr = document.getElementById('add-date').value;
    const employeId = document.getElementById('add-employe').value;
    const remarque = document.getElementById('add-remarque').value;
    const details = collectDetailRows('add');
    const bonsLivraison = collectBonRows('add');
    const validation = document.getElementById('add-validation').checked;
    const repairTarget = getRepairTargetPayload('add');

    if (hasUnresolvedDesignation('add')) {
        alert('Certaines désignations saisies ne sont pas reconnues. Sélectionnez une valeur valide dans la liste.');
        return;
    }

    if (!repairTarget.targetType || (!repairTarget.pointEauId && !repairTarget.equipementId)) {
        alert("Sélectionnez un point d'eau ou un équipement pour la réparation.");
        return;
    }

    try {
        const response = await fetch(``, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                ouvrage_id: ouvrageId,
                fiche_poste_id: fichePosteId,
                date: dateStr,
                employe_id: employeId || null,
                remarque: remarque,
                point_eau_id: repairTarget.pointEauId || null,
                equipement_id: repairTarget.equipementId || null,
                details: details,
                bons_livraison: bonsLivraison,
                validation: validation
            })
        });

        // Vérifier si la réponse est OK avant de parser JSON
        if (!response.ok) {
            const text = await response.text();
            console.error('Erreur serveur:', text);
            throw new Error(`Erreur serveur (${response.status}): ${text.substring(0, 200)}`);
        }

        const result = await response.json();

        if (result.success) {
            // Afficher un message de succès
            const employeSelect = document.getElementById('add-employe');
            const employeNom = employeSelect.options[employeSelect.selectedIndex]?.text || '';

            let message = '✓ Réparation ajoutée au planning avec succès !';
            if (employeNom) {
                message += '\n\nAssignée à : ' + employeNom;
            }

            alert(message);

            document.getElementById('modalAddReparation').close();
            loadOuvrages(); // Recharger la liste
        } else {
            alert('Erreur: ' + (result.error || 'Impossible de créer la réparation'));
        }
    } catch (error) {
        alert('Erreur réseau: ' + error.message);
    }
});

// Voir les réparations d'un ouvrage
async function viewReparations(ouvrageId, ouvrageNom) {
    console.log('[DEBUG] viewReparations appelé - Ouvrage:', ouvrageNom, 'ID:', ouvrageId);

    // Stocker l'ID de l'ouvrage pour pouvoir recharger après marquage
    currentViewOuvrageId = ouvrageId;

    document.getElementById('view-ouvrage-nom').textContent = ouvrageNom;

    const listContainer = document.getElementById('reparations-list');
    listContainer.innerHTML = '<p class="text-center py-4"><span class="loading loading-spinner loading-md"></span></p>';

    document.getElementById('modalViewReparations').showModal();

    try {
        const url = `?ouvrage_id=${ouvrageId}`;
        console.log('[DEBUG] URL API:', url);

        const response = await fetch(url);
        const data = await response.json();

        console.log('[DEBUG] Réponse API:', data);
        console.log('[DEBUG] Nombre de réparations:', data.reparations ? data.reparations.length : 0);

        if (data.success) {
            currentModalReparations = Array.isArray(data.reparations) ? data.reparations : [];
            applyViewReparationsToggle();
        } else {
            currentModalReparations = [];
            listContainer.innerHTML = '<p class="text-error">Erreur lors du chargement</p>';
        }
    } catch (error) {
        console.error('[DEBUG] Erreur réseau:', error);
        currentModalReparations = [];
        listContainer.innerHTML = '<p class="text-error">Erreur réseau</p>';
    }
}

function isReparationTerminee(rep) {
    return rep && (rep.statut === 'terminee' || rep.statut === 'validee');
}

function applyViewReparationsToggle() {
    const modalToggle = document.getElementById('view-toggle-non-terminees');
    const onlyNonTerminees = Boolean(modalToggle && modalToggle.checked);
    const reparations = onlyNonTerminees
        ? currentModalReparations.filter(rep => !isReparationTerminee(rep))
        : currentModalReparations;

    displayReparationsList(reparations);
}

// Afficher la liste des réparations
function displayReparationsList(reparations) {
    const container = document.getElementById('reparations-list');

    if (reparations.length === 0) {
        const onlyNonTerminees = document.getElementById('view-toggle-non-terminees')?.checked;
        container.innerHTML = onlyNonTerminees
            ? '<p class="text-center text-base-content/50 py-4">Aucune reparation non terminee pour cet ouvrage</p>'
            : '<p class="text-center text-base-content/50 py-4">Aucune réparation pour cet ouvrage</p>';
        return;
    }

    container.innerHTML = '';

    reparations.forEach(rep => {
        const statusBadge = getStatusBadge(rep.statut_display);
        const estTerminee = rep.statut === 'terminee' || rep.statut === 'validee';
        const manualPriority = getManualPriorityMeta(rep.priorite_suivi);
        const escapedDescription = (rep.description || '').replace(/'/g, "\\'");
        const photoProofs = renderRepairPhotoProofs(rep.photos, rep.photo_count);
        const hasPendingBons = Array.isArray(rep.bons_livraison)
            && rep.bons_livraison.some(bon => bon.statut !== 'livre');

        const card = document.createElement('div');
        card.className = 'card bg-base-200 shadow-sm';
        card.innerHTML = `
            <div class="card-body p-4">
                <div class="flex justify-between items-start gap-3">
                    <div class="flex-1">
                        <div class="flex items-center gap-2 mb-2">
                            <h4 class="font-bold">${rep.description}</h4>
                            ${statusBadge}
                            ${estTerminee ? '<span class="badge badge-success badge-sm"><i class="fas fa-check mr-1"></i>Terminé</span>' : ''}
                            ${manualPriority ? `<span class="badge ${manualPriority.badgeClass} badge-sm">Priorité ${manualPriority.label}</span>` : ''}
                            ${rep.photo_count ? `<span class="badge badge-accent badge-sm"><i class="fas fa-camera mr-1"></i>${rep.photo_count}</span>` : ''}
                        </div>

                        ${rep.remarque ? `
                            <div class="mt-2">
                                <p class="text-xs font-semibold text-base-content/80">Remarque:</p>
                                <p class="text-sm text-base-content/70">${rep.remarque}</p>
                            </div>
                        ` : ''}

                        ${rep.bilan ? `
                            <div class="mt-2">
                                <p class="text-xs font-semibold text-base-content/80">Bilan:</p>
                                <p class="text-sm text-base-content/70">${rep.bilan}</p>
                            </div>
                        ` : ''}

                        ${rep.suite_a_donner ? `
                            <div class="mt-2">
                                <p class="text-xs font-semibold text-base-content/80">Suite à donner:</p>
                                <p class="text-sm text-base-content/70">${rep.suite_a_donner}</p>
                            </div>
                        ` : ''}

                        ${photoProofs}
                    </div>

                    <div class="flex gap-2">
                        <button onclick="openEditReparation('${rep.id}')"
                                class="btn btn-info btn-sm"
                                title="Modifier la fiche de poste et la remarque">
                            <i class="fas fa-edit"></i>
                        </button>
                        ${hasPendingBons ? (
                            rep.statut === 'validee'
                                ? `<button onclick="livrerReparation('${rep.id}', '${escapedDescription}')"
                                        class="btn btn-secondary btn-sm"
                                        title="Livrer et générer le bon de livraison PDF">
                                        <i class="fas fa-truck"></i>
                                   </button>`
                                : `<button class="btn btn-secondary btn-sm btn-disabled"
                                        disabled
                                        title="Validez la réparation avant livraison">
                                        <i class="fas fa-truck"></i>
                                   </button>`
                        ) : ''}
                        ${hasPendingBons ? `
                            <button onclick="utiliserPiecesTransferees('${rep.id}', '${escapedDescription}')"
                                    class="btn btn-accent btn-sm"
                                    title="Marquer directement les pièces déjà transférées comme livrées et utilisées, sans PDF">
                                <i class="fas fa-box-open"></i>
                            </button>
                        ` : ''}
                        ${!estTerminee ? `
                            <button onclick="marquerTerminee('${rep.id}', '${escapedDescription}')"
                                    class="btn btn-success btn-sm"
                                    title="Marquer comme terminée">
                                <i class="fas fa-check"></i>
                            </button>
                        ` : ''}
                        ${estTerminee ? `
                            <button onclick="marquerNonTerminee('${rep.id}', '${escapedDescription}')"
                                    class="btn btn-warning btn-sm"
                                    title="Marquer comme non terminée">
                                <i class="fas fa-undo"></i>
                            </button>
                        ` : ''}
                        <button onclick="supprimerReparation('${rep.id}', '${escapedDescription}')"
                                class="btn btn-error btn-sm"
                                title="Supprimer cette réparation">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>

                <div class="flex gap-4 mt-3 text-xs text-base-content/70 border-t border-base-300 pt-2">
                    <span><i class="fas fa-calendar mr-1"></i>Signalé: ${rep.date_signalement}</span>
                    ${rep.date_prevue ? `<span><i class="fas fa-calendar-check mr-1"></i>Prévu: ${rep.date_prevue}</span>` : ''}
                    ${rep.assigne_a ? `<span><i class="fas fa-user mr-1"></i>${rep.assigne_a.surnom}</span>` : ''}
                </div>

                <!-- Section Détails de planning -->
                ${rep.details && rep.details.length > 0 ? `
                    <div class="mt-4 border-t border-base-300 pt-3">
                        <div class="flex items-center gap-2 mb-3">
                            <i class="fas fa-list-ul text-info"></i>
                            <h5 class="font-bold text-sm">Détails (avances) (${rep.total_details || rep.details.length})</h5>
                        </div>

                        <div class="overflow-x-auto">
                            <table class="table table-xs table-zebra">
                                <thead>
                                    <tr class="bg-base-300">
                                        <th>Désignation</th>
                                        <th>Type</th>
                                        <th>Cible</th>
                                        <th>Qté</th>
                                        <th>P.U.</th>
                                        <th>Montant</th>
                                        <th>Retour</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${rep.details.map(detail => {
                                        const hasRetour = detail.retour_caissiere;

                                        return `
                                        <tr>
                                                <td class="font-semibold">${detail.designation || '-'}</td>
                                                <td><span class="badge badge-sm badge-ghost">${detail.type_designation || '-'}</span></td>
                                                <td><span class="badge badge-outline badge-sm">${detail.point_eau ? `PE: ${detail.point_eau}` : detail.equipement ? `EQ: ${detail.equipement}` : '-'}</span></td>
                                                <td class="text-right">${detail.quantite || 0}</td>
                                                <td class="text-right">${detail.prix_unitaire ? detail.prix_unitaire.toLocaleString('fr-FR') + ' Ar' : '-'}</td>
                                                <td class="text-right font-bold">${detail.montant ? detail.montant.toLocaleString('fr-FR') + ' Ar' : '-'}</td>
                                                <td class="text-center">
                                                    ${hasRetour ?
                                                        `<span class="badge badge-success badge-xs" title="Retourné le ${detail.date_retour || ''}">
                                                            <i class="fas fa-check"></i>
                                                        </span>` :
                                                        `<span class="badge badge-warning badge-xs">
                                                            <i class="fas fa-clock"></i>
                                                        </span>`
                                                    }
                                                </td>
                                            </tr>
                                        `;
                                    }).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ` : ''}

                ${rep.bons_livraison && rep.bons_livraison.length > 0 ? `
                    <div class="mt-4 border-t border-base-300 pt-3">
                        <div class="flex items-center gap-2 mb-3">
                            <i class="fas fa-truck text-success"></i>
                            <h5 class="font-bold text-sm">Bons de livraison (${rep.bons_livraison.length})</h5>
                        </div>
                        <div class="overflow-x-auto">
                            <table class="table table-xs table-zebra">
                                <thead>
                                    <tr class="bg-base-300">
                                        <th>Désignation</th>
                                        <th>Cible</th>
                                        <th>Qté</th>
                                        <th>Magasin</th>
                                        <th>Statut</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${rep.bons_livraison.map(bon => `
                                        <tr>
                                            <td class="font-semibold">${bon.designation || '-'}</td>
                                            <td><span class="badge badge-outline badge-sm">${bon.point_eau ? `PE: ${bon.point_eau}` : bon.equipement ? `EQ: ${bon.equipement}` : '-'}</span></td>
                                            <td class="text-right">${bon.quantite || 0}</td>
                                            <td><span class="text-xs">${bon.magasin || '-'}</span></td>
                                            <td>
                                                <span class="badge badge-${bon.statut === 'livre' ? 'success' : bon.statut === 'en_cours' ? 'warning' : 'ghost'} badge-xs">
                                                    ${bon.statut || '-'}
                                                </span>
                                            </td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
        container.appendChild(card);
    });
}

// Badge de statut
function getStatusBadge(statut) {
    const badges = {
        'Signalée': '<span class="badge badge-error">Signalée</span>',
        'Planifiée': '<span class="badge badge-warning">Planifiée</span>',
        'En cours': '<span class="badge badge-info">En cours</span>',
        'Terminée': '<span class="badge badge-success">Terminée</span>',
        'Validée': '<span class="badge badge-primary">Validée</span>'
    };
    return badges[statut] || '<span class="badge badge-ghost">Inconnue</span>';
}

// Fonction pour plier/déplier les sections (Districts et Communes)
function toggleSection(sectionId) {
    const icon = document.getElementById(`icon-${sectionId}`);

    if (!icon) return;

    const setIconState = (targetIcon, expanded) => {
        if (!targetIcon) return;
        targetIcon.classList.toggle('fa-chevron-down', expanded);
        targetIcon.classList.toggle('fa-chevron-right', !expanded);
    };

    // Détecter si c'est une vue Table ou Cards
    const isTable = sectionId.includes('-table-');

    if (isTable) {
        // Déterminer le bon tbody selon l'identifiant de section
        const ouvragesTbody = document.getElementById('ouvrages-table');
        const communesTbody = document.getElementById('communes-table');
        let tbody = ouvragesTbody;

        if (sectionId.startsWith('region-table-')) {
            tbody = communesTbody;
        } else if (sectionId.startsWith('district-table-')) {
            const hasOuvragesRows = !!(ouvragesTbody && ouvragesTbody.querySelector(`tr[data-district-group="${sectionId}"]`));
            tbody = hasOuvragesRows ? ouvragesTbody : communesTbody;
        } else if (sectionId.startsWith('commune-table-')) {
            tbody = ouvragesTbody;
        }
        if (!tbody) return;

        const isRegion = sectionId.startsWith('region-table-');
        const isDistrict = sectionId.startsWith('district-table-');
        const isCollapsed = icon.classList.contains('fa-chevron-right');
        const willExpand = isCollapsed;
        const isOuvragesTable = tbody.id === 'ouvrages-table';

        if (isRegion) {
            // Toggle région: afficher les districts, puis les communes des districts déjà ouverts
            const rows = tbody.querySelectorAll(`tr[data-region-group="${sectionId}"]`);
            rows.forEach(row => {
                if (!willExpand) {
                    row.classList.add('hidden');
                    return;
                }

                const districtGroup = row.dataset.districtGroup;
                if (!districtGroup) {
                    row.classList.remove('hidden');
                    return;
                }

                const districtIcon = document.getElementById(`icon-${districtGroup}`);
                const districtExpanded = districtIcon && districtIcon.classList.contains('fa-chevron-down');
                if (districtExpanded) {
                    row.classList.remove('hidden');
                } else {
                    row.classList.add('hidden');
                }
            });
        } else if (isDistrict) {
            // Toggle district: en vue ouvrages, respecter l'état plié/déplié des communes
            const rows = tbody.querySelectorAll(`tr[data-district-group="${sectionId}"]`);
            rows.forEach(row => {
                if (!willExpand) {
                    row.classList.add('hidden');
                    return;
                }

                if (!isOuvragesTable) {
                    row.classList.remove('hidden');
                    return;
                }

                const communeGroup = row.dataset.communeGroup;
                if (!communeGroup) {
                    row.classList.remove('hidden');
                    return;
                }

                const communeIcon = document.getElementById(`icon-${communeGroup}`);
                const communeExpanded = communeIcon && communeIcon.classList.contains('fa-chevron-down');
                if (communeExpanded) {
                    row.classList.remove('hidden');
                } else {
                    row.classList.add('hidden');
                }
            });
        } else {
            // Toggle commune: afficher les lignes seulement si le district parent est ouvert
            const rows = tbody.querySelectorAll(`tr[data-commune-group="${sectionId}"]`);
            rows.forEach(row => {
                if (!willExpand) {
                    row.classList.add('hidden');
                    return;
                }

                const districtGroup = row.dataset.districtGroup;
                const districtIcon = districtGroup ? document.getElementById(`icon-${districtGroup}`) : null;
                const districtExpanded = districtIcon ? districtIcon.classList.contains('fa-chevron-down') : true;
                if (districtExpanded) {
                    row.classList.remove('hidden');
                } else {
                    row.classList.add('hidden');
                }
            });
        }

        setIconState(icon, willExpand);
    } else {
        // Pour la vue Cards
        const section = document.getElementById(sectionId);
        if (!section) return;

        if (section.classList.contains('hidden')) {
            section.classList.remove('hidden');
            setIconState(icon, true);
        } else {
            section.classList.add('hidden');
            setIconState(icon, false);
        }
    }
}

// Filtres
function applyFilters() {
    const organisationSelect = document.getElementById('filter-organisation');
    if (organisationSelect) {
        currentFilters.organisation = organisationSelect.value;
    }
    currentFilters.region_id = document.getElementById('filter-region').value;
    currentFilters.district_id = document.getElementById('filter-district').value;
    currentFilters.commune_id = document.getElementById('filter-commune').value;
    currentFilters.employe_id = document.getElementById('filter-employe').value;
    currentFilters.recherche = document.getElementById('filter-recherche').value.trim();
    currentFilters.grading = document.getElementById('filter-grading').value;
    currentFilters.annee = document.getElementById('filter-annee').value;
    loadOuvrages();
}

function resetFilters() {
    const organisationSelect = document.getElementById('filter-organisation');
    if (organisationSelect) {
        organisationSelect.value = defaultOrganisationFilter;
    }
    document.getElementById('filter-region').value = 'all';
    document.getElementById('filter-district').value = 'all';
    document.getElementById('filter-commune').value = 'all';
    document.getElementById('filter-employe').value = 'all';
    document.getElementById('filter-recherche').value = '';
    document.getElementById('filter-grading').value = 'all';
    document.getElementById('filter-annee').value = 'null';
    currentFilters = {
        organisation: defaultOrganisationFilter,
        region_id: 'all',
        district_id: 'all',
        commune_id: 'all',
        employe_id: 'all',
        recherche: '',
        statut: 'all',
        grading: 'all',
        annee: 'null'
    };
    // Retirer la surbrillance des stats
    updateStatutHighlight();
    loadFilterOptions();
    loadOuvrages();
}

function filterByStatut(statut) {
    console.log('[DEBUG] Filtrage par statut:', statut);

    // Si on clique sur le même statut, on désactive le filtre
    if (currentFilters.statut === statut) {
        currentFilters.statut = 'all';
    } else {
        currentFilters.statut = statut;
    }

    // Mettre à jour l'apparence visuelle des stats
    updateStatutHighlight();

    // Réappliquer le filtrage
    filterAndDisplayOuvrages();
}

function filterByGrading(grading) {
    console.log('[DEBUG] Filtrage par grading:', grading);

    // Si on clique sur le même grading, on désactive le filtre
    if (currentFilters.grading === grading) {
        currentFilters.grading = 'all';
    } else {
        currentFilters.grading = grading;
    }

    // Mettre à jour le select
    document.getElementById('filter-grading').value = currentFilters.grading;

    // Mettre à jour l'apparence visuelle des barres
    updateGradingHighlight();

    // Recharger les ouvrages avec le nouveau filtre
    loadOuvrages();
}

// Mettre en surbrillance la barre de grading sélectionnée
function updateGradingHighlight() {
    const gradings = ['a', 'b', 'b-panne', 'c', 'd', 'd-panne'];

    gradings.forEach(g => {
        const row = document.getElementById(`bar-row-grading-${g}`);
        if (row) {
            const gradingValue = g.replace('-', '_').toUpperCase();
            if (currentFilters.grading === gradingValue) {
                row.classList.add('ring', 'ring-primary', 'ring-offset-2');
            } else {
                row.classList.remove('ring', 'ring-primary', 'ring-offset-2');
            }
        }
    });
}

// Mettre en surbrillance la stat sélectionnée
function updateStatutHighlight() {
    // Liste des statuts
    const statuts = ['signalee', 'planifiee', 'en_cours', 'terminee', 'validee'];
    const statutLabels = {
        'signalee': 'Signalées',
        'planifiee': 'Planifiées',
        'en_cours': 'En cours',
        'terminee': 'Terminées',
        'validee': 'Validées'
    };

    // Retirer toutes les surbrillances
    statuts.forEach(s => {
        const statDiv = document.querySelector(`.stat[onclick*="${s}"]`);
        if (statDiv) {
            statDiv.classList.remove('bg-base-300', 'ring-2', 'ring-primary');
        }
    });

    // Ajouter la surbrillance au statut sélectionné
    const indicator = document.getElementById('statut-filter-indicator');
    const indicatorText = document.getElementById('statut-filter-text');

    if (currentFilters.statut !== 'all') {
        const selectedDiv = document.querySelector(`.stat[onclick*="${currentFilters.statut}"]`);
        if (selectedDiv) {
            selectedDiv.classList.add('bg-base-300', 'ring-2', 'ring-primary');
        }

        // Afficher l'indicateur de filtre
        if (indicator && indicatorText) {
            indicator.classList.remove('hidden');
            indicatorText.textContent = `Filtré par: ${statutLabels[currentFilters.statut]}`;
        }
    } else {
        // Masquer l'indicateur
        if (indicator) {
            indicator.classList.add('hidden');
        }
    }
}

// Supprimer une réparation
async function supprimerReparation(planningId, description) {
    if (!confirm(`⚠️ ATTENTION ⚠️\n\nSupprimer définitivement la réparation "${description}" ?\n\nCette action est IRRÉVERSIBLE et supprimera toutes les données liées.`)) {
        return;
    }

    try {
        const url = `/plannings/reparations/api/${planningId}/supprimer/`;

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();

        if (data.success) {
            // Recharger la liste des réparations
            const ouvrageNom = document.getElementById('view-ouvrage-nom').textContent;
            const ouvrageId = currentViewOuvrageId;
            await viewReparations(ouvrageId, ouvrageNom);

            // Recharger aussi la liste des ouvrages pour mettre à jour les stats
            loadOuvrages();

            alert('✓ ' + data.message);
        } else {
            alert('Erreur: ' + data.error);
        }
    } catch (error) {
        alert('Erreur réseau: ' + error.message);
    }
}

// Ouvrir le modal d'édition d'une réparation
async function openEditReparation(planningId) {
    try {
        let rep = findRepairRecord(planningId);

        if (
            !rep
            || rep.summary_only
            || !Array.isArray(rep.details)
            || !Array.isArray(rep.bons_livraison)
            || !Array.isArray(rep.photos)
        ) {
            const params = new URLSearchParams();
            params.set('planning_id', planningId);
            const url = `?${params.toString()}`;
            const response = await fetch(url);
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Impossible de charger la réparation');
            }
            rep = (data.reparations || []).find((item) => item.id === planningId) || rep;
        }

        if (rep) {
            // Remplir le formulaire
            document.getElementById('edit-planning-id').value = rep.id;
            document.getElementById('edit-ouvrage-id').value = rep.ouvrage_id || '';
            await refreshRepairFicheOptions(
                'edit-fiche-poste',
                'edit-fiche-poste-search',
                rep.fiche_poste_id || rep.activite_id || ''
            );
            resetFichePosteSearch('edit-fiche-poste', 'edit-fiche-poste-search');
            document.getElementById('edit-fiche-poste').value = rep.fiche_poste_id || rep.activite_id || '';
            document.getElementById('edit-remarque').value = rep.remarque || '';
            document.getElementById('edit-suite-a-donner').value = rep.suite_a_donner || '';
            document.getElementById('edit-priorite-suivi').value = rep.priorite_suivi || '';

            // Remplir employé assigné
            if (rep.assigne_a && rep.assigne_a.id) {
                document.getElementById('edit-employe').value = rep.assigne_a.id;
            } else {
                document.getElementById('edit-employe').value = '';
            }

            // Remplir date prévue
            if (rep.date_prevue) {
                document.getElementById('edit-date').value = rep.date_prevue;
            } else {
                document.getElementById('edit-date').value = '';
            }

            const repPointEauId = rep.point_eau_id
                || rep.details?.find(d => d.point_eau_id)?.point_eau_id
                || rep.bons_livraison?.find(b => b.point_eau_id)?.point_eau_id
                || '';
            const repEquipementId = rep.equipement_id
                || rep.details?.find(d => d.equipement_id)?.equipement_id
                || rep.bons_livraison?.find(b => b.equipement_id)?.equipement_id
                || '';
            const repTargetType = repPointEauId ? 'point_eau' : (repEquipementId ? 'equipement' : '');
            setRepairTargetFields('edit', repTargetType, repPointEauId, repEquipementId);

            setEditRepairPhotos(rep.photos || []);

            // Remplir tous les détails existants
            const detailRows = (rep.details || []).map(d => ({
                detail_id: d.id || null,
                designation_id: d.designation_id || '',
                quantity: d.quantite || 1,
                pu: d.prix_unitaire || 0,
            }));
            resetDetailRows('edit', detailRows);
            const bonRows = (rep.bons_livraison || []).map(b => ({
                bon_id: b.id || null,
                designation_id: b.designation_id || '',
                quantite: b.quantite || 1,
                magasin: b.magasin || '',
            }));
            resetBonRows('edit', bonRows);
            // Ouvrir le modal
            document.getElementById('modalEditReparation').showModal();
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur lors du chargement des données');
    }
}

// Soumettre le formulaire de modification
document.getElementById('formEditReparation').addEventListener('submit', async function(e) {
    e.preventDefault();

    const planningId = document.getElementById('edit-planning-id').value;
    const fichePosteId = document.getElementById('edit-fiche-poste').value;
    const employeId = document.getElementById('edit-employe').value;
    const datePrevue = document.getElementById('edit-date').value;
    const remarque = document.getElementById('edit-remarque').value;
    const suiteADonner = document.getElementById('edit-suite-a-donner').value;
    const prioriteSuivi = document.getElementById('edit-priorite-suivi').value;
    const details = collectDetailRows('edit');
    const bonsLivraison = collectBonRows('edit');
    const photos = editRepairPhotosData;
    const repairTarget = getRepairTargetPayload('edit');
    if (hasUnresolvedDesignation('edit')) {
        alert('Certaines désignations saisies ne sont pas reconnues. Sélectionnez une valeur valide dans la liste.');
        return;
    }
    if (!repairTarget.targetType || (!repairTarget.pointEauId && !repairTarget.equipementId)) {
        alert("Sélectionnez un point d'eau ou un équipement pour la réparation.");
        return;
    }

    try {
        const url = `/plannings/reparations/api/${planningId}/modifier/`;
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                fiche_poste_id: fichePosteId,
                employe_id: employeId,
                date_prevue: datePrevue,
                remarque: remarque,
                suite_a_donner: suiteADonner,
                priorite_suivi: prioriteSuivi,
                point_eau_id: repairTarget.pointEauId || null,
                equipement_id: repairTarget.equipementId || null,
                photos: photos,
                details: details,
                bons_livraison: bonsLivraison
            })
        });

        const data = await response.json();

        if (data.success) {
            // Fermer le modal d'édition
            document.getElementById('modalEditReparation').close();
            await refreshRepairViewsAfterMutation(planningId);

            alert('✓ Réparation modifiée avec succès !');
        } else {
            alert('Erreur: ' + (data.error || 'Erreur inconnue'));
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
    }
});

// Livrer une réparation (bons de livraison) et télécharger le PDF
async function livrerReparation(planningId, description) {
    if (!confirm(`Livrer les bons de "${description}" et générer le bon PDF ?`)) {
        return;
    }

    try {
        const url = `/plannings/reparations/api/${planningId}/livrer/`;
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({})
        });

        if (!response.ok) {
            let errorMessage = 'Erreur lors de la livraison';
            try {
                const errorData = await response.json();
                errorMessage = errorData.error || errorMessage;
            } catch (_) {}
            alert('Erreur: ' + errorMessage);
            return;
        }

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `bon_livraison_reparation_${planningId}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);

        const ouvrageNom = document.getElementById('view-ouvrage-nom').textContent;
        const ouvrageId = currentViewOuvrageId;
        await viewReparations(ouvrageId, ouvrageNom);
        loadOuvrages();
    } catch (error) {
        alert('Erreur réseau: ' + error.message);
    }
}

// Enregistrer les pièces déjà transférées et déjà utilisées, sans BL/PDF
async function utiliserPiecesTransferees(planningId, description) {
    if (!confirm(`Enregistrer les pièces déjà transférées de "${description}" comme livrées et utilisées ?\n\nCette action validera aussi la réparation sans générer de bon PDF.`)) {
        return;
    }

    try {
        const url = `/plannings/reparations/api/${planningId}/utiliser-pieces-transferees/`;
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({})
        });

        const data = await response.json();

        if (data.success) {
            await refreshRepairViewsAfterMutation(planningId);
            alert('✓ ' + (data.message || 'Pièces transférées enregistrées avec succès.'));
        } else {
            alert('Erreur: ' + (data.error || 'Erreur inconnue'));
        }
    } catch (error) {
        alert('Erreur réseau: ' + error.message);
    }
}

// Marquer une réparation comme terminée
async function marquerTerminee(planningId, description) {
    if (!confirm(`Marquer la réparation "${description}" comme terminée ?\n\nCette action mettra à jour le statut dans la base de données.`)) {
        return;
    }

    try {
        // Construire l'URL en JavaScript sans passer par Django template
        const url = `/plannings/reparations/api/${planningId}/marquer-terminee/`;

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                planning_id: planningId
            })
        });

        const data = await response.json();

        if (data.success) {
            await refreshRepairViewsAfterMutation(planningId);

            alert('✓ Réparation marquée comme terminée !');
        } else {
            alert('Erreur: ' + (data.error || 'Erreur inconnue'));
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
    }
}

// Marquer une reparation comme non terminee
async function marquerNonTerminee(planningId, description) {
    if (!confirm(`Marquer la réparation "${description}" comme non terminée ?\n\nCette action retirera le statut terminé.`)) {
        return;
    }

    try {
        const url = `/plannings/reparations/api/${planningId}/marquer-non-terminee/`;

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                planning_id: planningId
            })
        });

        const data = await response.json();

        if (data.success) {
            await refreshRepairViewsAfterMutation(planningId);
            alert('✓ Réparation marquée comme non terminée !');
        } else {
            alert('Erreur: ' + (data.error || 'Erreur inconnue'));
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
    }
}

// Helper pour CSRF
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Variable globale pour stocker l'ID de l'ouvrage en cours de visualisation
let currentViewOuvrageId = null;

// Toggle du bouton "Voir planning" selon si un employé est sélectionné
function togglePlanningButton() {
    const employeId = document.getElementById('add-employe').value;
    const btn = document.getElementById('btn-voir-planning');

    if (employeId && employeId !== '') {
        btn.classList.remove('hidden');
    } else {
        btn.classList.add('hidden');
    }
}

// Ouvrir le planning de l'employé sélectionné dans un nouvel onglet
function voirPlanningEmploye() {
    const employeId = document.getElementById('add-employe').value;
    const dateStr = document.getElementById('add-date').value;

    if (!employeId) {
        alert('Veuillez d\'abord sélectionner un employé');
        return;
    }

    // Construire l'URL du planning (route correcte: /plannings/)
    let url = `/plannings/?employe_id=${employeId}`;

    // Si une date est saisie, l'ajouter au filtre
    if (dateStr) {
        // Convertir DD/MM/YYYY → YYYY-MM
        const parts = dateStr.split('/');
        if (parts.length === 3) {
            const mois = `${parts[2]}-${parts[1]}`;
            url += `&mois=${mois}`;
        }
    }

    // Ouvrir dans un nouvel onglet
    window.open(url, '_blank');
}

// ========== FONCTIONS POUR L'IMPRESSION ==========

function exportReparationsExcel() {
    function askChoiceFromOptions(label, options, defaultIndex = 0) {
        if (!options || !options.length) return null;
        const safeDefault = Math.min(Math.max(defaultIndex, 0), options.length - 1);
        const list = options.map((opt, idx) => `${idx + 1}. ${opt.text}`).join('\n');
        const answer = prompt(`${label} (tapez le numéro):\n${list}`, String(safeDefault + 1));
        if (answer === null) return null;
        const idx = parseInt(answer, 10) - 1;
        if (Number.isNaN(idx) || idx < 0 || idx >= options.length) {
            alert(`${label}: choix invalide.`);
            return null;
        }
        return options[idx];
    }

    const anneeSelect = document.getElementById('filter-annee');
    const organisationSelect = document.getElementById('filter-organisation');
    const regionSelect = document.getElementById('filter-region');
    const districtSelect = document.getElementById('filter-district');
    if (!anneeSelect || !regionSelect || !districtSelect) {
        alert("Filtres d'export introuvables.");
        return;
    }

    const anneeOptions = Array.from(anneeSelect.options || [])
        .filter(opt => (opt.value || '') !== 'all')
        .map(opt => ({ value: opt.value, text: (opt.text || '').trim() }));
    const anneeDefault = Math.max(anneeOptions.findIndex(o => o.value === (anneeSelect.value || '')), 0);
    const anneeChoice = askChoiceFromOptions('Année', anneeOptions, anneeDefault);
    if (!anneeChoice) return;

    const regionOptions = Array.from(regionSelect.options || [])
        .map(opt => ({ value: opt.value || 'all', text: (opt.text || '').trim() }));
    const regionDefault = Math.max(regionOptions.findIndex(o => o.value === (regionSelect.value || 'all')), 0);
    const regionChoice = askChoiceFromOptions('Région', regionOptions, regionDefault);
    if (!regionChoice) return;

    const regionValue = regionChoice.value || 'all';
    const districtOptions = Array.from(districtSelect.options || [])
        .filter((opt) => {
            const v = opt.value || 'all';
            if (v === 'all') return true;
            if (regionValue === 'all') return true;
            return String(opt.getAttribute('data-region-id') || '') === String(regionValue);
        })
        .map(opt => ({ value: opt.value || 'all', text: (opt.text || '').trim() }));

    let districtChoice = askChoiceFromOptions('District (optionnel)', districtOptions, 0);
    if (!districtChoice) {
        districtChoice = { value: 'all', text: 'Tous les districts' };
    }

    const params = new URLSearchParams({
        organisation: organisationSelect ? (organisationSelect.value || 'all') : (currentFilters.organisation || 'all'),
        region_id: regionChoice.value || 'all',
        district_id: districtChoice.value || 'all',
        commune_id: 'all',
        employe_id: currentFilters.employe_id || 'all',
        recherche: '',
        grading: 'all',
        annee: anneeChoice.value,
        statut: 'all'
    });

    window.location.href = `?${params.toString()}`;
}

function openPrintModal() {
    document.getElementById('modalPrint').showModal();
    loadPrintOptions();
}

async function loadPrintOptions() {
    const container = document.getElementById('print-options-container');
    container.innerHTML = '<p class="text-center py-4"><span class="loading loading-spinner loading-md"></span></p>';

    try {
        // Récupérer tous les ouvrages avec leurs réparations
        const params = new URLSearchParams(currentFilters);
        const response = await fetch(`?${params.toString()}`);
        const data = await response.json();

        if (data.success && data.ouvrages) {
            // Grouper par district et commune
            const grouped = {};

            data.ouvrages.forEach(ouvrage => {
                const district = ouvrage.district || 'Sans district';
                const commune = ouvrage.commune || 'Sans commune';

                if (!grouped[district]) grouped[district] = {};
                if (!grouped[district][commune]) grouped[district][commune] = [];

                grouped[district][commune].push(ouvrage);
            });

            displayPrintOptions(grouped);
        } else {
            container.innerHTML = '<p class="text-error">Erreur lors du chargement des ouvrages</p>';
        }
    } catch (error) {
        console.error('Erreur:', error);
        container.innerHTML = '<p class="text-error">Erreur réseau</p>';
    }
}

function displayPrintOptions(districts) {
    const container = document.getElementById('print-options-container');
    container.innerHTML = '';

    Object.keys(districts).sort().forEach((district, dIndex) => {
        const districtDiv = document.createElement('div');
        districtDiv.className = 'border border-base-300 rounded-lg p-3 mb-3';

        // Header District avec checkbox
        const districtHeader = document.createElement('div');
        districtHeader.className = 'flex items-center gap-2 mb-2 font-bold';
        districtHeader.innerHTML = `
            <input type="checkbox"
                   class="checkbox checkbox-primary district-checkbox"
                   id="district-${dIndex}"
                   onchange="toggleDistrict(this, '${district}')">
            <label for="district-${dIndex}" class="cursor-pointer flex-1">
                <i class="fas fa-map-marked-alt mr-2 text-primary"></i>${district}
                <span class="badge badge-ghost badge-sm ml-2">
                    ${Object.values(districts[district]).reduce((sum, arr) => sum + arr.length, 0)} ouvrage(s)
                </span>
            </label>
        `;
        districtDiv.appendChild(districtHeader);

        // Communes du district
        const communesDiv = document.createElement('div');
        communesDiv.className = 'ml-6 space-y-2';

        Object.keys(districts[district]).sort().forEach((commune, cIndex) => {
            const ouvrages = districts[district][commune];
            const communeDiv = document.createElement('div');
            communeDiv.className = 'p-2 hover:bg-base-200 rounded transition-colors';

            // Header Commune avec checkbox - stocke les IDs des ouvrages dans data-ouvrages
            const ouvrageIds = ouvrages.map(o => o.id).join(',');
            communeDiv.innerHTML = `
                <label class="flex items-center gap-3 cursor-pointer">
                    <input type="checkbox"
                           class="checkbox checkbox-secondary commune-checkbox"
                           data-district="${district}"
                           data-commune="${commune}"
                           data-ouvrages="${ouvrageIds}">
                    <div class="flex-1">
                        <div class="font-semibold">
                            <i class="fas fa-map-marker-alt mr-2 text-secondary"></i>${commune}
                        </div>
                        <div class="text-xs text-base-content/60 mt-1">
                            ${ouvrages.length} ouvrage(s) : ${ouvrages.map(o => o.nom).join(', ')}
                        </div>
                    </div>
                    <span class="badge badge-secondary badge-sm">${ouvrages.length}</span>
                </label>
            `;

            communesDiv.appendChild(communeDiv);
        });

        districtDiv.appendChild(communesDiv);
        container.appendChild(districtDiv);
    });
}

function toggleDistrict(checkbox, district) {
    const isChecked = checkbox.checked;
    // Cocher/décocher toutes les communes du district
    const communeCheckboxes = document.querySelectorAll(`.commune-checkbox[data-district="${district}"]`);
    communeCheckboxes.forEach(cb => {
        cb.checked = isChecked;
    });
}

function imprimerSelection() {
    // Récupérer toutes les communes sélectionnées et leurs ouvrages
    const selectedCommunes = Array.from(document.querySelectorAll('.commune-checkbox:checked'));

    if (selectedCommunes.length === 0) {
        alert('Veuillez sélectionner au moins une commune');
        return;
    }

    // Récupérer tous les IDs d'ouvrages des communes sélectionnées
    const allOuvrageIds = [];
    selectedCommunes.forEach(checkbox => {
        const ouvrageIds = checkbox.dataset.ouvrages.split(',');
        allOuvrageIds.push(...ouvrageIds);
    });

    // Récupérer le type d'activités sélectionné
    const activitiesType = document.querySelector('input[name="print-activities-type"]:checked').value;

    // Construire l'URL avec les paramètres
    const ouvragesParam = allOuvrageIds.join(',');
    const url = `?ouvrages=${ouvragesParam}&type=${activitiesType}`;

    // Ouvrir dans un nouvel onglet
    window.open(url, '_blank');
    document.getElementById('modalPrint').close();
}
