let demandes = [];
let employes = [];
let typesPermissions = [];
let occupiedJourFerieDates = new Set();
let occupiedReposDates = new Set();
let rawJourFerieOptions = [];
let rawReposOptions = [];

function getInitialEmployeIdFromUrl() {
    const params = new URLSearchParams(window.location.search || '');
    return (params.get('employe_id') || params.get('employe') || '').trim();
}

function applyInitialEmployeFilterFromUrl() {
    const employeId = getInitialEmployeIdFromUrl();
    if (!employeId) {
        return;
    }

    ['filterEmploye', 'createEmploye'].forEach((selectId) => {
        const select = document.getElementById(selectId);
        if (!select) {
            return;
        }

        const hasOption = Array.from(select.options).some((option) => option.value === employeId);
        if (hasOption) {
            select.value = employeId;
        }
    });
}

async function loadInitialData() {
    try {
        const [resTypes] = await Promise.all([
            fetch('/api/employes/?per_page=1000'),  // Charger tous les employés (max 1000)
            fetch('/api/types-permissions/list/')
        ]);

        const dataTypes = await (await fetch('/api/types-permissions/list/')).json();

        employes = Array.isArray(window.demandesCongesEmployes) ? window.demandesCongesEmployes : [];
        typesPermissions = dataTypes.types || [];

        populateEmployeSelects();
        applyInitialEmployeFilterFromUrl();
        populateTypePermissionSelect();
        loadDemandes();
    } catch (error) {
        console.error('Erreur chargement initial:', error);
    }
}

function populateEmployeSelects() {
    ['filterEmploye', 'createEmploye', 'jourFerieEmploye', 'reposEmploye'].forEach(selectId => {
        const select = document.getElementById(selectId);
        if (!select) return;

        if (!Array.isArray(employes) || employes.length === 0) {
            return;
        }

        const currentValue = select.value;
        const firstOption = select.querySelector('option:first-child');
        select.innerHTML = firstOption.outerHTML;

        employes.forEach(emp => {
            const option = document.createElement('option');
            option.value = emp.id;
            // Afficher le surnom, ou fallback sur nom complet si surnom vide
            option.textContent = emp.surnom || `${emp.nom} ${emp.prenom}`;
            select.appendChild(option);
        });

        if (currentValue) select.value = currentValue;
    });

    syncJourFerieEmployeSelect();
}

function syncJourFerieEmployeSelect() {
    const createSelect = document.getElementById('createEmploye');
    const jourFerieSelect = document.getElementById('jourFerieEmploye');
    if (!createSelect || !jourFerieSelect) return;

    const currentValue = jourFerieSelect.value;
    jourFerieSelect.innerHTML = createSelect.innerHTML;

    if (currentValue && Array.from(jourFerieSelect.options).some((option) => option.value === currentValue)) {
        jourFerieSelect.value = currentValue;
    }
}

function monthLabelFromKey(monthKey) {
    if (!monthKey || !monthKey.includes('-')) return '';
    const [year, month] = monthKey.split('-');
    const dateObj = new Date(Number(year), Number(month) - 1, 1);
    return dateObj.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
}

function extractOptionsData(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return [];
    return Array.from(select.querySelectorAll('option'))
        .filter((option) => option.value)
        .map((option) => ({
            value: option.value,
            label: option.textContent,
            month: option.dataset.month || option.value.slice(0, 7),
        }));
}

function rebuildGroupedDateSelect(selectId, optionsData, occupiedSet, placeholderText) {
    const select = document.getElementById(selectId);
    if (!select) return;

    const currentValue = select.value;
    const availableOptions = (Array.isArray(optionsData) ? optionsData : [])
        .filter((option) => !occupiedSet.has(String(option.value)));

    select.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = placeholderText;
    select.appendChild(placeholder);

    const groups = new Map();
    availableOptions.forEach((option) => {
        const monthKey = option.month || option.value.slice(0, 7);
        if (!groups.has(monthKey)) groups.set(monthKey, []);
        groups.get(monthKey).push(option);
    });

    Array.from(groups.keys()).sort().forEach((monthKey) => {
        const optgroup = document.createElement('optgroup');
        optgroup.label = monthLabelFromKey(monthKey);
        groups.get(monthKey).forEach((option) => {
            const opt = document.createElement('option');
            opt.value = option.value;
            opt.textContent = option.label;
            opt.dataset.month = option.month || monthKey;
            optgroup.appendChild(opt);
        });
        select.appendChild(optgroup);
    });

    if (currentValue && availableOptions.some((option) => option.value === currentValue)) {
        select.value = currentValue;
    } else {
        select.value = '';
    }
}

function populateTypePermissionSelect() {
    const select = document.getElementById('createTypePermission');
    if (!select) return;

    select.innerHTML = '<option value="">Sélectionner</option>';
    typesPermissions.filter(t => t.actif).forEach(type => {
        const option = document.createElement('option');
        option.value = type.id;
        option.textContent = `${type.evenement} (${type.nb_jours_accordes} jour(s))`;
        select.appendChild(option);
    });
}

