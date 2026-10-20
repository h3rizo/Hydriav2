
// Variables globales
let currentType = null;
let currentTypeId = null;
let currentFiche = null;
let currentFicheId = null;
let currentActivite = null;
let currentActiviteId = null;
let currentEditId = null;
let currentEditType = null;
let currentDeleteId = null;
let currentDeleteType = null;
let currentImportType = null;
let ficheMode = 'create';
let pendingFicheModalId = null;
let fichesCourantes = [];

// Charger les données au démarrage
document.addEventListener('DOMContentLoaded', function() {
    loadTypesActivites();
    updateStats();
});

// ===== FONCTIONS DE CHARGEMENT =====

let groupesTypes = [];

async function loadGroupesTypes() {
    const response = await fetch('/plannings/crud/api/groupes-types-activites/');
    if (!response.ok) throw new Error(`Groupes: HTTP ${response.status}`);
    groupesTypes = await response.json();
    return groupesTypes;
}

function groupeOptionsHtml(selectedId) {
    return '<option value="">— Non classé —</option>' + groupesTypes.map(g =>
        `<option value="${g.id}" ${g.id === selectedId ? 'selected' : ''}>${escapeHtml(g.nom)}</option>`
    ).join('');
}

// Regroupements pliés : mémorisés par navigateur (localStorage)
const GROUPES_COLLAPSED_KEY = 'hydria.typesActivites.groupesPlies';

function getGroupesCollapsed() {
    try {
        const raw = JSON.parse(localStorage.getItem(GROUPES_COLLAPSED_KEY) || '[]');
        return new Set(Array.isArray(raw) ? raw : []);
    } catch (e) {
        return new Set();
    }
}

function saveGroupesCollapsed(set) {
    try {
        localStorage.setItem(GROUPES_COLLAPSED_KEY, JSON.stringify([...set]));
    } catch (e) { /* stockage indisponible : le choix ne sera pas mémorisé */ }
}

function currentKeyOf(headerRow) {
    return headerRow.dataset.groupe;
}

function applyGroupeState(key, isCollapsed) {
    document.querySelectorAll('#typesActivitesTable tbody tr').forEach(row => {
        if (row.dataset.groupe !== key) return;
        if (row.classList.contains('groupe-header')) {
            const chevron = row.querySelector('.groupe-chevron');
            if (chevron) chevron.classList.toggle('-rotate-90', isCollapsed);
        } else {
            row.classList.toggle('hidden', isCollapsed);
        }
    });
}

function toggleGroupe(key) {
    const collapsed = getGroupesCollapsed();
    const nowCollapsed = !collapsed.has(key);
    if (nowCollapsed) collapsed.add(key); else collapsed.delete(key);
    saveGroupesCollapsed(collapsed);
    applyGroupeState(key, nowCollapsed);
}

function setAllGroupesCollapsed(isCollapsed) {
    const keys = [...document.querySelectorAll('#typesActivitesTable tr.groupe-header')]
        .map(h => h.dataset.groupe);
    saveGroupesCollapsed(isCollapsed ? new Set(keys) : new Set());
    keys.forEach(k => applyGroupeState(k, isCollapsed));
}

async function loadTypesActivites() {
    try {
        const response = await fetch('/plannings/crud/api/types-activites/');
        if (!response.ok) {
            const text = await response.text();
            throw new Error(`HTTP ${response.status} - ${text.slice(0, 200)}`);
        }
        const types = await response.json();

        const tbody = document.querySelector('#typesActivitesTable tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        const collapsed = getGroupesCollapsed();
        let currentKey = null;

        const renderType = type => {
            const row = document.createElement('tr');
            row.className = 'cursor-pointer';
            row.dataset.groupe = currentKey;
            if (collapsed.has(currentKey)) row.classList.add('hidden');
            row.onclick = () => selectType(type.id, type.nomtype);
            
            const deleteButton = canDeleteItems ? `
                    <button data-name="${escapeHtml(type.nomtype)}" onclick="event.stopPropagation(); deleteItem('type_activite', '${type.id}', this.dataset.name, ${type.fiches_poste_count || 0})"
                            class="btn btn-ghost btn-xs text-error" title="Supprimer">
                        <i class="fas fa-trash"></i>
                    </button>
                ` : '';

            row.innerHTML = `
            <td>
                <input type="radio" name="selectedTypeActivite" value="${type.id}" class="radio radio-primary radio-sm"
                       onclick="event.stopPropagation();" onchange="selectTypeActiviteRadio('${type.id}')">
            </td>
            <td class="font-semibold pl-6">${escapeHtml(type.nomtype)}</td>
            <td><span class="badge badge-secondary badge-outline">${type.fiches_poste_count || 0}</span></td>
            <td>${type.createdat ? new Date(type.createdat).toLocaleDateString('fr-FR') : '-'}</td>
            <td>
                <div class="flex gap-1">
                    <button data-name="${escapeHtml(type.nomtype)}" onclick="event.stopPropagation(); editItem('type_activite', '${type.id}', this.dataset.name)"
                            class="btn btn-ghost btn-xs" title="Modifier">
                        <i class="fas fa-edit"></i>
                    </button>
                    ${deleteButton}
                </div>
            </td>
        `;
            tbody.appendChild(row);
        };

        const groupes = await loadGroupesTypes();
        const ids = new Set(groupes.map(g => g.id));
        const sections = groupes.map(g => [g.id, g.nom, g.icone || 'fa-layer-group']);
        sections.push([null, 'Non classés', 'fa-ellipsis-h']);
        sections.forEach(([gid, label, icon]) => {
            const items = types.filter(t => gid === null ? !ids.has(t.groupe_id) : t.groupe_id === gid);
            if (!items.length) return;
            currentKey = gid === null ? '__none__' : gid;
            const isCollapsed = collapsed.has(currentKey);
            const header = document.createElement('tr');
            header.className = 'groupe-header cursor-pointer select-none';
            header.dataset.groupe = currentKey;
            header.onclick = () => toggleGroupe(currentKeyOf(header));
            header.innerHTML = `<td colspan="5" class="bg-base-300 font-bold text-sm">
                <i class="fas fa-chevron-down groupe-chevron mr-2 transition-transform ${isCollapsed ? '-rotate-90' : ''}"></i>
                <i class="fas ${escapeHtml(icon)} mr-2"></i>${escapeHtml(label)}
                <span class="badge badge-sm ml-2">${items.length}</span></td>`;
            tbody.appendChild(header);
            items.forEach(renderType);
        });
    } catch (error) {
        console.error('Erreur lors du chargement des types:', error);
        const tbody = document.querySelector('#typesActivitesTable tbody');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-error text-center">Erreur de chargement: ${escapeHtml(error.message)}</td></tr>`;
        }
        showAlert('Erreur lors du chargement des types d\'activités', 'error');
    }
}

async function selectType(typeId, typeName) {
    // Mettre en évidence la ligne sélectionnée
    document.querySelectorAll('#typesActivitesTable tbody tr').forEach(row => {
        row.classList.remove('selected-row');
    });
    // Si l'événement est déclenché par un clic
    if (event && event.currentTarget && event.currentTarget.classList) {
        event.currentTarget.classList.add('selected-row');
    }

    // Synchroniser le radio button
    const radioInput = document.querySelector(`input[name="selectedTypeActivite"][value="${typeId}"]`);
    if (radioInput) {
        radioInput.checked = true;
    }

    currentTypeId = typeId;
    currentType = typeName;

    const typeNameFichesEl = document.getElementById('selectedTypeNameForFiches');
    if (typeNameFichesEl) typeNameFichesEl.textContent = typeName;
    
    const fichesSection = document.getElementById('fichesPosteSection');
    if (fichesSection) fichesSection.style.display = 'block';

    // Masquer la section postes si elle était ouverte
    const postesSection = document.getElementById('postesFicheSection');
    if (postesSection) postesSection.style.display = 'none';
    currentFicheId = null;
    currentFiche = null;
    await loadFichesPoste(typeId);
}

function selectTypeActiviteRadio(typeId) {
    const radioInput = document.querySelector(`input[value="${typeId}"]`);
    if (radioInput) {
        const rowElement = radioInput.closest('tr');
        if (rowElement) {
            const typeName = rowElement.querySelector('td:nth-child(2)').textContent.trim();
            selectType(typeId, typeName);
        }
    }
}

function selectActiviteRadio(activiteId) {
    const radioInput = document.querySelector(`input[name="selectedActivite"][value="${activiteId}"]`);
    if (radioInput) {
        const rowElement = radioInput.closest('tr');
        if (rowElement) {
            const activiteName = rowElement.querySelector('td:nth-child(2)').textContent.trim();
            selectActivite(activiteId, activiteName);
        }
    }
}

