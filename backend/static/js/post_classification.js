/**
 * Classification transversale des postes (Type x Niveau).
 *
 * Source unique pour toutes les vues qui affichent ou filtrent la
 * classification d'un poste (grille salariale, vue matricielle, vue
 * graphique, formulaires). Ne pas dupliquer ces regles ailleurs.
 *
 * Principe visuel :
 *   - la COULEUR encode le TYPE de poste (Operationnel/Administratif/Soutien/Transversal)
 *   - l'INTENSITE du badge encode le NIVEAU (Execution = leger, Management = plein/marque)
 *
 * Expose window.PostClassification.
 */
(function (window) {
    'use strict';

    const TYPES = {
        // hex DOIT rester identique a la teinte Tailwind -600 utilisee par badgeSolid/dotClass
        // (bg-{couleur}-600), pour que la couleur du graphique et celle des badges soient
        // strictement la meme couleur, pas juste des teintes voisines.
        OPERATIONNEL: {
            code: 'OPERATIONNEL',
            label: 'Opérationnel',
            shortLabel: 'Opé.',
            // Bleu
            hex: '#2563eb', // = blue-600
            dotClass: 'bg-blue-600',
            textClass: 'text-blue-600 dark:text-blue-400',
            badgeLight: 'bg-blue-100 text-blue-700 border border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800',
            badgeSolid: 'bg-blue-600 text-white dark:bg-blue-600',
        },
        ADMINISTRATIF: {
            code: 'ADMINISTRATIF',
            label: 'Administratif',
            shortLabel: 'Admin.',
            // Violet
            hex: '#7c3aed', // = violet-600
            dotClass: 'bg-violet-600',
            textClass: 'text-violet-600 dark:text-violet-400',
            badgeLight: 'bg-violet-100 text-violet-700 border border-violet-200 dark:bg-violet-950 dark:text-violet-300 dark:border-violet-800',
            badgeSolid: 'bg-violet-600 text-white dark:bg-violet-600',
        },
        SOUTIEN: {
            code: 'SOUTIEN',
            label: 'Soutien',
            shortLabel: 'Soutien',
            // Gris / slate
            hex: '#475569', // = slate-600
            dotClass: 'bg-slate-600',
            textClass: 'text-slate-600 dark:text-slate-400',
            badgeLight: 'bg-slate-100 text-slate-700 border border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600',
            badgeSolid: 'bg-slate-600 text-white dark:bg-slate-600',
        },
        TRANSVERSAL: {
            code: 'TRANSVERSAL',
            label: 'Transversal',
            shortLabel: 'Transv.',
            // Teal / turquoise
            hex: '#0d9488', // = teal-600
            dotClass: 'bg-teal-600',
            textClass: 'text-teal-600 dark:text-teal-400',
            badgeLight: 'bg-teal-100 text-teal-700 border border-teal-200 dark:bg-teal-950 dark:text-teal-300 dark:border-teal-800',
            badgeSolid: 'bg-teal-600 text-white dark:bg-teal-600',
        },
    };

    const NIVEAUX = {
        EXECUTION: {
            code: 'EXECUTION',
            label: 'Exécution',
            shortLabel: 'Exéc.',
            symbol: '◌',
            // Rendu leger : reutilise badgeLight du type
            weightClass: 'font-normal',
            variant: 'light',
        },
        MANAGEMENT: {
            code: 'MANAGEMENT',
            label: 'Management',
            shortLabel: 'Mgmt',
            symbol: '●',
            // Rendu marque : reutilise badgeSolid du type, semi-bold
            weightClass: 'font-semibold',
            variant: 'solid',
        },
    };

    const TYPE_ORDER = ['OPERATIONNEL', 'ADMINISTRATIF', 'SOUTIEN', 'TRANSVERSAL'];
    const NIVEAU_ORDER = ['EXECUTION', 'MANAGEMENT'];

    // Styles de trait (Chart.js borderDash) pour distinguer plusieurs postes
    // PARTAGEANT LE MEME TYPE (donc la meme couleur) sur le nuage de points.
    // Ne PAS utiliser comme systeme de couleur : uniquement un style de ligne.
    const LINE_DASH_PATTERNS = [
        [],           // trait plein (1er poste du type)
        [6, 3],       // tirets
        [2, 2],       // pointille
        [8, 3, 2, 3], // tiret-point
    ];

    /** Style de trait cyclique, a utiliser par index de poste AU SEIN DE SON TYPE. */
    function lineDashPattern(indexWithinType) {
        return LINE_DASH_PATTERNS[(indexWithinType || 0) % LINE_DASH_PATTERNS.length];
    }

    function getType(code) {
        return (code && TYPES[code]) || null;
    }

    function getNiveau(code) {
        return (code && NIVEAUX[code]) || null;
    }

    /** Couleur hex du point dans le nuage de points (= couleur du type, gris si non classe). */
    function chartColor(typeCode) {
        const type = getType(typeCode);
        return type ? type.hex : '#94a3b8';
    }

    /**
     * Rayon du point selon le niveau (Management legerement plus grand),
     * et epaisseur de contour (Management plus marque). Utilise par Chart.js.
     */
    function chartPointStyle(niveauCode) {
        if (niveauCode === 'MANAGEMENT') {
            return { radius: 7, hoverRadius: 9, borderWidth: 2 };
        }
        return { radius: 5, hoverRadius: 7, borderWidth: 1 };
    }

    /** Classes Tailwind du badge Type (couleur pleine, toujours "solide" pour le badge de type). */
    function typeBadgeClass(typeCode) {
        const type = getType(typeCode);
        if (!type) return 'bg-base-200 text-base-content/50 border border-base-300';
        return type.badgeLight;
    }

    /**
     * Classe de texte (montant, valeur) coloree selon le TYPE de poste. Utilisee
     * par ex. pour le salaire affiche dans une cellule de la matrice, afin que le
     * montant partage la meme couleur que les badges de classification du poste.
     */
    function textClass(typeCode) {
        const type = getType(typeCode);
        return type ? type.textClass : 'text-base-content/70';
    }

    /**
     * Classes du badge Employe dans la matrice : couleur du TYPE de poste
     * (comme les autres badges), avec un anneau d'alerte (ring) distinct si
     * incoherent (ecart entre stade estime et stade declare en evaluation).
     * L'alerte reste visible SANS remplacer la couleur de classification.
     */
    function employeeBadgeClass(typeCode, coherent) {
        const base = typeBadgeClass(typeCode);
        return coherent ? base : `${base} ring-2 ring-warning ring-offset-1 ring-offset-base-100`;
    }

    /**
     * Classes du badge Niveau : reprend la couleur du TYPE associe (pas une
     * couleur independante), avec un rendu leger (Execution) ou plein
     * (Management), conformement au principe "couleur=type, intensite=niveau".
     */
    function niveauBadgeClass(typeCode, niveauCode) {
        const type = getType(typeCode);
        const niveau = getNiveau(niveauCode);
        if (!type || !niveau) return 'bg-base-200 text-base-content/50 border border-base-300';
        return niveau.variant === 'solid' ? type.badgeSolid : type.badgeLight;
    }

    function typeLabel(typeCode) {
        const type = getType(typeCode);
        return type ? type.label : 'Non classé';
    }

    function niveauLabel(niveauCode) {
        const niveau = getNiveau(niveauCode);
        return niveau ? niveau.label : 'Non classé';
    }

    /** Libelle combine pour tooltips/titres ("Opérationnel · Management"). */
    function combinedLabel(typeCode, niveauCode) {
        if (!typeCode && !niveauCode) return 'Non classé';
        return `${typeLabel(typeCode)} · ${niveauLabel(niveauCode)}`;
    }

    window.PostClassification = {
        TYPES,
        NIVEAUX,
        TYPE_ORDER,
        NIVEAU_ORDER,
        getType,
        getNiveau,
        chartColor,
        chartPointStyle,
        lineDashPattern,
        typeBadgeClass,
        niveauBadgeClass,
        textClass,
        employeeBadgeClass,
        typeLabel,
        niveauLabel,
        combinedLabel,
    };
})(window);
