/**
 * Workflow Avances - Gestion des avances terrain
 * Ce fichier gère les fonctions pour le traitement des avances avec champs éditables
 */

console.log('💰 workflow_avances.js chargé');

// Fonction de mise à jour du compteur d'avances
window.updateAvanceCount = function() {
    const count = document.querySelectorAll('.avance-select:checked').length;
    const countElement = document.getElementById('count-avances-selection');
    if (countElement) {
        countElement.textContent = count;
        console.log('📊 Compteur avances mis à jour:', count);
    }
};

// Fonction pour gérer le traitement des avances sélectionnées
window.handleTraiterAvances = function() {
    console.log('✅ handleTraiterAvances appelée');

    const checkboxes = document.querySelectorAll('.avance-select:checked');
    console.log('Checkboxes cochées:', checkboxes.length);

    if (checkboxes.length === 0) {
        alert('Veuillez sélectionner au moins une avance');
        return;
    }

    // Préparer les lignes avec les données
    const lignes = Array.from(checkboxes).map(cb => ({
        id: cb.dataset.detailId,
        designation: cb.dataset.designation,
        designation_id: cb.dataset.designationId,
        quantity: parseFloat(cb.dataset.quantity) || 0,
        pu: parseFloat(cb.dataset.pu) || 0,
        montant: parseFloat(cb.dataset.montant) || 0,
        fournisseur_id: cb.dataset.fournisseur || ''
    }));

    console.log('Lignes préparées:', lignes);

    // Stocker globalement pour utilisation dans le modal
    window.lignesAvances = lignes;

    // Charger les comptes autorisés pour la première désignation
    const premiereDesignationId = lignes[0].designation_id;
    if (premiereDesignationId) {
        chargerComptesAutorises(premiereDesignationId);
    }

    // Calculer le montant total
    const montantTotal = lignes.reduce((sum, l) => sum + l.montant, 0);

    // Remplir le modal avec tableau des lignes
    document.getElementById('avance-detail-ids').value = lignes.map(l => l.id).join(',');
    document.getElementById('avance-montant-total').textContent = montantTotal.toLocaleString('fr-FR');

    // Construire le tableau HTML des lignes
    const tableBody = document.getElementById('avance-lignes-table-body');
    tableBody.innerHTML = lignes.map((ligne, index) => `
        <tr>
            <td class="text-sm">${ligne.designation}</td>
            <td>
                <input type="number"
                       class="input input-bordered input-sm w-20"
                       value="${ligne.quantity}"
                       data-index="${index}"
                       data-field="quantity"
                       onchange="updateAvanceLigne(this)">
            </td>
            <td>
                <input type="number"
                       class="input input-bordered input-sm w-28"
                       value="${ligne.pu}"
                       data-index="${index}"
                       data-field="pu"
                       onchange="updateAvanceLigne(this)">
            </td>
            <td class="font-bold" data-index="${index}" data-field="montant">${ligne.montant.toLocaleString('fr-FR')} Ar</td>
        </tr>
    `).join('');

    // Ouvrir le modal
    const modal = document.getElementById('modal-traiter-avance');
    if (modal) {
        modal.showModal();
        console.log('✅ Modal ouvert');
    } else {
        console.error('❌ Modal introuvable');
        alert('Erreur: Modal introuvable');
    }
};

// Fonction pour mettre à jour une ligne d'avance
window.updateAvanceLigne = function(input) {
    const index = parseInt(input.dataset.index);
    const field = input.dataset.field;
    const value = parseFloat(input.value) || 0;

    if (!window.lignesAvances || !window.lignesAvances[index]) {
        console.error('❌ Ligne introuvable:', index);
        return;
    }

    // Mettre à jour la valeur
    window.lignesAvances[index][field] = value;

    // Recalculer le montant si quantity ou pu a changé
    if (field === 'quantity' || field === 'pu') {
        const quantity = window.lignesAvances[index].quantity;
        const pu = window.lignesAvances[index].pu;
        window.lignesAvances[index].montant = quantity * pu;

        // Mettre à jour l'affichage du montant
        const montantCell = document.querySelector(`td[data-index="${index}"][data-field="montant"]`);
        if (montantCell) {
            montantCell.textContent = window.lignesAvances[index].montant.toLocaleString('fr-FR') + ' Ar';
        }
    }

    // Recalculer le total
    const montantTotal = window.lignesAvances.reduce((sum, l) => sum + l.montant, 0);
    document.getElementById('avance-montant-total').textContent = montantTotal.toLocaleString('fr-FR');

    console.log('📝 Ligne mise à jour:', window.lignesAvances[index]);
};

