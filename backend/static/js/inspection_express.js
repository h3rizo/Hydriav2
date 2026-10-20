/**
 * inspection_express.js
 *
 * Gestion du workflow d'inspection express
 * Permet de sélectionner un point de contrôle spécifique et de l'inspecter rapidement
 */

// Contexte global de l'inspection
window.inspectionContext = {
    itemId: null,
    itemType: null, // 'point_eau' ou 'equipement'
    ouvrageNom: null,
    inspectionId: null,
    numeroInspection: null,
    currentStep: 1,
    selectedControlPoint: null,
    controlPoints: []
};

/**
 * Ouvre le modal d'inspection express
 * @param {String} itemId - UUID de l'item (point d'eau ou équipement)
 * @param {String} itemType - Type d'item ('point_eau' ou 'equipement')
 * @param {String} ouvrageNom - Nom de l'ouvrage pour affichage
 */
function openInspectionExpressModal(itemId, itemType, ouvrageNom) {
    // Réinitialiser le contexte
    window.inspectionContext = {
        itemId: itemId,
        itemType: itemType,
        ouvrageNom: ouvrageNom,
        inspectionId: null,
        numeroInspection: null,
        currentStep: 1,
        selectedControlPoint: null,
        controlPoints: []
    };

    // Afficher le titre avec le nom de l'ouvrage
    const title = ouvrageNom ? `Inspection Express - ${ouvrageNom}` : 'Inspection Express';
    document.getElementById('inspection-express-title').textContent = title;
    setInspectionExpressDate(null);
    resetCorrectiveSection();

    // Ouvrir le modal
    document.getElementById('inspectionExpressModal').showModal();

    // Si le type est déjà connu, charger directement les points de contrôle
    if (itemType === 'point_eau' || itemType === 'equipement') {
        selectInspectionType(itemType);
    } else {
        // Afficher l'étape 1 (sélection du type)
        showStep(1);
    }
}

async function parseResponsePayload(response) {
    const text = await response.text();
    if (!text) {
        return { ok: response.ok, status: response.status, data: {} };
    }
    try {
        return { ok: response.ok, status: response.status, data: JSON.parse(text) };
    } catch (error) {
        return { ok: response.ok, status: response.status, data: { error: text } };
    }
}

/**
 * Affiche une étape spécifique du workflow
 * @param {Number} stepNumber - Numéro de l'étape (1, 2, ou 3)
 */
function showStep(stepNumber) {
    window.inspectionContext.currentStep = stepNumber;

    // Masquer toutes les étapes
    document.querySelectorAll('.inspection-step').forEach(step => {
        step.classList.add('hidden');
    });

    // Afficher l'étape demandée
    const stepElement = document.getElementById(`step${stepNumber}`);
    if (stepElement) {
        stepElement.classList.remove('hidden');
    }

    // Mettre à jour les indicateurs de progression
    updateProgressIndicators(stepNumber);
}

/**
 * Met à jour les indicateurs de progression
 * @param {Number} currentStep - Étape actuelle
 */
function updateProgressIndicators(currentStep) {
    for (let i = 1; i <= 3; i++) {
        const indicator = document.getElementById(`progress-step-${i}`);
        if (indicator) {
            if (i < currentStep) {
                indicator.className = 'step step-primary';
            } else if (i === currentStep) {
                indicator.className = 'step step-primary';
            } else {
                indicator.className = 'step';
            }
        }
    }
}

/**
 * Sélectionne le type d'inspection (Point d'Eau ou Équipement)
 * @param {String} type - Type sélectionné ('point_eau' ou 'equipement')
 */
async function selectInspectionType(type) {
    window.inspectionContext.itemType = type;

    // Afficher le loader
    showLoader('Chargement des points de contrôle...');

    try {
        // Charger les points de contrôle disponibles
        await loadControlPoints(window.inspectionContext.itemId, type);

        // Passer à l'étape 2
        showStep(2);
    } catch (error) {
        console.error('Erreur lors du chargement des points de contrôle:', error);
        alert('Erreur lors du chargement des points de contrôle: ' + error.message);
    } finally {
        hideLoader();
    }
}

/**
 * Charge les points de contrôle disponibles pour l'item
 * @param {String} itemId - UUID de l'item
 * @param {String} itemType - Type d'item
 */
