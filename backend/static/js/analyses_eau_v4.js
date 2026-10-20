// ANALYSES EAU - VERSION 5 - Logique par Packs
// Date: 24 décembre 2025
// Logique: Pack = groupe d'analyses du même jour (date_analyse)
// Statut pack: Validé (témoin +), Problématique (coli sur équip/PE), Contaminé (coli sur bouteille)

console.log('='.repeat(60));
console.log('🚀 FICHIER JAVASCRIPT EXTERNE CHARGÉ - v5 (PACKS)');
console.log('Date chargement: ' + new Date().toISOString());
console.log('='.repeat(60));

let analysesData = [];
let packsData = {};  // Cache des données de packs par date

// Charger les analyses ET les stats de packs
async function loadAnalyses() {
    console.log('[INFO] loadAnalyses() appelée');
    const annee = document.getElementById('filter-annee').value;
    const commune = document.getElementById('filter-commune').value;
    const type = document.getElementById('filter-type').value;
    const resultat = document.getElementById('filter-resultat').value;
    const search = document.getElementById('filter-search').value;

    // Construire l'URL analyses - ROUTE CORRECTE
    let urlAnalyses = '/inspections/analyses-eau/api/list/?';
    if (annee) urlAnalyses += `annee=${annee}&`;
    if (commune !== 'all') urlAnalyses += `commune_id=${commune}&`;
    if (type) urlAnalyses += `type_prelevement=${type}&`;
    if (resultat) urlAnalyses += `resultat=${resultat}&`;
    if (search) urlAnalyses += `search=${encodeURIComponent(search)}&`;

    // Construire l'URL packs stats
    let urlPacks = '/inspections/analyses-eau/api/packs/stats/?';
    if (annee) urlPacks += `annee=${annee}&`;
    if (commune !== 'all') urlPacks += `commune_id=${commune}&`;

    console.log('[INFO] URL API Analyses:', urlAnalyses);
    console.log('[INFO] URL API Packs:', urlPacks);

    try {
        // Charger les deux APIs en parallèle
        const [responseAnalyses, responsePacks] = await Promise.all([
            fetch(urlAnalyses),
            fetch(urlPacks)
        ]);

        console.log('[INFO] Réponse Analyses status:', responseAnalyses.status);
        console.log('[INFO] Réponse Packs status:', responsePacks.status);

        if (!responseAnalyses.ok || !responsePacks.ok) {
            throw new Error(`Erreur HTTP Analyses:${responseAnalyses.status} Packs:${responsePacks.status}`);
        }

        const dataAnalyses = await responseAnalyses.json();
        const dataPacks = await responsePacks.json();

        console.log('[INFO] Analyses reçues:', dataAnalyses.success, 'total:', dataAnalyses.total);
        console.log('[INFO] Packs reçus:', dataPacks.success, 'packs:', dataPacks.packs?.length);

        if (dataAnalyses.success && dataPacks.success) {
            analysesData = dataAnalyses.data;

            // Créer un index des packs par date d'analyse
            packsData = {};
            dataPacks.packs.forEach(pack => {
                packsData[pack.date_analyse] = pack;
            });

            console.log('[INFO] Appel displayAnalyses avec', dataAnalyses.data.length, 'analyses');
            displayAnalyses(dataAnalyses.data);
            updatePacksStats(dataPacks.stats);
        } else {
            throw new Error(dataAnalyses.error || dataPacks.error || 'Erreur inconnue');
        }
    } catch (error) {
        console.error('[ERROR] Erreur détaillée:', error);
        alert(`Erreur lors du chargement des analyses: ${error.message}`);
    }
}

