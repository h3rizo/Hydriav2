/**
 * Workflow Livraisons - Gestion des livraisons terrain
 * Ce fichier gère les fonctions pour le traitement des livraisons
 */

console.log('📦 workflow_livraisons.js chargé');

// Fonction de mise à jour du compteur de livraisons
window.updateLivraisonCount = function() {
    const count = document.querySelectorAll('.livraison-select:checked').length;
    const countElement = document.getElementById('count-livraisons-selection');
    if (countElement) {
        countElement.textContent = count;
        console.log('📊 Compteur livraisons mis à jour:', count);
    }
};

// Fonction pour gérer l'utilisation des livraisons sélectionnées
window.handleUtiliserLivraisons = function() {
    console.log('✅ handleUtiliserLivraisons appelée');

    const checkboxes = document.querySelectorAll('.livraison-select:checked');
    console.log('Checkboxes cochées:', checkboxes.length);

    if (checkboxes.length === 0) {
        alert('Veuillez sélectionner au moins une livraison');
        return;
    }

    // Vérifier que tous les fournisseurs sont identiques
    let fournisseur = null;
    let different = false;
    checkboxes.forEach(cb => {
        const f = cb.dataset.fournisseur;
        if (fournisseur === null) fournisseur = f;
        else if (fournisseur !== f) different = true;
    });

    if (different) {
        alert('Erreur: Les livraisons sélectionnées ont des fournisseurs différents. Veuillez sélectionner des livraisons du même fournisseur.');
        return;
    }

    // Préparer les lignes
    const lignes = Array.from(checkboxes).map(cb => ({
        id: cb.dataset.detailId,
        designation: cb.dataset.designation,
        quantity: cb.dataset.quantity,
        pu: cb.dataset.pu,
        montant: cb.dataset.montant
    }));

    console.log('Lignes préparées:', lignes);

    // Ouvrir le modal directement
    document.getElementById('livraison-detail-ids').value = lignes.map(l => l.id).join(',');
    document.getElementById('livraison-designation').value = `${lignes.length} ligne(s) sélectionnée(s)`;
    window.lignesFacture = lignes;

    const modal = document.getElementById('modal-utiliser-livraison');
    if (modal) {
        modal.showModal();
        console.log('✅ Modal ouvert');
    } else {
        console.error('❌ Modal introuvable');
        alert('Erreur: Modal introuvable');
    }
};

// Fonction de soumission du formulaire de livraison
window.handleSubmitLivraison = async function(event) {
    event.preventDefault();
    console.log('📝 Soumission du formulaire de livraison interceptée');

    const form = event.target;
    const formData = new FormData(form);
    const detailIds = formData.get('detail_ids');

    if (!detailIds) {
        alert('Erreur: Aucune sélection détectée');
        return false;
    }

    if (!navigator.onLine) {
        await enregistrerActionOffline('livraison_bon', form.action, Object.fromEntries(formData.entries()));
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
            console.log('✅ Bon de livraison généré:', numeroBon);

            // Fermer le modal immédiatement
            const modal = document.getElementById('modal-utiliser-livraison');
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
                type: 'Livraison',
                isBonLivraison: true,
                numero_bon: numeroBon,
                date: new Date().toLocaleString('fr-FR'),
                employe: window.planningData.employe,
                ouvrage: window.planningData.ouvrage,
                organisation: window.planningData.organisation,
                logo_url: window.planningData.logo_url,
                nif: window.planningData.nif,
                stat: window.planningData.stat,
                base: window.planningData.base
            };

            // Ajouter les lignes et calculer le montant
            if (details.length > 0) {
                ticketData.lignes = details;
                ticketData.montant = details.reduce((sum, d) => sum + parseFloat(d.montant || 0), 0);
            } else {
                // Fallback au cas où le serveur ne retourne pas de details
                ticketData.designation = 'Livraison';
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
                console.log(`✅ Bon de livraison ${numeroBon} généré avec succès`);
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
        console.error('❌ Erreur dans handleSubmitLivraison:', error);
        if (!navigator.onLine || error instanceof TypeError) {
            await enregistrerActionOffline('livraison_bon', form.action, Object.fromEntries(formData.entries()));
        } else if (!error.message.includes('navigation') && !error.message.includes('Aborted')) {
            // Ne pas afficher d'alerte si c'est juste le rechargement de la page
            alert('Erreur : ' + error.message);
        }
    }

    return false;
};

// Enregistrement generique hors ligne d'une action terrain (livraison,
// avance) : aucun store IndexedDB dedie pour ces types, sync_queue reste
// la seule source de verite (le numero de bon reel ne peut etre genere
// que par le serveur, a la synchronisation).
async function enregistrerActionOffline(type, endpoint, payload) {
    if (typeof offlineDB === 'undefined') {
        alert('Enregistrement hors ligne indisponible sur cet appareil. Reessayez avec une connexion.');
        return;
    }

    await offlineDB.addToSyncQueue(type, 'create', payload, endpoint);

    alert('Action enregistree hors ligne. Elle sera transmise automatiquement au retour de connexion (le ticket ne peut pas etre imprime immediatement).');

    const modalLivraison = document.getElementById('modal-utiliser-livraison');
    if (modalLivraison && typeof modalLivraison.close === 'function') modalLivraison.close();
    const modalAvance = document.getElementById('modal-traiter-avance');
    if (modalAvance && typeof modalAvance.close === 'function') modalAvance.close();

    if (typeof pwaManager !== 'undefined') {
        pwaManager.showNotification('1 action en attente de synchronisation', 'info');
    }
}

console.log('✅ Fonctions workflow_livraisons.js définies: updateLivraisonCount, handleUtiliserLivraisons, handleSubmitLivraison');
