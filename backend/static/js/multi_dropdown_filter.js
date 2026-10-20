/**
 * Menu déroulant discret pour filtre à choix multiple (cases à cocher).
 *
 * Remplace les listes déroulantes natives <select multiple> et les longues
 * listes de cases à cocher toujours visibles par un menu <details>/<summary>
 * compact : résumé du nombre d'éléments cochés, recherche, "Cocher les
 * visibles" / "Tout décocher". Mêmes principes que le filtre géographique de
 * la page Analyse villages (core/analyse_villages_desserte.html).
 *
 * Structure HTML attendue pour un préfixe "xxx" :
 *   <details class="dropdown w-full" id="xxxDropdown">
 *     <summary class="select select-bordered w-full flex items-center">
 *       <span id="xxxSummary" class="truncate">Tous les xxx</span>
 *     </summary>
 *     <div class="dropdown-content ...">
 *       <input type="search" id="xxxFilter" ...>
 *       <button id="xxxCheckVisible">...</button>
 *       <button id="xxxUncheckAll">...</button>
 *       <ul>
 *         <li data-name="...">
 *           <label><input type="checkbox" class="multi-cb" data-label="..." ...></label>
 *         </li>
 *       </ul>
 *     </div>
 *   </details>
 */
function initMultiDropdown(prefix, options) {
    const opts = options || {};
    const allLabel = opts.allLabel || 'Tous';
    const plural = opts.plural || 'éléments';
    const onChange = opts.onChange || function () {};

    const dd = document.getElementById(prefix + 'Dropdown');
    if (!dd) return null;
    const list = dd.querySelector('ul');
    if (!list) return null;
    const summary = document.getElementById(prefix + 'Summary');
    const filterInput = document.getElementById(prefix + 'Filter');
    const checkVisibleBtn = document.getElementById(prefix + 'CheckVisible');
    const uncheckAllBtn = document.getElementById(prefix + 'UncheckAll');

    const boxes = () => Array.from(list.querySelectorAll('.multi-cb'));

    const api = {
        checked() {
            return boxes().filter((c) => c.checked).map((c) => c.value);
        },
        refresh() {
            if (!summary) return;
            const on = boxes().filter((c) => c.checked);
            summary.textContent = !on.length
                ? allLabel
                : on.length <= 2
                    ? on.map((c) => c.dataset.label || c.value).join(', ')
                    : on.length + ' ' + plural + ' sélectionné' + (on.length > 1 ? 's' : '');
        },
        search() {
            if (!filterInput) return;
            const q = filterInput.value.trim().toLowerCase();
            list.querySelectorAll('li[data-name]').forEach((li) => {
                li.classList.toggle('hidden', !!q && !li.dataset.name.includes(q));
            });
        },
        // items: [{id, nom}], keep: liste d'ids à recocher, fieldName: attribut "name" des cases à cocher
        fill(items, keep, fieldName) {
            const k = new Set(keep || []);
            const name = fieldName || prefix;
            list.innerHTML = '';
            if (!items || !items.length) {
                const empty = document.createElement('li');
                empty.className = 'text-sm text-base-content/50 py-2 px-1';
                empty.textContent = 'Aucun élément disponible';
                list.appendChild(empty);
                api.refresh();
                return;
            }
            items.forEach((it) => {
                const li = document.createElement('li');
                li.dataset.name = String(it.nom || '').toLowerCase();
                const label = document.createElement('label');
                label.className = 'label cursor-pointer justify-start gap-2 py-1';
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.name = name;
                cb.value = it.id;
                cb.className = 'checkbox checkbox-sm multi-cb';
                cb.dataset.label = it.nom;
                cb.checked = k.has(String(it.id));
                const span = document.createElement('span');
                span.className = 'label-text';
                span.textContent = it.nom;
                label.append(cb, span);
                li.append(label);
                list.append(li);
            });
            api.search();
            api.refresh();
        },
    };

    list.addEventListener('change', (e) => {
        if (e.target.classList && e.target.classList.contains('multi-cb')) {
            api.refresh();
            onChange();
        }
    });
    if (filterInput) filterInput.addEventListener('input', api.search);
    if (checkVisibleBtn) {
        checkVisibleBtn.addEventListener('click', () => {
            list.querySelectorAll('li:not(.hidden) .multi-cb').forEach((c) => { c.checked = true; });
            api.refresh();
            onChange();
        });
    }
    if (uncheckAllBtn) {
        uncheckAllBtn.addEventListener('click', () => {
            boxes().forEach((c) => { c.checked = false; });
            api.refresh();
            onChange();
        });
    }
    document.addEventListener('click', (e) => {
        if (!dd.contains(e.target)) dd.removeAttribute('open');
    });

    api.refresh();
    return api;
}
