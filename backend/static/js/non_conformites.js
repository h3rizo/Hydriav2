/**
 * Gestion des non-conformités lors des inspections
 * Permet de saisir un narratif détaillé, une solution, et de planifier les actions correctives
 */

// État global
let currentResultatId = null;
let materiaux = [];

/**
 * Ouvre le modal de saisie de non-conformité
 * @param {string} resultatId - ID du ResultatInspectionComposant
 * @param {string} pointControleNom - Nom du point de contrôle non conforme
 */
function ouvrirModalNonConformite(resultatId, pointControleNom) {
    currentResultatId = resultatId;
    materiaux = [];

    // Réinitialiser le formulaire
    document.getElementById('nc-point-controle-nom').textContent = pointControleNom;
    document.getElementById('nc-narratif-probleme').value = '';
    document.getElementById('nc-solution-detaillee').value = '';
    document.getElementById('nc-besoin-superviseur').checked = false;
    document.getElementById('nc-niveau-solution').value = 'mpikojakoja';
    document.getElementById('nc-priorite').value = 'moyenne';
    document.getElementById('nc-echeance').value = '3_mois';
    document.getElementById('nc-cout-estime').value = '';

    // Réinitialiser la liste des matériaux
    afficherListeMateriaux();

    // Ouvrir le modal
    document.getElementById('modal-non-conformite').showModal();
}

/**
 * Ajoute un matériau à la liste
 */
function ajouterMateriau() {
    const designation = document.getElementById('nc-materiau-designation').value.trim();
    const quantite = parseFloat(document.getElementById('nc-materiau-quantite').value);
    const unite = document.getElementById('nc-materiau-unite').value.trim();

    if (!designation || !quantite || quantite <= 0) {
        alert('Veuillez remplir tous les champs du matériau');
        return;
    }

    materiaux.push({
        designation: designation,
        quantite: quantite,
        unite: unite
    });

    // Réinitialiser les champs
    document.getElementById('nc-materiau-designation').value = '';
    document.getElementById('nc-materiau-quantite').value = '';
    document.getElementById('nc-materiau-unite').value = 'pièces';

    afficherListeMateriaux();
}

/**
 * Affiche la liste des matériaux
 */
function afficherListeMateriaux() {
    const liste = document.getElementById('nc-liste-materiaux');

    if (materiaux.length === 0) {
        liste.innerHTML = '<p class="text-sm text-gray-500 italic">Aucun matériau ajouté</p>';
        return;
    }

    let html = '<div class="space-y-2">';
    materiaux.forEach((mat, index) => {
        html += `
            <div class="flex items-center justify-between bg-base-200 p-2 rounded">
                <div class="flex-1">
                    <span class="font-semibold">${mat.designation}</span>
                    <span class="text-sm text-gray-600"> - ${mat.quantite} ${mat.unite}</span>
                </div>
                <button type="button" onclick="supprimerMateriau(${index})"
                        class="btn btn-ghost btn-xs text-error">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
    });
    html += '</div>';

    liste.innerHTML = html;
}

/**
 * Supprime un matériau de la liste
 */
function supprimerMateriau(index) {
    materiaux.splice(index, 1);
    afficherListeMateriaux();
}

/**
 * Sauvegarde la non-conformité
 */
async function sauvegarderNonConformite() {
    // Validation
    const narratif = document.getElementById('nc-narratif-probleme').value.trim();
    const solution = document.getElementById('nc-solution-detaillee').value.trim();

    if (!narratif) {
        alert('Le narratif du problème est obligatoire');
        return;
    }

    if (!solution) {
        alert('La solution détaillée est obligatoire');
        return;
    }

    // Récupérer les données du formulaire
    const formData = new FormData();
    formData.append('resultat_inspection_id', currentResultatId);
    formData.append('narratif_probleme', narratif);
    formData.append('solution_detaillee', solution);
    formData.append('materiaux_necessaires', JSON.stringify(materiaux));
    formData.append('besoin_superviseur', document.getElementById('nc-besoin-superviseur').checked);
    formData.append('niveau_solution', document.getElementById('nc-niveau-solution').value);
    formData.append('priorite', document.getElementById('nc-priorite').value);
    formData.append('echeance', document.getElementById('nc-echeance').value);

    const cout = document.getElementById('nc-cout-estime').value;
    if (cout && cout.trim() !== '') {
        formData.append('cout_estime', cout);
    }

    // Afficher le loader
    const btnSauvegarder = document.getElementById('btn-sauvegarder-nc');
    const btnText = btnSauvegarder.innerHTML;
    btnSauvegarder.disabled = true;
    btnSauvegarder.innerHTML = '<span class="loading loading-spinner loading-sm"></span> Enregistrement...';

    try {
        const response = await fetch('/inspections/api/non-conformite/creer/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            // Afficher un message de succès
            alert('✓ Non-conformité enregistrée avec succès\nUne action corrective a été générée automatiquement.');

            // Fermer le modal
            document.getElementById('modal-non-conformite').close();

            // Optionnel : Recharger la page ou mettre à jour l'affichage
            // location.reload();
        } else {
            alert('Erreur : ' + (data.error || 'Une erreur est survenue'));
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('Erreur réseau : ' + error.message);
    } finally {
        // Restaurer le bouton
        btnSauvegarder.disabled = false;
        btnSauvegarder.innerHTML = btnText;
    }
}

/**
 * Récupère le CSRF token
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
