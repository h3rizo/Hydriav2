/**
 * consolidated_grouping.js
 *
 * Gestion du regroupement hiérarchique pour les pages consolidées
 * (Points d'eau et Équipements)
 *
 * Hiérarchie : Région → District → Commune → Ouvrage
 */

// État global pour stocker les données groupées
let groupedData = {};
let currentExpandedGroups = new Set();

/**
 * Groupe les données de manière hiérarchique
 * @param {Array} data - Tableau de données à grouper
 * @param {Array} keys - Clés de regroupement ['region', 'district', 'commune', 'ouvrage']
 * @returns {Object} Arbre hiérarchique avec compteurs
 */
function groupDataHierarchically(data, keys = ['region', 'district', 'commune', 'ouvrage']) {
    const tree = {};

    data.forEach(item => {
        let currentLevel = tree;

        // Parcourir chaque niveau de la hiérarchie
        keys.forEach((key, index) => {
            const value = item[key] || 'Non défini';

            // Initialiser le groupe s'il n'existe pas
            if (!currentLevel[value]) {
                currentLevel[value] = {
                    count: 0,
                    items: []
                };

                // Ajouter un niveau enfant si ce n'est pas le dernier
                if (index < keys.length - 1) {
                    currentLevel[value].children = {};
                }
            }

            // Incrémenter le compteur
            currentLevel[value].count++;

            // Si c'est le dernier niveau (ouvrage), ajouter l'item
            if (index === keys.length - 1) {
                currentLevel[value].items.push(item);
            } else {
                // Descendre au niveau suivant
                currentLevel = currentLevel[value].children;
            }
        });
    });

    return tree;
}

/**
 * Génère un ID unique pour un groupe
 * @param {Array} path - Chemin du groupe ['region', 'district', ...]
 * @returns {String} ID unique
 */
function generateGroupId(path) {
    return 'group-' + path.map(p => p.replace(/\s+/g, '-')).join('-');
}

/**
 * Charge l'état des groupes depuis localStorage
 */
function loadGroupState() {
    const saved = localStorage.getItem('consolidatedGroupState');
    if (saved) {
        try {
            const parsed = JSON.parse(saved);
            currentExpandedGroups = new Set(parsed);
        } catch (e) {
            console.error('Erreur lors du chargement de l\'état des groupes:', e);
            currentExpandedGroups = new Set();
        }
    }
}

/**
 * Sauvegarde l'état des groupes dans localStorage
 */
function saveGroupState() {
    localStorage.setItem('consolidatedGroupState', JSON.stringify([...currentExpandedGroups]));
}

/**
 * Bascule l'état d'un groupe (ouvert/fermé)
 * @param {String} groupId - ID du groupe
 */
function toggleGroup(groupId) {
    const collapseElement = document.getElementById(groupId);
    if (!collapseElement) return;

    const isExpanded = currentExpandedGroups.has(groupId);

    if (isExpanded) {
        currentExpandedGroups.delete(groupId);
        collapseElement.removeAttribute('open');
    } else {
        currentExpandedGroups.add(groupId);
        collapseElement.setAttribute('open', '');
    }

    saveGroupState();
}

/**
 * Génère le HTML pour un en-tête de groupe collapsible
 * @param {String} label - Libellé du groupe
 * @param {Number} count - Nombre d'éléments dans le groupe
 * @param {Number} level - Niveau de profondeur (0=Région, 1=District, etc.)
 * @param {String} groupId - ID unique du groupe
 * @returns {String} HTML de l'en-tête
 */
function renderGroupHeader(label, count, level, groupId) {
    const colors = ['primary', 'secondary', 'accent', 'info'];
    const icons = ['fa-map', 'fa-map-marker-alt', 'fa-building', 'fa-tint'];
    const color = colors[level] || 'neutral';
    const icon = icons[level] || 'fa-folder';
    const indent = level * 2; // Indentation en rem

    const isExpanded = currentExpandedGroups.has(groupId);
    const openAttr = isExpanded ? 'open' : '';

    return `
        <details class="collapse collapse-arrow bg-base-200 mb-2" id="${groupId}" ${openAttr}>
            <summary class="collapse-title text-${color}-content bg-${color} font-semibold cursor-pointer flex items-center"
                     style="padding-left: ${indent}rem;"
                     onclick="toggleGroup('${groupId}')">
                <i class="fas ${icon} mr-2"></i>
                <span>${label}</span>
                <span class="badge badge-${color} badge-sm ml-2">${count}</span>
            </summary>
            <div class="collapse-content" id="${groupId}-content">
                <!-- Contenu inséré dynamiquement -->
            </div>
        </details>
    `;
}

/**
 * Rend récursivement l'arbre hiérarchique en HTML
 * @param {Object} tree - Arbre de données
 * @param {Number} level - Niveau actuel (0-3)
 * @param {Array} path - Chemin actuel dans l'arbre
 * @param {Function} renderItemCallback - Fonction pour rendre un item final
 * @returns {String} HTML complet
 */