async function loadDemandes() {
    try {
        const params = new URLSearchParams();
        const statut = document.getElementById('filterStatut')?.value;
        const type = document.getElementById('filterType')?.value;
        const employeId = document.getElementById('filterEmploye')?.value;

        if (statut) params.append('statut', statut);
        if (type) params.append('type', type);
        if (employeId) params.append('employe_id', employeId);

        const response = await fetch(`/api/demandes-conges/list/?${params}`);
        const data = await response.json();

        if (data.success) {
            demandes = data.demandes;
            displayDemandes();
            updateStats();
        }
    } catch (error) {
        console.error('Erreur chargement demandes:', error);
    }
}

function displayDemandes() {
    const tbody = document.getElementById('demandesTableBody');

    if (demandes.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-base-content/50">Aucune demande trouvée</td></tr>';
        return;
    }

    tbody.innerHTML = demandes.map(demande => {
        const statutBadge = {
            'brouillon': 'badge-ghost',
            'soumise': 'badge-warning',
            'validee_chef': 'badge-info',
            'validee_directeur': 'badge-success',
            'inscrite_planning': 'badge-secondary',
            'annulee': 'badge-error',
            'refusee': 'badge-warning'
        }[demande.statut] || 'badge-ghost';

        // Mapping des types de congés avec leurs labels et badges
        const typeInfo = {
            'conge': { label: 'Congé normal', badge: 'badge-primary' },
            'conge_demi': { label: 'Congé demi-journée', badge: 'badge-primary' },
            'permission': { label: 'Permission', badge: 'badge-accent' },
            'repos': { label: 'Repos', badge: 'badge-info' },
            'jour_ferie': { label: 'Jour férié', badge: 'badge-secondary' }
        };

        const currentType = typeInfo[demande.type_demande] || { label: 'Inconnu', badge: 'badge-ghost' };

        return `
            <tr>
                <td class="font-semibold">${demande.employe_nom}</td>
                <td><span class="badge ${currentType.badge}">${currentType.label}</span></td>
                <td>${formatDate(demande.date_debut)} → ${formatDate(demande.date_fin)}</td>
                <td><span class="badge badge-lg">${demande.nb_jours_demandes} jour(s)</span></td>
                <td><span class="badge ${statutBadge}">${demande.statut_display}</span></td>
                <td class="text-sm">Congés: ${demande.reliquat_conge_actuel || 0}<br>Permissions: ${demande.reliquat_permission_actuel || 0}</td>
                <td>${getActionsDropdown(demande)}</td>
            </tr>
        `;
    }).join('');
}

function getActionsDropdown(demande) {
    let actions = `<li><a onclick="viewDetail('${demande.id}')"><i class="fas fa-eye"></i> Voir détails</a></li>`;

    if (demande.statut === 'brouillon') {
        actions += `<li><a onclick="soumettreDemande('${demande.id}')"><i class="fas fa-paper-plane text-warning"></i> Soumettre</a></li>`;
    } else if (demande.statut === 'soumise') {
        actions += `<li><a onclick="validerChef('${demande.id}')"><i class="fas fa-check text-info"></i> Valider (Chef)</a></li>`;
        actions += `<li><a onclick="refuserDemande('${demande.id}')"><i class="fas fa-times text-error"></i> Refuser</a></li>`;
    } else if (demande.statut === 'validee_chef') {
        actions += `<li><a onclick="validerDirecteur('${demande.id}')"><i class="fas fa-check-double text-success"></i> Valider (Directeur)</a></li>`;
        actions += `<li><a onclick="refuserDemande('${demande.id}')"><i class="fas fa-times text-error"></i> Refuser</a></li>`;
    } else if (demande.statut === 'validee_directeur' && !demande.inscrit_planning) {
        actions += `<li><a onclick="inscrirePlanning('${demande.id}')"><i class="fas fa-calendar-plus text-secondary"></i> Inscrire au planning</a></li>`;
    }

    // Reporter (seulement si pas encore inscrit au planning)
    if (demande.statut !== 'inscrite_planning' && demande.statut !== 'annulee' && demande.statut !== 'refusee') {
        actions += `<li><a onclick="reporterDemande('${demande.id}')"><i class="fas fa-calendar-alt text-warning"></i> Reporter</a></li>`;
    }

    // Annuler (à tout moment sauf si déjà annulée ou refusée)
    if (demande.statut !== 'annulee' && demande.statut !== 'refusee') {
        actions += `<li><a onclick="annulerDemande('${demande.id}')"><i class="fas fa-ban text-error"></i> Annuler</a></li>`;
    }

    return `<div class="dropdown dropdown-end"><label tabindex="0" class="btn btn-sm btn-ghost"><i class="fas fa-ellipsis-v"></i></label>
           <ul tabindex="0" class="dropdown-content menu p-2 shadow bg-base-100 rounded-box w-52 z-50">${actions}</ul></div>`;
}

