
let employesData = [];
let paiementsData = [];

// Charger les paiements
async function loadPaiements() {
    try {
        const annee = document.getElementById('filter-annee').value;
        const mois = document.getElementById('filter-mois').value;
        const statut = document.getElementById('filter-statut').value;

        let url = '/api/paiements-irsa-list/?';
        if (annee) url += `annee=${annee}&`;
        if (mois) url += `mois=${mois}&`;
        if (statut && statut !== 'all') url += `statut=${statut}&`;

        const response = await fetch(url);
        const data = await response.json();

        if (data.success) {
            paiementsData = data.paiements;
            displayPaiements();
        } else {
            alert('Erreur: ' + data.error);
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
    }
}

function displayPaiements() {
    const tbody = document.getElementById('paiements-tbody');

    if (paiementsData.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center py-8 text-base-content/60">
                    <i class="fas fa-inbox text-4xl mb-2"></i>
                    <p>Aucun paiement IRSA trouvé</p>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = paiementsData.map(p => {
        const statutBadge = {
            'brouillon': 'badge-warning',
            'valide': 'badge-info',
            'paye': 'badge-success'
        }[p.statut] || 'badge-ghost';

        return `
            <tr>
                <td><span class="font-mono">${p.periode}</span></td>
                <td>${p.organisation}</td>
                <td>${formatDate(p.date_paiement)}</td>
                <td>${p.nb_employes}</td>
                <td class="text-right font-mono">${p.montant_total_irsa.toLocaleString('fr-FR')} Ar</td>
                <td><span class="badge ${statutBadge}">${p.statut_display}</span></td>
                <td>
                    ${p.facture_generee ?
                        `<span class="badge badge-success badge-sm"><i class="fas fa-check mr-1"></i>Générée</span>` :
                        `<span class="badge badge-ghost badge-sm"><i class="fas fa-times mr-1"></i>Non générée</span>`
                    }
                </td>
                <td>
                    ${p.facture_imprimee ?
                        `<span class="badge badge-success badge-sm"><i class="fas fa-print mr-1"></i>Imprimée</span>` :
                        `<span class="badge badge-ghost badge-sm"><i class="fas fa-times mr-1"></i>Non imprimée</span>`
                    }
                </td>
                <td class="text-center">
                    <div class="dropdown dropdown-end">
                        <label tabindex="0" class="btn btn-ghost btn-sm">
                            <i class="fas fa-ellipsis-v"></i>
                        </label>
                        <ul tabindex="0" class="dropdown-content z-[1] menu p-2 shadow bg-base-100 rounded-box w-52">
                            <li><a onclick="voirDetails('${p.id}')"><i class="fas fa-eye mr-2"></i>Voir détails</a></li>
                            <li><a onclick="genererFacture('${p.id}')"><i class="fas fa-file-excel mr-2"></i>Générer facture</a></li>
                            ${p.facture_generee && !p.facture_imprimee ? `
                                <li><a onclick="marquerImprime('${p.id}', ${p.mois}, ${p.annee})" class="text-success"><i class="fas fa-print mr-2"></i>Marquer imprimée + Export</a></li>
                            ` : ''}
                            ${p.statut === 'brouillon' ? `
                                <li><a onclick="validerPaiement('${p.id}')"><i class="fas fa-check mr-2"></i>Valider</a></li>
                                <li><a onclick="supprimerPaiement('${p.id}')" class="text-error"><i class="fas fa-trash mr-2"></i>Supprimer</a></li>
                            ` : ''}
                        </ul>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// Ouvrir modal de création
function openCreateModal() {
    // Réinitialiser
    document.getElementById('create-mois').value = '';
    document.getElementById('create-annee').value = new Date().getFullYear();
    document.getElementById('create-date-paiement').value = '';
    document.getElementById('step1-periode').classList.remove('hidden');
    document.getElementById('step2-employes').classList.add('hidden');
    employesData = [];

    document.getElementById('modal-create-paiement').showModal();
}

// Charger les employés
async function chargerEmployes() {
    const mois = document.getElementById('create-mois').value;
    const annee = document.getElementById('create-annee').value;
    const datePaiement = document.getElementById('create-date-paiement').value;

    if (!mois || !annee || !datePaiement) {
        alert('Veuillez remplir tous les champs obligatoires');
        return;
    }

    try {
        // Passer à l'étape 2
        document.getElementById('step1-periode').classList.add('hidden');
        document.getElementById('step2-employes').classList.remove('hidden');

        const response = await fetch(`/api/employes-irsa/?mois=${mois}&annee=${annee}`);
        const data = await response.json();

        if (data.success) {
            employesData = data.employes;
            displayEmployes();

            document.getElementById('alert-employes').innerHTML = `
                <strong>${data.total} employé(s)</strong> trouvé(s) avec salaire payé pour ${mois}/${annee}
            `;
        } else {
            alert('Erreur: ' + data.error);
            retourStep1();
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
        retourStep1();
    }
}

function displayEmployes() {
    const tbody = document.getElementById('employes-tbody');

    if (employesData.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-4 text-error">
                    <i class="fas fa-exclamation-triangle mr-2"></i>
                    Aucun employé avec salaire payé pour cette période
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = employesData.map((emp, idx) => `
        <tr>
            <td>
                <input type="checkbox" class="checkbox checkbox-sm employe-checkbox"
                       data-index="${idx}" checked onchange="updateTotals()">
            </td>
            <td>${emp.employe_fonction}</td>
            <td>${emp.employe_nom_complet}</td>
            <td class="text-right font-mono">${emp.salaire_brut.toLocaleString('fr-FR')}</td>
            <td class="text-right font-mono">${emp.base_imposable.toLocaleString('fr-FR')}</td>
            <td class="text-right font-mono">${emp.montant_irsa.toLocaleString('fr-FR')}</td>
        </tr>
    `).join('');

    // Tous cochés par défaut
    updateTotals();
}

function toggleAllEmployes() {
    const selectAll = document.getElementById('select-all-employes').checked;
    document.querySelectorAll('.employe-checkbox').forEach(cb => {
        cb.checked = selectAll;
    });
    updateTotals();
}

function updateTotals() {
    let totalBrut = 0;
    let totalBase = 0;
    let totalIrsa = 0;

    document.querySelectorAll('.employe-checkbox').forEach(cb => {
        if (cb.checked) {
            const idx = parseInt(cb.dataset.index);
            const emp = employesData[idx];
            totalBrut += emp.salaire_brut;
            totalBase += emp.base_imposable;
            totalIrsa += emp.montant_irsa;
        }
    });

    document.getElementById('total-salaire-brut').textContent = totalBrut.toLocaleString('fr-FR') + ' Ar';
    document.getElementById('total-base-imposable').textContent = totalBase.toLocaleString('fr-FR') + ' Ar';
    document.getElementById('total-irsa').textContent = totalIrsa.toLocaleString('fr-FR') + ' Ar';
}

function retourStep1() {
    document.getElementById('step2-employes').classList.add('hidden');
    document.getElementById('step1-periode').classList.remove('hidden');
}

async function creerPaiement() {
    const mois = document.getElementById('create-mois').value;
    const annee = document.getElementById('create-annee').value;
    const datePaiement = document.getElementById('create-date-paiement').value;

    // Récupérer les employés sélectionnés
    const employesSelectionnes = [];
    document.querySelectorAll('.employe-checkbox').forEach(cb => {
        if (cb.checked) {
            const idx = parseInt(cb.dataset.index);
            employesSelectionnes.push(employesData[idx]);
        }
    });

    if (employesSelectionnes.length === 0) {
        alert('Veuillez sélectionner au moins un employé');
        return;
    }

    if (!confirm(`Créer le paiement IRSA pour ${employesSelectionnes.length} employé(s) ?`)) {
        return;
    }

    document.getElementById('btn-creer-paiement').disabled = true;

    try {
        const response = await fetch('/api/creer-paiement-irsa/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                mois: parseInt(mois),
                annee: parseInt(annee),
                date_paiement: datePaiement,
                employes: employesSelectionnes
            })
        });

        const data = await response.json();

        if (data.success) {
            alert('✓ Paiement IRSA créé avec succès');
            document.getElementById('modal-create-paiement').close();
            loadPaiements();
        } else {
            alert('Erreur: ' + data.error);
            document.getElementById('btn-creer-paiement').disabled = false;
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
        document.getElementById('btn-creer-paiement').disabled = false;
    }
}

async function voirDetails(paiementId) {
    document.getElementById('modal-detail-paiement').showModal();

    try {
        const response = await fetch(`/api/paiement-irsa/${paiementId}/detail/`);
        const data = await response.json();

        if (data.success) {
            const p = data.paiement;

            document.getElementById('detail-content').innerHTML = `
                <div class="grid grid-cols-2 gap-4 mb-4">
                    <div class="stat bg-base-200 rounded-lg">
                        <div class="stat-title">Période</div>
                        <div class="stat-value text-2xl">${String(p.mois).padStart(2, '0')}/${p.annee}</div>
                    </div>
                    <div class="stat bg-base-200 rounded-lg">
                        <div class="stat-title">Date de paiement</div>
                        <div class="stat-value text-2xl">${formatDate(p.date_paiement)}</div>
                    </div>
                    <div class="stat bg-base-200 rounded-lg">
                        <div class="stat-title">Total IRSA</div>
                        <div class="stat-value text-2xl text-primary">${p.montant_total_irsa.toLocaleString('fr-FR')} Ar</div>
                    </div>
                    <div class="stat bg-base-200 rounded-lg">
                        <div class="stat-title">Statut</div>
                        <div class="stat-value text-2xl">
                            <span class="badge badge-lg ${p.statut === 'paye' ? 'badge-success' : p.statut === 'valide' ? 'badge-info' : 'badge-warning'}">
                                ${p.statut}
                            </span>
                        </div>
                    </div>
                </div>

                <div class="overflow-x-auto">
                    <table class="table table-sm table-zebra">
                        <thead>
                            <tr>
                                <th>Fonction</th>
                                <th>Nom complet</th>
                                <th class="text-right">Salaire brut</th>
                                <th class="text-right">Base imposable</th>
                                <th class="text-right">IRSA</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${p.details.map(d => `
                                <tr>
                                    <td>${d.employe_fonction}</td>
                                    <td>${d.employe_nom_complet}</td>
                                    <td class="text-right font-mono">${d.salaire_brut.toLocaleString('fr-FR')}</td>
                                    <td class="text-right font-mono">${d.base_imposable.toLocaleString('fr-FR')}</td>
                                    <td class="text-right font-mono">${d.montant_irsa.toLocaleString('fr-FR')}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                        <tfoot>
                            <tr class="font-bold">
                                <td colspan="2">TOTAL</td>
                                <td class="text-right">${p.montant_total_brut.toLocaleString('fr-FR')} Ar</td>
                                <td class="text-right">${p.montant_total_base_imposable.toLocaleString('fr-FR')} Ar</td>
                                <td class="text-right">${p.montant_total_irsa.toLocaleString('fr-FR')} Ar</td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            `;
        } else {
            document.getElementById('detail-content').innerHTML = `
                <div class="alert alert-error">
                    <i class="fas fa-exclamation-circle"></i>
                    <span>${data.error}</span>
                </div>
            `;
        }
    } catch (error) {
        console.error('Erreur:', error);
        document.getElementById('detail-content').innerHTML = `
            <div class="alert alert-error">
                <i class="fas fa-exclamation-circle"></i>
                <span>Erreur réseau: ${error.message}</span>
            </div>
        `;
    }
}

async function genererFacture(paiementId) {
    if (!confirm('Générer la facture Excel pour ce paiement IRSA ?')) {
        return;
    }

    try {
        window.location.href = `/paiement-irsa/${paiementId}/facture/`;

        // Recharger après 2 secondes
        setTimeout(() => loadPaiements(), 2000);
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur: ' + error.message);
    }
}

async function validerPaiement(paiementId) {
    if (!confirm('Valider ce paiement IRSA ? Cette action est irréversible.')) {
        return;
    }

    try {
        const response = await fetch(`/api/paiement-irsa/${paiementId}/valider/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();

        if (data.success) {
            alert('✓ Paiement validé avec succès');
            loadPaiements();
        } else {
            alert('Erreur: ' + data.error);
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
    }
}

async function supprimerPaiement(paiementId) {
    if (!confirm('⚠️ Supprimer ce paiement IRSA ? Cette action est irréversible.')) {
        return;
    }

    try {
        const response = await fetch(`/api/paiement-irsa/${paiementId}/supprimer/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();

        if (data.success) {
            alert('✓ Paiement supprimé avec succès');
            loadPaiements();
        } else {
            alert('Erreur: ' + data.error);
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
    }
}

async function marquerImprime(paiementId, mois, annee) {
    if (!confirm(`⚠️ Marquer la facture IRSA comme imprimée et exporter vers DiameX ?\n\n` +
                 `Cette action va :\n` +
                 `1. Marquer la facture comme imprimée (irréversible)\n` +
                 `2. Exporter toutes les lignes IRSA vers DiameXTemporaire\n\n` +
                 `Continuer ?`)) {
        return;
    }

    try {
        const response = await fetch('/api/marquer-irsa-imprime/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                paiement_ids: [paiementId],
                mois: mois,
                annee: annee
            })
        });

        const data = await response.json();

        if (data.success) {
            let message = `✓ ${data.message}`;

            if (data.erreurs && data.erreurs.length > 0) {
                message += '\n\n⚠️ Erreurs rencontrées :\n' + data.erreurs.join('\n');
            }

            alert(message);
            loadPaiements();
        } else {
            alert('Erreur: ' + data.error);
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau: ' + error.message);
    }
}

// Helpers
function formatDate(dateString) {
    if (!dateString) return '';
    const parts = dateString.split('-');
    if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateString;
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

// Charger au démarrage
document.addEventListener('DOMContentLoaded', function() {
    loadPaiements();
});
