/**
 * Toggles des tableaux de recouvrement volumetrique, partages par les 3 pages
 * /plannings/volumetrique/ (matriciel), /details/ et /global/.
 *
 * Contrat cote template (sur un ou plusieurs conteneurs `.js-volume-recouvrement-table`) :
 *   - colonnes de mois : <th>/<td> avec data-volume-month="<n>"
 *   - mois "solde" (total du mois a 100% pour le filtre actif) : le <th> porte
 *     en plus la classe .js-volume-month-settled
 *   - colonne + sous-colonnes de synthese du mois en cours : attribut
 *     data-current-month-col (sur <th> ET <td>)
 *   - lignes point d'eau / ouvrage :
 *       <tr data-point-settled-past="1">      plus d'impaye sur les mois passes
 *       <tr data-point-settled-current="1">   plus d'impaye sur le mois en cours
 *     (attribut -current optionnel ; absent = considere non solde en cours)
 *   - en-tetes de regroupement (parcelle) :
 *       <tr data-parcelle-group="<id>">  et  <tr data-parcelle-row="<id>"> sur
 *       chaque ligne du groupe -> l'en-tete se masque si le groupe est vide.
 *
 * Interrupteurs (coches par defaut) :
 *   #toggle-hide-current-month   -> masque data-current-month-col
 *   #toggle-hide-settled-months  -> masque les colonnes de mois a 100%
 *   #toggle-hide-settled-points  -> masque les lignes soldees. "Solde" =
 *       plus d'impaye sur les mois passes ET (mois en cours masque OU plus
 *       d'impaye sur le mois en cours) : une ligne dont le seul reste a traiter
 *       est dans le mois en cours disparait aussi quand ce mois est masque.
 */
(function () {
    'use strict';

    function isChecked(id) {
        var el = document.getElementById(id);
        return el ? !!el.checked : false;
    }

    function applyVolumeRecouvrementToggles() {
        var hideCurrent = isChecked('toggle-hide-current-month');
        var hideSettledMonths = isChecked('toggle-hide-settled-months');
        var hideSettledPoints = isChecked('toggle-hide-settled-points');

        var tables = document.querySelectorAll('.js-volume-recouvrement-table');
        if (!tables.length) return;

        tables.forEach(function (table) {
            var settledMonths = {};
            table.querySelectorAll('th.js-volume-month-settled[data-volume-month]').forEach(function (th) {
                settledMonths[th.getAttribute('data-volume-month')] = true;
            });

            table.querySelectorAll('[data-volume-month]').forEach(function (el) {
                var n = el.getAttribute('data-volume-month');
                var isCurrent = el.hasAttribute('data-current-month-col');
                // Boolean() indispensable : `hideSettledMonths && settledMonths[n]`
                // vaut `undefined` pour un mois non soldé, et
                // classList.toggle(cls, undefined) *bascule* au lieu de forcer.
                var hide = Boolean(
                    (hideCurrent && isCurrent) || (hideSettledMonths && settledMonths[n])
                );
                el.classList.toggle('hidden', hide);
            });

            table.querySelectorAll('[data-current-month-col]:not([data-volume-month])').forEach(function (el) {
                el.classList.toggle('hidden', Boolean(hideCurrent));
            });

            table.querySelectorAll('tr[data-point-settled-past]').forEach(function (tr) {
                var pastSettled = tr.getAttribute('data-point-settled-past') === '1';
                var currentSettled = tr.getAttribute('data-point-settled-current') === '1';
                var rowSettled = pastSettled && (hideCurrent || currentSettled);
                tr.classList.toggle('hidden', Boolean(hideSettledPoints && rowSettled));
            });

            // Masquer les en-tetes de regroupement (parcelle / ouvrage / district)
            // devenus vides. La valeur (id ou nom) ne contient jamais de
            // guillemet : concatenation directe dans le selecteur d'attribut.
            table.querySelectorAll('tr[data-parcelle-group]').forEach(function (header) {
                var g = header.getAttribute('data-parcelle-group');
                var visibleRow = table.querySelector(
                    'tr[data-parcelle-row="' + g + '"]:not(.hidden)'
                );
                header.classList.toggle('hidden', !visibleRow);
            });
        });

        // Blocs "une table par parcelle" (page d'impression) : masquer le bloc
        // entier (banniere + table) quand toutes ses lignes sont masquees.
        document.querySelectorAll('[data-volume-parcelle-block]').forEach(function (block) {
            var visibleRow = block.querySelector('tbody tr[data-point-settled-past]:not(.hidden)');
            block.classList.toggle('hidden', !visibleRow);
        });
    }

    // Expose pour les onchange="applyVolumeRecouvrementToggles()" du markup.
    window.applyVolumeRecouvrementToggles = applyVolumeRecouvrementToggles;

    // Appliquer l'état par défaut des interrupteurs dès que le DOM est prêt
    // (le script peut être injecté après DOMContentLoaded selon la page).
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', applyVolumeRecouvrementToggles);
    } else {
        applyVolumeRecouvrementToggles();
    }
})();
