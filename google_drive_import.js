/**
 * Module JavaScript pour l'import DiameX depuis Google Drive
 */

// État global
let googleDriveState = {
    selectedBase: null,
    currentFolderId: null,
    selectedFileId: null,
    breadcrumb: []
};

/**
 * Charge la liste des bases Google Drive disponibles
 */
async function loadGoogleDriveBases() {
    try {
        const response = await fetch('/comptabilite/api/google-drive/bases/');
        const data = await response.json();

        if (data.success) {
            displayGoogleDriveBases(data.bases);
        } else {
            showError('Erreur lors du chargement des bases Google Drive: ' + data.error);
        }
    } catch (error) {
        showError('Erreur réseau: ' + error.message);
    }
}

/**
 * Affiche la liste des bases Google Drive
 */
function displayGoogleDriveBases(bases) {
    const container = document.getElementById('googleDriveBasesContainer');

    if (!bases || bases.length === 0) {
        container.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i>
                <div>
                    <h3 class="font-bold">Aucune base Google Drive configurée</h3>
                    <p class="text-sm">Aucune base n'a Google Drive activé.</p>
                </div>
            </div>
        `;
        return;
    }

    let html = '<div class="space-y-3">';
    bases.forEach(base => {
        html += `
            <div class="card bg-base-200 hover:bg-base-300 cursor-pointer" onclick="selectGoogleDriveBase('${base.id}', '${base.folder_id}', '${base.nom}')">
                <div class="card-body p-4">
                    <div class="flex items-center gap-3">
                        <i class="fas fa-google-drive text-3xl text-info"></i>
                        <div class="flex-1">
                            <h4 class="font-semibold">${base.nom}</h4>
                            <p class="text-xs text-gray-500">${base.organisation}</p>
                            <p class="text-xs text-gray-600 mt-1">
                                <i class="fas fa-folder mr-1"></i>${base.folder_path || 'Chemin non défini'}
                            </p>
                        </div>
                        <i class="fas fa-chevron-right text-gray-400"></i>
                    </div>
                </div>
            </div>
        `;
    });
    html += '</div>';

    container.innerHTML = html;
}

/**
 * Sélectionne une base Google Drive et charge sa structure
 */
async function selectGoogleDriveBase(baseId, folderId, baseName) {
    googleDriveState.selectedBase = {
        id: baseId,
        name: baseName
    };
    googleDriveState.currentFolderId = folderId;
    googleDriveState.breadcrumb = [{ name: baseName, id: folderId }];

    // Afficher le conteneur de navigation
    document.getElementById('googleDriveBasesContainer').classList.add('hidden');
    document.getElementById('googleDriveBrowserContainer').classList.remove('hidden');

    // Charger la structure du dossier
    await loadGoogleDriveStructure(baseId);
}

/**
 * Charge la structure complète d'une base (03 COMPTA, .accde, scan)
 */
async function loadGoogleDriveStructure(baseId) {
    try {
        showLoading('Chargement de la structure Google Drive...');

        const response = await fetch(`/comptabilite/api/google-drive/structure/?base_id=${baseId}`);
        const data = await response.json();

        hideLoading();

        if (data.success) {
            displayGoogleDriveStructure(data.structure);
        } else {
            showError('Erreur: ' + data.error);
        }
    } catch (error) {
        hideLoading();
        showError('Erreur réseau: ' + error.message);
    }
}

/**
 * Affiche la structure du dossier Google Drive
 */
function displayGoogleDriveStructure(structure) {
    const container = document.getElementById('googleDriveFilesContainer');

    let html = '<div class="space-y-4">';

    // Afficher le breadcrumb
    html += '<div class="breadcrumbs text-sm">';
    html += '<ul>';
    googleDriveState.breadcrumb.forEach((item, index) => {
        if (index === googleDriveState.breadcrumb.length - 1) {
            html += `<li class="font-bold">${item.name}</li>`;
        } else {
            html += `<li><a onclick="navigateToBreadcrumb(${index})">${item.name}</a></li>`;
        }
    });
    html += '</ul>';
    html += '</div>';

    // Dossier 03 COMPTA
    if (structure.compta_folder) {
        html += `
            <div class="card bg-base-200">
                <div class="card-body p-4">
                    <h4 class="font-semibold mb-3">
                        <i class="fas fa-folder text-warning mr-2"></i>${structure.compta_folder.name}
                    </h4>
        `;

        // Fichier .accde
        if (structure.accde_file) {
            const file = structure.accde_file;
            const fileSize = file.size ? (parseInt(file.size) / (1024 * 1024)).toFixed(2) + ' MB' : 'N/A';
            html += `
                <div class="flex items-center gap-3 p-3 bg-base-100 rounded cursor-pointer hover:bg-base-300"
                     onclick="selectGoogleDriveFile('${file.id}', '${file.name}')">
                    <i class="fas fa-file-excel text-2xl text-success"></i>
                    <div class="flex-1">
                        <p class="font-semibold">${file.name}</p>
                        <p class="text-xs text-gray-500">${fileSize}</p>
                    </div>
                    <button class="btn btn-sm btn-primary">
                        <i class="fas fa-download mr-1"></i>Sélectionner
                    </button>
                </div>
            `;
        }

        // Dossier scan
        if (structure.scan_folder) {
            html += `
                <div class="mt-3 p-3 bg-base-100 rounded">
                    <p class="text-sm text-gray-600">
                        <i class="fas fa-folder text-info mr-2"></i>
                        Dossier scan détecté: ${structure.scan_folder.name}
                    </p>
                </div>
            `;
        }

        html += '</div></div>';
    }

    html += '</div>';

    container.innerHTML = html;
}

/**
 * Sélectionne un fichier Google Drive pour l'import
 */
function selectGoogleDriveFile(fileId, fileName) {
    googleDriveState.selectedFileId = fileId;

    // Afficher une confirmation
    const confirmHtml = `
        <div class="alert alert-success">
            <i class="fas fa-check-circle"></i>
            <div>
                <h4 class="font-bold">Fichier sélectionné</h4>
                <p class="text-sm">${fileName}</p>
            </div>
        </div>
    `;

    document.getElementById('googleDriveSelectionContainer').innerHTML = confirmHtml;
    document.getElementById('googleDriveSelectionContainer').classList.remove('hidden');

    // Activer le bouton d'import
    document.getElementById('importFromGoogleDriveBtn').disabled = false;
}

/**
 * Lance l'import depuis Google Drive
 */
async function importFromGoogleDrive() {
    if (!googleDriveState.selectedBase || !googleDriveState.selectedFileId) {
        alert('Veuillez sélectionner une base et un fichier');
        return;
    }

    const confirmMsg = `Voulez-vous vraiment importer ce fichier depuis Google Drive ?\n\nBase: ${googleDriveState.selectedBase.name}`;

    if (!confirm(confirmMsg)) {
        return;
    }

    try {
        showLoading('Import en cours depuis Google Drive...');

        const response = await fetch('/comptabilite/api/google-drive/import/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                base_id: googleDriveState.selectedBase.id,
                file_id: googleDriveState.selectedFileId,
                import_type: 'DATA'
            })
        });

        const data = await response.json();

        hideLoading();

        if (data.success) {
            showSuccess('Fichier téléchargé avec succès: ' + data.file_name);

            // Recharger la page après 2 secondes
            setTimeout(() => {
                location.reload();
            }, 2000);
        } else {
            showError('Erreur: ' + data.error);
        }
    } catch (error) {
        hideLoading();
        showError('Erreur réseau: ' + error.message);
    }
}

/**
 * Retour à la liste des bases
 */
function backToGoogleDriveBases() {
    googleDriveState.selectedBase = null;
    googleDriveState.currentFolderId = null;
    googleDriveState.selectedFileId = null;
    googleDriveState.breadcrumb = [];

    document.getElementById('googleDriveBasesContainer').classList.remove('hidden');
    document.getElementById('googleDriveBrowserContainer').classList.add('hidden');
    document.getElementById('googleDriveSelectionContainer').classList.add('hidden');
    document.getElementById('importFromGoogleDriveBtn').disabled = true;

    loadGoogleDriveBases();
}

/**
 * Fonctions utilitaires
 */
function showLoading(message) {
    const loadingEl = document.getElementById('googleDriveLoading');
    if (loadingEl) {
        loadingEl.querySelector('.loading-text').textContent = message;
        loadingEl.classList.remove('hidden');
    }
}

function hideLoading() {
    const loadingEl = document.getElementById('googleDriveLoading');
    if (loadingEl) {
        loadingEl.classList.add('hidden');
    }
}

function showError(message) {
    alert('Erreur: ' + message);
}

function showSuccess(message) {
    alert('Succès: ' + message);
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

// Ouvrir le modal Google Drive
function openGoogleDriveModal() {
    document.getElementById('googleDriveModal').showModal();
    loadGoogleDriveBases();
}

function closeGoogleDriveModal() {
    document.getElementById('googleDriveModal').close();
    backToGoogleDriveBases();
}