async function loadControlPoints(itemId, itemType) {
    const url = `/inspections/api/control-points/${itemType}/${itemId}/`;

    const response = await fetch(url, {
        method: 'GET',
        headers: {
            'Accept': 'application/json',
        }
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();

    if (!data.success) {
        throw new Error(data.error || 'Erreur inconnue');
    }

    window.inspectionContext.controlPoints = data.control_points || [];

    // Afficher les points de contrôle
    renderControlPointsList(data.control_points);
}

/**
 * Affiche la liste des points de contrôle
 * @param {Array} controlPoints - Liste des points de contrôle
 */
function renderControlPointsList(controlPoints) {
    const container = document.getElementById('control-points-list');

    if (!controlPoints || controlPoints.length === 0) {
        container.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle mr-2"></i>
                Aucun point de contrôle disponible pour cet élément.
            </div>
        `;
        return;
    }

    let html = '<div class="space-y-2">';

    controlPoints.forEach(point => {
        const typeIcon = point.type === 'BOOL' ? 'fa-check-circle' :
                        point.type === 'NUM' ? 'fa-hashtag' : 'fa-align-left';
        const composantLabel = point.composant_nom ? `Composant: ${point.composant_nom}` : '';

        html += `
            <div class="card bg-base-100 shadow hover:shadow-lg transition-shadow cursor-pointer"
                 onclick="selectControlPoint('${point.id}')">
                <div class="card-body p-4">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <i class="fas ${typeIcon} text-2xl text-primary"></i>
                            <div>
                                <h3 class="font-semibold">${point.nom}</h3>
                                <p class="text-sm text-base-content/70">${point.type}</p>
                                ${composantLabel ? `<p class="text-xs text-base-content/60">${composantLabel}</p>` : ''}
                            </div>
                        </div>
                        <i class="fas fa-chevron-right text-base-content/50"></i>
                    </div>
                </div>
            </div>
        `;
    });

    html += '</div>';

    container.innerHTML = html;
}

/**
 * Sélectionne un point de contrôle et passe à l'étape 3
 * @param {String} pointId - UUID du point de contrôle
 */
async function selectControlPoint(pointId) {
    const point = window.inspectionContext.controlPoints.find(p => p.id === pointId);
    if (!point) {
        alert('Point de contrôle introuvable');
        return;
    }

    window.inspectionContext.selectedControlPoint = point;

    // Créer l'inspection si pas encore créée
    if (!window.inspectionContext.inspectionId) {
        showLoader('Création de l\'inspection...');

        try {
            await createInspectionExpress();
        } catch (error) {
            console.error('Erreur lors de la création de l\'inspection:', error);
            alert('Erreur lors de la création de l\'inspection: ' + error.message);
            hideLoader();
            return;
        }

        hideLoader();
    }

    // Afficher le formulaire d'inspection
    renderInspectionForm(point);

    // Passer à l'étape 3
    showStep(3);
}

/**
 * Crée une nouvelle inspection express
 */
async function createInspectionExpress() {
    const url = '/inspections/api/create-inspection-express/';

    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            item_id: window.inspectionContext.itemId,
            item_type: window.inspectionContext.itemType
        })
    });

    const payload = await parseResponsePayload(response);

    if (!payload.ok) {
        throw new Error(payload.data.error || `HTTP ${payload.status}`);
    }

    if (!payload.data.success) {
        throw new Error(payload.data.error || 'Erreur inconnue');
    }

    window.inspectionContext.inspectionId = payload.data.inspection_id;
    window.inspectionContext.numeroInspection = payload.data.numero_inspection;
    setInspectionExpressDate(new Date());
}

/**
 * Affiche le formulaire d'inspection pour un point de contrôle
 * @param {Object} point - Point de contrôle
 */
function renderInspectionForm(point) {
    document.getElementById('control-point-name').textContent = point.nom;

    const formContainer = document.getElementById('inspection-form-container');
    const today = new Date();
    const todayIso = today.toISOString().split('T')[0];
    const todayFr = today.toLocaleDateString('fr-FR');

    let html = '';

    // Formulaire selon le type de point de contrôle
    if (point.type === 'BOOL') {
        html = `
            <div class="form-control">
                <label class="label">
                    <span class="label-text font-semibold">État</span>
                </label>
                <div class="flex gap-4">
                    <label class="label cursor-pointer gap-2">
                        <input type="radio" name="bool-value" value="true" class="radio radio-success" />
                        <span class="label-text">Conforme</span>
                    </label>
                    <label class="label cursor-pointer gap-2">
                        <input type="radio" name="bool-value" value="false" class="radio radio-error" />
                        <span class="label-text">Non conforme</span>
                    </label>
                </div>
            </div>
        `;
    } else if (point.type === 'NUM') {
        html = `
            <div class="form-control">
                <label class="label">
                    <span class="label-text font-semibold">Valeur numérique</span>
                </label>
                <input type="number" id="numeric-value" class="input input-bordered"
                       placeholder="Entrez une valeur" step="0.01" />
            </div>
        `;
    } else if (point.type === 'TEXT') {
        html = `
            <div class="form-control">
                <label class="label">
                    <span class="label-text font-semibold">Description</span>
                </label>
                <textarea id="text-value" class="textarea textarea-bordered h-24"
                          placeholder="Entrez vos observations"></textarea>
            </div>
        `;
    }

    const referenceHtml = `
        <div class="card bg-base-200 mt-4">
            <div class="card-body p-4">
                <h4 class="card-title text-sm text-info">
                    <i class="fas fa-image mr-2"></i>Photo de référence
                </h4>
                ${point.photo_reference_url ? `
                    <img src="${point.photo_reference_url}" class="w-full max-h-64 object-cover rounded cursor-pointer"
                         alt="Photo de référence"
                         onclick="window.open('${point.photo_reference_url}', '_blank')">
                ` : `
                    <div class="bg-base-300 h-48 rounded flex items-center justify-center text-sm text-base-content/60">
                        <i class="fas fa-image-slash mr-2"></i>Aucune photo de référence
                    </div>
                `}
            </div>
        </div>
    `;

    const correctiveHtml = `
        <div id="express-corrective-section" class="mt-4 hidden">
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i>
                <div>
                    <div class="font-bold">Point non conforme - Action corrective</div>
                    <div class="text-sm">Définir l'activité et la date prévue.</div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Activité corrective</span>
                    </label>
                    <select id="express-corrective-activite" class="select select-bordered">
                        <option value="">Sélectionner une activité...</option>
                        <option value="maintenance">Maintenance préventive</option>
                        <option value="reparation">Réparation</option>
                        <option value="remplacement">Remplacement</option>
                        <option value="nettoyage">Nettoyage</option>
                        <option value="verification">Vérification technique</option>
                        <option value="autre">Autre</option>
                    </select>
                </div>

                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Date prévue</span>
                    </label>
                    <div class="join w-full">
                        <input type="text" id="express-corrective-date"
                               class="input input-bordered join-item flex-1"
                               value="${todayFr}"
                               readonly
                               data-date-value="${todayIso}">
                        <button type="button" class="btn btn-primary join-item"
                                onclick="openExpressAgendaModal()">
                            <i class="fas fa-calendar-alt mr-2"></i>
                            Choisir une date
                        </button>
                    </div>
                </div>
            </div>

            <div class="form-control mt-3">
                <label class="label">
                    <span class="label-text">Remarque</span>
                </label>
                <textarea id="express-corrective-remarque" class="textarea textarea-bordered"
                          placeholder="Détails supplémentaires sur l'action corrective..."></textarea>
            </div>
        </div>
    `;

    // Zone photo
    html += `
        <div class="form-control mt-4">
            <label class="label">
                <span class="label-text font-semibold">Photo (optionnel)</span>
            </label>
            <input type="file" id="photo-upload" accept="image/*" class="file-input file-input-bordered" />
            <div id="photo-preview" class="mt-2"></div>
        </div>
    `;

    html += referenceHtml;
    html += correctiveHtml;

    // Zone observations
    html += `
        <div class="form-control mt-4">
            <label class="label">
                <span class="label-text font-semibold">Observations (optionnel)</span>
            </label>
            <textarea id="observations" class="textarea textarea-bordered h-20"
                      placeholder="Commentaires supplémentaires"></textarea>
        </div>
    `;

    formContainer.innerHTML = html;

    // Gestionnaire pour la prévisualisation de photo
    const photoInput = document.getElementById('photo-upload');
    if (photoInput) {
        photoInput.addEventListener('change', handlePhotoPreview);
    }

    const boolInputs = document.querySelectorAll('input[name="bool-value"]');
    boolInputs.forEach((input) => {
        input.addEventListener('change', () => {
            toggleCorrectiveSection(input.value === 'false');
        });
    });
}

/**
 * Gère la prévisualisation de la photo
 * @param {Event} event - Événement de changement
 */
function handlePhotoPreview(event) {
    const file = event.target.files[0];
    const preview = document.getElementById('photo-preview');

    if (!file) {
        preview.innerHTML = '';
        return;
    }

    const reader = new FileReader();
    reader.onload = function(e) {
        preview.innerHTML = `
            <img src="${e.target.result}" class="max-w-xs rounded shadow" alt="Prévisualisation" />
        `;
    };
    reader.readAsDataURL(file);
}

/**
 * Récupère les données du formulaire
 * @returns {Object} Données du formulaire
 */
function getFormData() {
    const point = window.inspectionContext.selectedControlPoint;
    const data = {
        inspection_id: window.inspectionContext.inspectionId,
        point_link_id: point.id,
        point_id: point.point_id || null,
        observations: document.getElementById('observations')?.value || ''
    };

    // Valeur selon le type
    if (point.type === 'BOOL') {
        const selected = document.querySelector('input[name="bool-value"]:checked');
        if (!selected) {
            throw new Error('Veuillez sélectionner un état (Conforme/Non conforme)');
        }
        data.valeur_bool = selected.value === 'true';
    } else if (point.type === 'NUM') {
        const value = document.getElementById('numeric-value')?.value;
        if (!value || value.trim() === '') {
            throw new Error('Veuillez entrer une valeur numérique');
        }
        data.valeur_num = parseFloat(value);
    } else if (point.type === 'TEXT') {
        const value = document.getElementById('text-value')?.value;
        if (!value || value.trim() === '') {
            throw new Error('Veuillez entrer une description');
        }
        data.valeur_text = value;
    }

    if (point.type === 'BOOL') {
        const selected = document.querySelector('input[name="bool-value"]:checked');
        if (selected && selected.value === 'false') {
            const correctiveData = getCorrectiveActionData();
            if (correctiveData) {
                data.corrective_action = correctiveData;
            }
        }
    }

    // Photo (base64)
    const photoInput = document.getElementById('photo-upload');
    if (photoInput && photoInput.files.length > 0) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = function(e) {
                data.photo = e.target.result;
                resolve(data);
            };
            reader.onerror = reject;
            reader.readAsDataURL(photoInput.files[0]);
        });
    }

    return Promise.resolve(data);
}

/**
 * Enregistre le résultat et continue vers un autre point de contrôle
 */
async function saveAndContinue() {
    showLoader('Enregistrement...');

    try {
        const formData = await getFormData();
        await saveInspectionResult(formData);

        // Retourner à l'étape 2 (sélection d'un autre point)
        showStep(2);

        // Afficher un message de succès
        showToast('Point de contrôle enregistré avec succès', 'success');
    } catch (error) {
        console.error('Erreur lors de l\'enregistrement:', error);
        alert('Erreur: ' + error.message);
    } finally {
        hideLoader();
    }
}

/**
 * Enregistre le résultat et termine l'inspection
 */
async function saveAndFinish() {
    showLoader('Finalisation de l\'inspection...');

    try {
        const formData = await getFormData();
        await saveInspectionResult(formData);
        await finishInspectionExpress();

        // Fermer le modal
        document.getElementById('inspectionExpressModal').close();

        // Afficher un message de succès
        showToast('Inspection terminée avec succès', 'success');

        // Recharger la page pour voir les nouvelles données
        setTimeout(() => location.reload(), 1000);
    } catch (error) {
        console.error('Erreur lors de la finalisation:', error);
        alert('Erreur: ' + error.message);
        hideLoader();
    }
}

/**
 * Enregistre le résultat d'un point de contrôle
 * @param {Object} data - Données du formulaire
 */
async function saveInspectionResult(data) {
    const url = '/inspections/api/save-inspection-result/';

    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify(data)
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const result = await response.json();

    if (!result.success) {
        throw new Error(result.error || 'Erreur inconnue');
    }
}

/**
 * Termine l'inspection express
 */
async function finishInspectionExpress() {
    const url = '/inspections/api/finish-inspection-express/';

    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            inspection_id: window.inspectionContext.inspectionId
        })
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const result = await response.json();

    if (!result.success) {
        throw new Error(result.error || 'Erreur inconnue');
    }
}

/**
 * Ferme le modal d'inspection express
 */
function closeInspectionExpressModal() {
    document.getElementById('inspectionExpressModal').close();
}

/**
 * Affiche un loader avec un message
 * @param {String} message - Message à afficher
 */
function showLoader(message = 'Chargement...') {
    const loader = document.getElementById('inspection-express-loader');
    if (loader) {
        loader.querySelector('.loading-text').textContent = message;
        loader.classList.remove('hidden');
    }
}

/**
 * Masque le loader
 */
function hideLoader() {
    const loader = document.getElementById('inspection-express-loader');
    if (loader) {
        loader.classList.add('hidden');
    }
}

/**
 * Affiche un toast de notification
 * @param {String} message - Message à afficher
 * @param {String} type - Type de toast ('success', 'error', 'info')
 */
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    const colors = {
        success: 'alert-success',
        error: 'alert-error',
        info: 'alert-info'
    };

    toast.className = `alert ${colors[type]} fixed top-4 right-4 w-auto max-w-md z-50 shadow-lg`;
    toast.innerHTML = `
        <span>${message}</span>
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function setInspectionExpressDate(dateObj) {
    const target = document.getElementById('inspection-express-date');
    if (!target) return;
    if (!dateObj) {
        target.textContent = '';
        return;
    }
    const formatted = dateObj.toLocaleString('fr-FR');
    target.textContent = `Date d'inspection : ${formatted}`;
}

function toggleCorrectiveSection(show) {
    const section = document.getElementById('express-corrective-section');
    if (!section) return;
    if (show) {
        section.classList.remove('hidden');
    } else {
        section.classList.add('hidden');
    }
}

function resetCorrectiveSection() {
    const section = document.getElementById('express-corrective-section');
    if (!section) return;
    section.classList.add('hidden');
}

function getCorrectiveActionData() {
    const section = document.getElementById('express-corrective-section');
    if (!section || section.classList.contains('hidden')) {
        return null;
    }
    const dateInput = document.getElementById('express-corrective-date');
    return {
        activite: document.getElementById('express-corrective-activite')?.value || '',
        date_prevue: dateInput?.getAttribute('data-date-value') || '',
        remarque: document.getElementById('express-corrective-remarque')?.value || ''
    };
}

// Agenda planning (inspection express)
let expressEmployePlannings = {};
let expressJoursFeries = [];

async function openExpressAgendaModal() {
    const modal = document.getElementById('express-agenda-modal');
    if (!modal) return;
    modal.showModal();

    const employeId = getInspectionExpressEmployeId();
    if (!employeId) {
        showToast("Employé introuvable pour l'agenda.", 'error');
        return;
    }
    await loadExpressEmployeePlannings(employeId);
}

function getInspectionExpressEmployeId() {
    const container = document.getElementById('inspection-express-employe');
    if (container && container.dataset.employeId) {
        return container.dataset.employeId;
    }
    return window.inspectionExpressEmployeId || '';
}

async function loadExpressEmployeePlannings(employeId) {
    try {
        const response = await fetch(`/inspections/api/employe-plannings/${employeId}/`);
        if (!response.ok) {
            throw new Error('Erreur lors du chargement des plannings');
        }
        const data = await response.json();
        expressEmployePlannings = data.plannings_by_date;
        expressJoursFeries = data.jours_feries || [];
        displayExpressAgendaCalendar(data.today);
    } catch (error) {
        console.error('Erreur chargement plannings:', error);
        showToast("Erreur lors du chargement de l'agenda.", 'error');
    }
}

function displayExpressAgendaCalendar(todayStr) {
    const container = document.getElementById('express-agenda-calendar');
    if (!container) return;
    const today = new Date(todayStr);
    let html = '<div class="space-y-2">';

    for (let i = 0; i < 90; i++) {
        const date = new Date(today);
        date.setDate(date.getDate() + i);
        const dateStr = date.toISOString().split('T')[0];
        const dayData = expressEmployePlannings[dateStr];
        const plannings = dayData ? dayData.activites : [];
        const hasReparation = dayData ? dayData.has_reparation : false;

        const isToday = i === 0;
        const isWeekend = date.getDay() === 0 || date.getDay() === 6;
        const isHoliday = expressJoursFeries.includes(dateStr);

        let borderClass = '';
        if (isToday) borderClass = 'border-2 border-primary';
        else if (isHoliday) borderClass = 'border-2 border-warning';
        else if (isWeekend) borderClass = 'border-l-4 border-info';

        let statusBadges = '';
        if (isToday) {
            statusBadges += '<span class="badge badge-primary badge-sm gap-1"><i class="fas fa-star"></i>Aujourd\'hui</span>';
        }
        if (isHoliday) {
            statusBadges += '<span class="badge badge-warning badge-sm gap-1 ml-1"><i class="fas fa-star"></i>Férié</span>';
        }
        if (isWeekend && !isHoliday) {
            statusBadges += '<span class="badge badge-info badge-sm gap-1 ml-1"><i class="fas fa-mug-hot"></i>Week-end</span>';
        }
        if (hasReparation) {
            statusBadges += '<span class="badge badge-error badge-sm gap-1 ml-1"><i class="fas fa-wrench"></i>Occupé</span>';
        }

        html += `
            <div class="card bg-base-200 hover:bg-base-300 cursor-pointer transition ${borderClass}"
                 onclick="selectExpressAgendaDate('${dateStr}')">
                <div class="card-body p-3">
                    <div class="flex items-center justify-between">
                        <div class="flex-1">
                            <div class="flex items-center gap-2 mb-1">
                                <span class="font-semibold ${isToday ? 'text-primary' : isHoliday ? 'text-warning' : isWeekend ? 'text-info' : ''}">
                                    ${date.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })}
                                </span>
                            </div>
                            <div class="flex flex-wrap gap-1 mb-2">
                                ${statusBadges}
                            </div>
                            ${plannings.length > 0 ? `
                                <div class="text-sm text-base-content/70">
                                    <i class="fas fa-tasks mr-1"></i>
                                    ${plannings.length} activité${plannings.length > 1 ? 's' : ''} prévue${plannings.length > 1 ? 's' : ''}
                                </div>
                            ` : `
                                <div class="text-sm text-success/70">
                                    <i class="fas fa-check-circle mr-1"></i>
                                    Aucune activité prévue
                                </div>
                            `}
                        </div>
                        <button type="button" class="btn btn-sm btn-primary">
                            <i class="fas fa-check"></i>
                        </button>
                    </div>

                    ${plannings.length > 0 ? `
                        <div class="mt-2 space-y-1">
                            ${plannings.map(p => `
                                <div class="text-xs ${p.is_reparation ? 'bg-error/10 border border-error/20' : 'bg-base-300'} p-2 rounded flex items-center gap-2">
                                    <i class="fas ${p.is_reparation ? 'fa-wrench text-error' : 'fa-clock text-primary'}"></i>
                                    <span class="font-medium ${p.is_reparation ? 'text-error' : ''}">${p.activite_nom}</span>
                                    <span class="text-base-content/60">- ${p.ouvrage}</span>
                                    ${p.heure ? `<span class="badge badge-sm">${p.heure}</span>` : ''}
                                    ${p.is_reparation ? '<span class="badge badge-error badge-xs ml-auto">Réparation</span>' : ''}
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    html += '</div>';
    container.innerHTML = html;
}

function selectExpressAgendaDate(dateStr) {
    const date = new Date(dateStr);
    const frenchDate = date.toLocaleDateString('fr-FR');
    const dateInput = document.getElementById('express-corrective-date');
    if (dateInput) {
        dateInput.value = frenchDate;
        dateInput.setAttribute('data-date-value', dateStr);
    }
    closeExpressAgendaModal();
    showToast(`Date sélectionnée: ${frenchDate}`, 'success');
}

function closeExpressAgendaModal() {
    const modal = document.getElementById('express-agenda-modal');
    if (modal) {
        modal.close();
    }
}

/**
 * Récupère un cookie par son nom
 * @param {String} name - Nom du cookie
 * @returns {String} Valeur du cookie
 */
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