// Afficher les analyses avec statut du pack
function displayAnalyses(analyses) {
    console.log('[INFO] displayAnalyses() appelée avec', analyses.length, 'analyses');
    const tbody = document.getElementById('analyses-tbody');
    const noData = document.getElementById('no-data');

    if (!tbody) {
        console.error('[ERROR] Element analyses-tbody non trouvé');
        return;
    }

    if (!analyses || analyses.length === 0) {
        tbody.innerHTML = '';
        if (noData) noData.classList.remove('hidden');
        console.log('[INFO] Aucune analyse, affichage message "Aucune donnée"');
        return;
    }

    console.log('[INFO] Génération HTML pour', analyses.length, 'lignes');
    if (noData) noData.classList.add('hidden');

    try {
        tbody.innerHTML = analyses.map(a => {
            // Extraire la date d'analyse (sans heure) pour trouver le pack
            const dateAnalyseParts = a.date_analyse.split(' ')[0].split('/');  // DD/MM/YYYY
            const dateAnalyseISO = `${dateAnalyseParts[2]}-${dateAnalyseParts[1]}-${dateAnalyseParts[0]}`;  // YYYY-MM-DD

            const pack = packsData[dateAnalyseISO];
            let statutBadge = '';

            if (pack) {
                if (pack.statut === 'valide') {
                    statutBadge = '<span class="badge badge-success badge-xs">✅</span>';
                } else if (pack.statut === 'problematique') {
                    statutBadge = '<span class="badge badge-warning badge-xs">⚠️</span>';
                } else if (pack.statut === 'contamine') {
                    statutBadge = '<span class="badge badge-error badge-xs">❌</span>';
                } else {
                    statutBadge = '<span class="badge badge-ghost badge-xs">?</span>';
                }
            }

            return `
            <tr>
                <td class="text-center">${statutBadge}</td>
                <td><span class="badge badge-sm badge-outline">${a.type_prelevement_display || a.type_prelevement}</span></td>
                <td class="text-xs">${a.lieu || '-'}</td>
                <td class="text-xs">${a.commune || '-'}</td>
                <td class="text-xs">${a.village || '-'}</td>
                <td class="text-xs font-semibold text-primary">${a.date_analyse}</td>
                <td class="text-xs">${a.date_resultat}</td>
                <td class="text-center">${a.volume_analyse}</td>
                <td class="text-center">${a.tnc ? 'TNC' : (a.nombre_coliformes !== null ? a.nombre_coliformes : '-')}</td>
                <td class="text-center">
                    ${a.tnc ? '<span class="badge badge-warning badge-sm">TNC</span>' :
                      (a.nombre_pour_100ml !== null ?
                        (a.nombre_pour_100ml === 0 ? '<span class="badge badge-success badge-sm">0</span>' :
                         `<span class="badge badge-error badge-sm">${a.nombre_pour_100ml}</span>`) :
                      '-')}
                </td>
                <td class="text-center">${a.ph !== null ? a.ph.toFixed(1) : '-'}</td>
                <td>
                    <div class="flex gap-1">
                        <button data-action="edit" data-analyse-id="${a.id}" class="btn btn-xs btn-ghost" title="Modifier">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button data-action="delete" data-analyse-id="${a.id}" class="btn btn-xs btn-ghost text-error" title="Supprimer">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
            `;
        }).join('');
        console.log('[OK] HTML généré avec succès');
    } catch (error) {
        console.error('[ERROR] Erreur lors de la génération HTML:', error);
        tbody.innerHTML = '<tr><td colspan="12" class="text-center text-error">Erreur lors de l\'affichage des données</td></tr>';
    }
}

// Mettre à jour statistiques des PACKS (et non des analyses individuelles)
function updatePacksStats(stats) {
    console.log('[INFO] updatePacksStats() appelée avec:', stats);

    // Vérifications nulles avant mise à jour
    const statTotalPacks = document.getElementById('stat-total-packs');
    const statPacksValides = document.getElementById('stat-packs-valides');
    const statPacksProblematiques = document.getElementById('stat-packs-problematiques');
    const statPacksContamines = document.getElementById('stat-packs-contamines');
    const statTotalAnalyses = document.getElementById('stat-total-analyses');
    const statTotalAnalysesDesc = document.getElementById('stat-total-analyses-desc');

    if (statTotalPacks) statTotalPacks.textContent = stats.total_packs || 0;
    if (statPacksValides) statPacksValides.textContent = stats.packs_valides || 0;
    if (statPacksProblematiques) statPacksProblematiques.textContent = stats.packs_problematiques || 0;
    if (statPacksContamines) statPacksContamines.textContent = stats.packs_contamines || 0;
    if (statTotalAnalyses) statTotalAnalyses.textContent = stats.total_analyses || 0;
    if (statTotalAnalysesDesc) statTotalAnalysesDesc.textContent = `${stats.total_analyses || 0} analyses`;
}

