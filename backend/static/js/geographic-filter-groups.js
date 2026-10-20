(function () {
    'use strict';

    const ENDPOINT = '/api/geographic-filter-hierarchy/';
    const HEADING_ATTR = 'data-geographic-group-heading';
    const collator = new Intl.Collator('fr', { sensitivity: 'base', numeric: true });

    function geographicLevel(select) {
        const rawName = String(select.name || '').toLowerCase().replace(/\[\]$/, '');
        const aliases = {
            region: ['region', 'regions', 'region_id', 'region_ids'],
            district: ['district', 'districts', 'district_id', 'district_ids'],
            commune: ['commune', 'communes', 'commune_id', 'commune_ids'],
            ouvrage: ['ouvrage', 'ouvrages', 'ouvrage_id', 'ouvrage_ids'],
        };
        return Object.keys(aliases).find((level) => aliases[level].includes(rawName)) || '';
    }

    function isFilterForm(form) {
        if (!form || form.dataset.geographicGrouping === 'off') return false;
        return String(form.getAttribute('method') || 'get').toLowerCase() === 'get';
    }

    function discoverGroups() {
        const groups = [];
        document.querySelectorAll('form').forEach((form) => {
            if (!isFilterForm(form)) return;
            const selects = {};
            form.querySelectorAll('select[name]').forEach((select) => {
                if (select.dataset.geographicGrouping === 'off') return;
                const level = geographicLevel(select);
                if (level && !selects[level]) selects[level] = select;
            });
            if (Object.keys(selects).length >= 2) groups.push({ form, selects });
        });
        return groups;
    }

    function isAllValue(value) {
        const normalized = String(value || '').trim().toLowerCase();
        return normalized === '' || normalized === 'all' || normalized === 'tous' || normalized === 'toutes';
    }

    function selectedValues(select) {
        if (!select) return [];
        return Array.from(select.selectedOptions || [])
            .map((option) => String(option.value || '').trim())
            .filter((value) => !isAllValue(value));
    }

    function selectableOptions(select) {
        return Array.from(select.options || []).filter((option) => {
            if (option.hasAttribute(HEADING_ATTR)) return false;
            if (!option.disabled) return true;
            const text = String(option.textContent || '').trim().toLowerCase();
            return !/^(──\s*)?(région|region|district|commune)\s*:/.test(text);
        });
    }

    function collectIds(groups) {
        const result = { district_ids: new Set(), commune_ids: new Set(), ouvrage_ids: new Set() };
        groups.forEach(({ selects }) => {
            ['district', 'commune', 'ouvrage'].forEach((level) => {
                const select = selects[level];
                if (!select) return;
                selectableOptions(select).forEach((option) => {
                    if (!isAllValue(option.value)) result[`${level}_ids`].add(String(option.value));
                });
            });
        });
        return {
            district_ids: Array.from(result.district_ids),
            commune_ids: Array.from(result.commune_ids),
            ouvrage_ids: Array.from(result.ouvrage_ids),
        };
    }

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content && meta.content !== 'NOTPROVIDED') return meta.content;
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function heading(label, depth) {
        const option = document.createElement('option');
        option.disabled = true;
        option.setAttribute(HEADING_ATTR, '1');
        option.textContent = `${'  '.repeat(depth)}${depth === 0 ? '── ' : ''}${label}${depth === 0 ? ' ──' : ''}`;
        return option;
    }

    function chooseOuvragePath(paths, active) {
        if (!Array.isArray(paths) || !paths.length) return null;
        return paths.find((path) => (
            (!active.region.length || active.region.includes(String(path.region_id))) &&
            (!active.district.length || active.district.includes(String(path.district_id))) &&
            (!active.commune.length || active.commune.includes(String(path.commune_id)))
        )) || paths[0];
    }

    function metadataFor(level, option, metadata, active) {
        const id = String(option.value || '');
        if (level === 'district') return metadata.districts[id] || null;
        if (level === 'commune') return metadata.communes[id] || null;
        if (level === 'ouvrage') return chooseOuvragePath(metadata.ouvrages[id], active);
        return null;
    }

    function renderGroupedSelect(select, level, metadata, active) {
        const originalOptions = selectableOptions(select);
        const specialOptions = originalOptions.filter((option) => isAllValue(option.value) || option.disabled);
        const candidates = originalOptions.filter((option) => !isAllValue(option.value) && !option.disabled);
        const mapped = [];
        const unmapped = [];

        candidates.forEach((option) => {
            const meta = metadataFor(level, option, metadata, active);
            if (meta) mapped.push({ option, meta });
            else unmapped.push(option);
        });
        if (!mapped.length) return;

        mapped.sort((left, right) => {
            for (const key of ['region', 'district', 'commune']) {
                const compared = collator.compare(left.meta[key] || '', right.meta[key] || '');
                if (compared) return compared;
            }
            return collator.compare(left.option.textContent || '', right.option.textContent || '');
        });

        const regionActive = active.region.length > 0;
        const districtActive = active.district.length > 0;
        const communeActive = active.commune.length > 0;
        const showRegion = level === 'district'
            ? !regionActive
            : level === 'commune'
                ? !(regionActive || districtActive)
                : !(regionActive || districtActive || communeActive);
        const showDistrict = level === 'commune'
            ? !districtActive
            : level === 'ouvrage' && !(districtActive || communeActive);
        const showCommune = level === 'ouvrage' && !communeActive;

        select.replaceChildren();
        specialOptions.forEach((option) => select.appendChild(option));

        let lastRegion = null;
        let lastDistrict = null;
        let lastCommune = null;
        mapped.forEach(({ option, meta }) => {
            const regionId = String(meta.region_id || meta.region || '');
            const districtId = String(meta.district_id || meta.district || '');
            const communeId = String(meta.commune_id || meta.commune || '');

            if (showRegion && regionId !== lastRegion) {
                select.appendChild(heading(`Région : ${meta.region || 'Sans région'}`, 0));
                lastDistrict = null;
                lastCommune = null;
            }
            if (showDistrict && districtId !== lastDistrict) {
                select.appendChild(heading(`District : ${meta.district || 'Sans district'}`, showRegion ? 1 : 0));
                lastCommune = null;
            }
            if (showCommune && communeId !== lastCommune) {
                select.appendChild(heading(`Commune : ${meta.commune || 'Sans commune'}`, (showRegion ? 1 : 0) + (showDistrict ? 1 : 0)));
            }
            select.appendChild(option);
            lastRegion = regionId;
            lastDistrict = districtId;
            lastCommune = communeId;
        });
        unmapped.forEach((option) => select.appendChild(option));
        select.dataset.geographicGrouped = '1';
    }

    async function initialize() {
        const groups = discoverGroups();
        if (!groups.length) return;
        const ids = collectIds(groups);
        if (!ids.district_ids.length && !ids.commune_ids.length && !ids.ouvrage_ids.length) return;

        try {
            const response = await fetch(ENDPOINT, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                },
                body: JSON.stringify(ids),
            });
            if (!response.ok) return;
            const metadata = await response.json();
            if (!metadata.success) return;

            groups.forEach(({ selects }) => {
                const active = {
                    region: selectedValues(selects.region),
                    district: selectedValues(selects.district),
                    commune: selectedValues(selects.commune),
                };
                ['district', 'commune', 'ouvrage'].forEach((level) => {
                    if (selects[level]) renderGroupedSelect(selects[level], level, metadata, active);
                });
            });
        } catch (error) {
            // The filters remain fully usable without grouping if metadata fails.
            console.debug('Regroupement géographique indisponible', error);
        }
    }

    if (document.readyState === 'loading' || document.readyState === 'interactive') {
        document.addEventListener('DOMContentLoaded', function () {
            // Let page-specific DOMContentLoaded handlers populate dependent lists first.
            window.setTimeout(initialize, 0);
        }, { once: true });
    } else {
        initialize();
    }
}());
