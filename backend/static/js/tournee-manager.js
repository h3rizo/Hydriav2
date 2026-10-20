/**
 * Gestionnaire de préparation de tournée hors ligne pour Hydria.
 * Précharge en un seul appel les données de référence (points d'eau,
 * historique, plannings, réparations, tarifs) nécessaires à un agent
 * terrain pour consulter/saisir même sans réseau.
 */

const TOURNEE_LOCALSTORAGE_KEY = 'hydria_tournee_last_prepared';
const TOURNEE_ALERTE_HEURES = 24;

class TourneeManager {
    constructor() {
        this.isPreparing = false;
    }

    async preparer(horizonJours = 7) {
        if (this.isPreparing) return;

        if (!navigator.onLine) {
            pwaManager.showNotification(
                'Impossible de préparer la tournée hors ligne : une connexion est nécessaire pour le téléchargement initial.',
                'warning'
            );
            return;
        }

        this.isPreparing = true;
        const btn = document.getElementById('prepare-tournee-btn');
        if (btn) {
            btn.disabled = true;
            btn.classList.add('loading');
        }

        try {
            const response = await fetch(`/plannings/api/preparer-tournee/?horizon_jours=${horizonJours}`);
            const data = await response.json();

            if (!data.success) {
                pwaManager.showNotification('Erreur préparation tournée : ' + (data.error || 'inconnue'), 'error');
                return;
            }

            await offlineDB.replaceReferenceData('planning', data.plannings);
            await offlineDB.replaceReferenceData('reparation', data.reparations);

            const tousPointsEau = [];
            const tousTarifs = [];
            (data.ouvrages || []).forEach((ouvrage) => {
                (ouvrage.points_eau || []).forEach((pe) => {
                    tousPointsEau.push({ ...pe, ouvrage_id: ouvrage.id, ouvrage_nom: ouvrage.nom });
                });
                (ouvrage.tarifs || []).forEach((tarif, index) => {
                    tousTarifs.push({ id: `${ouvrage.id}:${index}`, ouvrage_id: ouvrage.id, ...tarif });
                });
            });
            await offlineDB.replaceReferenceData('point_eau', tousPointsEau);
            await offlineDB.replaceReferenceData('tarif', tousTarifs);

            localStorage.setItem(TOURNEE_LOCALSTORAGE_KEY, new Date().toISOString());
            this.updateStatusDisplay(data.stats);

            let message = `Tournée préchargée : ${data.stats.nb_points_eau} point(s) d'eau, ${data.stats.nb_plannings} planning(s), ${data.stats.nb_reparations} réparation(s).`;
            if (data.warning) {
                message += ' ' + data.warning;
            }
            pwaManager.showNotification(message, 'success');
        } catch (error) {
            console.error('[TourneeManager] Erreur:', error);
            pwaManager.showNotification('Erreur réseau lors de la préparation de la tournée.', 'error');
        } finally {
            this.isPreparing = false;
            if (btn) {
                btn.disabled = false;
                btn.classList.remove('loading');
            }
        }
    }

    /**
     * Met à jour la zone de statut sous le bouton, avec un stat immédiat
     * ("Y points d'eau, à l'instant") ou, au chargement de page, l'état
     * calculé depuis le timestamp stocké en localStorage.
     */
    updateStatusDisplay(stats) {
        const el = document.getElementById('tournee-status');
        if (!el) return;
        el.classList.remove('hidden');
        el.classList.remove('text-warning', 'text-error');
        el.textContent = `Dernière tournée : ${stats.nb_points_eau} point(s) d'eau (à l'instant)`;
    }

    /**
     * Rafraîchit l'affichage du statut au chargement de page à partir du
     * timestamp localStorage, avec alerte visuelle si > 24h.
     */
    refreshStatusFromStorage() {
        const el = document.getElementById('tournee-status');
        if (!el) return;

        const iso = localStorage.getItem(TOURNEE_LOCALSTORAGE_KEY);
        if (!iso) return;

        const lastPrepared = new Date(iso);
        const heuresEcoulees = (Date.now() - lastPrepared.getTime()) / (1000 * 60 * 60);

        el.classList.remove('hidden');
        if (heuresEcoulees >= TOURNEE_ALERTE_HEURES) {
            el.classList.add('text-error');
            el.classList.remove('text-warning');
            el.textContent = `Tournée obsolète (${Math.floor(heuresEcoulees)}h) - à rafraîchir avant de partir`;
        } else if (heuresEcoulees >= TOURNEE_ALERTE_HEURES / 2) {
            el.classList.add('text-warning');
            el.classList.remove('text-error');
            el.textContent = `Dernière tournée : il y a ${Math.floor(heuresEcoulees)}h`;
        } else {
            el.classList.remove('text-warning', 'text-error');
            const minutes = Math.floor(heuresEcoulees * 60);
            el.textContent = minutes < 60
                ? `Dernière tournée : il y a ${minutes} min`
                : `Dernière tournée : il y a ${Math.floor(heuresEcoulees)}h`;
        }
    }
}

const tourneeManager = new TourneeManager();

document.addEventListener('DOMContentLoaded', () => {
    tourneeManager.refreshStatusFromStorage();
});