function selectPosteActiviteRadio(posteActiviteId) {
    const radioInput = document.querySelector(`input[name="selectedPosteActivite"][value="${posteActiviteId}"]`);
    if (radioInput) {
        const rowElement = radioInput.closest('tr');
        if (rowElement) {
            document.querySelectorAll('#postesActivitesTable tbody tr').forEach(row => {
                row.classList.remove('selected-row');
            });
            rowElement.classList.add('selected-row');
        }
    }
}

async function loadActivites(typeId) {
    try {
        const response = await fetch(`/plannings/crud/api/activites/type/${typeId}/`);
        const activites = await response.json();

        const tbody = document.querySelector('#activitesTable tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        activites.forEach(activite => {
            const row = document.createElement('tr');
            row.className = 'cursor-pointer';
            row.onclick = () => selectActivite(activite.id, activite.nom);
            
            const deleteButton = canDeleteItems ? `
                        <button data-name="${escapeHtml(activite.nom)}" onclick="event.stopPropagation(); deleteItem('activite', '${activite.id}', this.dataset.name, ${activite.postes_count || 0})"
                                class="btn btn-ghost btn-xs text-error" title="Supprimer">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : '';

            row.innerHTML = `
                <td>
                    <input type="radio" name="selectedActivite" value="${activite.id}"
                           class="radio radio-primary" onclick="event.stopPropagation(); selectActiviteRadio('${activite.id}')">
                </td>
                <td class="font-semibold">${escapeHtml(activite.nom)}</td>
                <td class="text-sm text-base-content/70">${escapeHtml(activite.description || '-')}</td>
                <td><span class="badge badge-outline">${activite.postes_count || 0}</span></td>
                <td>
                    <span class="badge ${activite.is_active ? 'badge-success' : 'badge-ghost'}">
                        ${activite.is_active ? 'Actif' : 'Inactif'}
                    </span>
                </td>
                <td>
                    <div class="flex gap-1">
                        <button data-name="${escapeHtml(activite.nom)}" onclick="event.stopPropagation(); editItem('activite', '${activite.id}', this.dataset.name)"
                                class="btn btn-ghost btn-xs" title="Modifier">
                            <i class="fas fa-edit"></i>
                        </button>
                        ${deleteButton}
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Erreur lors du chargement des activités:', error);
        showAlert('Erreur lors du chargement des activités', 'error');
    }
}

async function selectActivite(activiteId, activiteName) {
    document.querySelectorAll('#activitesTable tbody tr').forEach(row => {
        row.classList.remove('selected-row');
    });
    if (event && event.currentTarget && event.currentTarget.classList) {
        event.currentTarget.classList.add('selected-row');
    }

    const radioInput = document.querySelector(`input[name="selectedActivite"][value="${activiteId}"]`);
    if (radioInput) {
        radioInput.checked = true;
    }

    currentActiviteId = activiteId;
    currentActivite = activiteName;

    document.getElementById('selectedActiviteName').textContent = activiteName;
    document.getElementById('postesActivitesSection').style.display = 'block';

    await loadPostesActivites(activiteId);
}

async function loadPostesActivites(activiteId) {
    try {
        const response = await fetch(`/plannings/crud/api/activites-postes/activite/${activiteId}/`);
        const postes = await response.json();

        const tbody = document.querySelector('#postesActivitesTable tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        postes.forEach(poste => {
            const row = document.createElement('tr');
            
            const deleteButton = canDeleteItems ? `
                        <button data-name="${escapeHtml(poste.poste_nom || poste.nom)}" onclick="deleteItem('activite_poste', '${poste.id}', this.dataset.name, 0)"
                                class="btn btn-ghost btn-xs text-error" title="Supprimer">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : '';
            row.innerHTML = `
                <td>
                    <input type="radio" name="selectedPosteActivite" value="${poste.id}"
                           class="radio radio-primary" onclick="event.stopPropagation(); selectPosteActiviteRadio('${poste.id}')">
                </td>
                <td class="font-semibold">${escapeHtml(poste.poste_nom || 'Poste non défini')}</td>
                <td>${poste.fiche_poste_tache ? escapeHtml(poste.fiche_poste_tache) : '-'}</td>
                <td>
                    <span class="badge ${poste.is_active ? 'badge-success' : 'badge-ghost'}">
                        ${poste.is_active ? 'Actif' : 'Inactif'}
                    </span>
                </td>
                <td>${poste.created_at ? new Date(poste.created_at).toLocaleDateString('fr-FR') : '-'}</td>
                <td>
                    <div class="flex gap-1">
                        <button data-name="${escapeHtml(poste.poste_nom || poste.nom)}" onclick="editItem('activite_poste', '${poste.id}', this.dataset.name)"
                                class="btn btn-ghost btn-xs" title="Modifier">
                            <i class="fas fa-edit"></i>
                        </button>
                        ${deleteButton}
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Erreur lors du chargement des postes:', error);
        showAlert('Erreur lors du chargement des postes d\'activités', 'error');
    }
}

async function loadFichesPoste(typeId) {
    try {
        const response = await fetch(`/plannings/crud/api/fiches-poste/type/${typeId}/`);
        const fiches = await response.json();

        const tbody = document.querySelector('#fichesPosteTable tbody');
        if (!tbody) return;
        tbody.innerHTML = '';
        fichesCourantes = fiches;
        updateFusionButton();

        fiches.forEach(fiche => {
            const row = document.createElement('tr');
            row.className = 'cursor-pointer';
            row.onclick = () => selectFichePoste(fiche.id, fiche.tache);
            const fusionCells = canDeleteItems ? `
                <td>
                    <input type="checkbox" class="checkbox checkbox-sm fusion-check" value="${fiche.id}"
                           onclick="event.stopPropagation(); updateFusionButton()">
                </td>` : '';
            const fusionButton = canDeleteItems ? `
                        <button onclick="event.stopPropagation(); openFusionModal('${fiche.id}')"
                                class="btn btn-ghost btn-xs text-warning" title="Fusionner avec d'autres fiches">
                            <i class="fas fa-code-merge"></i>
                        </button>` : '';
            const deleteButton = canDeleteItems ? `
                        <button data-name="${escapeHtml(fiche.tache)}" onclick="event.stopPropagation(); deleteItem('fiche_poste', '${fiche.id}', this.dataset.name, ${fiche.postes_count || 0})"
                                class="btn btn-ghost btn-xs text-error" title="Supprimer">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : '';
            
            const aEvaluerIcon = fiche.a_evaluer ? '<i class="fas fa-check-circle text-success"></i>' : '<i class="fas fa-times-circle text-error"></i>';
            const dansPlanningIcon = fiche.dans_planning ? '<i class="fas fa-check-circle text-success"></i>' : '<i class="fas fa-times-circle text-error"></i>';
            
            row.innerHTML = `
                ${fusionCells}
                <td>
                    <input type="radio" name="selectedFichePoste" value="${fiche.id}"
                           class="radio radio-primary" onclick="event.stopPropagation(); selectFichePosteRadio('${fiche.id}')">
                </td>
                <td class="font-semibold">${escapeHtml(fiche.tache)}</td>
                <td class="text-sm text-base-content/70">${escapeHtml(fiche.description || '-')}</td>
                <td class="text-center">${aEvaluerIcon}</td>
                <td class="text-center">${dansPlanningIcon}</td>
                <td class="text-center"><span class="badge badge-secondary badge-outline">${fiche.postes_count || 0}</span></td>
                <td class="text-center"><span class="badge ${fiche.plannings_count ? 'badge-accent' : 'badge-ghost'}" title="Lignes inscrites dans le planning">${fiche.plannings_count || 0}</span></td>
                <td>${reglesFicheBadges(fiche)}</td>
                <td><span class="badge badge-outline">${fiche.ordre}</span></td>
                <td>
                    <div class="flex gap-1">
                        <button data-name="${escapeHtml(fiche.tache)}" onclick="event.stopPropagation(); editItem('fiche_poste', '${fiche.id}', this.dataset.name)"
                                class="btn btn-ghost btn-xs" title="Modifier">
                            <i class="fas fa-edit"></i>
                        </button>
                        ${fusionButton}
                        ${deleteButton}
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Erreur lors du chargement des fiches de poste:', error);
        showAlert('Erreur lors du chargement des fiches de poste', 'error');
    }
}

function selectFichePosteRadio(ficheId) {
    const radioInput = document.querySelector(`input[name="selectedFichePoste"][value="${ficheId}"]`);
    if (!radioInput) return;
    const rowElement = radioInput.closest('tr');
    const ficheName = rowElement ? rowElement.querySelector('td.font-semibold').textContent.trim() : 'Fiche';
    selectFichePoste(ficheId, ficheName);
}

async function selectFichePoste(ficheId, ficheName) {
    document.querySelectorAll('#fichesPosteTable tbody tr').forEach(row => {
        row.classList.remove('selected-row');
    });
    if (event && event.currentTarget && event.currentTarget.classList) {
        event.currentTarget.classList.add('selected-row');
    } else {
        const radioInput = document.querySelector(`input[name="selectedFichePoste"][value="${ficheId}"]`);
        const rowElement = radioInput ? radioInput.closest('tr') : null;
        if (rowElement) rowElement.classList.add('selected-row');
    }

    const radioInput = document.querySelector(`input[name="selectedFichePoste"][value="${ficheId}"]`);
    if (radioInput) radioInput.checked = true;

    currentFicheId = ficheId;
    currentFiche = ficheName;

    const ficheNameEl = document.getElementById('selectedFicheNameForPostes');
    if (ficheNameEl) ficheNameEl.textContent = ficheName;

    const postesSection = document.getElementById('postesFicheSection');
    if (postesSection) postesSection.style.display = 'block';

    await loadPostesForFiche(ficheId);
}

async function loadPostesForFiche(ficheId) {
    try {
        const response = await fetch(`/plannings/crud/api/activites-postes/fiche/${ficheId}/`);
        const postes = await response.json();

        const tbody = document.querySelector('#postesFicheTable tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!Array.isArray(postes) || postes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-base-content/70">Aucun poste associe a cette fiche.</td></tr>';
            return;
        }

        postes.forEach(poste => {
            const row = document.createElement('tr');
            const deleteButton = canDeleteItems ? `
                        <button data-name="${escapeHtml(poste.poste_nom || poste.nom)}" onclick="event.stopPropagation(); deleteItem('fiche_poste_poste', '${poste.id}', this.dataset.name, 0)"
                                class="btn btn-ghost btn-xs text-error" title="Supprimer">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : '';
            row.innerHTML = `
                <td>
                    <input type="radio" name="selectedFichePosteLink" value="${poste.id}" class="radio radio-primary radio-sm">
                </td>
                <td class="font-semibold">${escapeHtml(poste.poste_nom || 'Poste non defini')}</td>
                <td>${escapeHtml(poste.fiche_poste_tache || currentFiche || '-')}</td>
                <td>
                    <span class="badge ${poste.is_active ? 'badge-success' : 'badge-ghost'}">
                        ${poste.is_active ? 'Actif' : 'Inactif'}
                    </span>
                </td>
                <td>${poste.created_at ? new Date(poste.created_at).toLocaleDateString('fr-FR') : '-'}</td>
                <td>
                    <div class="flex gap-1">
                        <button data-name="${escapeHtml(poste.poste_nom || poste.nom)}" onclick="event.stopPropagation(); editItem('fiche_poste_poste', '${poste.id}', this.dataset.name)"
                                class="btn btn-ghost btn-xs" title="Modifier">
                            <i class="fas fa-edit"></i>
                        </button>
                        ${deleteButton}
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Erreur lors du chargement des postes de la fiche:', error);
        const tbody = document.querySelector('#postesFicheTable tbody');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-error text-center">Erreur de chargement: ${escapeHtml(error.message)}</td></tr>`;
        }
        showAlert('Erreur lors du chargement des postes de la fiche', 'error');
    }
}

async function loadLinkedActivitesForFiche(ficheId) {
    const tbody = document.querySelector('#linkedActivitesTable tbody');
    if (!tbody || !ficheId) return;

    tbody.innerHTML = '<tr><td colspan="3" class="text-center">Chargement...</td></tr>';

    try {
        const response = await fetch(`/plannings/crud/api/activites-postes/fiche/${ficheId}/`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const postes = await response.json();
        if (!Array.isArray(postes) || postes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center">Aucune activite liee a cette fiche.</td></tr>';
            return;
        }

        tbody.innerHTML = '';
        postes.forEach(poste => {
            const row = document.createElement('tr');
            const posteIdArg = JSON.stringify(poste.id);
            const labelArg = JSON.stringify(poste.poste_nom || poste.nom || 'Poste');
            row.innerHTML = `
                <td>${escapeHtml(poste.poste_nom || 'Poste non defini')}</td>
                <td>${escapeHtml(poste.activite_nom || '-')}</td>
                <td>
                    <button type="button" class="btn btn-ghost btn-xs" onclick='openLinkedActivitePosteEdit(${posteIdArg}, ${labelArg})'>
                        Modifier
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Erreur lors du chargement des activites liees:', error);
        tbody.innerHTML = `<tr><td colspan="3" class="text-error text-center">Erreur de chargement: ${escapeHtml(error.message)}</td></tr>`;
    }
}

function openLinkedActivitePosteCreate() {
    if (!currentEditId) return;
    pendingFicheModalId = currentEditId;
    showAddModal('activite_poste');
}

async function openLinkedActivitePosteEdit(posteId, posteName) {
    if (!currentEditId || !posteId) return;
    pendingFicheModalId = currentEditId;
    await editItem('activite_poste', posteId, posteName || 'Poste');
}


// ===== FONCTIONS MODALES =====

function showAddModal(type, isEdit = false) {
    currentEditType = type;
    if (!isEdit) {
        currentEditId = null;
    }

    const modalTitle = document.getElementById('modalTitle');
    const submitBtn = document.getElementById('submitBtn');
    const formFields = document.getElementById('formFields');

    // Configuration selon le type
    switch(type) {
        case 'type_activite':
            modalTitle.textContent = 'Ajouter un Type d\'Activité';
            submitBtn.textContent = 'Ajouter';
            formFields.innerHTML = `
                <div class="form-control mb-4">
                    <label class="label"><span class="label-text">Nom du type *</span></label>
                    <input type="text" id="nomtype" class="input input-bordered" placeholder="Ex: Maintenance, Installation..." required>
                </div>
                <div class="form-control mb-4">
                    <label class="label"><span class="label-text">Groupe</span></label>
                    <select id="groupe" class="select select-bordered w-full">${groupeOptionsHtml(null)}</select>
                </div>
            `;
            break;

        case 'activite':
            if (!currentTypeId) {
                showAlert('Veuillez d\'abord sélectionner un type d\'activité', 'warning');
                return;
            }
            modalTitle.textContent = 'Ajouter une Activité';
            submitBtn.textContent = 'Ajouter';
            formFields.innerHTML = `
                <div class="form-control mb-4">
                    <label class="label"><span class="label-text">Type d'activité *</span></label>
                    <select id="type_activite_id" class="select select-bordered w-full" required>
                        <option value="">-- Chargement des types... --</option>
                    </select>
                    <div class="label">
                        <span class="label-text-alt">Sélectionnez le type d'activité</span>
                    </div>
                </div>
                <div class="form-control mb-4">
                    <label class="label"><span class="label-text">Nom de l'activité *</span></label>
                    <input type="text" id="nom" class="input input-bordered" placeholder="Ex: Réparation pompe..." required>
                </div>
                <div class="form-control mb-4">
                    <label class="label"><span class="label-text">Description</span></label>
                    <textarea id="description" class="textarea textarea-bordered" placeholder="Description détaillée..."></textarea>
                </div>
                <div class="form-control mb-4">
                    <label class="cursor-pointer label">
                        <span class="label-text">Activité active</span>
                        <input type="checkbox" id="is_active" class="checkbox checkbox-primary" checked>
                    </label>
                </div>
            `;

            loadTypesActivitesForSelect();
            break;

        case 'activite_poste':
            if (!currentTypeId && !currentActiviteId) {
                showAlert('Veuillez d\'abord sélectionner une activité', 'warning');
                return;
            }
            modalTitle.textContent = "Ajouter un Poste d'Activité";
            submitBtn.textContent = 'Ajouter';
            formFields.innerHTML = `
                <div class="form-control mb-4">
                    <label class="label"><span class="label-text">Activite *</span></label>
                    <select id="activite_id" class="select select-bordered w-full" required>
                        <option value="">-- Chargement des activites... --</option>
                    </select>
                    <div class="label">
                        <span class="label-text-alt">Vous pouvez modifier l'activite associee au poste.</span>
                    </div>
                </div>
                <div class="form-control mb-4">
                    <label class="label"><span class="label-text">Poste *</span></label>
                    <select id="poste_id" class="select select-bordered w-full" required>
                        <option value="">-- Chargement des postes... --</option>
                    </select>
                    <div class="label">
                        <span class="label-text-alt">Sélectionnez un poste existant</span>
                    </div>
                </div>
                <div class="form-control mb-4">
                    <label class="label"><span class="label-text">Fiche de poste (optionnel)</span></label>
                    <select id="fiche_poste_id" class="select select-bordered w-full">
                        <option value="">-- Aucune --</option>
                    </select>
                    <div class="label">
                        <span class="label-text-alt">Associer une fiche ?? ce poste d'activité</span>
                    </div>
                </div>
                <div class="form-control mb-4">
                    <label class="cursor-pointer label">
                        <span class="label-text">Activité active pour ce poste</span>
                        <input type="checkbox" id="is_active" class="checkbox checkbox-primary" checked>
                    </label>
                </div>
            `;

            loadActivitesForSelect(currentActiviteId || null);
            loadPostesForSelect();
            loadFichesForSelect();
            break;

        case 'fiche_poste':
            if (!currentTypeId) {
                showAlert('Veuillez d\'abord sélectionner un type d\'activité', 'warning');
                return;
            }
            modalTitle.textContent = 'Ajouter une Fiche de Poste';
            submitBtn.textContent = 'Ajouter';
            
            let tabsHtml = '';
            // Si pas en édition, on affiche les onglets
            if (!isEdit) {
                 tabsHtml = `
                    <div role="tablist" class="tabs tabs-boxed mb-4">
                      <a role="tab" class="tab tab-active" id="tabCreate" onclick="toggleFicheMode('create')">Créer Nouvelle</a>
                      <a role="tab" class="tab" id="tabSelect" onclick="toggleFicheMode('select')">Sélectionner Existante</a>
                    </div>
                 `;
            }

            formFields.innerHTML = `
                ${tabsHtml}
                
                <div id="ficheCreateSection">
                    <div class="form-control mb-4">
                        <label class="label"><span class="label-text">Type d'activite *</span></label>
                        <select id="type_activite_id" class="select select-bordered w-full" required>
                            <option value="">-- Chargement des types... --</option>
                        </select>
                        <div class="label">
                            <span class="label-text-alt">La fiche sera rattachee directement au type choisi.</span>
                        </div>
                    </div>
                    <div class="form-control mb-4">
                        <label class="label"><span class="label-text">TÃ¢che *</span></label>
                        <input type="text" id="tache" class="input input-bordered" placeholder="Ex: Vérifier les niveaux d'eau..." required>
                    </div>
                    <div class="form-control mb-4">
                        <label class="label"><span class="label-text">Description</span></label>
                        <textarea id="description" class="textarea textarea-bordered" placeholder="Description détaillée de la tÃ¢che..."></textarea>
                    </div>
                    <div class="form-control mb-4">
                        <label class="label"><span class="label-text">Outils nécessaires</span></label>
                        <textarea id="outils" class="textarea textarea-bordered" placeholder="Liste des outils nécessaires..."></textarea>
                    </div>
                    <div class="form-control mb-4">
                        <label class="label"><span class="label-text">Ordre d'affichage</span></label>
                        <input type="number" id="ordre" class="input input-bordered" value="0" min="0">
                    </div>
                    <div class="form-control mb-4">
                        <label class="cursor-pointer label">
                            <span class="label-text">Ã€ évaluer</span>
                            <input type="checkbox" id="a_evaluer" class="checkbox checkbox-primary">
                        </label>
                    </div>
                    <div class="form-control mb-4">
                        <label class="cursor-pointer label">
                            <span class="label-text">Dans planning</span>
                            <input type="checkbox" id="dans_planning" class="checkbox checkbox-primary">
                        </label>
                    </div>
                    <div class="divider text-sm">Précisions demandées à la saisie</div>
                    <p class="text-xs text-base-content/60 mb-3">
                        Pour les réparations, entretiens, réhabilitations et maçonnerie : ce que l'utilisateur doit préciser
                        quand il choisit cette activité. Par défaut tout est facultatif.
                    </p>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-2">
                        <div class="form-control">
                            <label class="label"><span class="label-text">Précision sur la cible</span></label>
                            <select id="cible_mode" class="select select-bordered" onchange="updateReglesFicheForm()">
                                <option value="optionnel">Facultative</option>
                                <option value="obligatoire">Obligatoire</option>
                                <option value="non">Non demandée</option>
                            </select>
                        </div>
                        <div class="form-control">
                            <label class="label"><span class="label-text">Types de cible admis</span></label>
                            <select id="cible_types" class="select select-bordered">
                                <option value="les_deux">Point d'eau ou équipement</option>
                                <option value="point_eau">Point d'eau uniquement</option>
                                <option value="equipement">Équipement uniquement</option>
                            </select>
                        </div>
                        <div class="form-control">
                            <label class="label"><span class="label-text">Précision sur les composants</span></label>
                            <select id="composants_mode" class="select select-bordered" onchange="updateReglesFicheForm()">
                                <option value="optionnel">Facultative</option>
                                <option value="obligatoire">Obligatoire</option>
                                <option value="non">Non demandée</option>
                            </select>
                        </div>
                        <div class="form-control">
                            <label class="cursor-pointer label mt-6">
                                <span class="label-text">Plusieurs composants possibles</span>
                                <input type="checkbox" id="composants_multiple" class="checkbox checkbox-primary" checked>
                            </label>
                        </div>
                    </div>
                    <div class="form-control mb-2">
                        <label class="label"><span class="label-text">Composants admis (un par ligne)</span></label>
                        <textarea id="composants_admis" class="textarea textarea-bordered h-24"
                                  placeholder="Vide = tous les composants du type de la cible&#10;Ex. pour l'anti-rouille :&#10;Boîte métallique&#10;Fer plat&#10;Cadenas vita gasy"></textarea>
                        <div class="label"><span class="label-text-alt">Seuls ces composants seront proposés (web et app terrain). Accents et majuscules ignorés.</span></div>
                    </div>
                    <div id="reglesFicheHint" class="text-xs text-info mb-4"></div>
                </div>

                <div id="ficheSelectSection" style="display: none;">
                    <div class="form-control mb-4">
                        <label class="label"><span class="label-text">Sélectionner une fiche existante (orpheline)</span></label>
                         <select id="existing_fiche_id" class="select select-bordered w-full">
                            <option value="">-- Chargement... --</option>
                        </select>
                        <div class="label"><span class="label-text-alt text-warning">Seules les fiches sans type assigné sont listées ici.</span></div>
                    </div>
                </div>
            `;
            
            if (!isEdit) {
                // Reset mode par défaut
                toggleFicheMode('create');
                loadOrphanFiches();
            }
            loadTypesActivitesForSelect(currentTypeId || null);
            break;

        case 'fiche_poste_poste':
            if (!currentFicheId) {
                showAlert('Veuillez d\'abord selectionner une fiche de poste', 'warning');
                return;
            }
            modalTitle.textContent = `Associer un poste a ${currentFiche || 'la fiche'}`;
            submitBtn.textContent = 'Enregistrer';
            formFields.innerHTML = `
                <div class="form-control mb-4">
                    <label class="label"><span class="label-text">Fiche de poste</span></label>
                    <input type="text" class="input input-bordered" value="${escapeHtml(currentFiche || '')}" disabled>
                </div>
                <div class="form-control mb-4">
                    <label class="label"><span class="label-text">Poste *</span></label>
                    <select id="poste_id" class="select select-bordered w-full" required>
                        <option value="">-- Chargement des postes... --</option>
                    </select>
                </div>
                <div class="form-control mb-4">
                    <label class="cursor-pointer label">
                        <span class="label-text">Liaison active</span>
                        <input type="checkbox" id="is_active" class="checkbox checkbox-primary" checked>
                    </label>
                </div>
            `;
            loadPostesForSelect();
            break;
    }

    document.getElementById('crudModal').checked = true;
}

async function editItem(type, id, name) {
    currentEditType = type;
    currentEditId = id;

    try {
        const url = getDetailApiUrl(type, id);
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.error) {
            showAlert('Erreur lors du chargement des données: ' + data.error, 'error');
            return;
        }

        showAddModal(type, true);
        populateFormData(type, data);

        document.getElementById('modalTitle').textContent = `Modifier ${getTypeLabel(type)}`;
        document.getElementById('submitBtn').textContent = 'Modifier';

    } catch (error) {
        console.error('Erreur lors du chargement:', error);
        showAlert('Erreur lors du chargement des données: ' + error.message, 'error');
    }
}

function getDetailApiUrl(type, id) {
    const baseUrls = {
        'type_activite': '/plannings/crud/api/types-activites/',
        'activite': '/plannings/crud/api/activites/',
        'activite_poste': '/plannings/crud/api/activites-postes/',
        'fiche_poste_poste': '/plannings/crud/api/activites-postes/',
        'fiche_poste': '/plannings/crud/api/fiches-poste/'
    };
    return baseUrls[type] + id + '/';
}

function populateFormData(type, data) {
    switch(type) {
        case 'type_activite': {
            const nomtypeField = document.getElementById('nomtype');
            if (nomtypeField) nomtypeField.value = data.nomtype || '';
            const groupeField = document.getElementById('groupe');
            if (groupeField) groupeField.value = data.groupe_id || '';
            break;
        }

        case 'activite': {
            const nomField = document.getElementById('nom');
            const descriptionField = document.getElementById('description');
            const isActiveField = document.getElementById('is_active');

            if (nomField) nomField.value = data.nom || '';
            if (descriptionField) descriptionField.value = data.description || '';
            if (isActiveField) isActiveField.checked = data.is_active !== false;

            if (data.type_activite_id || data.type_activite) {
                const typeId = data.type_activite_id || data.type_activite;
                loadTypesActivitesForSelect(typeId);
            } else {
                loadTypesActivitesForSelect();
            }
            break;
        }

        case 'activite_poste': {
            const isActivePosteField = document.getElementById('is_active');
            currentActiviteId = data.activite_id || currentActiviteId;
            loadActivitesForSelect(data.activite_id || currentActiviteId || null);
            if (data.poste_id) {
                loadPostesForSelect(data.poste_id);
            }
            loadFichesForSelect(data.fiche_poste_id || null);
            if (isActivePosteField) isActivePosteField.checked = data.is_active !== false;
            break;
        }

        case 'fiche_poste_poste': {
            const isActiveLinkField = document.getElementById('is_active');
            loadPostesForSelect(data.poste_id || null);
            if (isActiveLinkField) isActiveLinkField.checked = data.is_active !== false;
            if (data.fiche_poste_id) currentFicheId = data.fiche_poste_id;
            if (data.fiche_poste_tache) currentFiche = data.fiche_poste_tache;
            break;
        }

        case 'fiche_poste': {
            const tacheField = document.getElementById('tache');
            const descFicheField = document.getElementById('description');
            const outilsField = document.getElementById('outils');
            const ordreField = document.getElementById('ordre');
            const aEvaluerField = document.getElementById('a_evaluer');
            const dansPlanningField = document.getElementById('dans_planning');
            const selectedTypeId = data.type_activites_id || currentTypeId || null;

            if (tacheField) tacheField.value = data.tache || '';
            if (descFicheField) descFicheField.value = data.description || '';
            if (outilsField) outilsField.value = data.outils || '';
            if (ordreField) ordreField.value = data.ordre || 0;
            if (aEvaluerField) aEvaluerField.checked = data.a_evaluer || false;
            if (dansPlanningField) dansPlanningField.checked = data.dans_planning || false;
            const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
            setVal('cible_mode', data.cible_mode || 'optionnel');
            setVal('cible_types', data.cible_types || 'les_deux');
            setVal('composants_mode', data.composants_mode || 'optionnel');
            const multipleField = document.getElementById('composants_multiple');
            if (multipleField) multipleField.checked = data.composants_multiple !== false;
            setVal('composants_admis', data.composants_admis || '');
            updateReglesFicheForm();
            loadTypesActivitesForSelect(selectedTypeId);
            if (data.type_activites_nom) {
                currentTypeId = selectedTypeId;
                currentType = data.type_activites_nom;
            }
            break;
        }
    }
}

function deleteItem(type, id, name, childrenCount) {
    currentDeleteType = type;
    currentDeleteId = id;

    const deleteMessage = document.getElementById('deleteMessage');
    const deleteWarning = document.getElementById('deleteWarning');
    const confirmBtn = document.getElementById('confirmDeleteBtn');

    deleteMessage.textContent = `ÃŠtes-vous sÃ»r de vouloir supprimer "${name}" ?`;

    if (childrenCount > 0) {
        deleteWarning.textContent = `Attention : cet élément contient ${childrenCount} élément(s) lié(s). Suppression impossible.`;
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Suppression impossible';
    } else {
        deleteWarning.textContent = 'Cette action est irréversible.';
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Supprimer';
    }

    document.getElementById('deleteModal').checked = true;
}

function getTypeLabel(type) {
    const labels = {
        'type_activite': 'Type d\'Activité',
        'activite': 'Activité',
        'activite_poste': 'Poste d\'Activité',
        'fiche_poste_poste': 'Poste lie',
        'fiche_poste': 'Fiche de Poste'
    };
    return labels[type] || 'Ã‰lément';
}

// ===== SOUMISSION FORMULAIRES =====

const crudForm = document.getElementById('crudForm');
if (crudForm) {
    crudForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await submitForm();
    });
}

async function submitForm() {
    const formData = {};

    switch(currentEditType) {
        case 'type_activite': {
            formData.nomtype = document.getElementById('nomtype').value.trim();
            formData.groupe_id = document.getElementById('groupe').value || null;
            if (!formData.nomtype) {
                showAlert('Le nom du type est obligatoire', 'error');
                return;
            }
            break;
        }

        case 'activite': {
            formData.nom = document.getElementById('nom').value.trim();
            formData.description = document.getElementById('description').value.trim();
            formData.is_active = document.getElementById('is_active').checked;

            const typeActiviteSelect = document.getElementById('type_activite_id');
            formData.type_activite = typeActiviteSelect ? typeActiviteSelect.value : currentTypeId;
            if (typeActiviteSelect && typeActiviteSelect.value) {
                currentTypeId = typeActiviteSelect.value;
                currentType = typeActiviteSelect.options[typeActiviteSelect.selectedIndex].textContent.trim();
            }

            if (!formData.nom) {
                showAlert('Le nom de l\'activité est obligatoire', 'error');
                return;
            }
            if (!formData.type_activite) {
                showAlert('Le type d\'activité est obligatoire', 'error');
                return;
            }
            break;
        }

        case 'activite_poste': {
            formData.poste_id = document.getElementById('poste_id').value;
            formData.activite_id = document.getElementById('activite_id') ? document.getElementById('activite_id').value : currentActiviteId;
            formData.fiche_poste_id = document.getElementById('fiche_poste_id') ? document.getElementById('fiche_poste_id').value : null;
            formData.is_active = document.getElementById('is_active').checked;
            if (!formData.activite_id) {
                showAlert('Veuillez selectionner une activite', 'error');
                return;
            }
            currentActiviteId = formData.activite_id;

            if (!formData.poste_id) {
                showAlert('Veuillez sélectionner un poste', 'error');
                return;
            }
            break;
        }
        case 'fiche_poste_poste': {
            formData.poste_id = document.getElementById('poste_id').value;
            formData.fiche_poste_id = currentFicheId;
            formData.is_active = document.getElementById('is_active').checked;

            if (!formData.fiche_poste_id) {
                showAlert('Veuillez selectionner une fiche de poste', 'error');
                return;
            }
            if (!formData.poste_id) {
                showAlert('Veuillez selectionner un poste', 'error');
                return;
            }
            break;
        }
        case 'fiche_poste': {
            const ficheTypeSelect = document.getElementById('type_activite_id');
            const selectedFicheTypeId = ficheTypeSelect ? ficheTypeSelect.value : currentTypeId;
            if (ficheTypeSelect && ficheTypeSelect.value) {
                currentTypeId = ficheTypeSelect.value;
                currentType = ficheTypeSelect.options[ficheTypeSelect.selectedIndex].textContent.trim();
            }
            // Gestion du mode Sélection (Lier existante)
            if (ficheMode === 'select' && !currentEditId) {
                 const existingId = document.getElementById('existing_fiche_id').value;
                 if (!existingId) {
                     showAlert('Veuillez sélectionner une fiche', 'error');
                     return;
                 }
                 
                 // Appel spécial pour lier la fiche (Update avec type_activite_id)
                 try {
                     const url = `/plannings/crud/api/fiches-poste/${existingId}/update/`;
                     const response = await fetch(url, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: JSON.stringify({ type_activites: selectedFicheTypeId })
                     });
                     
                     if (response.ok) {
                         showAlert('Fiche associée avec succès', 'success');
                         closeModal();
                         await loadTypesActivites();
                         await selectType(currentTypeId, currentType);
                         updateStats();
                     } else {
                         const err = await response.json();
                         showAlert(err.message || 'Erreur lors de l\'association', 'error');
                     }
                 } catch (e) {
                     console.error(e);
                     showAlert('Erreur réseau', 'error');
                 }
                 return; // Stop flow
            }

            // Mode standard (Création / Edition)
            formData.tache = document.getElementById('tache').value.trim();
            formData.description = document.getElementById('description').value.trim();
            formData.outils = document.getElementById('outils').value.trim();
            formData.ordre = parseInt(document.getElementById('ordre').value) || 0;
            formData.a_evaluer = document.getElementById('a_evaluer').checked;
            formData.dans_planning = document.getElementById('dans_planning').checked;
            formData.cible_mode = document.getElementById('cible_mode').value;
            formData.cible_types = document.getElementById('cible_types').value;
            formData.composants_mode = document.getElementById('composants_mode').value;
            formData.composants_multiple = document.getElementById('composants_multiple').checked;
            formData.composants_admis = document.getElementById('composants_admis').value;
            formData.type_activite_id = selectedFicheTypeId;

            if (!formData.tache) {
                showAlert('La tÃ¢che est obligatoire', 'error');
                return;
            }
            if (!formData.type_activite_id) {
                showAlert('Le type d\'activité est obligatoire', 'error');
                return;
            }
            break;
        }
    }

    try {
        const url = getApiUrl(currentEditType, currentEditId);
        const method = currentEditId ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify(formData)
        });

        if (!response.ok) {
            let errorMessage = `Erreur HTTP ${response.status}`;
            try {
                const errorData = await response.json();
                if (errorData.message) errorMessage = errorData.message;
            } catch (e) {}
            showAlert(errorMessage, 'error');
            return;
        }

        const result = await response.json();

        if (result.success) {
            showAlert(result.message, 'success');
            closeModal();

            if (currentEditType === 'type_activite') {
                loadTypesActivites();
            } else if (currentEditType === 'activite') {
                loadActivites(currentTypeId);
            } else if (currentEditType === 'activite_poste') {
                loadPostesActivites(currentActiviteId);
                if (pendingFicheModalId) {
                    const ficheIdToReopen = pendingFicheModalId;
                    pendingFicheModalId = null;
                    await editItem('fiche_poste', ficheIdToReopen, 'Fiche de Poste');
                    updateStats();
                    return;
                }
            } else if (currentEditType === 'fiche_poste_poste') {
                await loadTypesActivites();
                await selectType(currentTypeId, currentType);
                if (currentFicheId && currentFiche) {
                    await selectFichePoste(currentFicheId, currentFiche);
                }
            } else if (currentEditType === 'fiche_poste') {
                await loadTypesActivites();
                await selectType(currentTypeId, currentType);
            }

            updateStats();
        } else {
            showAlert(result.message, 'error');
        }
    } catch (error) {
        console.error('Erreur:', error);
        showAlert('Erreur lors de l\'opération', 'error');
    }
}

async function confirmDelete() {
    if (!currentDeleteId || !currentDeleteType) return;

    try {
        const url = getApiUrl(currentDeleteType, currentDeleteId, true);

        const response = await fetch(url, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });

        const result = await response.json();

        if (result.success) {
            showAlert(result.message, 'success');
            closeDeleteModal();

            if (currentDeleteType === 'type_activite') {
                loadTypesActivites();
                const fichesSection = document.getElementById('fichesPosteSection');
                if (fichesSection) fichesSection.style.display = 'none';
                currentTypeId = null;
                currentType = null;
            } else if (currentDeleteType === 'activite') {
                loadActivites(currentTypeId);
            } else if (currentDeleteType === 'activite_poste') {
                loadPostesActivites(currentActiviteId);
            } else if (currentDeleteType === 'fiche_poste_poste') {
                await loadTypesActivites();
                await selectType(currentTypeId, currentType);
                if (currentFicheId && currentFiche) {
                    await selectFichePoste(currentFicheId, currentFiche);
                }
            } else if (currentDeleteType === 'fiche_poste') {
                if (currentDeleteId === currentFicheId) {
                    currentFicheId = null;
                    currentFiche = null;
                    const postesSection = document.getElementById('postesFicheSection');
                    if (postesSection) postesSection.style.display = 'none';
                }
                await loadTypesActivites();
                await selectType(currentTypeId, currentType);
            }

            updateStats();
        } else {
            showAlert(result.message, 'error');
        }
    } catch (error) {
        console.error('Erreur:', error);
        showAlert('Erreur lors de la suppression', 'error');
    }
}

function getApiUrl(type, id = null, isDelete = false) {
    const baseUrls = {
        'type_activite': '/plannings/crud/api/types-activites/',
        'activite': '/plannings/crud/api/activites/',
        'activite_poste': '/plannings/crud/api/activites-postes/',
        'fiche_poste_poste': '/plannings/crud/api/activites-postes/',
        'fiche_poste': '/plannings/crud/api/fiches-poste/'
    };

    let url = baseUrls[type];

    if (id) {
        if (isDelete) {
            url += `${id}/delete/`;
        } else {
            url += `${id}/update/`;
        }
    } else {
        url += 'create/';
    }
    return url;
}

async function updateStats() {
    try {
        const typesResponse = await fetch('/plannings/crud/api/types-activites/');
        const types = await typesResponse.json();
        const totalTypes = document.getElementById('totalTypes');
        if (totalTypes) totalTypes.textContent = types.length;

        const fichesResponse = await fetch('/plannings/crud/api/fiches-poste/');
        const fiches = await fichesResponse.json();
        const totalFichesElement = document.getElementById('totalFiches');
        if (totalFichesElement) {
            totalFichesElement.textContent = fiches.length;
        }

        const totalFichesPlanning = document.getElementById('totalFichesPlanning');
        if (totalFichesPlanning) {
            totalFichesPlanning.textContent = fiches.filter(fiche => fiche.dans_planning).length;
        }

    } catch (error) {
        console.error('Erreur lors du chargement des statistiques:', error);
    }
}

function closeModal() {
    document.getElementById('crudModal').checked = false;
}

function closeDeleteModal() {
    document.getElementById('deleteModal').checked = false;
}

async function loadOrphanFiches() {
    try {
        const response = await fetch('/plannings/crud/api/fiches-poste/orphelines/');
        const fiches = await response.json();
        
        const select = document.getElementById('existing_fiche_id');
        if (!select) return;
        
        select.innerHTML = '<option value="">-- Sélectionner une fiche --</option>';
        if (fiches.length === 0) {
            const opt = document.createElement('option');
            opt.disabled = true;
            opt.text = "Aucune fiche orpheline disponible";
            select.add(opt);
        } else {
            fiches.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f.id;
                opt.text = f.tache;
                select.add(opt);
            });
        }
    } catch (e) {
        console.error("Erreur chargement orphelines", e);
        const select = document.getElementById('existing_fiche_id');
        if(select) select.innerHTML = '<option>Erreur chargement</option>';
    }
}

function toggleFicheMode(mode) {
    if (currentEditType !== 'fiche_poste') return;
    ficheMode = mode;
    
    const tabCreate = document.getElementById('tabCreate');
    const tabSelect = document.getElementById('tabSelect');
    if (tabCreate) tabCreate.classList.toggle('tab-active', mode === 'create');
    if (tabSelect) tabSelect.classList.toggle('tab-active', mode === 'select');
    
    const sectCreate = document.getElementById('ficheCreateSection');
    const sectSelect = document.getElementById('ficheSelectSection');
    if (sectCreate) sectCreate.style.display = mode === 'create' ? 'block' : 'none';
    if (sectSelect) sectSelect.style.display = mode === 'select' ? 'block' : 'none';
    
    // Manage required attributes
    const tacheInput = document.getElementById('tache');
    const existInput = document.getElementById('existing_fiche_id');
    
    if (tacheInput) tacheInput.required = (mode === 'create');
    if (existInput) existInput.required = (mode === 'select');
}

function showImportModal(type) {
    currentImportType = type;
    document.getElementById('importModal').checked = true;
}

const importForm = document.getElementById('importForm');
if (importForm) {
    importForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await submitImportForm();
    });
}

async function submitImportForm() {
    const fileInput = document.getElementById('excelFile');
    const file = fileInput.files[0];

    if (!file) {
        showAlert('Veuillez sélectionner un fichier Excel', 'error');
        return;
    }

    if (!currentImportType) {
        showAlert('Type d\'import non défini', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`/plannings/crud/import-excel/${currentImportType}/`, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });

        if (response.ok) {
            const result = await response.json();
            showAlert(`Import réussi: ${result.imported_count} éléments importés`, 'success');
            closeImportModal();
            loadTypesActivites();
            updateStats();
        } else {
            const error = await response.json();
            showAlert(`Erreur d'import: ${error.error || 'Erreur inconnue'}`, 'error');
        }
    } catch (error) {
        console.error('Erreur lors de l\'import:', error);
        showAlert('Erreur lors de l\'import du fichier', 'error');
    }
}

// Valeur destinée à un argument string JS dans un attribut onclick="...('valeur')" :
// échappement JS (\ et ') puis HTML, car le navigateur décode les entités avant d'exécuter le JS.
function jsArg(value) {
    const BS = String.fromCharCode(92);
    const s = String(value == null ? '' : value)
        .split(BS).join(BS + BS)
        .split("'").join(BS + "'")
        .split(String.fromCharCode(13)).join('')
        .split(String.fromCharCode(10)).join(' ');
    return escapeHtml(s);
}

function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function showAlert(message, type = 'info') {
    const safeMessage = message || 'Message non défini';

    const alertClass = {
        'success': 'alert-success',
        'error': 'alert-error',
        'warning': 'alert-warning',
        'info': 'alert-info'
    }[type] || 'alert-info';

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert ${alertClass} fixed top-4 right-4 w-auto max-w-sm z-50`;
    alertDiv.innerHTML = `
        <span>${escapeHtml(safeMessage)}</span>
        <button class="btn btn-ghost btn-sm" onclick="this.parentElement.remove()">Ã—</button>
    `;

    document.body.appendChild(alertDiv);

    setTimeout(() => {
        if (alertDiv.parentElement) {
            alertDiv.remove();
        }
    }, 5000);
}

function getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

async function loadPostesForSelect(selectedPosteId = null) {
    try {
        const response = await fetch('/plannings/crud/api/postes/');
        const postes = await response.json();

        const selectElement = document.getElementById('poste_id');
        if (!selectElement) return;

        selectElement.innerHTML = '<option value="">-- Sélectionner un poste --</option>';

        postes.forEach(poste => {
            const option = document.createElement('option');
            option.value = poste.id;
            option.textContent = `${poste.nom_poste} (${poste.organisation_nom})`;

            if (selectedPosteId && poste.id === selectedPosteId) {
                option.selected = true;
            }

            selectElement.appendChild(option);
        });

        if (postes.length === 0) {
            selectElement.innerHTML = '<option value="">Aucun poste disponible</option>';
            showAlert('Aucun poste disponible. Vous devez d\'abord créer des postes dans la gestion des employés.', 'warning');
        }

    } catch (error) {
        console.error('Erreur lors du chargement des postes:', error);
        const selectElement = document.getElementById('poste_id');
        if (selectElement) {
            selectElement.innerHTML = '<option value="">Erreur de chargement</option>';
        }
        showAlert('Erreur lors du chargement des postes', 'error');
    }
}



async function loadFichesForSelect(selectedFicheId = null) {
    try {
        const url = currentTypeId
            ? `/plannings/crud/api/fiches-poste/type/${currentTypeId}/`
            : '/plannings/crud/api/fiches-poste/';
        const response = await fetch(url);
        const fiches = await response.json();

        const selectElement = document.getElementById('fiche_poste_id');
        if (!selectElement) return;

        selectElement.innerHTML = '<option value="">-- Aucune --</option>';

        fiches.forEach(fiche => {
            const option = document.createElement('option');
            option.value = fiche.id;
            option.textContent = fiche.tache;

            if (selectedFicheId && fiche.id === selectedFicheId) {
                option.selected = true;
            }

            selectElement.appendChild(option);
        });
    } catch (error) {
        console.error('Erreur lors du chargement des fiches:', error);
        const selectElement = document.getElementById('fiche_poste_id');
        if (selectElement) {
            selectElement.innerHTML = '<option value="">Erreur de chargement</option>';
        }
        showAlert('Erreur lors du chargement des fiches de poste', 'error');
    }
}

async function loadActivitesForSelect(selectedActiviteId = null) {
    try {
        const url = currentTypeId
            ? `/plannings/crud/api/activites/type/${currentTypeId}/`
            : '/plannings/crud/api/activites/';
        const response = await fetch(url);
        const activites = await response.json();

        const selectElement = document.getElementById('activite_id');
        if (!selectElement) return;

        selectElement.innerHTML = '<option value="">-- Selectionner une activite --</option>';

        activites.forEach(activite => {
            const option = document.createElement('option');
            option.value = activite.id;
            option.textContent = activite.nom;

            if ((selectedActiviteId && activite.id === selectedActiviteId) || (!selectedActiviteId && currentActiviteId && activite.id === currentActiviteId)) {
                option.selected = true;
            }

            selectElement.appendChild(option);
        });

        if (activites.length === 0) {
            selectElement.innerHTML = '<option value="">Aucune activite disponible</option>';
            showAlert('Aucune activite disponible pour ce type.', 'warning');
        }
    } catch (error) {
        console.error('Erreur lors du chargement des activites:', error);
        const selectElement = document.getElementById('activite_id');
        if (selectElement) {
            selectElement.innerHTML = '<option value="">Erreur de chargement</option>';
        }
        showAlert('Erreur lors du chargement des activites', 'error');
    }
}

async function loadTypesActivitesForSelect(selectedTypeId = null) {
    try {
        const response = await fetch('/plannings/crud/api/types-activites/');
        const types = await response.json();

        const selectElement = document.getElementById('type_activite_id');
        if (!selectElement) return;

        selectElement.innerHTML = '<option value="">-- Sélectionner un type --</option>';

        types.forEach(type => {
            const option = document.createElement('option');
            option.value = type.id;
            option.textContent = type.nomtype;

            if ((selectedTypeId && type.id === selectedTypeId) || (!selectedTypeId && currentTypeId && type.id === currentTypeId)) {
                option.selected = true;
            }

            selectElement.appendChild(option);
        });

        if (types.length === 0) {
            selectElement.innerHTML = '<option value="">Aucun type disponible</option>';
            showAlert('Aucun type d\'activité disponible.', 'warning');
        }

    } catch (error) {
        console.error('Erreur lors du chargement des types:', error);
        const selectElement = document.getElementById('type_activite_id');
        if (selectElement) {
            selectElement.innerHTML = '<option value="">Erreur de chargement</option>';
        }
        showAlert('Erreur lors du chargement des types d\'activité', 'error');
    }
}



// ===== FUSION DES FICHES DE POSTE =====

const FUSION_API = '/plannings/reparations/fusion-activites/api';

function fichesCochees() {
    return Array.from(document.querySelectorAll('.fusion-check:checked')).map(c => c.value);
}

function updateFusionButton() {
    const btn = document.getElementById('btnFusionnerFiches');
    if (!btn) return;
    const n = fichesCochees().length;
    btn.disabled = n < 2;
    const label = document.getElementById('btnFusionnerCount');
    if (label) label.textContent = n >= 2 ? ` (${n})` : '';
}

function toggleAllFusionChecks(checked) {
    document.querySelectorAll('.fusion-check').forEach(c => { c.checked = checked; });
    updateFusionButton();
}

// targetId : fiche cible pré-sélectionnée (bouton de ligne) ; sinon on part des cases cochées
function openFusionModal(targetId = null) {
    const cochees = fichesCochees();
    let cible = targetId || cochees[0];
    if (!cible) return;
    const sources = targetId ? cochees.filter(id => id !== targetId) : cochees.slice(1);

    const liste = document.getElementById('fusionListe');
    liste.innerHTML = fichesCourantes.map(f => `
        <tr>
            <td><input type="radio" name="fusionCible" class="radio radio-sm radio-primary" value="${f.id}" ${f.id === cible ? 'checked' : ''}
                       onchange="fusionCibleChange()"></td>
            <td><input type="checkbox" class="checkbox checkbox-sm fusion-source" value="${f.id}" ${sources.includes(f.id) ? 'checked' : ''}
                       onchange="document.getElementById('btnFusionAppliquer').disabled = true"
                       ${f.id === cible ? 'disabled' : ''}></td>
            <td>${escapeHtml(f.tache)}</td>
        </tr>`).join('');
    document.getElementById('fusionNouveauNom').value = '';
    document.getElementById('fusionApercu').innerHTML = '';
    document.getElementById('btnFusionAppliquer').disabled = true;
    document.getElementById('fusionModal').checked = true;
}

function fusionCibleChange() {
    const cible = document.querySelector('input[name="fusionCible"]:checked')?.value;
    document.querySelectorAll('.fusion-source').forEach(c => {
        c.disabled = c.value === cible;
        if (c.disabled) c.checked = false;
    });
    document.getElementById('btnFusionAppliquer').disabled = true;
}

function fusionPayload() {
    const target_id = document.querySelector('input[name="fusionCible"]:checked')?.value || '';
    const source_ids = Array.from(document.querySelectorAll('.fusion-source:checked')).map(c => c.value);
    return { target_id, source_ids, nouveau_nom: document.getElementById('fusionNouveauNom').value.trim() };
}

async function fusionPost(action, payload) {
    const response = await fetch(`${FUSION_API}/${action}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify(payload),
    });
    return response.json();
}

async function fusionApercu() {
    const payload = fusionPayload();
    if (!payload.target_id || !payload.source_ids.length) {
        showAlert('Choisissez une fiche cible et au moins une fiche à fusionner', 'warning');
        return;
    }
    const zone = document.getElementById('fusionApercu');
    zone.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';
    try {
        const data = await fusionPost('apercu', payload);
        if (!data.success) {
            zone.innerHTML = `<div class="alert alert-error text-sm">${escapeHtml(data.error || 'Erreur')}</div>`;
            return;
        }
        const lignes = data.fiches.map(f => `
            <tr><td>${escapeHtml(f.tache)}</td><td class="text-center">${f.plannings}</td>
            <td class="text-center">${f.activites_postes}</td><td class="text-center">${f.evaluations}</td>
            <td class="text-center">${f.politiques}</td></tr>`).join('');
        const typeWarn = data.changement_type.length
            ? `<div class="alert alert-warning text-sm mt-2">Ces fiches changeront de type : ${data.changement_type.map(c => escapeHtml(c.tache)).join(', ')}</div>` : '';
        zone.innerHTML = `
            <p class="text-sm mb-2">Conservée : <strong>${escapeHtml(data.cible.nouveau_nom)}</strong>. Les éléments ci-dessous seront rattachés à cette fiche puis les fiches fusionnées supprimées.</p>
            <table class="table table-xs"><thead><tr><th>Fiche fusionnée</th><th>Réparations</th><th>Postes</th><th>Évaluations</th><th>Politiques</th></tr></thead>
            <tbody>${lignes}</tbody></table>${typeWarn}`;
        document.getElementById('btnFusionAppliquer').disabled = false;
    } catch (e) {
        zone.innerHTML = '<div class="alert alert-error text-sm">Erreur réseau</div>';
    }
}

async function fusionAppliquer() {
    const payload = fusionPayload();
    const btn = document.getElementById('btnFusionAppliquer');
    btn.disabled = true;
    try {
        const data = await fusionPost('appliquer', payload);
        if (!data.success) {
            showAlert(data.error || 'Fusion impossible', 'error');
            btn.disabled = false;
            return;
        }
        document.getElementById('fusionModal').checked = false;
        showAlert('Fiches fusionnées avec succès', 'success');
        if (currentTypeId) await loadFichesPoste(currentTypeId);
        loadTypesActivites();
        if (typeof updateStats === 'function') updateStats();
    } catch (e) {
        showAlert('Erreur réseau pendant la fusion', 'error');
        btn.disabled = false;
    }
}

// ===== PRÉCISIONS DEMANDÉES (CIBLE / COMPOSANTS) =====

const REGLES_MODE_LABEL = { non: 'non demandée', optionnel: 'facultative', obligatoire: 'obligatoire' };
const REGLES_CIBLE_TYPES_LABEL = { les_deux: '', point_eau: " (point d'eau)", equipement: ' (équipement)' };

// Badges résumant les règles effectives d'une fiche (rien n'est affiché tant que tout est facultatif)
function reglesFicheBadges(fiche) {
    const r = fiche.regles || {};
    const cible = r.cible_mode || 'optionnel';
    const comp = r.composants_mode || 'optionnel';
    const badges = [];
    const cls = (mode) => mode === 'obligatoire' ? 'badge-warning' : mode === 'non' ? 'badge-ghost' : 'badge-outline';
    if (cible !== 'optionnel' || (r.cible_types && r.cible_types !== 'les_deux')) {
        badges.push(`<span class="badge badge-sm ${cls(cible)}" title="Précision sur la cible">Cible ${REGLES_MODE_LABEL[cible]}${cible === 'non' ? '' : (REGLES_CIBLE_TYPES_LABEL[r.cible_types] || '')}</span>`);
    }
    if (comp !== 'optionnel' || r.composants_multiple === false) {
        const unique = r.composants_multiple === false && comp !== 'non' ? ' · un seul' : '';
        badges.push(`<span class="badge badge-sm ${cls(comp)}" title="Précision sur les composants">Composants ${REGLES_MODE_LABEL[comp]}${unique}</span>`);
    }
    const admis = Array.isArray(r.composants_admis) ? r.composants_admis : [];
    if (admis.length && comp !== 'non') {
        const liste = admis.map(n => String(n).replace(/[&<>"]/g, '')).join(', ');
        badges.push(`<span class="badge badge-sm badge-info" title="Composants admis : ${liste}">${admis.length} composant(s) admis</span>`);
    }
    return badges.length ? `<div class="flex flex-col gap-1 items-start">${badges.join('')}</div>` : '<span class="text-base-content/40">—</span>';
}

// Cohérence du formulaire : composants obligatoires => cible obligatoire ; cible non demandée => pas de composants
function updateReglesFicheForm() {
    const cible = document.getElementById('cible_mode');
    const comp = document.getElementById('composants_mode');
    const types = document.getElementById('cible_types');
    const multiple = document.getElementById('composants_multiple');
    const hint = document.getElementById('reglesFicheHint');
    if (!cible || !comp) return;
    let message = '';
    if (comp.value === 'obligatoire' && cible.value !== 'obligatoire') {
        cible.value = 'obligatoire';
        message = "Des composants obligatoires impliquent une cible obligatoire.";
    }
    if (cible.value === 'non') {
        if (comp.value !== 'non') message = "Sans cible, les composants ne sont pas demandés non plus.";
        comp.value = 'non';
    }
    if (types) types.disabled = cible.value === 'non';
    if (multiple) multiple.disabled = comp.value === 'non';
    const admis = document.getElementById('composants_admis');
    if (admis) admis.disabled = comp.value === 'non';
    if (hint) hint.textContent = message;
}


// ===== GESTION DES GROUPES =====

async function openGroupesModal() {
    document.getElementById('groupesModal').checked = true;
    await renderGroupesManager();
}

async function renderGroupesManager() {
    const tbody = document.getElementById('groupesListe');
    try {
        const groupes = await loadGroupesTypes();
        tbody.innerHTML = groupes.map(g => `
            <tr data-id="${g.id}">
                <td><input type="number" class="input input-bordered input-xs w-16 g-ordre" value="${g.ordre}"></td>
                <td><input type="text" class="input input-bordered input-xs w-full g-nom" maxlength="255" value="${escapeHtml(g.nom)}"></td>
                <td><input type="text" class="input input-bordered input-xs w-32 g-icone" maxlength="50" value="${escapeHtml(g.icone)}" title="Classe Font Awesome, ex: fa-users"></td>
                <td><span class="badge badge-outline">${g.types_count}</span></td>
                <td class="whitespace-nowrap">
                    <button class="btn btn-ghost btn-xs text-success" title="Enregistrer" onclick="saveGroupe('${g.id}', this)"><i class="fas fa-save"></i></button>
                    ${canDeleteItems ? `<button class="btn btn-ghost btn-xs text-error" title="Supprimer" onclick="deleteGroupe('${g.id}')"><i class="fas fa-trash"></i></button>` : ''}
                </td>
            </tr>`).join('') || '<tr><td colspan="5" class="text-center text-base-content/60">Aucun groupe</td></tr>';
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-error">${escapeHtml(e.message)}</td></tr>`;
    }
}

async function groupeRequest(url, method, body) {
    const response = await fetch(url, {
        method,
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken()},
        body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.message || `HTTP ${response.status}`);
    return data;
}

async function saveGroupe(id, btn) {
    const tr = btn.closest('tr');
    try {
        await groupeRequest(`/plannings/crud/api/groupes-types-activites/${id}/update/`, 'PUT', {
            nom: tr.querySelector('.g-nom').value,
            icone: tr.querySelector('.g-icone').value,
            ordre: tr.querySelector('.g-ordre').value,
        });
        showAlert('Groupe enregistré', 'success');
        await renderGroupesManager();
        loadTypesActivites();
    } catch (e) {
        showAlert(e.message, 'error');
    }
}

async function addGroupe() {
    const nom = document.getElementById('newGroupeNom').value.trim();
    if (!nom) { showAlert('Le nom du groupe est obligatoire', 'error'); return; }
    try {
        await groupeRequest('/plannings/crud/api/groupes-types-activites/create/', 'POST', {
            nom,
            icone: document.getElementById('newGroupeIcone').value.trim(),
            ordre: groupesTypes.length ? Math.max(...groupesTypes.map(g => g.ordre)) + 1 : 1,
        });
        document.getElementById('newGroupeNom').value = '';
        document.getElementById('newGroupeIcone').value = '';
        await renderGroupesManager();
        loadTypesActivites();
    } catch (e) {
        showAlert(e.message, 'error');
    }
}

async function deleteGroupe(id) {
    if (!confirm('Supprimer ce groupe ?')) return;
    try {
        await groupeRequest(`/plannings/crud/api/groupes-types-activites/${id}/delete/`, 'DELETE');
        await renderGroupesManager();
        loadTypesActivites();
    } catch (e) {
        showAlert(e.message, 'error');
    }
}
