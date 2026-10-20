(function () {
    let monthlyPreviewAbortController = null;
    let monthlyPreviewDebounceTimer = null;

    function getPlanningFormConfig() {
        return window.planningFormConfig || {};
    }

    function escapeHtml(value) {
        if (value === null || value === undefined) {
            return '';
        }
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function getSelectedOptionText(selectElement) {
        if (!selectElement || !selectElement.value) {
            return '';
        }
        const selected = selectElement.options[selectElement.selectedIndex];
        return selected ? (selected.textContent || '').trim() : '';
    }

    function getCurrentPreviewMonth() {
        const dateInput = document.querySelector('input[name="date_planning"]');
        if (dateInput && dateInput.value && dateInput.value.length >= 7) {
            return dateInput.value.slice(0, 7);
        }
        const now = new Date();
        return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    }

    function isoToDateLabel(isoDate) {
        if (!isoDate || isoDate.length < 10) {
            return '-';
        }
        const parts = isoDate.slice(0, 10).split('-');
        if (parts.length !== 3) {
            return isoDate;
        }
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }

    function monthToLabel(monthValue) {
        if (!monthValue || monthValue.length < 7) {
            return '';
        }
        const parts = monthValue.split('-');
        if (parts.length !== 2) {
            return monthValue;
        }
        const monthNames = [
            'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre'
        ];
        const monthIndex = parseInt(parts[1], 10) - 1;
        if (monthIndex < 0 || monthIndex > 11) {
            return monthValue;
        }
        return `${monthNames[monthIndex]} ${parts[0]}`;
    }

    function getDraftMonthlyPreviewRow(expectedMonth) {
        const employeSelect = document.getElementById('employe');
        const dateInput = document.querySelector('input[name="date_planning"]');
        if (!employeSelect || !employeSelect.value || !dateInput || !dateInput.value) {
            return null;
        }

        const draftDate = dateInput.value.slice(0, 10);
        if (!draftDate || (expectedMonth && draftDate.slice(0, 7) !== expectedMonth)) {
            return null;
        }

        const activiteSelect = document.getElementById('activite');
        const typeActiviteSelect = document.getElementById('type_activite');
        const ouvrageInput = document.getElementById('ouvrage-search');
        const remarqueInput = document.querySelector('textarea[name="remarque"]');

        const activiteLabel = getSelectedOptionText(activiteSelect) || getSelectedOptionText(typeActiviteSelect) || 'Activite en cours';
        const ouvrageLabel = ouvrageInput && ouvrageInput.value ? ouvrageInput.value.trim() : '-';

        return {
            id: '__draft__',
            date: draftDate,
            date_label: isoToDateLabel(draftDate),
            activite: activiteLabel,
            ouvrage: ouvrageLabel,
            statut: 'brouillon',
            statut_label: 'Brouillon',
            validation: false,
            validation_label: 'Non enregistre',
            remarque: remarqueInput ? remarqueInput.value.trim() : '',
            is_draft: true,
        };
    }

    function getMonthlyStatusBadgeClass(row) {
        if (row && row.is_draft) {
            return 'badge-outline';
        }
        const statut = (row && row.statut ? row.statut : '').toLowerCase();
        if (statut === 'termine') return 'badge-success';
        if (statut === 'annule') return 'badge-error';
        if (statut === 'reporte') return 'badge-warning';
        if (statut === 'en_cours') return 'badge-info';
        return 'badge-ghost';
    }

    function renderMonthlyPreviewRows(rows, monthValue) {
        const tbody = document.getElementById('monthly-preview-body');
        const meta = document.getElementById('monthly-preview-meta');
        const employeSelect = document.getElementById('employe');
        if (!tbody) {
            return;
        }

        const previewRows = Array.isArray(rows) ? rows.slice() : [];
        const draftRow = getDraftMonthlyPreviewRow(monthValue);
        if (draftRow) {
            previewRows.push(draftRow);
        }

        previewRows.sort((a, b) => {
            const dateA = (a && a.date) ? a.date : '';
            const dateB = (b && b.date) ? b.date : '';
            if (dateA === dateB) {
                const draftWeightA = a && a.is_draft ? 1 : 0;
                const draftWeightB = b && b.is_draft ? 1 : 0;
                return draftWeightA - draftWeightB;
            }
            return dateA.localeCompare(dateB);
        });

        if (meta && employeSelect && employeSelect.value) {
            const employeeLabel = getSelectedOptionText(employeSelect) || 'Employe';
            const monthLabel = monthToLabel(monthValue);
            const savedCount = Array.isArray(rows) ? rows.length : 0;
            const savedSuffix = savedCount > 1 ? 's' : '';
            meta.textContent = `${employeeLabel} - ${monthLabel} (${savedCount} enregistre${savedSuffix})`;
        } else if (meta) {
            meta.textContent = '';
        }

        if (!previewRows.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center py-5 text-base-content/60">
                        Aucun planning pour cet employe sur ce mois.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = previewRows.map(row => {
            const statusClass = getMonthlyStatusBadgeClass(row);
            const validationClass = row.validation ? 'badge-success' : (row.is_draft ? 'badge-outline' : 'badge-ghost');
            const remarqueHtml = row.remarque ? `<div class="text-xs text-base-content/60 mt-1">${escapeHtml(row.remarque)}</div>` : '';

            return `
                <tr class="${row.is_draft ? 'bg-base-200/60' : ''}">
                    <td class="whitespace-nowrap">${escapeHtml(row.date_label || isoToDateLabel(row.date || ''))}</td>
                    <td>
                        <div>${escapeHtml(row.activite || '-')}</div>
                        ${remarqueHtml}
                    </td>
                    <td>${escapeHtml(row.ouvrage || '-')}</td>
                    <td><span class="badge badge-sm ${statusClass}">${escapeHtml(row.statut_label || '-')}</span></td>
                    <td><span class="badge badge-sm ${validationClass}">${escapeHtml(row.validation_label || '-')}</span></td>
                </tr>
            `;
        }).join('');
    }

    function setMonthlyPreviewLoading() {
        const tbody = document.getElementById('monthly-preview-body');
        if (!tbody) {
            return;
        }
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center py-5 text-base-content/60">
                    Chargement...
                </td>
            </tr>
        `;
    }

    function scheduleMonthlyPreviewRefresh() {
        if (monthlyPreviewDebounceTimer) {
            clearTimeout(monthlyPreviewDebounceTimer);
        }
        monthlyPreviewDebounceTimer = setTimeout(() => {
            refreshMonthlyPreview();
        }, 250);
    }

    async function refreshMonthlyPreview() {
        const employeSelect = document.getElementById('employe');
        const tbody = document.getElementById('monthly-preview-body');
        if (!tbody || !employeSelect) {
            return;
        }

        const employeId = (employeSelect.value || '').trim();
        const monthValue = getCurrentPreviewMonth();
        if (!employeId) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center py-5 text-base-content/60">
                        Selectionnez un employe pour afficher son planning mensuel.
                    </td>
                </tr>
            `;
            const meta = document.getElementById('monthly-preview-meta');
            if (meta) {
                meta.textContent = '';
            }
            return;
        }

        setMonthlyPreviewLoading();

        if (monthlyPreviewAbortController) {
            monthlyPreviewAbortController.abort();
        }
        monthlyPreviewAbortController = new AbortController();

        const config = getPlanningFormConfig();
        if (!config.apiEmployeeMonthPreviewUrl) {
            return;
        }

        const params = new URLSearchParams({
            employe_id: employeId,
            month: monthValue,
        });
        if (config.currentPlanningId) {
            params.set('exclude_planning_id', config.currentPlanningId);
        }

        try {
            const response = await fetch(`${config.apiEmployeeMonthPreviewUrl}?${params.toString()}`, {
                signal: monthlyPreviewAbortController.signal,
            });
            const payload = await response.json();

            if (!response.ok) {
                throw new Error((payload && payload.error) ? payload.error : 'Erreur de chargement');
            }

            const rows = payload && Array.isArray(payload.rows) ? payload.rows : [];
            renderMonthlyPreviewRows(rows, monthValue);
        } catch (error) {
            if (error && error.name === 'AbortError') {
                return;
            }
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center py-5 text-error">
                        Impossible de charger l'apercu mensuel.
                    </td>
                </tr>
            `;
        }
    }

    function updatePlanningQuickLinks() {
        const employeSelect = document.getElementById('employe');
        const status = document.getElementById('planning-quick-links-status');
        const employeId = employeSelect ? (employeSelect.value || '').trim() : '';
        const employeLabel = employeSelect && employeSelect.selectedIndex >= 0
            ? (employeSelect.options[employeSelect.selectedIndex]?.text || '').trim()
            : '';

        document.querySelectorAll('[data-base-url]').forEach((link) => {
            const baseUrl = link.dataset.baseUrl || '#';
            const requiresEmploye = link.dataset.requiresEmploye === '1';
            const paramName = link.dataset.prefillParam || 'employe_id';

            if (requiresEmploye && !employeId) {
                link.href = baseUrl;
                link.classList.add('pointer-events-none', 'opacity-50');
                link.setAttribute('aria-disabled', 'true');
                link.setAttribute('tabindex', '-1');
                return;
            }

            const url = new URL(baseUrl, window.location.origin);
            if (employeId) {
                url.searchParams.set(paramName, employeId);
            }
            link.href = `${url.pathname}${url.search}`;
            link.classList.remove('pointer-events-none', 'opacity-50');
            link.removeAttribute('aria-disabled');
            link.removeAttribute('tabindex');
        });

        if (status) {
            status.textContent = employeId && employeLabel
                ? `Acces RH pre-filtres pour ${employeLabel}.`
                : 'Selectionnez un employe pour activer les acces pre-filtres.';
        }
    }

    window.getSelectedOptionText = getSelectedOptionText;
    window.scheduleMonthlyPreviewRefresh = scheduleMonthlyPreviewRefresh;
    window.refreshMonthlyPreview = refreshMonthlyPreview;
    window.updatePlanningQuickLinks = updatePlanningQuickLinks;
})();
