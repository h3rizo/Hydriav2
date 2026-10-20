/* Editeur de liaisons entre villages (Leaflet) : modals creation/edition/suppression + mode trace.
 * Utilise par /geography/map/liaisons/ et la fiche village.
 *
 * const editor = LiaisonsEditor.create({ map, onChange(evt) {...} });
 * editor.openEdit(props) | editor.openCreate(source, cible) | editor.startDraw(source?) | editor.stopDraw()
 * Les villages sont des objets { id, nom, lat, lng, commune }.
 */
(function (global) {
    'use strict';

    const TYPES = [['desserte', 'Desserte'], ['proximite', 'Proximité'], ['dependance', 'Dépendance']];
    const ROUTES = [['', 'Non renseigné'], ['route', 'Route'], ['piste', 'Piste'], ['sentier', 'Sentier'], ['riviere', 'Rivière']];
    const MOYENS = [['', 'Non renseigné'], ['voiture', 'Voiture'], ['moto', 'Moto'], ['pied', 'À pied'], ['pirogue', 'Pirogue']];
    const MOYEN_ICON = { voiture: '🚗', moto: '🏍', pied: '🚶', pirogue: '🛶' };

    const URLS = {
        create: '/geography/api/liaisons/create/',
        update: (id) => `/geography/api/liaisons/${id}/update/`,
        remove: (id) => `/geography/api/liaisons/${id}/delete/`,
    };

    function getCookie(name) {
        const match = document.cookie.split('; ').find((c) => c.startsWith(name + '='));
        return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : '';
    }

    function fmtKm(value) {
        return Number(value).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
    }

    function haversine(a, b) {
        const rad = (d) => (d * Math.PI) / 180;
        const dLat = rad(b.lat - a.lat);
        const dLng = rad(b.lng - a.lng);
        const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
        return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
    }

    /** Texte court affiche sur le trait : "3,2 km · 🏍 45 min". */
    function edgeText(p) {
        const parts = [];
        if (p.distance_km !== null && p.distance_km !== undefined) parts.push(`${fmtKm(p.distance_km)} km`);
        const moyen = [MOYEN_ICON[p.moyen_acces] || '', p.temps_acces_minutes ? `${p.temps_acces_minutes} min` : ''].filter(Boolean).join(' ');
        if (moyen) parts.push(moyen);
        // Distance par la route, affichée seulement si elle diffère nettement de la valeur saisie.
        if (p.route_statut === 'ok' && p.distance_route_km != null &&
            (p.distance_km == null || Math.abs(p.distance_route_km - p.distance_km) > 0.15 * p.distance_km)) {
            parts.push(`🛣 ${fmtKm(p.distance_route_km)} km${p.duree_route_min ? ' · ' + p.duree_route_min + ' min' : ''}`);
        }
        return parts.join(' · ');
    }

    function injectStyles() {
        if (document.getElementById('liaisons-editor-styles')) return;
        const style = document.createElement('style');
        style.id = 'liaisons-editor-styles';
        style.textContent = `
            .leaflet-tooltip.liaison-label { background: rgba(255,255,255,.92); color: #1f2937; border: 1px solid #d97706; border-radius: 6px; padding: 1px 6px; font-size: 11px; font-weight: 600; box-shadow: none; }
            .leaflet-tooltip.liaison-label:before { display: none; }
            .leaflet-tooltip.liaison-edge-label { background: rgba(124,58,237,.92); color: #fff; border: 0; border-radius: 10px; padding: 0 7px; font-size: 11px; box-shadow: none; }
            .leaflet-tooltip.liaison-edge-label:before { display: none; }
            .liaison-arrow { font-size: 14px; line-height: 14px; text-align: center; color: #5b21b6; text-shadow: 0 0 2px #fff, 0 0 2px #fff; cursor: pointer; }
            .liaison-draw-control a { width: auto !important; padding: 0 10px; font-size: 13px; line-height: 30px !important; cursor: pointer; white-space: nowrap; }
            .liaison-draw-control.active a { background: #7c3aed; color: #fff; }
            .liaison-draw-hint { background: #7c3aed; color: #fff; border-radius: 8px; padding: 6px 10px; font-size: 12px; max-width: 260px; }
        `;
        document.head.appendChild(style);
    }

    function optionsHtml(list) {
        return list.map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
    }

    function create(config) {
        injectStyles();
        const map = config.map;
        const onChange = config.onChange || function () {};
        const state = { drawing: false, source: null, rubber: null, control: null, hint: null };

        // ---------- Modal ----------
        const dialog = document.createElement('dialog');
        dialog.className = 'modal';
        dialog.innerHTML = `
            <div class="modal-box max-w-xl">
                <div class="flex items-start justify-between gap-3">
                    <h3 class="text-lg font-bold" data-role="title"></h3>
                    <button type="button" class="btn btn-sm btn-circle btn-ghost" data-role="close">✕</button>
                </div>
                <div class="mt-3 flex items-center gap-2 rounded-lg bg-base-200 px-3 py-2 text-sm">
                    <span class="font-semibold" data-role="source"></span>
                    <span class="text-lg">→</span>
                    <span class="font-semibold" data-role="cible"></span>
                    <button type="button" class="btn btn-ghost btn-xs ml-auto" data-role="swap" title="Inverser le sens">⇄ Inverser</button>
                </div>
                <div class="mt-1 text-xs text-base-content/60" data-role="air"></div>
                <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                    <label class="form-control"><span class="label-text mb-1">Type de liaison</span>
                        <select class="select select-bordered select-sm w-full" data-field="type_liaison">${optionsHtml(TYPES)}</select></label>
                    <label class="form-control"><span class="label-text mb-1">Moyen d'accès</span>
                        <select class="select select-bordered select-sm w-full" data-field="moyen_acces">${optionsHtml(MOYENS)}</select></label>
                    <label class="form-control"><span class="label-text mb-1">Type de route</span>
                        <select class="select select-bordered select-sm w-full" data-field="type_route">${optionsHtml(ROUTES)}</select></label>
                    <label class="form-control"><span class="label-text mb-1">Distance terrain (km)</span>
                        <input type="number" min="0" step="0.01" class="input input-bordered input-sm w-full" data-field="distance_km"></label>
                    <label class="form-control"><span class="label-text mb-1">Temps d'accès (minutes)</span>
                        <input type="number" min="0" step="1" class="input input-bordered input-sm w-full" data-field="temps_acces_minutes"></label>
                    <div class="flex items-end"><button type="button" class="btn btn-outline btn-xs" data-role="use-air">Utiliser la distance à vol d'oiseau</button></div>
                </div>
                <div class="mt-3 hidden text-sm text-error" data-role="error"></div>
                <div class="modal-action items-center">
                    <button type="button" class="btn btn-error btn-outline btn-sm mr-auto hidden" data-role="delete">Supprimer</button>
                    <button type="button" class="btn btn-ghost btn-sm" data-role="cancel">Annuler</button>
                    <button type="button" class="btn btn-primary btn-sm" data-role="save">Enregistrer</button>
                </div>
            </div>
            <form method="dialog" class="modal-backdrop"><button>close</button></form>`;
        document.body.appendChild(dialog);

        const q = (sel) => dialog.querySelector(sel);
        const role = (name) => q(`[data-role="${name}"]`);
        const field = (name) => q(`[data-field="${name}"]`);
        const modal = { mode: 'create', source: null, cible: null, liaisonId: null, airKm: null, inverser: false };

        function renderEnds() {
            role('source').textContent = modal.source.nom;
            role('cible').textContent = modal.cible.nom;
            role('air').textContent = modal.airKm !== null ? `Distance à vol d'oiseau : ${fmtKm(modal.airKm)} km` : '';
            role('use-air').classList.toggle('hidden', modal.airKm === null);
        }

        function showError(message) {
            const box = role('error');
            box.textContent = message || '';
            box.classList.toggle('hidden', !message);
        }

        async function send(url, body) {
            const response = await fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken'), 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify(body || {}),
            });
            let data = {};
            try { data = await response.json(); } catch (e) { /* reponse non JSON */ }
            if (!response.ok || !data.success) {
                throw new Error(data.error || `Erreur ${response.status}`);
            }
            return data;
        }

        function formValues() {
            const values = {};
            dialog.querySelectorAll('[data-field]').forEach((el) => { values[el.dataset.field] = el.value; });
            return values;
        }

        function fillForm(p) {
            field('type_liaison').value = p.type_liaison || 'desserte';
            field('moyen_acces').value = p.moyen_acces || '';
            field('type_route').value = p.type_route || '';
            field('distance_km').value = p.distance_km ?? '';
            field('temps_acces_minutes').value = p.temps_acces_minutes ?? '';
        }

        function villageFromProps(p, side) {
            return { id: p[`${side}_id`], nom: p[`${side}_nom`] };
        }

        role('close').onclick = role('cancel').onclick = () => dialog.close();
        role('use-air').onclick = () => { if (modal.airKm !== null) field('distance_km').value = modal.airKm; };
        role('swap').onclick = () => {
            [modal.source, modal.cible] = [modal.cible, modal.source];
            modal.inverser = !modal.inverser;
            renderEnds();
        };

        role('save').onclick = async () => {
            showError('');
            const btn = role('save');
            btn.disabled = true;
            try {
                let data;
                if (modal.mode === 'create') {
                    data = await send(URLS.create, { source_id: modal.source.id, cible_id: modal.cible.id, ...formValues() });
                } else {
                    data = await send(URLS.update(modal.liaisonId), { ...formValues(), inverser: modal.inverser });
                }
                dialog.close();
                onChange({ type: modal.mode === 'create' ? 'created' : 'updated', liaison: data.liaison, trace_route: data.trace_route });
            } catch (error) {
                showError(error.message);
            } finally {
                btn.disabled = false;
            }
        };

        role('delete').onclick = async () => {
            if (!window.confirm(`Supprimer la liaison ${modal.source.nom} → ${modal.cible.nom} ?`)) return;
            showError('');
            try {
                await send(URLS.remove(modal.liaisonId));
                dialog.close();
                onChange({ type: 'deleted', liaison: { id: modal.liaisonId } });
            } catch (error) {
                showError(error.message);
            }
        };

        dialog.addEventListener('close', () => { if (state.drawing) resetSource(); });

        // ---------- API modals ----------
        function openEdit(props) {
            modal.mode = 'update';
            modal.liaisonId = props.id;
            modal.source = villageFromProps(props, 'source');
            modal.cible = villageFromProps(props, 'cible');
            modal.airKm = props.distance_vol_oiseau_km ?? null;
            modal.inverser = false;
            role('title').textContent = 'Modifier la liaison';
            role('delete').classList.remove('hidden');
            role('save').textContent = 'Enregistrer';
            fillForm(props);
            renderEnds();
            showError('');
            dialog.showModal();
        }

        function openCreate(source, cible) {
            modal.mode = 'create';
            modal.liaisonId = null;
            modal.source = source;
            modal.cible = cible;
            modal.inverser = false;
            modal.airKm = (source.lat != null && cible.lat != null) ? Math.round(haversine(source, cible) * 100) / 100 : null;
            role('title').textContent = 'Nouvelle liaison';
            role('delete').classList.add('hidden');
            role('save').textContent = 'Créer la liaison';
            fillForm({ type_liaison: 'desserte', distance_km: modal.airKm });
            renderEnds();
            showError('');
            dialog.showModal();
        }

        // ---------- Mode trace ----------
        function setHint(text) {
            if (state.hint) state.hint.textContent = text;
        }

        function clearRubber() {
            if (state.rubber) { map.removeLayer(state.rubber); state.rubber = null; }
        }

        function resetSource() {
            state.source = null;
            clearRubber();
            if (config.onDrawSource) config.onDrawSource(null);
            if (state.drawing) setHint('Cliquez sur le village de départ');
        }

        function onMouseMove(event) {
            if (!state.source) return;
            const from = [state.source.lat, state.source.lng];
            if (!state.rubber) {
                state.rubber = L.polyline([from, event.latlng], { color: '#7c3aed', weight: 3, dashArray: '6 6', interactive: false }).addTo(map);
            } else {
                state.rubber.setLatLngs([from, event.latlng]);
            }
        }

        function onKey(event) {
            if (event.key === 'Escape' && state.drawing) {
                if (state.source) resetSource(); else stopDraw();
            }
        }

        function startDraw(source) {
            state.drawing = true;
            if (state.control) state.control.getContainer().classList.add('active');
            map.getContainer().style.cursor = 'crosshair';
            map.on('mousemove', onMouseMove);
            document.addEventListener('keydown', onKey);
            if (source) {
                state.source = source;
                if (config.onDrawSource) config.onDrawSource(source);
                setHint(`Départ : ${source.nom}. Cliquez sur le village d'arrivée (Échap pour annuler)`);
            } else {
                setHint('Cliquez sur le village de départ');
            }
            if (state.hint) state.hint.classList.remove('hidden');
        }

        function stopDraw() {
            state.drawing = false;
            resetSource();
            if (state.control) state.control.getContainer().classList.remove('active');
            map.getContainer().style.cursor = '';
            map.off('mousemove', onMouseMove);
            document.removeEventListener('keydown', onKey);
            if (state.hint) state.hint.classList.add('hidden');
        }

        /** A appeler depuis le clic d'un village. Retourne true si le clic a ete consomme par le mode trace. */
        function handleVillageClick(village) {
            if (!state.drawing) return false;
            if (!state.source) {
                state.source = village;
                if (config.onDrawSource) config.onDrawSource(village);
                setHint(`Départ : ${village.nom}. Cliquez sur le village d'arrivée (Échap pour annuler)`);
                return true;
            }
            if (state.source.id === village.id) {
                resetSource();
                return true;
            }
            const source = state.source;
            clearRubber();
            openCreate(source, village);
            return true;
        }

        function addDrawControl() {
            const Control = L.Control.extend({
                options: { position: 'topright' },
                onAdd() {
                    const container = L.DomUtil.create('div', 'leaflet-bar liaison-draw-control');
                    const link = L.DomUtil.create('a', '', container);
                    link.href = '#';
                    link.title = 'Tracer une liaison entre deux villages';
                    link.textContent = '✏️ Tracer une liaison';
                    const hint = L.DomUtil.create('div', 'liaison-draw-hint hidden', container);
                    hint.style.marginTop = '6px';
                    state.hint = hint;
                    L.DomEvent.disableClickPropagation(container);
                    L.DomEvent.on(link, 'click', (e) => {
                        L.DomEvent.preventDefault(e);
                        if (state.drawing) stopDraw(); else startDraw();
                    });
                    return container;
                },
            });
            state.control = new Control();
            state.control.addTo(map);
        }

        return {
            openEdit, openCreate, startDraw, stopDraw, handleVillageClick, addDrawControl,
            isDrawing: () => state.drawing,
            drawSource: () => state.source,
        };
    }

    global.LiaisonsEditor = { create, edgeText, haversine, fmtKm, MOYEN_ICON };
})(window);