// Réinitialiser filtres
function resetFilters() {
    document.getElementById('filter-annee').value = new Date().getFullYear();
    document.getElementById('filter-commune').value = 'all';
    document.getElementById('filter-type').value = '';
    document.getElementById('filter-resultat').value = '';
    document.getElementById('filter-search').value = '';
    loadAnalyses();
}

// ===== CRUD FUNCTIONS =====

// Toggle visibility of lieu fields based on type selection
function toggleLieuFields() {
    const typeElement = document.getElementById('type-prelevement');
    const type = typeElement ? typeElement.value : '';

    console.log('[DEBUG] toggleLieuFields() - type:', type);

    const fieldEquipement = document.getElementById('field-equipement');
    const fieldPointEau = document.getElementById('field-point-eau');
    const fieldDescription = document.getElementById('field-description');

    if (fieldEquipement) {
        fieldEquipement.style.display = type === 'equipement' ? 'block' : 'none';
        console.log('[DEBUG] field-equipement display:', fieldEquipement.style.display);
    } else {
        console.error('[ERROR] Element field-equipement non trouvé');
    }

    if (fieldPointEau) {
        fieldPointEau.style.display = type === 'point_eau' ? 'block' : 'none';
        console.log('[DEBUG] field-point-eau display:', fieldPointEau.style.display);
    } else {
        console.error('[ERROR] Element field-point-eau non trouvé');
    }

    if (fieldDescription) {
        fieldDescription.style.display = (type === 'point_eau_traditionnel' || type === 'bouteille' || type === 'autre') ? 'block' : 'none';
        console.log('[DEBUG] field-description display:', fieldDescription.style.display);
    } else {
        console.error('[ERROR] Element field-description non trouvé');
    }
}

// Open modal for creating new analysis
function openCreateModal() {
    console.log('[INFO] openCreateModal() appelée');

    // Reset form completely
    const form = document.getElementById('form-analyse');
    if (form) {
        form.reset();
    }

    document.getElementById('analyse-id').value = '';
    document.getElementById('modal-title').textContent = 'Nouvelle analyse';

    // Reset cascade filters for equipements
    document.getElementById('equipement-commune').value = '';
    document.getElementById('equipement-ouvrage').innerHTML = '<option value="">Tous les ouvrages</option>';
    document.getElementById('equipement-id').innerHTML = '<option value="">Sélectionner un équipement...</option>';

    // Reset cascade filters for points d'eau
    document.getElementById('pointeau-commune').value = '';
    document.getElementById('pointeau-ouvrage').innerHTML = '<option value="">Tous les ouvrages</option>';
    document.getElementById('point-eau-id').innerHTML = '<option value="">Sélectionner un point d\'eau...</option>';

    // Reset description
    document.getElementById('description-lieu').value = '';

    // Hide all conditional fields
    toggleLieuFields();

    // Reinitialize cascade data (call template functions if they exist)
    // IMPORTANT: Appeler filterOuvrages* AVANT filterEquipements/filterPointsEau
    if (typeof filterOuvragesEquipement === 'function') {
        filterOuvragesEquipement();  // Peuple la liste des ouvrages pour équipements
    }
    if (typeof filterEquipements === 'function') {
        filterEquipements();  // Peuple la liste des équipements
    }
    if (typeof filterOuvragesPointEau === 'function') {
        filterOuvragesPointEau();  // Peuple la liste des ouvrages pour points d'eau
    }
    if (typeof filterPointsEau === 'function') {
        filterPointsEau();  // Peuple la liste des points d'eau
    }

    // Attach event listeners for cascade filters (replaces inline onchange)
    if (typeof window.attachCascadeListeners === 'function') {
        window.attachCascadeListeners();
    }

    // Open modal
    document.getElementById('modal-form').showModal();
}

// Close modal
function closeModal() {
    document.getElementById('modal-form').close();
}

// Convert DD/MM/YYYY HH:MM to YYYY-MM-DDTHH:MM for datetime-local input
function convertToDatetimeLocal(dateStr) {
    if (!dateStr) return '';

    // Format: "DD/MM/YYYY HH:MM"
    const parts = dateStr.split(' ');
    if (parts.length !== 2) return '';

    const dateParts = parts[0].split('/');
    if (dateParts.length !== 3) return '';

    // Return YYYY-MM-DDTHH:MM
    return `${dateParts[2]}-${dateParts[1]}-${dateParts[0]}T${parts[1]}`;
}

