
document.addEventListener('alpine:init', () => {
    Alpine.data('revalorisationApp', () => ({
        selectedYear: '2026',
        selectedOrganisationId: 'org-1',
        organisations: [],
        employes: [],
        groupedEmployesData: [],
        selectedPosteIds: [],
        posteFilterInitialized: false,
        loading: false,
        saving: false,
        savingEmployee: false,
        loadingHistory: false,
        loadingEvaluation: false,
        loadingEvaluationResultats: false,
        errorMessage: '',
        successMessage: '',
        _successTimeout: null,
        currentEmp: null,
        history: [],
        evaluationError: '',
        evaluationSummary: null,
        evaluationDetails: [],
        evaluationResultatsError: '',
        evaluationResultatsSummary: null,
        evaluationResultatsDetails: [],
        evaluationStats: {
            total: 0,
            mastered: 0,
            inProgress: 0,
            notAcquired: 0
        },
        evaluationStrengths: [],
        evaluationProgress: [],
        evaluationWatchpoints: [],
        urls: {
            list: "/mock/url/",
            save: "/mock/url/",
            updateEmployee: "/mock/url/",
            actionTemplate: "/mock/url/",
            historyTemplate: "/mock/url/",
            evaluationDetailTemplate: "/mock/url/",
            evaluationResultatsDetailTemplate: "/mock/url/",
            evaluationPageTemplate: "/mock/url/"
        },
        formData: {
            salaire_propose: 0,
            justification: '',
            commentaire: ''
        },
        employeeFormData: {
            date_embauche: '',
            date_debauchage: ''
        },
        
        init() {
            this.selectedYear = '2026';
            this.selectedOrganisationId = 'org-1';
            this.loadData();
        },
        
        formatMoney(amount) {
            if (amount === undefined || amount === null) return '-';
            return new Intl.NumberFormat('fr-MG', { style: 'currency', currency: 'MGA', maximumFractionDigits: 0 }).format(amount).replace('MGA', 'Ar');
        },

        salaryUnitLabel(emp) {
            return emp && emp.salary_display_unit === 'jour' ? 'par jour' : 'par mois';
        },

        salaryUnitSuffix(emp) {
            return emp && emp.salary_display_unit === 'jour' ? '/ jour' : '/ mois';
        },

        syncOrganisationSelect() {
            if (!this.$refs.organisationSelect) {
                return;
            }

            this.$refs.organisationSelect.innerHTML = '';
            for (const org of this.organisations) {
                const option = document.createElement('option');
                option.value = org.id;
                option.textContent = org.nom;
                if (org.id === this.selectedOrganisationId) {
                    option.selected = true;
                }
                this.$refs.organisationSelect.appendChild(option);
            }
        },

        formatAnciennete(value) {
            if (value === undefined || value === null || value === '') return '-';
            const monthsTotal = Math.max(0, Math.round(Number(value) * 12));
            const years = Math.floor(monthsTotal / 12);
            const months = monthsTotal % 12;
            const parts = [];

            if (years > 0) {
                parts.push(`${years} ${years > 1 ? 'ans' : 'an'}`);
            }
            if (months > 0) {
                parts.push(`${months} mois`);
            }

            return parts.length > 0 ? parts.join(' ') : '0 mois';
        },

        evaluationScoreStatus(score) {
            if (!score || score.percentage === null || score.percentage === undefined) {
                return 'none';
            }

            const percentage = Number(score.percentage);
            if (!Number.isFinite(percentage)) {
                return 'none';
            }
            if (percentage < 50) return 'below';
            if (percentage < 75) return 'average';
            return 'good';
        },

        evaluationProgressClass(score) {
            const status = this.evaluationScoreStatus(score);
            return {
                'progress-error': status === 'below',
                'progress-warning': status === 'average',
                'progress-success': status === 'good',
                'progress-neutral': status === 'none',
            };
        },

        evaluationScoreTextClass(score) {
            const status = this.evaluationScoreStatus(score);
            return {
                'text-error': status === 'below',
                'text-warning': status === 'average',
                'text-success': status === 'good',
                'text-base-content/40': status === 'none',
            };
        },

        evaluationScoreTitle(score) {
            if (!score) {
                return 'Aucune evaluation de reference';
            }

            return `Note ponderee ${this.formatPercent(score.percentage)} (${score.evaluations_count} evaluation(s) : ${score.standard_count} standard, ${score.direction_count} direction, ${score.auto_count} auto)`;
        },

        formatResultatsScore(result) {
            if (!result) {
                return '-';
            }

            return `${Number(result.score_obtenu || 0)}/${Number(result.score_maximum || 0)}`;
        },

        evaluationResultatsTitle(result) {
            if (!result) {
                return 'Aucune evaluation resultats de reference';
            }

            return `Score ${this.formatResultatsScore(result)} (${this.formatPercent(result.pourcentage)}) - recouvrement ${this.formatPercent(result.taux_recouvrement)}`;
        },

        salaryStatus(grille, amount) {
            if (!grille) return 'no_grille';
            if (amount === undefined || amount === null || amount === '') return 'no_value';

            const value = Number(amount);
            const low = Number(grille.fourchette_basse);
            const high = Number(grille.fourchette_haute);

            if (!Number.isFinite(value) || !Number.isFinite(low) || !Number.isFinite(high)) {
                return 'unknown';
            }
            if (value < low) return 'below';
            if (value > high) return 'above';
            return 'within';
        },

        salaryStatusClass(grille, amount) {
            const status = this.salaryStatus(grille, amount);
            return {
                'badge-error': status === 'below',
                'badge-success': status === 'within',
                'badge-warning': status === 'above',
                'badge-ghost': ['no_grille', 'no_value', 'unknown'].includes(status),
            };
        },

        salaryStatusText(label, grille, amount) {
            const status = this.salaryStatus(grille, amount);
            if (status === 'below') return `${label}: bas`;
            if (status === 'within') return `${label}: OK`;
            if (status === 'above') return `${label}: haut`;
            if (status === 'no_grille') return `${label}: sans grille`;
            if (status === 'no_value') return `${label}: -`;
            return `${label}: ?`;
        },

        salaryStatusTitle(label, grille, amount) {
            const status = this.salaryStatus(grille, amount);
            if (!grille) {
                return `${label}: aucune grille salariale applicable`;
            }

            const range = `${this.formatMoney(grille.fourchette_basse)} - ${this.formatMoney(grille.fourchette_haute)}`;
            if (status === 'below') return `${label} en dessous de la fourchette permise (${range})`;
            if (status === 'within') return `${label} dans la fourchette permise (${range})`;
            if (status === 'above') return `${label} au dessus de la fourchette permise (${range})`;
            if (status === 'no_value') return `${label} non renseigné`;
            return `${label}: statut indéterminé`;
        },

        salaryRangePercentage(grille, amount) {
            if (!grille || amount === undefined || amount === null || amount === '') return 0;
            const value = Number(amount);
            const low = Number(grille.fourchette_basse);
            const high = Number(grille.fourchette_haute);
            if (!Number.isFinite(value) || !Number.isFinite(low) || !Number.isFinite(high) || high <= low) return 0;
            
            const percentage = ((value - low) / (high - low)) * 100;
            return Math.max(0, Math.min(100, Math.round(percentage)));
        },

        salaryProgressClass(grille, amount) {
            const status = this.salaryStatus(grille, amount);
            return {
                'progress-error': status === 'below',
                'progress-success': status === 'within',
                'progress-warning': status === 'above',
                'progress-neutral': ['no_grille', 'no_value', 'unknown'].includes(status),
            };
        },

        salaryStatusLabel(grille, amount) {
            const status = this.salaryStatus(grille, amount);
            if (status === 'below') return 'Bas';
            if (status === 'within') return 'OK';
            if (status === 'above') return 'Haut';
            return '';
        },

        salaryStatusTextClass(grille, amount) {
            const status = this.salaryStatus(grille, amount);
            return {
                'text-error': status === 'below',
                'text-success': status === 'within',
                'text-warning': status === 'above',
                'text-base-content/40': !['below', 'within', 'above'].includes(status),
            };
        },

        seniorityRangePercentage(grille, value) {
            if (!grille) return 0;
            const current = Number(value || 0);
            const min = Number(grille.anciennete_min || 0);
            const max = Number(grille.anciennete_max || 0);
            if (max <= min) return 100;
            const percentage = ((current - min) / (max - min)) * 100;
            return Math.max(0, Math.min(100, Math.round(percentage)));
        },

        refreshGroupedEmployes() {
            const baseGroups = new Map();

            for (const emp of this.employes) {
                if (!this.isPosteSelected(emp.poste_id || 'sans-poste')) {
                    continue;
                }

                const baseId = emp.base_id || 'sans-base';
                const baseNom = emp.base_nom || 'Sans base';
                const baseKey = `${baseId}::${baseNom}`;

                if (!baseGroups.has(baseKey)) {
                    baseGroups.set(baseKey, {
                        key: baseKey,
                        base_id: emp.base_id,
                        base_nom: baseNom,
                        total: 0,
                        postes: [],
                        _postes: new Map(),
                    });
                }

                const baseGroup = baseGroups.get(baseKey);
                baseGroup.total += 1;

                const posteId = emp.poste_id || 'sans-poste';
                const posteNom = emp.poste || 'Non assigné';
                const posteKey = `${baseKey}::${posteId}::${posteNom}`;

                if (!baseGroup._postes.has(posteKey)) {
                    const posteGroup = {
                        key: posteKey,
                        poste_id: emp.poste_id,
                        poste_nom: posteNom,
                        total: 0,
                        employes: [],
                    };
                    baseGroup._postes.set(posteKey, posteGroup);
                    baseGroup.postes.push(posteGroup);
                }

                const posteGroup = baseGroup._postes.get(posteKey);
                posteGroup.total += 1;
                posteGroup.employes.push(emp);
            }

            this.groupedEmployesData = Array.from(baseGroups.values())
                .sort((a, b) => String(a.base_nom || '').localeCompare(String(b.base_nom || '')))
                .map(group => {
                    const rows = [];
                    const postes = group.postes
                        .sort((a, b) => String(a.poste_nom || '').localeCompare(String(b.poste_nom || '')));

                    for (const poste of postes) {
                        rows.push({
                            key: `${poste.key}::header`,
                            type: 'poste',
                            poste_nom: poste.poste_nom,
                            total: poste.total,
                        });

                        for (const emp of poste.employes) {
                            rows.push({
                                key: `${poste.key}::${emp.employe_id}`,
                                type: 'employe',
                                emp,
                            });
                        }
                    }

                    return {
                        key: group.key,
                        base_id: group.base_id,
                        base_nom: group.base_nom,
                        total: group.total,
                        rows,
                    };
                });
        },

        formatDate(value) {
            if (!value) return '-';
            if (value.includes('/')) return value;
            const date = new Date(value);
            if (Number.isNaN(date.getTime())) return value;
            return new Intl.DateTimeFormat('fr-FR').format(date);
        },

        formatEvaluationScore(evaluation) {
            if (!evaluation || evaluation.note_totale === null || evaluation.note_totale === undefined) {
                return 'Non notee';
            }
            return `${evaluation.note_totale}/${evaluation.note_maximale ?? 0}`;
        },

        formatEvaluationPercent(value) {
            if (value === null || value === undefined) return '-';
            return this.formatPercent(value);
        },

        formatPercent(value) {
            if (value === null || value === undefined || value === '') return '-';
            return `${Math.round(Number(value))}%`;
        },

        emptyStateMessage() {
            if (this.employes.length === 0) {
                return "Verifiez les criteres ou reessayez.";
            }
            return "Aucun employe ne correspond aux postes coches.";
        },

        flashSuccess(message) {
            this.successMessage = message || '';
            if (!this.successMessage) return;

            window.clearTimeout(this._successTimeout);
            this._successTimeout = window.setTimeout(() => {
                this.successMessage = '';
            }, 5000);
        },

        availablePostes() {
            const postes = new Map();

            for (const emp of this.employes) {
                const id = emp.poste_id || 'sans-poste';
                const nom = emp.poste || 'Non assigné';

                if (!postes.has(id)) {
                    postes.set(id, { id, nom, count: 0 });
                }
                postes.get(id).count += 1;
            }

            return Array.from(postes.values()).sort((a, b) => String(a.nom || '').localeCompare(String(b.nom || '')));
        },

        isDefaultExcludedPoste(poste) {
            const normalized = String(poste?.nom || '').trim().toLowerCase();
            return ['mpikojakoja ifotony', 'directeur', 'directeur adjoint'].includes(normalized);
        },

        syncSelectedPostes() {
            const availablePostes = this.availablePostes();
            const availableIds = availablePostes.map(poste => poste.id);

            if (!this.posteFilterInitialized) {
                this.selectedPosteIds = availablePostes
                    .filter(poste => !this.isDefaultExcludedPoste(poste))
                    .map(poste => poste.id);
                this.posteFilterInitialized = true;
                this.refreshGroupedEmployes();

                // CRITICAL: Forcer la mise à jour de l'UI Alpine.js
                // Sans cela, les checkboxes apparaissent décochées malgré l'état correct
                this.$nextTick(() => {
                    console.log('[Revalo] Postes sélectionnés après init:', this.selectedPosteIds);
                    console.log('[Revalo] Données groupées:', this.groupedEmployesData.length);
                });
                return;
            }

            this.selectedPosteIds = this.selectedPosteIds.filter(id => availableIds.includes(id));
            this.refreshGroupedEmployes();
        },

        isPosteSelected(posteId) {
            return this.selectedPosteIds.includes(posteId || 'sans-poste');
        },

        togglePoste(posteId) {
            const normalizedId = posteId || 'sans-poste';
            if (this.selectedPosteIds.includes(normalizedId)) {
                this.selectedPosteIds = this.selectedPosteIds.filter(id => id !== normalizedId);
            } else {
                this.selectedPosteIds = [...this.selectedPosteIds, normalizedId];
            }
            this.refreshGroupedEmployes();
        },

        selectAllPostes() {
            this.selectedPosteIds = this.availablePostes().map(poste => poste.id);
            this.refreshGroupedEmployes();
        },

        clearSelectedPostes() {
            this.selectedPosteIds = [];
            this.refreshGroupedEmployes();
        },

        getStats() {
            let count = 0;
            let totalActual = 0;
            let totalProposed = 0;
            
            let actualStatus = { below: 0, within: 0, above: 0, none: 0 };
            let proposedStatus = { below: 0, within: 0, above: 0, none: 0 };

            for (const group of this.groupedEmployesData) {
                for (const row of group.rows) {
                    if (row.type === 'employe') {
                        count++;
                        const actual = Number(row.emp.salaire_actuel || 0);
                        totalActual += actual;
                        
                        const sActual = this.salaryStatus(row.emp.grille, row.emp.salaire_actuel);
                        if (actualStatus.hasOwnProperty(sActual)) actualStatus[sActual]++;
                        else actualStatus.none++;

                        let proposed = actual;
                        if (row.emp.revalorisation) {
                            proposed = Number(row.emp.revalorisation.salaire_propose || 0);
                        }
                        totalProposed += proposed;

                        const sProposed = this.salaryStatus(row.emp.grille, proposed);
                        if (proposedStatus.hasOwnProperty(sProposed)) proposedStatus[sProposed]++;
                        else proposedStatus.none++;
                    }
                }
            }

            const diff = totalProposed - totalActual;
            const rate = totalActual > 0 ? (diff / totalActual) * 100 : 0;

            return {
                count,
                totalActual,
                totalProposed,
                diff,
                rate: Math.round(rate * 10) / 10,
                actualStatus,
                proposedStatus
            };
        },

        async readJson(response) {
            const contentType = response.headers.get('content-type') || '';
            const data = contentType.includes('application/json') ? await response.json() : null;

            if (!response.ok || !data || !data.success) {
                throw new Error(data?.error || `Erreur HTTP ${response.status}`);
            }

            return data;
        },

        buildActionUrl(revalId, action) {
            return this.urls.actionTemplate
                .replace('00000000-0000-0000-0000-000000000000', revalId)
                .replace('__ACTION__', action);
        },

        buildHistoryUrl(employeId) {
            return this.urls.historyTemplate
                .replace('00000000-0000-0000-0000-000000000000', employeId);
        },

        buildEvaluationDetailUrl(evaluationId) {
            return this.urls.evaluationDetailTemplate
                .replace('00000000-0000-0000-0000-000000000000', evaluationId);
        },

        buildEvaluationResultatsDetailUrl(evaluationId) {
            return this.urls.evaluationResultatsDetailTemplate
                .replace('00000000-0000-0000-0000-000000000000', evaluationId);
        },

        buildEvaluationPageUrl(evaluationId) {
            return this.urls.evaluationPageTemplate
                .replace('00000000-0000-0000-0000-000000000000', evaluationId);
        },

        evaluationStatusLabel(statut) {
            const labels = {
                brouillon: 'Brouillon',
                terminee: 'Terminee',
                validee: 'Validee'
            };
            return labels[statut] || statut || '-';
        },

        statusBadgeClass(statut) {
            return {
                'badge-ghost': !statut || statut === 'brouillon',
                'badge-info': statut === 'terminee',
                'badge-success': statut === 'validee'
            };
        },

        evaluationResultatsStatusLabel(statut, statutDisplay = '') {
            const labels = {
                provisoire: 'Provisoire',
                validee: 'Validee'
            };
            return labels[statut] || statutDisplay || statut || '-';
        },

        evaluationResultatsStatusBadgeClass(statut) {
            return {
                'badge-warning': statut === 'provisoire',
                'badge-success': statut === 'validee',
                'badge-ghost': !statut
            };
        },

        detailBadgeClass(note) {
            return {
                'badge-success': Number(note) >= 2,
                'badge-warning': Number(note) === 1,
                'badge-error': Number(note) <= 0
            };
        },

        resetEvaluationState() {
            this.evaluationError = '';
            this.evaluationSummary = null;
            this.evaluationDetails = [];
            this.evaluationStats = {
                total: 0,
                mastered: 0,
                inProgress: 0,
                notAcquired: 0
            };
            this.evaluationStrengths = [];
            this.evaluationProgress = [];
            this.evaluationWatchpoints = [];
        },

        resetEvaluationResultatsState() {
            this.evaluationResultatsError = '';
            this.evaluationResultatsSummary = null;
            this.evaluationResultatsDetails = [];
        },

        applyEvaluationSummary(evaluation, details) {
            const safeDetails = Array.isArray(details) ? details : [];
            this.evaluationSummary = evaluation || null;
            this.evaluationDetails = safeDetails;
            this.evaluationStrengths = safeDetails.filter(detail => Number(detail.note) >= 2);
            this.evaluationProgress = safeDetails.filter(detail => Number(detail.note) === 1);
            this.evaluationWatchpoints = safeDetails.filter(detail => Number(detail.note) <= 0);
            this.evaluationStats = {
                total: safeDetails.length,
                mastered: this.evaluationStrengths.length,
                inProgress: this.evaluationProgress.length,
                notAcquired: this.evaluationWatchpoints.length
            };
        },

        applyEvaluationResultatsSummary(evaluation, details) {
            this.evaluationResultatsSummary = evaluation || null;
            this.evaluationResultatsDetails = Array.isArray(details) ? details : [];
        },
        
        loadData() {
            this.loading = true;
            this.errorMessage = '';
            console.log('[Revalo] Chargement des donn?es pour Année:', this.selectedYear);
            const params = new URLSearchParams({
                annee: this.selectedYear,
            });
            if (this.selectedOrganisationId) {
                params.set('organisation_id', this.selectedOrganisationId);
            }
            fetch(`${this.urls.list}?${params.toString()}`)
                .then(res => this.readJson(res))
                .then(data => {
                    console.log("[Revalo] Données reçues de l'API:", data);
                    this.organisations = Array.isArray(data.organisations) ? data.organisations : [];
                    this.selectedOrganisationId = data.selected_organisation_id || (this.organisations[0]?.id || '');
                    this.$nextTick(() => this.syncOrganisationSelect());
                    this.employes = Array.isArray(data.data) ? data.data : [];
                    console.log("[Revalo] Nombre d'employes charges:", this.employes.length);
                    this.syncSelectedPostes();
                })
                .catch(err => {
                    this.employes = [];
                    this.groupedEmployesData = [];
                    this.selectedPosteIds = [];
                    this.errorMessage = err.message || "Erreur de chargement des revalorisations";
                    console.error("[Revalo] Erreur de chargement", err);
                })
                .finally(() => {
                    this.loading = false;
                });
        },

        openModalEmployee(emp) {
            this.currentEmp = emp;
            this.employeeFormData.date_embauche = emp.date_embauche || '';
            this.employeeFormData.date_debauchage = emp.date_debauchage || '';
            document.getElementById('modal_employee').showModal();
        },

        saveEmployeeData() {
            if (!this.currentEmp) return;

            this.savingEmployee = true;
            this.errorMessage = '';

            const payload = {
                employe_id: this.currentEmp.employe_id,
                date_embauche: this.employeeFormData.date_embauche || null,
                date_debauchage: this.employeeFormData.date_debauchage || null
            };

            fetch(this.urls.updateEmployee, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify(payload)
            })
            .then(res => this.readJson(res))
            .then(data => {
                this.flashSuccess(data.message || "Donnees employe mises a jour.");
                document.getElementById('modal_employee').close();
                this.loadData();
            })
            .catch(err => {
                this.errorMessage = err.message || "Erreur lors de la mise a jour des donnees employe";
                alert(this.errorMessage);
            })
            .finally(() => {
                this.savingEmployee = false;
            });
        },
        
        openModalEdit(emp) {
            this.currentEmp = emp;
            if (emp.revalorisation) {
                this.formData.salaire_propose = emp.revalorisation.salaire_propose;
                this.formData.justification = emp.revalorisation.justification;
            } else {
                this.formData.salaire_propose = emp.salaire_actuel;
                this.formData.justification = '';
            }
            this.formData.commentaire = '';
            document.getElementById('modal_edit').showModal();
        },
        
        calculatePercentage() {
            if (!this.currentEmp || !this.currentEmp.salaire_actuel) return 0;
            const current = parseFloat(this.currentEmp.salaire_actuel);
            const proposed = parseFloat(this.formData.salaire_propose || 0);
            if (current <= 0) return 0;
            return Math.round(((proposed - current) / current) * 100);
        },
        
        saveRevalorisation() {
            this.saving = true;
            const payload = {
                employe_id: this.currentEmp.employe_id,
                annee: parseInt(this.selectedYear),
                salaire_propose: parseFloat(this.formData.salaire_propose),
                justification: this.formData.justification
            };
            
            fetch(this.urls.save, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify(payload)
            })
            .then(res => this.readJson(res))
            .then(() => {
                this.loadData();
                document.getElementById('modal_edit').close();
            })
            .catch(err => alert(err.message || "Erreur serveur"))
            .finally(() => {
                this.saving = false;
            });
        },
        
        changeStatus(action) {
            if (!this.currentEmp || !this.currentEmp.revalorisation) return;
            
            // Si l'utilisateur clique sur un bouton de changement d'état (soumettre, etc) depuis le form
            // on sauvegarde d'abord si c'est "soumettre" ou "appliquer".
            
            this.saving = true;
            const payload = { commentaire: this.formData.commentaire };
            
            fetch(this.buildActionUrl(this.currentEmp.revalorisation.id, action), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify(payload)
            })
            .then(res => this.readJson(res))
            .then(() => {
                this.loadData();
                document.getElementById('modal_edit').close();
            })
            .catch(err => alert(err.message || "Erreur serveur"))
            .finally(() => {
                this.saving = false;
            });
        },
        
        openModalHistory(emp) {
            this.currentEmp = emp;
            this.loadingHistory = true;
            this.history = [];
            document.getElementById('modal_history').showModal();
            
            fetch(this.buildHistoryUrl(emp.employe_id))
                .then(res => this.readJson(res))
                .then(data => {
                    this.history = Array.isArray(data.data) ? data.data : [];
                })
                .catch(err => {
                    this.history = [];
                    this.errorMessage = err.message || "Erreur de chargement de l'historique";
                })
                .finally(() => {
                    this.loadingHistory = false;
                });
        },
        
        openModalEvaluation(emp) {
            this.currentEmp = emp;
            this.resetEvaluationState();
            this.loadingEvaluation = !!emp.evaluation;
            document.getElementById('modal_eval').showModal();

            if (!emp.evaluation) {
                return;
            }

            fetch(this.buildEvaluationDetailUrl(emp.evaluation.id))
                .then(res => this.readJson(res))
                .then(data => {
                    this.applyEvaluationSummary(data.evaluation, data.details);
                })
                .catch(err => {
                    this.evaluationError = err.message || "Erreur de chargement de l'evaluation";
                })
                .finally(() => {
                    this.loadingEvaluation = false;
                });
        },

        openModalEvaluationResultats(emp) {
            this.currentEmp = emp;
            this.resetEvaluationResultatsState();
            this.loadingEvaluationResultats = !!emp.evaluation_resultats;
            document.getElementById('modal_eval_resultats').showModal();

            if (!emp.evaluation_resultats) {
                return;
            }

            fetch(this.buildEvaluationResultatsDetailUrl(emp.evaluation_resultats.id))
                .then(res => this.readJson(res))
                .then(data => {
                    this.applyEvaluationResultatsSummary(data.evaluation, data.details);
                })
                .catch(err => {
                    this.evaluationResultatsError = err.message || "Erreur de chargement de l'evaluation resultats";
                })
                .finally(() => {
                    this.loadingEvaluationResultats = false;
                });
        },
        
        getCsrfToken() {
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, 10) === ('csrftoken=')) {
                        cookieValue = decodeURIComponent(cookie.substring(10));
                        break;
                    }
                }
            }
            return cookieValue;
        }
    }));
});