function updateStats() {
    const stats = {brouillon: 0, soumise: 0, validee_chef: 0, validee_directeur: 0, inscrite_planning: 0, annulee: 0, refusee: 0};
    demandes.forEach(d => {
        if (stats.hasOwnProperty(d.statut)) stats[d.statut]++;
    });

    document.getElementById('stat-brouillon').textContent = stats.brouillon;
    document.getElementById('stat-soumise').textContent = stats.soumise;
    document.getElementById('stat-validee-chef').textContent = stats.validee_chef;
    document.getElementById('stat-validee-directeur').textContent = stats.validee_directeur;
    document.getElementById('stat-inscrite').textContent = stats.inscrite_planning;
    document.getElementById('stat-annulee').textContent = stats.annulee;
    document.getElementById('stat-refusee').textContent = stats.refusee;
}

function openCreateModal() {
    document.getElementById('createForm').reset();
    document.getElementById('soldesDisplay').classList.add('hidden');
    document.getElementById('typePermissionField').classList.add('hidden');
    document.getElementById('jourFerieField')?.classList.add('hidden');
    document.getElementById('dateRangeFields')?.classList.remove('hidden');

    const filteredEmployeId = document.getElementById('filterEmploye')?.value || getInitialEmployeIdFromUrl();
    const createEmploye = document.getElementById('createEmploye');
    if (createEmploye && filteredEmployeId) {
        const hasOption = Array.from(createEmploye.options).some((option) => option.value === filteredEmployeId);
        if (hasOption) {
            createEmploye.value = filteredEmployeId;
            loadEmployeSoldes();
        }
    }

    document.getElementById('createModal').showModal();
}

function openJourFerieModal() {
    const form = document.getElementById('jourFerieForm');
    if (form) {
        form.reset();
    }

    syncJourFerieEmployeSelect();
    document.getElementById('jourFerieSoldesDisplay')?.classList.add('hidden');
    occupiedJourFerieDates = new Set();
    updateJourFerieOptionsAvailabilityForSelect('jourFerieDate');

    const filteredEmployeId = document.getElementById('filterEmploye')?.value || getInitialEmployeIdFromUrl();
    const jourFerieEmploye = document.getElementById('jourFerieEmploye');
    if (jourFerieEmploye && filteredEmployeId) {
        const hasOption = Array.from(jourFerieEmploye.options).some((option) => option.value === filteredEmployeId);
        if (hasOption) {
            jourFerieEmploye.value = filteredEmployeId;
            loadJourFerieEmployeData();
        }
    }

    document.getElementById('jourFerieModal')?.showModal();
}

function openReposModal() {
    const form = document.getElementById('reposForm');
    if (form) {
        form.reset();
    }

    document.getElementById('reposSoldesDisplay')?.classList.add('hidden');
    occupiedReposDates = new Set();
    updateReposOptionsAvailability();

    const filteredEmployeId = document.getElementById('filterEmploye')?.value || getInitialEmployeIdFromUrl();
    const reposEmploye = document.getElementById('reposEmploye');
    if (reposEmploye && filteredEmployeId) {
        const hasOption = Array.from(reposEmploye.options).some((option) => option.value === filteredEmployeId);
        if (hasOption) {
            reposEmploye.value = filteredEmployeId;
            loadReposEmployeData();
        }
    }

    document.getElementById('reposModal')?.showModal();
}

async function loadEmployeSoldes() {
    const employeId = document.getElementById('createEmploye').value;
    const currentType = document.getElementById('createType')?.value || '';
    if (!employeId) {
        document.getElementById('soldesDisplay').classList.add('hidden');
        occupiedJourFerieDates = new Set();
        updateJourFerieOptionsAvailability();
        return;
    }

    try {
        const planningTypeParam = currentType === 'repos' ? 'repos' : 'jour_ferie';
        const [soldeResponse, joursFeriesResponse] = await Promise.all([
            fetch(`/api/suivi-conges/?employe_id=${employeId}`),
            fetch(`/api/demandes-conges/jours-feries-planning/?employe_id=${employeId}&type=${planningTypeParam}`)
        ]);
        const data = await soldeResponse.json();
        const joursFeriesData = await joursFeriesResponse.json();

        if (data.success && data.soldes.length > 0) {
            const dernierSolde = data.soldes[0];
            document.getElementById('soldeConges').textContent = dernierSolde.solde_conges_fin;
            document.getElementById('soldePermissions').textContent = dernierSolde.solde_permissions_fin;
            document.getElementById('soldesDisplay').classList.remove('hidden');
        }
        occupiedJourFerieDates = new Set((joursFeriesData.success ? (joursFeriesData.dates || []) : []).map(String));
        if (currentType === 'repos') {
            updateJourFerieOptionsAvailability();
        } else {
            updateJourFerieOptionsAvailability();
        }
    } catch (error) {
        console.error('Erreur chargement soldes:', error);
        occupiedJourFerieDates = new Set();
        updateJourFerieOptionsAvailability();
    }
}

function updateJourFerieOptionsAvailability() {
    const select = document.getElementById('createJourFerieDate');
    if (!select) return;

    Array.from(select.options).forEach((option) => {
        if (!option.value) {
            option.disabled = false;
            return;
        }
        const isOccupied = occupiedJourFerieDates.has(String(option.value));
        option.disabled = isOccupied;
        option.textContent = isOccupied
            ? `${option.value.split('-').reverse().join('/')} - déjà dans le planning`
            : option.textContent.replace(' - déjà dans le planning', '');
    });

    if (select.value && occupiedJourFerieDates.has(String(select.value))) {
        select.value = '';
        handleJourFerieDateChange();
    }
}

