/**
 * Workflow Paiements Forfaitaires - Gestion des recettes terrain
 * Ce fichier gère les fonctions pour la collecte des paiements forfaitaires avec champs éditables
 */

console.log('💵 workflow_paiements.js chargé');

// Fonction de mise à jour du compteur de paiements
window.updatePaiementCount = function() {
    const count = document.querySelectorAll('.paiement-select:checked').length;
    const countElement = document.getElementById('count-paiements-selection');
    if (countElement) {
        countElement.textContent = count;
        console.log('📊 Compteur paiements mis à jour:', count);
    }
};

// Fonction pour gérer la collecte des paiements sélectionnés
window.handleCollecterPaiements = function() {
    console.log('✅ handleCollecterPaiements appelée');

    const checkboxes = document.querySelectorAll('.paiement-select:checked');
    console.log('Checkboxes cochées:', checkboxes.length);

    if (checkboxes.length === 0) {
        alert('Veuillez sélectionner au moins un paiement');
        return;
    }

    // Préparer les lignes avec les données
    const lignes = Array.from(checkboxes).map(cb => ({
        id: cb.dataset.detailId,
        designation: cb.dataset.designation,
        point_eau: cb.dataset.pointEau || 'N/A',
        quantity: parseFloat(cb.dataset.quantity) || 1,
        pu: parseFloat(cb.dataset.montant) || 0,  // Pour les forfaitaires, le montant = PU
        montant: parseFloat(cb.dataset.montant) || 0
    }));

    console.log('Lignes préparées:', lignes);

    // Stocker globalement pour utilisation dans le modal
    window.lignesPaiements = lignes;

    // Calculer le montant total
    const montantTotal = lignes.reduce((sum, l) => sum + l.montant, 0);

    // Remplir le modal avec tableau des lignes
    document.getElementById('paiement-detail-ids').value = lignes.map(l => l.id).join(',');
    document.getElementById('paiement-montant-total').textContent = montantTotal.toLocaleString('fr-FR');

    // Construire le tableau HTML des lignes
    const tableBody = document.getElementById('paiement-lignes-table-body');
    tableBody.innerHTML = lignes.map((ligne, index) => `
        <tr>
            <td class="text-sm">${ligne.designation}</td>
            <td class="text-xs">${ligne.point_eau}</td>
            <td>
                <input type="number"
                       class="input input-bordered input-sm w-20"
                       value="${ligne.quantity}"
                       data-index="${index}"
                       data-field="quantity"
                       onchange="updatePaiementLigne(this)">
            </td>
            <td>
                <input type="number"
                       class="input input-bordered input-sm w-28"
                       value="${ligne.pu}"
                       data-index="${index}"
                       data-field="pu"
                       onchange="updatePaiementLigne(this)">
            </td>
            <td class="font-bold" data-index="${index}" data-field="montant">${ligne.montant.toLocaleString('fr-FR')} Ar</td>
        </tr>
    `).join('');

    // Ouvrir le modal
    const modal = document.getElementById('modal-collecter-paiement');
    if (modal) {
        modal.showModal();
        console.log('✅ Modal ouvert');
    } else {
        console.error('❌ Modal introuvable');
        alert('Erreur: Modal introuvable');
    }
};

// Fonction pour mettre à jour une ligne de paiement
window.updatePaiementLigne = function(input) {
    const index = parseInt(input.dataset.index);
    const field = input.dataset.field;
    const value = parseFloat(input.value) || 0;

    if (!window.lignesPaiements || !window.lignesPaiements[index]) {
        console.error('❌ Ligne introuvable:', index);
        return;
    }

    // Mettre à jour la valeur
    window.lignesPaiements[index][field] = value;

    // Recalculer le montant si quantity ou pu a changé
    if (field === 'quantity' || field === 'pu') {
        const quantity = window.lignesPaiements[index].quantity;
        const pu = window.lignesPaiements[index].pu;
        window.lignesPaiements[index].montant = quantity * pu;

        // Mettre à jour l'affichage du montant
        const montantCell = document.querySelector(`td[data-index="${index}"][data-field="montant"]`);
        if (montantCell) {
            montantCell.textContent = window.lignesPaiements[index].montant.toLocaleString('fr-FR') + ' Ar';
        }
    }

    // Recalculer le total
    const montantTotal = window.lignesPaiements.reduce((sum, l) => sum + l.montant, 0);
    document.getElementById('paiement-montant-total').textContent = montantTotal.toLocaleString('fr-FR');

    console.log('📝 Ligne mise à jour:', window.lignesPaiements[index]);
};

// Fonction de soumission du formulaire de paiement
window.handleSubmitPaiement = async function(event) {
    event.preventDefault();
    console.log('📝 Soumission du formulaire de paiement interceptée');

    const form = event.target;
    const formData = new FormData(form);
    const detailIds = formData.get('detail_ids');

    if (!detailIds) {
        alert('Erreur: Aucune sélection détectée');
        return false;
    }

    // Ajouter les lignes mises à jour au FormData
    if (window.lignesPaiements) {
        formData.set('lignes_data', JSON.stringify(window.lignesPaiements));
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
            const numeroFacture = data.numero_facture || 'N/A';
            console.log('✅ Facture générée:', numeroFacture);

            // Fermer le modal immédiatement
            const modal = document.getElementById('modal-collecter-paiement');
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
                <p style="font-size: 18px; margin: 0; font-weight: bold;">Génération de la facture en cours...</p>
                <p style="font-size: 14px; margin: 10px 0 0 0; color: #666;">Chargement du QR Code</p>
            `;
            document.body.appendChild(loadingDiv);

            // Utiliser les données retournées par le serveur
            const details = data.details_updated || [];

            // Préparer les données du ticket
            const ticketData = {
                type: 'Paiement Forfaitaire',
                isBonPaiement: true,  // Flag pour afficher "FACTURE"
                numero_bon: numeroFacture,
                date: new Date().toLocaleString('fr-FR'),
                employe: window.planningData.employe,
                ouvrage: window.planningData.ouvrage,
                organisation: window.planningData.organisation,
                logo_url: window.planningData.logo_url,
                nif: window.planningData.nif,
                stat: window.planningData.stat,
                base: window.planningData.base,
                compte: data.compte || ''
            };

            // Ajouter les lignes et calculer le montant
            if (details.length > 0) {
                ticketData.lignes = details;
                ticketData.montant = details.reduce((sum, d) => sum + parseFloat(d.montant || 0), 0);
            } else {
                ticketData.designation = 'Paiement Forfaitaire';
                ticketData.montant = 0;
            }

            console.log('🎫 Impression de la facture...');
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
                console.log(`✅ Facture ${numeroFacture} générée avec succès`);
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
        console.error('❌ Erreur dans handleSubmitPaiement:', error);
        // Ne pas afficher d'alerte si c'est juste le rechargement de la page
        if (!error.message.includes('navigation') && !error.message.includes('Aborted')) {
            alert('Erreur : ' + error.message);
        }
    }

    return false;
};

console.log('✅ Fonctions workflow_paiements.js définies: updatePaiementCount, handleCollecterPaiements, handleSubmitPaiement');
