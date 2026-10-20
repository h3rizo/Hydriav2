/**
 * JavaScript pour annuler un Repos ou Jour férié
 * Utilise l'API /plannings/api/<planning_id>/annuler-repos-ferie/
 *
 * Usage dans le template:
 * <script src="{% static 'js/planning_annulation.js' %}"></script>
 *
 * Dans le HTML:
 * <button onclick="annulerReposFerie('{{ planning.id }}', '{{ planning.activite.nom }}')">
 *     Annuler
 * </button>
 */

/**
 * Annuler un Planning de type Repos ou Jour férié
 *
 * @param {string} planningId - UUID du planning
 * @param {string} activiteNom - Nom de l'activité (pour affichage)
 */
async function annulerReposFerie(planningId, activiteNom) {
    // Confirmation
    const confirmMessage = `Voulez-vous vraiment annuler ce ${activiteNom} ?\n\n` +
        `⚠️ Note:\n` +
        `- Si c'est un Dimanche ou Jour férié: Une récupération sera créée automatiquement\n` +
        `- Si c'est un Samedi: PAS de récupération (non récupérable)`;

    if (!confirm(confirmMessage)) {
        return;
    }

    try {
        const response = await fetch(`/plannings/api/${planningId}/annuler-repos-ferie/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();

        if (data.success) {
            // Afficher message de succès
            if (data.recuperation_creee) {
                alert(`✅ ${data.message}\n\nUne récupération a été ajoutée à votre solde.`);
            } else {
                alert(`✅ ${data.message}`);
            }

            // Recharger la page
            location.reload();
        } else {
            alert(`❌ Erreur: ${data.error}`);
        }
    } catch (error) {
        console.error('Erreur:', error);
        alert('❌ Erreur réseau. Veuillez réessayer.');
    }
}

/**
 * Vérifie si un planning peut être annulé
 * (doit être un Repos ou Jour férié)
 *
 * @param {string} activiteNom - Nom de l'activité
 * @returns {boolean} - True si annulable
 */
function estAnnulable(activiteNom) {
    return activiteNom === 'Repos' || activiteNom === 'Jour férié';
}

/**
 * Récupère le cookie CSRF
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
