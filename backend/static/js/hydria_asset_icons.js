(function (global) {
    'use strict';

    function normalize(value) {
        return String(value || '')
            .trim()
            .toLocaleLowerCase('fr-FR')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '');
    }

    function includesAny(value, terms) {
        return terms.some((term) => value.includes(term));
    }

    function point(value) {
        const name = normalize(value);
        if (name.includes('kiosque')) return { icon: 'fa-store', tone: 'text-info', color: '#0891b2' };
        if (name === 'bi' || name.startsWith('bi ') || includesAny(name, ['borne', ' bi ', 'bi volume'])) {
            return { icon: 'fa-faucet', tone: 'text-primary', color: '#0284c7' };
        }
        if (name === 'bp' || name.startsWith('bp ') || includesAny(name, ['branchement', 'prive'])) {
            return { icon: 'fa-home', tone: 'text-success', color: '#16a34a' };
        }
        return { icon: 'fa-tint', tone: 'text-base-content/50', color: '#64748b' };
    }

    function equipment(value) {
        const name = normalize(value);
        const mappings = [
            [['citerne', 'reservoir', 'bache', 'chateau'], 'fa-database', 'text-info', '#0891b2'],
            [['compteur', 'debitmetre', 'manometre'], 'fa-tachometer-alt', 'text-primary', '#2563eb'],
            [['vanne', 'robinet', 'clapet'], 'fa-sliders-h', 'text-primary', '#2563eb'],
            [['filtre', 'traitement', 'chloration', 'chlorateur'], 'fa-filter', 'text-success', '#16a34a'],
            [['pompe', 'surpresseur', 'motopompe'], 'fa-cogs', 'text-base-content/60', '#475569'],
            [['conduite', 'canalisation', 'tuyau', 'collecteur'], 'fa-project-diagram', 'text-base-content/60', '#475569'],
            [['solaire', 'panneau'], 'fa-solar-panel', 'text-success', '#16a34a'],
            [['groupe', 'generateur', 'electrique'], 'fa-bolt', 'text-warning', '#d97706'],
            [['captage', 'source', 'forage', 'puits'], 'fa-water', 'text-info', '#0891b2'],
        ];
        for (const [terms, icon, tone, color] of mappings) {
            if (includesAny(name, terms)) return { icon, tone, color };
        }
        return { icon: 'fa-cog', tone: 'text-base-content/60', color: '#64748b' };
    }

    function ouvrage(value) {
        const name = normalize(value);
        if (includesAny(name, ['suspendu', 'suspend'])) return { icon: 'fa-pause', tone: 'text-error', color: '#dc2626' };
        if (name.includes('potentiel')) return { icon: 'fa-lightbulb', tone: 'text-warning', color: '#d97706' };
        if (includesAny(name, ['travaux', 'chantier'])) return { icon: 'fa-person-digging', tone: 'text-warning', color: '#d97706' };
        if (name.includes('bureau')) return { icon: 'fa-building', tone: 'text-base-content/60', color: '#64748b' };
        if (name.includes('terrain')) return { icon: 'fa-map-location-dot', tone: 'text-base-content/60', color: '#64748b' };
        if (includesAny(name, ['forage', 'puits', 'pmh'])) return { icon: 'fa-water', tone: 'text-info', color: '#0891b2' };
        if (includesAny(name, ['eau vive', 'traditionnelle'])) return { icon: 'fa-wave-square', tone: 'text-info', color: '#0891b2' };
        if (name.includes('aepp')) return { icon: 'fa-faucet-drip', tone: 'text-primary', color: '#2563eb' };
        if (includesAny(name, ['aepg', 'ranontsika', 'sam'])) return { icon: 'fa-droplet', tone: 'text-primary', color: '#2563eb' };
        return { icon: 'fa-water', tone: 'text-primary', color: '#2563eb' };
    }

    function iconHtml(definition, title, extraClass) {
        const safeTitle = String(title || '').replace(/[&<>'"]/g, (character) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
        })[character]);
        return `<i class="fas ${definition.icon} ${definition.tone} ${extraClass || ''}" title="${safeTitle}" aria-hidden="true"></i>`;
    }

    global.HydriaAssetIcons = Object.freeze({ point, equipment, ouvrage, iconHtml });
})(window);