// Fonction de soumission du formulaire d'avance
window.handleSubmitAvance = async function(event) {
    event.preventDefault();
    console.log('📝 Soumission du formulaire d\'avance interceptée');

    const form = event.target;
    const formData = new FormData(form);
    const detailIds = formData.get('detail_ids');

    if (!detailIds) {
        alert('Erreur: Aucune sélection détectée');
        return false;
    }

    // Ajouter les lignes mises à jour au FormData
    if (window.lignesAvances) {
        formData.set('lignes_data', JSON.stringify(window.lignesAvances));
    }

    if (!navigator.onLine) {
        await enregistrerActionOffline('avance_bon', form.action, Object.fromEntries(formData.entries()));
        return false;
    }

    try {
        const response = await fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': formData.get('csrfmiddlewaretoken')
            }
        });

        const data = await response.json();
        console.log('📥 Réponse serveur:', data);

        if (data.success) {
            const numeroBon = data.numero_bon || 'N/A';
            console.log('✅ Bon d\'avance généré:', numeroBon);

            // Fermer le modal immédiatement
            const modal = document.getElementById('modal-traiter-avance');
            if (modal) modal.close();

            // Afficher un message de chargement
            const loadingDiv = document.createElement('div');
            loadingDiv.id = 'loading-ticket';
            loadingDiv.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.3);
                z-index: 9999;
                text-align: center;
            `;
            loadingDiv.innerHTML = `
                <div style="font-size: 48px; margin-bottom: 20px;">⏳</div>
                <p style="font-size: 18px; margin: 0; font-weight: bold;">Génération du ticket en cours...</p>
                <p style="font-size: 14px; margin: 10px 0 0 0; color: #666;">Chargement du QR Code</p>
            `;
            document.body.appendChild(loadingDiv);

            // Utiliser les données retournées par le serveur
            const details = data.details_updated || [];

            // Préparer les données du ticket
            const ticketData = {
                type: 'Avance',
                isBonAvance: true,  // Flag pour afficher "BON D'AVANCE"
                numero_bon: numeroBon,
                date: new Date().toLocaleString('fr-FR'),
                employe: window.planningData.employe,
                ouvrage: window.planningData.ouvrage,
                organisation: window.planningData.organisation,
                logo_url: window.planningData.logo_url,
                nif: window.planningData.nif,
                stat: window.planningData.stat,
                base: window.planningData.base,
                fournisseur: data.fournisseur || '',
                compte: data.compte || ''
            };

            // Ajouter les lignes et calculer le montant
            if (details.length > 0) {
                ticketData.lignes = details;
                ticketData.montant = details.reduce((sum, d) => sum + parseFloat(d.montant || 0), 0);
            } else {
                ticketData.designation = 'Avance';
                ticketData.montant = 0;
            }

            console.log('🎫 Impression du ticket...');
            console.log('📦 ticketData:', ticketData);

            // Appeler imprimerTicket (ouvre un nouvel onglet)
            if (typeof window.imprimerTicket === 'function') {
                console.log('✅ imprimerTicket disponible, impression...');

                try {
                    window.imprimerTicket(ticketData);
                    console.log('✅ Fonction imprimerTicket appelée avec succès');
                } catch (error) {
                    console.error('❌ Erreur lors de l\'appel à imprimerTicket:', error);
                    document.getElementById('loading-ticket')?.remove();
                    alert('❌ Erreur lors de l\'impression: ' + error.message + '\n\nVeuillez autoriser les popups pour ce site.');
                    return;
                }

                // Attendre que le QR Code soit chargé puis recharger la page
                console.log(`✅ Bon d'avance ${numeroBon} généré avec succès`);
                setTimeout(() => {
                    console.log('🔄 Rechargement de la page...');
                    location.reload();
                }, 6000);  // 6 secondes pour laisser le temps au QR Code de charger
            } else {
                console.error('❌ imprimerTicket non trouvée');
                document.getElementById('loading-ticket')?.remove();
                alert('❌ Erreur: La fonction d\'impression n\'est pas disponible.');
            }
        } else {
            alert('❌ Erreur: ' + (data.error || 'Erreur inconnue'));
        }
    } catch (error) {
        console.error('❌ Erreur dans handleSubmitAvance:', error);
        if (!navigator.onLine || error instanceof TypeError) {
            await enregistrerActionOffline('avance_bon', form.action, Object.fromEntries(formData.entries()));
        } else if (!error.message.includes('navigation') && !error.message.includes('Aborted')) {
            // Ne pas afficher d'alerte si c'est juste le rechargement de la page
            alert('Erreur : ' + error.message);
        }
    }

    return false;
};