function renderGroupedTree(tree, level = 0, path = [], renderItemCallback) {
    let html = '';

    const sortedKeys = Object.keys(tree).sort();

    sortedKeys.forEach(key => {
        const node = tree[key];
        const currentPath = [...path, key];
        const groupId = generateGroupId(currentPath);

        // Créer l'en-tête du groupe
        html += renderGroupHeader(key, node.count, level, groupId);

        // Contenu du groupe
        let contentHtml = '';

        if (node.children) {
            // Il y a des sous-groupes, récursion
            contentHtml = renderGroupedTree(
                node.children,
                level + 1,
                currentPath,
                renderItemCallback
            );
        } else if (node.items && node.items.length > 0) {
            // Niveau final : afficher les items
            contentHtml = '<div class="overflow-x-auto">';
            contentHtml += '<table class="table table-zebra table-sm w-full">';

            // En-tête du tableau (sans colonnes Région, District, Commune, Ouvrage)
            contentHtml += renderItemCallback.header();

            // Corps du tableau
            contentHtml += '<tbody>';
            node.items.forEach((item, index) => {
                contentHtml += renderItemCallback.row(item, index);
            });
            contentHtml += '</tbody></table></div>';
        }

        // Injecter le contenu après avoir créé l'en-tête
        html = html.replace(
            `<div class="collapse-content" id="${groupId}-content">`,
            `<div class="collapse-content" id="${groupId}-content">${contentHtml}`
        );
    });

    return html;
}

/**
 * Filtre les données groupées selon un terme de recherche
 * @param {Object} tree - Arbre de données
 * @param {String} searchTerm - Terme de recherche
 * @param {Function} matchCallback - Fonction pour tester si un item correspond
 * @returns {Object} Arbre filtré
 */
function filterGroupedData(tree, searchTerm, matchCallback) {
    if (!searchTerm || searchTerm.trim() === '') {
        return tree;
    }

    const term = searchTerm.toLowerCase().trim();
    const filtered = {};

    function filterNode(node, key) {
        const newNode = {
            count: 0,
            items: []
        };

        if (node.children) {
            newNode.children = {};

            Object.keys(node.children).forEach(childKey => {
                const filteredChild = filterNode(node.children[childKey], childKey);
                if (filteredChild && filteredChild.count > 0) {
                    newNode.children[childKey] = filteredChild;
                    newNode.count += filteredChild.count;
                }
            });

            return newNode.count > 0 ? newNode : null;
        } else if (node.items) {
            newNode.items = node.items.filter(item => matchCallback(item, term));
            newNode.count = newNode.items.length;

            return newNode.count > 0 ? newNode : null;
        }

        return null;
    }

    Object.keys(tree).forEach(key => {
        const filteredNode = filterNode(tree[key], key);
        if (filteredNode && filteredNode.count > 0) {
            filtered[key] = filteredNode;
        }
    });

    return filtered;
}

/**
 * Développe automatiquement tous les groupes contenant des résultats de recherche
 * @param {Object} tree - Arbre de données
 * @param {Array} path - Chemin actuel
 */
function autoExpandSearchResults(tree, path = []) {
    Object.keys(tree).forEach(key => {
        const node = tree[key];
        const currentPath = [...path, key];
        const groupId = generateGroupId(currentPath);

        // Ajouter à l'ensemble des groupes développés
        currentExpandedGroups.add(groupId);

        // Récursion pour les enfants
        if (node.children) {
            autoExpandSearchResults(node.children, currentPath);
        }
    });

    saveGroupState();
}

/**
 * Développe tous les groupes
 */
function expandAll() {
    document.querySelectorAll('details.collapse').forEach(detail => {
        detail.setAttribute('open', '');
        currentExpandedGroups.add(detail.id);
    });
    saveGroupState();
}

/**
 * Ferme tous les groupes
 */
function collapseAll() {
    document.querySelectorAll('details.collapse').forEach(detail => {
        detail.removeAttribute('open');
    });
    currentExpandedGroups.clear();
    saveGroupState();
}

/**
 * Initialise le système de regroupement
 */
function initializeGrouping() {
    loadGroupState();

    // Ajouter des boutons Développer tout / Réduire tout
    const controlsHtml = `
        <div class="flex gap-2 mb-4">
            <button onclick="expandAll()" class="btn btn-sm btn-outline btn-primary">
                <i class="fas fa-plus-circle mr-1"></i>
                Développer tout
            </button>
            <button onclick="collapseAll()" class="btn btn-sm btn-outline btn-secondary">
                <i class="fas fa-minus-circle mr-1"></i>
                Réduire tout
            </button>
        </div>
    `;

    const container = document.getElementById('grouping-controls');
    if (container) {
        container.innerHTML = controlsHtml;
    }
}

// Initialiser au chargement du DOM
document.addEventListener('DOMContentLoaded', initializeGrouping);