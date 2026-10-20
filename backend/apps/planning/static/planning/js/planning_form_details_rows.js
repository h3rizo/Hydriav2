(function () {
    function getMagasinsData() {
        return window.magasinsData || [];
    }

    function getComptesData() {
        return window.comptesData || [];
    }

    function getVillagesData() {
        return window.villagesData || [];
    }

    function addDetailRow() {
        const tbody = document.getElementById('details-tbody');
        if (!tbody) {
            return;
        }

        const newRow = document.createElement('tr');
        newRow.className = 'detail-row';
        newRow.innerHTML = `
            <td class="relative">
                <select name="equipement_id[]" class="select select-bordered select-sm w-32 equipement-select" onchange="handleEquipementChange(this)">
                    <option value="">-</option>
                </select>
                <span class="loading loading-spinner loading-xs equipement-loading hidden absolute right-1 top-2"></span>
            </td>
            <td class="relative">
                <select name="point_eau_id[]" class="select select-bordered select-sm w-32 point-eau-select" onchange="handlePointEauChange(this)">
                    <option value="">-</option>
                </select>
                <span class="loading loading-spinner loading-xs point-eau-loading hidden absolute right-1 top-2"></span>
            </td>
            <td>
                <select name="designation_id[]" class="select select-bordered select-sm w-48 designation-select" onchange="handleDesignationChange(this)">
                    <option value="">Selectionner</option>
                </select>
            </td>
            <td>
                <input type="number" name="quantity[]" class="input input-bordered input-sm w-20 quantity-input" step="0.01" value="1" onchange="calculateMontant(this)">
            </td>
            <td>
                <input type="number" name="pu[]" class="input input-bordered input-sm w-24 pu-input" step="0.01" onchange="calculateMontant(this)">
            </td>
            <td>
                <input type="number" name="montant[]" class="input input-bordered input-sm w-24 montant-input" step="0.01" readonly>
            </td>
            <td>
                <select name="magasin[]" class="select select-bordered select-sm w-32 magasin-select">
                    <option value="">-</option>
                    ${getMagasinsData().map(m => `<option value="${m.nom}">${m.nom.substring(0, 20)}</option>`).join('')}
                </select>
            </td>
            <td>
                <input type="text" name="acheteur[]" class="input input-bordered input-sm w-24">
            </td>
            <td>
                <select name="compte_id[]" class="select select-bordered select-sm w-32 compte-select">
                    <option value="">-</option>
                    ${getComptesData().map(c => `<option value="${c.id}">${c.nom.substring(0, 15)}</option>`).join('')}
                </select>
            </td>
            <td class="text-center">
                <input type="checkbox" name="trajet[]" class="checkbox checkbox-sm trajet-checkbox" onchange="handleTrajetChange(this)">
            </td>
            <td>
                <select name="point_a_id[]" class="select select-bordered select-sm w-32 point-a-select" onchange="handlePointAChange(this)" disabled>
                    <option value="">-</option>
                    ${getVillagesData().map(v => `<option value="${v.id}">${v.nom.substring(0, 15)}</option>`).join('')}
                </select>
            </td>
            <td>
                <select name="point_b_id[]" class="select select-bordered select-sm w-32 point-b-select" onchange="handlePointBChange(this)" disabled>
                    <option value="">-</option>
                </select>
            </td>
            <td>
                <select name="moyen_transport[]" class="select select-bordered select-sm w-24 transport-select" onchange="handleTransportChange(this)" disabled>
                    <option value="">-</option>
                    <option value="taxi-brousse">Taxi</option>
                    <option value="pirogue">Pirogue</option>
                    <option value="bac">Bac</option>
                </select>
            </td>
            <td>
                <button type="button" class="btn btn-ghost btn-xs text-error" onclick="removeDetailRow(this)">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
            </td>
        `;

        tbody.appendChild(newRow);

        const ouvrageId = document.getElementById('ouvrage')?.value || '';
        const equipementSelect = newRow.querySelector('.equipement-select');
        const pointEauSelect = newRow.querySelector('.point-eau-select');

        if (ouvrageId) {
            if (equipementSelect && typeof window.loadEquipementsByOuvrage === 'function') {
                window.loadEquipementsByOuvrage(ouvrageId, [equipementSelect]);
            }
            if (pointEauSelect && typeof window.loadPointsEauByOuvrage === 'function') {
                window.loadPointsEauByOuvrage(ouvrageId, [pointEauSelect]);
            }
        }

        updateTotal();
        if (typeof window.updatePaiementsCount === 'function') {
            window.updatePaiementsCount();
        }

        document.querySelectorAll('#paiements-tbody .point-eau-select').forEach(select => {
            if (select.value && typeof window.handlePaiementPointEauChange === 'function') {
                window.handlePaiementPointEauChange(select);
            }
        });
    }

    function removeDetailRow(button) {
        const tbody = document.getElementById('details-tbody');
        const row = button.closest('tr');
        if (!tbody || !row) {
            return;
        }

        if (tbody.querySelectorAll('tr').length > 1) {
            row.remove();
        } else {
            row.querySelectorAll('input, select').forEach(input => {
                input.value = '';
            });
        }

        updateTotal();
    }

    function calculateMontant(input) {
        const row = input.closest('tr');
        const quantity = parseFloat(row.querySelector('.quantity-input').value) || 0;
        const pu = parseFloat(row.querySelector('.pu-input').value) || 0;
        const montant = quantity * pu;

        row.querySelector('.montant-input').value = montant.toFixed(2);
        updateTotal();
    }

    function updateTotal() {
        const montants = document.querySelectorAll('.montant-input');
        let total = 0;

        montants.forEach(input => {
            total += parseFloat(input.value) || 0;
        });

        const totalElement = document.getElementById('total-montant');
        if (totalElement) {
            totalElement.textContent = total.toFixed(2);
        }
    }

    window.addDetailRow = addDetailRow;
    window.removeDetailRow = removeDetailRow;
    window.calculateMontant = calculateMontant;
    window.updateTotal = updateTotal;
})();