console.log('✅ Fonctions workflow_avances.js définies: updateAvanceCount, handleTraiterAvances, handleSubmitAvance');

// Fonction pour charger les comptes autorisés par désignation
window.chargerComptesAutorises = async function(designation_id) {
    console.log('📋 Chargement des comptes pour désignation:', designation_id);
    
    try {
        const response = await fetch(`/plannings/terrain/api/comptes-par-designation/?designation_id=${designation_id}`);
        const data = await response.json();
        
        const selectCompte = document.getElementById('avance-compte');
        selectCompte.innerHTML = '<option value="">-- Sélectionner un compte --</option>';
        
        if (data.success && data.comptes && data.comptes.length > 0) {
            console.log('✅ Comptes chargés:', data.comptes.length);
            data.comptes.forEach(compte => {
                const option = document.createElement('option');
                option.value = compte.id;
                option.textContent = compte.display;
                selectCompte.appendChild(option);
            });
        } else {
            console.warn('⚠️ Aucun compte autorisé pour cette désignation');
            selectCompte.innerHTML = '<option value="">-- Aucun compte autorisé --</option>';
        }
    } catch (error) {
        console.error('❌ Erreur chargement comptes:', error);
        const selectCompte = document.getElementById('avance-compte');
        selectCompte.innerHTML = '<option value="">-- Erreur de chargement --</option>';
    }
};

// Fonction pour rechercher les fournisseurs (autocomplétion)
let fournisseurSearchTimeout;
window.rechercherFournisseursAvance = function(query) {
    console.log('🔍 Recherche fournisseur:', query);
    clearTimeout(fournisseurSearchTimeout);

    if (query.length < 2) {
        document.getElementById('fournisseurs-results-avance').innerHTML = '';
        console.log('⚠️ Query trop courte, minimum 2 caractères');
        return;
    }

    console.log('⏱️ Démarrage timer 300ms...');
    fournisseurSearchTimeout = setTimeout(async () => {
        const url = `/plannings/terrain/fournisseurs/rechercher/?q=${encodeURIComponent(query)}`;
        console.log('📡 Envoi requête:', url);

        try {
            const response = await fetch(url);
            console.log('📥 Statut réponse:', response.status, response.statusText);

            const data = await response.json();
            console.log('📦 Données reçues:', data);
            
            const resultsDiv = document.getElementById('fournisseurs-results-avance');
            resultsDiv.innerHTML = '';
            
            if (data.success && data.fournisseurs && data.fournisseurs.length > 0) {
                console.log('🔍 Fournisseurs trouvés:', data.fournisseurs.length);
                data.fournisseurs.forEach(f => {
                    const div = document.createElement('div');
                    div.className = 'p-3 hover:bg-base-200 cursor-pointer border-b border-base-300 transition';
                    div.innerHTML = `
                        <div class="font-semibold">${f.nom}</div>
                        <div class="text-xs text-base-content/70">${f.contact || f.telephone || 'Pas de contact'}</div>
                    `;
                    div.onclick = () => selectionnerFournisseurAvance(f);
                    resultsDiv.appendChild(div);
                });
            } else {
                resultsDiv.innerHTML = '<div class="p-3 text-sm text-base-content/50">Aucun fournisseur trouvé</div>';
            }
        } catch (error) {
            console.error('❌ Erreur recherche fournisseurs:', error);
            document.getElementById('fournisseurs-results-avance').innerHTML = '<div class="p-3 text-sm text-error">Erreur de recherche</div>';
        }
    }, 300);  // Délai de 300ms pour éviter trop de requêtes
};

// Fonction pour sélectionner un fournisseur
window.selectionnerFournisseurAvance = function(fournisseur) {
    console.log('✅ Fournisseur sélectionné:', fournisseur.nom);
    document.getElementById('avance-fournisseur-search').value = fournisseur.nom;
    document.getElementById('avance-fournisseur-id').value = fournisseur.id;
    document.getElementById('fournisseurs-results-avance').innerHTML = '';
};

console.log('✅ Fonctions autocomplétion ajoutées: chargerComptesAutorises, rechercherFournisseursAvance, selectionnerFournisseurAvance');