function updateJourFerieOptionsAvailabilityForSelect(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;

    Array.from(select.options).forEach((option) => {
        if (!option.value) {
            option.disabled = false;
            return;
        }

        if (!option.dataset.originalLabel) {
            option.dataset.originalLabel = option.textContent.replace(' - déjÃ  dans le planning', '');
        }

        const isOccupied = occupiedJourFerieDates.has(String(option.value));
        option.disabled = isOccupied;
        option.textContent = isOccupied
            ? `${option.dataset.originalLabel} - déjÃ  dans le planning`
            : option.dataset.originalLabel;
    });

    if (select.value && occupiedJourFerieDates.has(String(select.value))) {
        select.value = '';
    }
}

async function loadJourFerieEmployeData() {
    const employeId = document.getElementById('jourFerieEmploye')?.value;
    if (!employeId) {
        document.getElementById('jourFerieSoldesDisplay')?.classList.add('hidden');
        occupiedJourFerieDates = new Set();
        updateJourFerieOptionsAvailabilityForSelect('jourFerieDate');
        return;
    }

    try {
        const [soldeResponse, joursFeriesResponse] = await Promise.all([
            fetch(`/api/suivi-conges/?employe_id=${employeId}`),
            fetch(`/api/demandes-conges/jours-feries-planning/?employe_id=${employeId}`)
        ]);
        const data = await soldeResponse.json();
        const joursFeriesData = await joursFeriesResponse.json();

        if (data.success && data.soldes.length > 0) {
            const dernierSolde = data.soldes[0];
            document.getElementById('jourFerieSoldeConges').textContent = dernierSolde.solde_conges_fin;
            document.getElementById('jourFerieSoldePermissions').textContent = dernierSolde.solde_permissions_fin;
            document.getElementById('jourFerieSoldesDisplay')?.classList.remove('hidden');
        }

        occupiedJourFerieDates = new Set((joursFeriesData.success ? (joursFeriesData.dates || []) : []).map(String));
        updateJourFerieOptionsAvailabilityForSelect('jourFerieDate');
    } catch (error) {
        console.error('Erreur chargement jour ferie:', error);
        occupiedJourFerieDates = new Set();
        updateJourFerieOptionsAvailabilityForSelect('jourFerieDate');
    }
}

function updateReposOptionsAvailability() {
    const select = document.getElementById('reposDate');
    if (!select) return;

    Array.from(select.options).forEach((option) => {
        if (!option.value) {
            option.disabled = false;
            return;
        }

        if (!option.dataset.originalLabel) {
            option.dataset.originalLabel = option.textContent.replace(' - déjÃ  dans le planning', '');
        }

        const isOccupied = occupiedReposDates.has(String(option.value));
        option.disabled = isOccupied;
        option.textContent = isOccupied
            ? `${option.dataset.originalLabel} - déjÃ  dans le planning`
            : option.dataset.originalLabel;
    });

    if (select.value && occupiedReposDates.has(String(select.value))) {
        select.value = '';
    }
}

async function loadReposEmployeData() {
    const employeId = document.getElementById('reposEmploye')?.value;
    if (!employeId) {
        document.getElementById('reposSoldesDisplay')?.classList.add('hidden');
        occupiedReposDates = new Set();
        updateReposOptionsAvailability();
        return;
    }

    try {
        const [soldeResponse, reposResponse] = await Promise.all([
            fetch(`/api/suivi-conges/?employe_id=${employeId}`),
            fetch(`/api/demandes-conges/jours-feries-planning/?employe_id=${employeId}&type=repos`)
        ]);
        const data = await soldeResponse.json();
        const reposData = await reposResponse.json();

        const soldes = Array.isArray(data?.soldes) ? data.soldes : [];
        if (data.success && soldes.length > 0) {
            const dernierSolde = soldes[0];
            document.getElementById('reposSoldeConges').textContent = dernierSolde.solde_conges_fin;
            document.getElementById('reposSoldePermissions').textContent = dernierSolde.solde_permissions_fin;
            document.getElementById('reposSoldesDisplay')?.classList.remove('hidden');
        } else {
            document.getElementById('reposSoldesDisplay')?.classList.add('hidden');
        }

        const reposDates = reposData.success && Array.isArray(reposData?.dates) ? reposData.dates : [];
        occupiedReposDates = new Set(reposDates.map(String));
        updateReposOptionsAvailability();
    } catch (error) {
        console.error('Erreur chargement repos:', error);
        occupiedReposDates = new Set();
        updateReposOptionsAvailability();
    }
}