// Edit existing analysis
async function editAnalyse(analyseId) {
    console.log('[INFO] editAnalyse() appelée avec ID:', analyseId);
    try {
        const response = await fetch(`/inspections/analyses-eau/api/${analyseId}/`);
        const data = await response.json();

        if (data.success) {
            const analyse = data.analyse;

            // Reset form completely FIRST to clear previous values
            const form = document.getElementById('form-analyse');
            if (form) {
                form.reset();
            }

            // Set form mode and ID
            document.getElementById('analyse-id').value = analyse.id;
            document.getElementById('modal-title').textContent = 'Modifier analyse';

            // Set type and show appropriate fields
            document.getElementById('type-prelevement').value = analyse.type_prelevement;
            toggleLieuFields();

            // Charger les données en cascade selon le type
            if (analyse.type_prelevement === 'equipement' && analyse.equipement_constitutif_id) {
                // L'API retourne déjà commune_id et ouvrage_id
                if (analyse.commune_id) {
                    // 1. Sélectionner la commune
                    document.getElementById('equipement-commune').value = analyse.commune_id;

                    // 2. Charger les ouvrages de cette commune
                    await loadOuvragesForEquipement();

                    // 3. Sélectionner l'ouvrage
                    if (analyse.ouvrage_id) {
                        document.getElementById('equipement-ouvrage').value = analyse.ouvrage_id;

                        // 4. Charger les équipements de cet ouvrage
                        await loadEquipements();

                        // 5. Sélectionner l'équipement
                        document.getElementById('equipement-id').value = analyse.equipement_constitutif_id;
                    }
                }
            } else if (analyse.type_prelevement === 'point_eau' && analyse.point_eau_id) {
                // L'API retourne déjà commune_id et ouvrage_id
                if (analyse.commune_id) {
                    // 1. Sélectionner la commune
                    document.getElementById('pointeau-commune').value = analyse.commune_id;

                    // 2. Charger les ouvrages de cette commune
                    await loadOuvragesForPointEau();

                    // 3. Sélectionner l'ouvrage
                    if (analyse.ouvrage_id) {
                        document.getElementById('pointeau-ouvrage').value = analyse.ouvrage_id;

                        // 4. Charger les points d'eau de cet ouvrage
                        await loadPointsEau();

                        // 5. Sélectionner le point d'eau
                        document.getElementById('point-eau-id').value = analyse.point_eau_id;
                    }
                }
            } else if (analyse.description_lieu) {
                // Pour les autres types (traditionnel, bouteille, autre)
                document.getElementById('description-lieu').value = analyse.description_lieu;
            }

            // Fill dates (convert to datetime-local format YYYY-MM-DDTHH:MM)
            document.getElementById('date-prelevement').value = convertToDatetimeLocal(analyse.date_prelevement);
            document.getElementById('date-analyse').value = convertToDatetimeLocal(analyse.date_analyse);
            document.getElementById('date-resultat').value = convertToDatetimeLocal(analyse.date_resultat);

            // Fill analysis fields
            document.getElementById('volume-analyse').value = analyse.volume_analyse;
            if (analyse.nombre_coliformes !== null) {
                document.getElementById('nombre-coliformes').value = analyse.nombre_coliformes;
            } else {
                document.getElementById('nombre-coliformes').value = '';
            }
            document.getElementById('tnc').checked = analyse.tnc || false;
            if (analyse.ph !== null) {
                document.getElementById('ph').value = analyse.ph;
            } else {
                document.getElementById('ph').value = '';
            }
            if (analyse.observation) {
                document.getElementById('observation').value = analyse.observation;
            } else {
                document.getElementById('observation').value = '';
            }

            // Open modal
            document.getElementById('modal-form').showModal();
        }
    } catch (error) {
        console.error('[ERROR] Erreur chargement analyse:', error);
        alert('Erreur lors du chargement de l\'analyse');
    }
}

// Delete analysis
async function deleteAnalyse(analyseId, lieu) {
    console.log('[INFO] deleteAnalyse() appelée avec ID:', analyseId, 'lieu:', lieu);
    if (!confirm(`Supprimer l'analyse "${lieu}" ?\n\nCette action est irréversible.`)) {
        return;
    }

    try {
        const response = await fetch(`/inspections/analyses-eau/api/${analyseId}/delete/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();

        if (data.success) {
            alert('Analyse supprimée avec succès');
            loadAnalyses(); // Reload list
        } else {
            alert('Erreur: ' + (data.error || 'Erreur inconnue'));
        }
    } catch (error) {
        console.error('[ERROR] Erreur suppression:', error);
        alert('Erreur lors de la suppression');
    }
}

// Export Excel
function exportExcel() {
    console.log('[INFO] exportExcel() appelée');
    const annee = document.getElementById('filter-annee').value;
    const commune = document.getElementById('filter-commune').value;

    let url = '/inspections/analyses-eau/export-excel/?';
    if (annee) url += `annee=${annee}&`;
    if (commune !== 'all') url += `commune_id=${commune}&`;

    window.location.href = url;
}

// Open import modal
function openImportModal() {
    console.log('[INFO] openImportModal() appelée');
    // Reset le formulaire
    const form = document.getElementById('form-import');
    if (form) {
        form.reset();
    }
    // Masquer progression et résultats
    document.getElementById('import-progress').classList.add('hidden');
    document.getElementById('import-result').classList.add('hidden');
    // Ouvrir modal
    document.getElementById('modal-import').showModal();
}

// Close import modal
function closeImportModal() {
    document.getElementById('modal-import').close();
    const form = document.getElementById('form-import');
    if (form) {
        form.reset();
    }
    document.getElementById('import-progress').classList.add('hidden');
    document.getElementById('import-result').classList.add('hidden');
}

// Helper function to get CSRF cookie
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

// ===== EVENT LISTENERS =====
// Event delegation pour boutons edit/delete

// Charger les ouvrages selon la commune sélectionnée (pour équipements)
async function loadOuvragesForEquipement() {
    const communeId = document.getElementById('equipement-commune').value;
    const ouvrageSelect = document.getElementById('equipement-ouvrage');

    ouvrageSelect.innerHTML = '<option value="">Tous les ouvrages</option>';

    if (!communeId) {
        // Charger tous les ouvrages
        await loadEquipements();
        return;
    }

    try {
        const response = await fetch(`/inspections/analyses-eau/api/ouvrages/?commune_id=${communeId}`);
        const data = await response.json();

        if (data.success && data.ouvrages) {
            data.ouvrages.forEach(ouvrage => {
                const option = document.createElement('option');
                option.value = ouvrage.id;
                option.textContent = ouvrage.nom_ouvrage;
                ouvrageSelect.appendChild(option);
            });
        }

        // Charger les équipements après avoir chargé les ouvrages
        await loadEquipements();
    } catch (error) {
        console.error('[ERROR] Erreur chargement ouvrages:', error);
    }
}

// Charger les équipements selon l'ouvrage sélectionné
async function loadEquipements() {
    const ouvrageId = document.getElementById('equipement-ouvrage').value;
    const equipementSelect = document.getElementById('equipement-id');

    equipementSelect.innerHTML = '<option value="">Sélectionner un équipement...</option>';

    if (!ouvrageId) return;

    try {
        const response = await fetch(`/inspections/analyses-eau/api/equipements/?ouvrage_id=${ouvrageId}`);
        const data = await response.json();

        if (data.success && data.equipements) {
            data.equipements.forEach(equipement => {
                const option = document.createElement('option');
                option.value = equipement.id;
                option.textContent = equipement.nom || equipement.type;
                equipementSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('[ERROR] Erreur chargement équipements:', error);
    }
}

// Charger les ouvrages pour point d'eau
async function loadOuvragesForPointEau() {
    const communeId = document.getElementById('pointeau-commune').value;
    const ouvrageSelect = document.getElementById('pointeau-ouvrage');

    ouvrageSelect.innerHTML = '<option value="">Tous les ouvrages</option>';

    if (!communeId) {
        await loadPointsEau();
        return;
    }

    try {
        const response = await fetch(`/inspections/analyses-eau/api/ouvrages/?commune_id=${communeId}`);
        const data = await response.json();

        if (data.success && data.ouvrages) {
            data.ouvrages.forEach(ouvrage => {
                const option = document.createElement('option');
                option.value = ouvrage.id;
                option.textContent = ouvrage.nom_ouvrage;
                ouvrageSelect.appendChild(option);
            });
        }

        await loadPointsEau();
    } catch (error) {
        console.error('[ERROR] Erreur chargement ouvrages PE:', error);
    }
}

// Charger les points d'eau selon l'ouvrage sélectionné
async function loadPointsEau() {
    const ouvrageId = document.getElementById('pointeau-ouvrage').value;
    const pointEauSelect = document.getElementById('point-eau-id');

    pointEauSelect.innerHTML = '<option value="">Sélectionner un point d\'eau...</option>';

    if (!ouvrageId) return;

    try {
        const response = await fetch(`/inspections/analyses-eau/api/points-eau/?ouvrage_id=${ouvrageId}`);
        const data = await response.json();

        if (data.success && data.points_eau) {
            data.points_eau.forEach(pe => {
                const option = document.createElement('option');
                option.value = pe.id;
                option.textContent = pe.nom || pe.type;
                pointEauSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('[ERROR] Erreur chargement points d\'eau:', error);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('[INFO] DOMContentLoaded - Initialisation v5 avec CRUD complet');

    loadAnalyses();

    // Event listener pour changement de type de prélèvement
    const typePrelevement = document.getElementById('type-prelevement');
    if (typePrelevement) {
        typePrelevement.addEventListener('change', toggleLieuFields);
        console.log('[OK] Event listener type-prelevement attaché');
    }

    // Event listeners pour cascade commune → ouvrage → équipement
    const equipementCommune = document.getElementById('equipement-commune');
    if (equipementCommune) {
        equipementCommune.addEventListener('change', loadOuvragesForEquipement);
        console.log('[OK] Event listener equipement-commune attaché');
    }

    const equipementOuvrage = document.getElementById('equipement-ouvrage');
    if (equipementOuvrage) {
        equipementOuvrage.addEventListener('change', loadEquipements);
        console.log('[OK] Event listener equipement-ouvrage attaché');
    }

    // Event listeners pour cascade commune → ouvrage → point d'eau
    const pointeauCommune = document.getElementById('pointeau-commune');
    if (pointeauCommune) {
        pointeauCommune.addEventListener('change', loadOuvragesForPointEau);
        console.log('[OK] Event listener pointeau-commune attaché');
    }

    const pointeauOuvrage = document.getElementById('pointeau-ouvrage');
    if (pointeauOuvrage) {
        pointeauOuvrage.addEventListener('change', loadPointsEau);
        console.log('[OK] Event listener pointeau-ouvrage attaché');
    }

    // Attach button click handlers
    const btnCreate = document.getElementById('btn-create');
    if (btnCreate) {
        btnCreate.addEventListener('click', openCreateModal);
        console.log('[OK] Event listener btn-create attaché');
    } else {
        console.error('[ERROR] Element btn-create non trouvé');
    }

    const btnImport = document.getElementById('btn-import');
    if (btnImport) {
        btnImport.addEventListener('click', openImportModal);
        console.log('[OK] Event listener btn-import attaché');
    }

    const btnExport = document.getElementById('btn-export');
    if (btnExport) {
        btnExport.addEventListener('click', exportExcel);
        console.log('[OK] Event listener btn-export attaché');
    }

    const btnFilter = document.getElementById('btn-filter');
    if (btnFilter) {
        btnFilter.addEventListener('click', loadAnalyses);
        console.log('[OK] Event listener btn-filter attaché');
    }

    const btnReset = document.getElementById('btn-reset');
    if (btnReset) {
        btnReset.addEventListener('click', resetFilters);
        console.log('[OK] Event listener btn-reset attaché');
    }

    const btnDeleteAll = document.getElementById('btn-delete-all');
    if (btnDeleteAll) {
        btnDeleteAll.addEventListener('click', async function() {
            if (!confirm('⚠️ ATTENTION : Vous êtes sur le point de supprimer TOUTES les analyses d\'eau.\n\nCette action est IRRÉVERSIBLE.\n\nÊtes-vous absolument certain de vouloir continuer ?')) {
                return;
            }

            // Deuxième confirmation pour sécurité
            try {
                const countResponse = await fetch('/inspections/analyses-eau/api/list/');
                const countData = await countResponse.json();
                const totalAnalyses = countData.data ? countData.data.length : 0;

                if (!confirm(`Vous allez supprimer ${totalAnalyses} analyse(s).\n\nDernière confirmation : Continuer ?`)) {
                    return;
                }

                const response = await fetch('/inspections/analyses-eau/api/delete-all/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken')
                    }
                });

                const data = await response.json();

                if (data.success) {
                    alert('✓ ' + data.message);
                    loadAnalyses(); // Recharger la liste (vide maintenant)
                } else {
                    alert('Erreur: ' + (data.error || 'Erreur inconnue'));
                }
            } catch (error) {
                console.error('[ERROR] Erreur suppression totale:', error);
                alert('Erreur lors de la suppression');
            }
        });
        console.log('[OK] Event listener btn-delete-all attaché');
    } else {
        console.error('[ERROR] Bouton btn-delete-all non trouvé');
    }

    const btnCancelModal = document.getElementById('btn-cancel-modal');
    if (btnCancelModal) {
        btnCancelModal.addEventListener('click', closeModal);
        console.log('[OK] Event listener btn-cancel-modal attaché');
    }

    // Gestionnaire de soumission du formulaire d'import
    const formImport = document.getElementById('form-import');
    if (formImport) {
        formImport.addEventListener('submit', async function(e) {
            e.preventDefault();
            console.log('[INFO] Form import submission');

            const fileInput = document.getElementById('file-import');
            const file = fileInput.files[0];

            if (!file) {
                alert('Veuillez sélectionner un fichier');
                return;
            }

            // Afficher progression
            const progressDiv = document.getElementById('import-progress');
            const resultDiv = document.getElementById('import-result');
            progressDiv.classList.remove('hidden');
            resultDiv.classList.add('hidden');

            // Créer FormData
            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch('/inspections/analyses-eau/import/', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken')
                    }
                });

                const data = await response.json();

                // Masquer progression
                progressDiv.classList.add('hidden');

                if (data.success) {
                    resultDiv.innerHTML = `
                        <div class="alert alert-success">
                            <i class="fas fa-check-circle mr-2"></i>
                            ${data.nb_imported} analyse(s) importée(s)
                            ${data.nb_errors > 0 ? '<br>⚠️ ' + data.nb_errors + ' erreur(s)' : ''}
                        </div>
                    `;
                    resultDiv.classList.remove('hidden');

                    // Afficher les erreurs si présentes
                    if (data.errors && data.errors.length > 0) {
                        resultDiv.innerHTML += '<div class="mt-2 text-xs"><strong>Erreurs:</strong><ul class="list-disc ml-5">';
                        data.errors.forEach(err => {
                            resultDiv.innerHTML += `<li>${err}</li>`;
                        });
                        resultDiv.innerHTML += '</ul></div>';
                    }

                    // Recharger la liste après 2 secondes
                    setTimeout(() => {
                        closeImportModal();
                        loadAnalyses();
                    }, 2000);
                } else {
                    resultDiv.innerHTML = `
                        <div class="alert alert-error">
                            <i class="fas fa-times-circle mr-2"></i>
                            Erreur: ${data.error || 'Erreur inconnue'}
                        </div>
                    `;
                    resultDiv.classList.remove('hidden');
                }
            } catch (error) {
                console.error('[ERROR] Erreur import:', error);
                progressDiv.classList.add('hidden');
                resultDiv.innerHTML = `
                    <div class="alert alert-error">
                        <i class="fas fa-times-circle mr-2"></i>
                        Erreur lors de l\'import
                    </div>
                `;
                resultDiv.classList.remove('hidden');
            }
        });
        console.log('[OK] Form import submission handler attaché');
    } else {
        console.error('[ERROR] Formulaire form-import non trouvé');
    }

    // Event delegation pour boutons edit/delete dans le tableau
    const tbody = document.getElementById('analyses-tbody');
    if (tbody) {
        tbody.addEventListener('click', (e) => {
            const button = e.target.closest('[data-action]');
            if (!button) return;

            const action = button.dataset.action;
            const analyseId = button.dataset.analyseId;

            if (action === 'edit') {
                editAnalyse(analyseId);
            } else if (action === 'delete') {
                const analyse = analysesData.find(a => a.id === analyseId);
                const lieu = analyse ? (analyse.lieu || 'cette analyse') : 'cette analyse';
                deleteAnalyse(analyseId, lieu);
            }
        });
        console.log('[OK] Event delegation tbody attachée');
    }
});

console.log('[OK] Fichier analyses_eau_v4.js chargé complètement - VERSION PACKS avec CRUD');