function toggleTypeFields() {
    const type = document.getElementById('createType').value;
    const typePermField = document.getElementById('typePermissionField');
    const motifField = document.getElementById('createMotif');
    const motifLabel = document.querySelector('label[for="createMotif"], #createMotif').closest('.form-control').querySelector('.label-text');

    // Afficher/masquer le champ type de permission
    if (type === 'permission') {
        typePermField.classList.remove('hidden');
    } else {
        typePermField.classList.add('hidden');
    }

    const jourFerieField = document.getElementById('jourFerieField');
    const dateRangeFields = document.getElementById('dateRangeFields');
    const dateDebutField = document.getElementById('createDateDebut');
    const dateFinField = document.getElementById('createDateFin');
    const jourFerieSelect = document.getElementById('createJourFerieDate');

    if (type === 'jour_ferie') {
        jourFerieField?.classList.remove('hidden');
        dateRangeFields?.classList.add('hidden');
        if (dateDebutField) {
            dateDebutField.removeAttribute('required');
            dateDebutField.value = '';
        }
        if (dateFinField) {
            dateFinField.removeAttribute('required');
            dateFinField.value = '';
        }
        if (jourFerieSelect) {
            jourFerieSelect.setAttribute('required', 'required');
        }
        updateJourFerieOptionsAvailability();
        document.getElementById('createNbJours').value = 1;
    } else if (type === 'repos') {
        jourFerieField?.classList.remove('hidden');
        if (jourFerieField) {
            const label = jourFerieField.querySelector('.label-text');
            if (label) {
                label.innerHTML = 'Jour de repos <span class="text-error">*</span>';
            }
        }
        if (jourFerieSelect) {
            jourFerieSelect.innerHTML = document.getElementById('reposDate')?.innerHTML || '<option value="">Sélectionner un samedi ou dimanche</option>';
            jourFerieSelect.setAttribute('required', 'required');
        }
        dateRangeFields?.classList.add('hidden');
        if (dateDebutField) {
            dateDebutField.removeAttribute('required');
            dateDebutField.value = '';
        }
        if (dateFinField) {
            dateFinField.removeAttribute('required');
            dateFinField.value = '';
        }
        loadEmployeSoldes();
        document.getElementById('createNbJours').value = 1;
    } else {
        jourFerieField?.classList.add('hidden');
        if (jourFerieField) {
            const label = jourFerieField.querySelector('.label-text');
            if (label) {
                label.innerHTML = 'Jour férié <span class="text-error">*</span>';
            }
        }
        dateRangeFields?.classList.remove('hidden');
        if (dateDebutField) {
            dateDebutField.setAttribute('required', 'required');
        }
        if (dateFinField) {
            dateFinField.setAttribute('required', 'required');
        }
        if (jourFerieSelect) {
            jourFerieSelect.removeAttribute('required');
            jourFerieSelect.value = '';
        }
    }

    // Rendre le motif optionnel pour les repos
    if (type === 'repos') {
        motifField.removeAttribute('required');
        if (motifLabel) {
            motifLabel.innerHTML = 'Motif';  // Retirer l'astérisque
        }
    } else {
        motifField.setAttribute('required', 'required');
        if (motifLabel) {
            motifLabel.innerHTML = 'Motif <span class="text-error">*</span>';
        }
    }
}

function calculateNbJours() {
    const dateDebut = document.getElementById('createDateDebut').value;
    const dateFin = document.getElementById('createDateFin').value;

    if (!dateDebut || !dateFin) return;

    const debut = new Date(dateDebut);
    const fin = new Date(dateFin);

    if (debut > fin) {
        alert('La date de fin doit être après la date de début');
        return;
    }

    let nbJours = 0;
    let current = new Date(debut);

    while (current <= fin) {
        const dayOfWeek = current.getDay();
        if (dayOfWeek !== 0 && dayOfWeek !== 6) nbJours++;
        current.setDate(current.getDate() + 1);
    }

    document.getElementById('createNbJours').value = nbJours;
}

function handleJourFerieDateChange() {
    const jourFerieSelect = document.getElementById('createJourFerieDate');
    const selectedDate = jourFerieSelect?.value || '';
    document.getElementById('createNbJours').value = selectedDate ? 1 : '';
}

async function handleCreate(event) {
    event.preventDefault();

    const typeDemande = document.getElementById('createType').value;
    const selectedJourFerieDate = document.getElementById('createJourFerieDate')?.value || '';
    const usesSingleSelectedDate = typeDemande === 'jour_ferie' || typeDemande === 'repos';
    const dateDebut = usesSingleSelectedDate
        ? selectedJourFerieDate
        : document.getElementById('createDateDebut').value;
    const dateFin = usesSingleSelectedDate
        ? selectedJourFerieDate
        : document.getElementById('createDateFin').value;

    const data = {
        employe_id: document.getElementById('createEmploye').value,
        type_demande: typeDemande,
        date_debut: dateDebut,
        date_fin: dateFin,
        jour_ferie_date: selectedJourFerieDate || null,
        motif: document.getElementById('createMotif').value,
        type_permission_id: document.getElementById('createTypePermission').value || null
    };

    try {
        const response = await fetch('/api/demandes-conges/create/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            document.getElementById('createModal').close();
            loadDemandes();
        } else {
            alert('Erreur: ' + result.error);
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur lors de la création');
    }
}

async function handleJourFerieCreate(event) {
    event.preventDefault();

    const selectedJourFerieDate = document.getElementById('jourFerieDate')?.value || '';
    const data = {
        employe_id: document.getElementById('jourFerieEmploye')?.value,
        type_demande: 'jour_ferie',
        date_debut: selectedJourFerieDate,
        date_fin: selectedJourFerieDate,
        jour_ferie_date: selectedJourFerieDate,
        motif: document.getElementById('jourFerieMotif')?.value || 'Jour férié',
        type_permission_id: null
    };

    try {
        const response = await fetch('/api/demandes-conges/create/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            document.getElementById('jourFerieModal')?.close();
            loadDemandes();
        } else {
            alert('Erreur: ' + result.error);
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur lors de la création du jour férié');
    }
}

async function handleReposCreate(event) {
    event.preventDefault();

    const selectedReposDate = document.getElementById('reposDate')?.value || '';
    const data = {
        employe_id: document.getElementById('reposEmploye')?.value,
        type_demande: 'repos',
        date_debut: selectedReposDate,
        date_fin: selectedReposDate,
        motif: document.getElementById('reposMotif')?.value || 'Repos',
        type_permission_id: null
    };

    try {
        const response = await fetch('/api/demandes-conges/create/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            document.getElementById('reposModal')?.close();
            loadDemandes();
        } else {
            alert('Erreur: ' + result.error);
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur lors de la création du repos');
    }
}

async function viewDetail(demandeId) {
    document.getElementById('detailModal').showModal();
    document.getElementById('detailContent').innerHTML = '<span class="loading loading-spinner loading-lg"></span>';

    try {
        const response = await fetch(`/api/demandes-conges/${demandeId}/detail/`);
        const data = await response.json();

        if (data.success) {
            const d = data.demande;
            let html = `<div class="space-y-4">
                <div class="grid grid-cols-2 gap-4">
                    <div><label class="font-semibold">Employé:</label><p>${d.employe_nom}</p></div>
                    <div><label class="font-semibold">Type:</label><p>${d.type_demande === 'conge' ? 'Congé' : 'Permission'}</p></div>
                    <div><label class="font-semibold">Période:</label><p>${formatDate(d.date_debut)} → ${formatDate(d.date_fin)}</p></div>
                    <div><label class="font-semibold">Nb jours:</label><p>${d.nb_jours_demandes} jour(s)</p></div>
                </div>
                <div><label class="font-semibold">Motif:</label><p class="bg-base-200 p-3 rounded">${d.motif}</p></div>
                <div class="grid grid-cols-2 gap-4">
                    <div><label class="font-semibold">Reliquat congés avant:</label><p>${d.reliquat_conge_avant} jour(s)</p></div>
                    <div><label class="font-semibold">Reliquat permissions avant:</label><p>${d.reliquat_permission_avant} jour(s)</p></div>
                </div>`;

            if (d.commentaire_chef) {
                html += `<div class="alert alert-info"><div><div class="font-semibold">Commentaire chef:</div>
                        <div>${d.commentaire_chef}</div>
                        <div class="text-sm">Par ${d.validee_par_chef_nom} le ${formatDateTime(d.date_validation_chef)}</div></div></div>`;
            }

            if (d.commentaire_directeur) {
                html += `<div class="alert alert-success"><div><div class="font-semibold">Commentaire directeur:</div>
                        <div>${d.commentaire_directeur}</div>
                        <div class="text-sm">Par ${d.validee_par_directeur_nom} le ${formatDateTime(d.date_validation_directeur)}</div></div></div>`;
            }

            if (d.statut === 'annulee' && d.motif_annulation) {
                html += `<div class="alert alert-error"><div><div class="font-semibold"><i class="fas fa-ban mr-2"></i>Demande annulée:</div>
                        <div>${d.motif_annulation}</div>
                        <div class="text-sm">Par ${d.annulee_par_nom || 'N/A'} le ${formatDateTime(d.date_annulation)}</div></div></div>`;
            }

            if (d.dates_originales && d.dates_originales.length > 0) {
                html += `<div class="alert alert-warning"><div><div class="font-semibold"><i class="fas fa-calendar-alt mr-2"></i>Historique des reports:</div><ul class="list-disc list-inside mt-2">`;
                d.dates_originales.forEach(report => {
                    html += `<li>${formatDate(report.date_debut)} → ${formatDate(report.date_fin)} (${report.motif || 'Aucun motif'}) - ${formatDateTime(report.date_report)}</li>`;
                });
                html += `</ul></div></div>`;
            }

            html += '</div>';
            document.getElementById('detailContent').innerHTML = html;
        }
    } catch (error) {
        console.error('Erreur:', error);
        document.getElementById('detailContent').innerHTML = '<p class="text-error">Erreur de chargement</p>';
    }
}

async function soumettreDemande(demandeId) {
    if (!confirm('Soumettre cette demande pour validation ?')) return;
    await performAction(demandeId, 'soumettre', {});
}

async function validerChef(demandeId) {
    const commentaire = prompt('Commentaire (optionnel):');
    await performAction(demandeId, 'valider-chef', {commentaire});
}

async function validerDirecteur(demandeId) {
    const commentaire = prompt('Commentaire (optionnel):');
    await performAction(demandeId, 'valider-directeur', {commentaire});
}

async function refuserDemande(demandeId) {
    const motif = prompt('Motif du refus (obligatoire):');
    if (!motif) return;
    await performAction(demandeId, 'refuser', {motif_refus: motif});
}

async function inscrirePlanning(demandeId) {
    if (!confirm('Inscrire cette demande au planning ?\n\nCela créera automatiquement les jours de congé dans le planning.')) return;
    await performAction(demandeId, 'inscrire-planning', {});
}

async function annulerDemande(demandeId) {
    const motif = prompt('Motif de l\'annulation (obligatoire):');
    if (!motif || motif.trim() === '') {
        alert('Le motif d\'annulation est obligatoire');
        return;
    }

    if (!confirm('⚠️ ATTENTION ⚠️\n\nEn annulant cette demande:\n- Si déjà inscrite au planning, les jours seront supprimés\n- Le solde de congés sera restauré\n- Cette action est irréversible\n\nConfirmer l\'annulation ?')) {
        return;
    }

    await performAction(demandeId, 'annuler', {motif_annulation: motif});
}

async function reporterDemande(demandeId) {
    // Récupérer les informations de la demande
    const demande = demandes.find(d => d.id === demandeId);
    if (!demande) {
        alert('Demande non trouvée');
        return;
    }

    // Stocker l'ID de la demande pour l'utiliser lors de la soumission
    window.currentDemandeIdToReport = demandeId;

    // Réinitialiser le formulaire
    document.getElementById('reportForm').reset();

    // Afficher les informations de la demande originale
    document.getElementById('reportOriginalDateDebut').textContent = formatDate(demande.date_debut);
    document.getElementById('reportOriginalDateFin').textContent = formatDate(demande.date_fin);
    document.getElementById('reportOriginalNbJours').textContent = demande.nb_jours_demandes;
    document.getElementById('reportOriginalMotif').textContent = demande.motif || 'Aucun motif';

    // Afficher le modal
    document.getElementById('reportModal').showModal();
}

async function submitReportDemande() {
    const nouvelleDateDebut = document.getElementById('reportDateDebut').value;
    const nouvelleDateFin = document.getElementById('reportDateFin').value;
    const motif = document.getElementById('reportMotif').value;

    if (!nouvelleDateDebut || !nouvelleDateFin) {
        alert('Les dates de début et de fin sont obligatoires');
        return;
    }

    if (!motif || motif.trim() === '') {
        alert('Le motif du report est obligatoire');
        return;
    }

    const data = {
        nouvelle_date_debut: nouvelleDateDebut,
        nouvelle_date_fin: nouvelleDateFin,
        motif_report: motif
    };

    await performAction(window.currentDemandeIdToReport, 'reporter', data);

    // Fermer le modal
    document.getElementById('reportModal').close();
    document.getElementById('reportForm').reset();
}

async function performAction(demandeId, action, data) {
    try {
        const response = await fetch(`/api/demandes-conges/${demandeId}/${action}/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            alert(result.message);
            loadDemandes();
        } else {
            alert('Erreur: ' + result.error);
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert("Erreur lors de l'action");
    }
}

function applyFilters() {
    loadDemandes();
}

function resetFilters() {
    document.getElementById('filterStatut').value = '';
    document.getElementById('filterType').value = '';
    document.getElementById('filterEmploye').value = '';
    loadDemandes();
}

function filterByStatut(statut) {
    document.getElementById('filterStatut').value = statut;
    loadDemandes();
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return d.toLocaleDateString('fr-FR');
}

function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return d.toLocaleString('fr-FR');
}

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

function monthLabelFromKey(monthKey) {
    if (!monthKey || !monthKey.includes('-')) return '';
    const [year, month] = monthKey.split('-');
    const dateObj = new Date(Number(year), Number(month) - 1, 1);
    return dateObj.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
}

function extractOptionsData(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return [];
    return Array.from(select.querySelectorAll('option'))
        .filter((option) => option.value)
        .map((option) => ({
            value: option.value,
            label: option.textContent,
            month: option.dataset.month || option.value.slice(0, 7),
        }));
}

function rebuildGroupedDateSelect(selectId, optionsData, occupiedSet, placeholderText) {
    const select = document.getElementById(selectId);
    if (!select) return;

    const currentValue = select.value;
    const availableOptions = (Array.isArray(optionsData) ? optionsData : [])
        .filter((option) => !occupiedSet.has(String(option.value)));

    select.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = placeholderText;
    select.appendChild(placeholder);

    const groups = new Map();
    availableOptions.forEach((option) => {
        const monthKey = option.month || option.value.slice(0, 7);
        if (!groups.has(monthKey)) groups.set(monthKey, []);
        groups.get(monthKey).push(option);
    });

    Array.from(groups.keys()).sort().forEach((monthKey) => {
        const optgroup = document.createElement('optgroup');
        optgroup.label = monthLabelFromKey(monthKey);
        groups.get(monthKey).forEach((option) => {
            const opt = document.createElement('option');
            opt.value = option.value;
            opt.textContent = option.label;
            opt.dataset.month = option.month || monthKey;
            optgroup.appendChild(opt);
        });
        select.appendChild(optgroup);
    });

    if (currentValue && availableOptions.some((option) => option.value === currentValue)) {
        select.value = currentValue;
    } else {
        select.value = '';
    }
}

updateJourFerieOptionsAvailability = function() {
    rebuildGroupedDateSelect(
        'createJourFerieDate',
        rawJourFerieOptions,
        occupiedJourFerieDates,
        'Sélectionner un jour férié'
    );
    handleJourFerieDateChange();
};

updateJourFerieOptionsAvailabilityForSelect = function(selectId) {
    rebuildGroupedDateSelect(
        selectId,
        rawJourFerieOptions,
        occupiedJourFerieDates,
        'Sélectionner un jour férié'
    );
};

updateReposOptionsAvailability = function() {
    rebuildGroupedDateSelect(
        'reposDate',
        rawReposOptions,
        occupiedReposDates,
        'Sélectionner un samedi ou dimanche'
    );
};

loadEmployeSoldes = async function() {
    const employeId = document.getElementById('createEmploye').value;
    const currentType = document.getElementById('createType')?.value || '';
    if (!employeId) {
        document.getElementById('soldesDisplay').classList.add('hidden');
        occupiedJourFerieDates = new Set();
        updateJourFerieOptionsAvailability();
        return;
    }

    try {
        const planningTypeParam = currentType === 'repos' ? 'repos' : 'jour_ferie';
        const [soldeResponse, joursFeriesResponse] = await Promise.all([
            fetch(`/api/suivi-conges/?employe_id=${employeId}`),
            fetch(`/api/demandes-conges/jours-feries-planning/?employe_id=${employeId}&type=${planningTypeParam}`)
        ]);
        const data = await soldeResponse.json();
        const joursFeriesData = await joursFeriesResponse.json();

        const soldes = Array.isArray(data?.soldes) ? data.soldes : [];
        if (data.success && soldes.length > 0) {
            const dernierSolde = soldes[0];
            document.getElementById('soldeConges').textContent = dernierSolde.solde_conges_fin;
            document.getElementById('soldePermissions').textContent = dernierSolde.solde_permissions_fin;
            document.getElementById('soldesDisplay').classList.remove('hidden');
        } else {
            document.getElementById('soldesDisplay').classList.add('hidden');
        }
        const joursFeriesDates = joursFeriesData.success && Array.isArray(joursFeriesData?.dates) ? joursFeriesData.dates : [];
        occupiedJourFerieDates = new Set(joursFeriesDates.map(String));
        updateJourFerieOptionsAvailability();
    } catch (error) {
        console.error('Erreur chargement soldes:', error);
        occupiedJourFerieDates = new Set();
        updateJourFerieOptionsAvailability();
    }
};

loadJourFerieEmployeData = async function() {
    const employeId = document.getElementById('jourFerieEmploye')?.value;
    if (!employeId) {
        document.getElementById('jourFerieSoldesDisplay')?.classList.add('hidden');
        occupiedJourFerieDates = new Set();
        updateJourFerieOptionsAvailabilityForSelect('jourFerieDate');
        return;
    }

    try {
        const [soldeResponse, joursFeriesResponse] = await Promise.all([
            fetch(`/api/suivi-conges/?employe_id=${employeId}`),
            fetch(`/api/demandes-conges/jours-feries-planning/?employe_id=${employeId}`)
        ]);
        const data = await soldeResponse.json();
        const joursFeriesData = await joursFeriesResponse.json();

        const soldes = Array.isArray(data?.soldes) ? data.soldes : [];
        if (data.success && soldes.length > 0) {
            const dernierSolde = soldes[0];
            document.getElementById('jourFerieSoldeConges').textContent = dernierSolde.solde_conges_fin;
            document.getElementById('jourFerieSoldePermissions').textContent = dernierSolde.solde_permissions_fin;
            document.getElementById('jourFerieSoldesDisplay')?.classList.remove('hidden');
        } else {
            document.getElementById('jourFerieSoldesDisplay')?.classList.add('hidden');
        }

        const joursFeriesDates = joursFeriesData.success && Array.isArray(joursFeriesData?.dates) ? joursFeriesData.dates : [];
        occupiedJourFerieDates = new Set(joursFeriesDates.map(String));
        updateJourFerieOptionsAvailabilityForSelect('jourFerieDate');
    } catch (error) {
        console.error('Erreur chargement jour ferie:', error);
        occupiedJourFerieDates = new Set();
        updateJourFerieOptionsAvailabilityForSelect('jourFerieDate');
    }
};

document.addEventListener('DOMContentLoaded', () => {
    const createType = document.getElementById('createType');
    if (createType) {
        const holidayOption = Array.from(createType.options).find((option) => option.value === 'jour_ferie');
        if (holidayOption) {
            holidayOption.remove();
        }
    }
    rawJourFerieOptions = extractOptionsData('createJourFerieDate');
    rawReposOptions = extractOptionsData('reposDate');
    loadInitialData();
});
