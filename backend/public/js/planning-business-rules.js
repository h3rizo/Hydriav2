// ========== RÈGLES MÉTIER PLANNING - Conversion VBA vers JavaScript ==========

class PlanningBusinessRules {
  constructor() {
    this.KelTypeActivite = 0;
    this.keltypeavancecaissiere = '';
    this.employes = [];
    this.activites = [];
    this.ouvrages = [];
    this.designations = [];
    this.currentUser = null;
    this.currentBase = null;
    this.currentOrganisation = null;
  }

  // ========== RÈGLES ACTIVITÉ ==========

  async onActiviteChange(activiteId, planningRow) {
    if (!activiteId) {
      this.KelTypeActivite = 0;
      return;
    }

    try {
      // Récupérer le type d'activité
      const activite = await this.getActiviteById(activiteId);
      this.KelTypeActivite = activite?.TypeActiviteID || 0;

      // Mettre à jour le type de planning
      this.setFieldValue(planningRow, 'TypePlanning', 'Base');

      // Réinitialiser les colonnes visibles
      this.reinitialiserColonnesVisibles(planningRow);

      // Appliquer les contraintes selon le type d'activité
      switch (this.KelTypeActivite) {
        case 2: // Clôture
        case 3: // Maçonnerie  
        case 8: // PMH
        case 9: // Réparation
          this.setFieldValue(planningRow, 'TypePlanning', 'Surplus');
          this.showField(planningRow, 'DateSignalement', true);
          break;

        case 4: // Bureau
          this.showField(planningRow, 'DateSignalement', false);
          this.showField(planningRow, 'Verif1', false);
          this.showField(planningRow, 'Verif1Commentaire', false);
          this.showField(planningRow, 'DebitOuNbCoup', false);
          break;

        case 5: // Absent
          this.showField(planningRow, 'DateSignalement', false);
          this.showField(planningRow, 'Verif1', false);
          this.showField(planningRow, 'Verif1Commentaire', false);
          this.showField(planningRow, 'Affectation', false);
          this.showField(planningRow, 'DebitOuNbCoup', false);
          break;
      }

      // Activer les détails si nécessaire
      await this.activerDetails(activiteId, planningRow);

    } catch (error) {
      console.error('Erreur lors du changement d\'activité:', error);
    }
  }

  // ========== RÈGLES EMPLOYÉ ==========

  async onEmployeChange(employeId, planningRow) {
    if (!employeId) return;

    try {
      // Récupérer le poste de l'employé
      const employe = await this.getEmployeById(employeId);
      const kelposte = employe?.PosteID || 0;

      if (kelposte > 0) {
        // Restreindre les activités selon le poste
        await this.updateActivitesDropdown(kelposte, planningRow);
      } else {
        this.clearActivitesDropdown(planningRow);
      }

    } catch (error) {
      console.error('Erreur lors du changement d\'employé:', error);
    }
  }

  // ========== VALIDATION PLANNING ==========

  async validatePlanningBeforeUpdate(planningData) {
    const errors = [];

    // Vérifications obligatoires
    if (!planningData.DatePlanning) {
      errors.push("Il faut saisir une date");
    }

    if (!planningData.EmployeID) {
      errors.push("Il faut saisir un employé");
    }

    if (!planningData.ActiviteID) {
      errors.push("Il faut saisir une activité");
    }

    // Vérification date
    if (planningData.DatePlanning && !this.checkDate(planningData.DatePlanning)) {
      errors.push("Date invalide");
    }

    // Vérifications spécifiques pour les réparations
    const activite = await this.getActiviteById(planningData.ActiviteID);
    const KelTypeActivite = activite?.TypeActiviteID || 0;

    if (KelTypeActivite === 9) { // Réparation
      if (!planningData.DateSignalement || !planningData.Remarques) {
        errors.push("Il faut renseigner la date de signalement et des commentaires sur la réparation");
      }
    }

    // Remarques obligatoires pour certaines activités
    const activitesRequierantRemarques = [72, 73, 74, 75, 87];
    if (activitesRequierantRemarques.includes(planningData.ActiviteID) && !planningData.Remarques) {
      errors.push("Vous devez expliquer la réparation dans remarques");
    }

    // Vérification unicité
    const isUnique = await this.verifyUniquePlanning(planningData);
    if (!isUnique) {
      errors.push("Un planning identique existe déjà pour cette date, employé, ouvrage et activité");
    }

    return errors;
  }

  // ========== RÈGLES DÉTAILS PLANNING ==========

  async onDesignationChange(designationId, detailRow, planningData) {
    if (!designationId) return;

    try {
      const designation = await this.getDesignationById(designationId);
      if (!designation) return;

      this.keltypeavancecaissiere = designation.TypeAvanceCaissiere || '';
      const kelposte = designation.PosteAcheteur || 0;

      // Réinitialiser PU et Quantité
      this.setFieldValue(detailRow, 'PU', null);
      this.setFieldValue(detailRow, 'Quantite', 1);

      // Logique spécifique selon la désignation
      switch (designationId) {
        case 153: // Frais de déplacement
          await this.handleFraisDeplacementLogic(detailRow, planningData);
          break;

        case 162: // Paiement forfaitaire
          await this.handlePaiementForfaitaireLogic(detailRow, planningData);
          break;

        default:
          await this.handleDefaultDesignationLogic(designationId, detailRow, planningData);
          break;
      }

      // Gestion de l'acheteur selon le poste
      await this.setAcheteurByPoste(kelposte, detailRow, planningData);

      // Gestion des comptes
      await this.handleCompteLogic(designationId, detailRow);

      // Vérification des coupures
      await this.verifieCoupure(detailRow, planningData);

    } catch (error) {
      console.error('Erreur lors du changement de désignation:', error);
    }
  }

  // ========== MÉTHODES UTILITAIRES ==========

  async getActiviteById(id) {
    try {
      const response = await $.ajax({
        url: `/api/activites/${id}`,
        method: 'GET'
      });
      return response;
    } catch (error) {
      console.error('Erreur récupération activité:', error);
      return null;
    }
  }

  async getEmployeById(id) {
    try {
      const response = await $.ajax({
        url: `/api/employes/${id}`,
        method: 'GET'
      });
      return response;
    } catch (error) {
      console.error('Erreur récupération employé:', error);
      return null;
    }
  }

  async getDesignationById(id) {
    try {
      const response = await $.ajax({
        url: `/api/designations/${id}`,
        method: 'GET'
      });
      return response;
    } catch (error) {
      console.error('Erreur récupération désignation:', error);
      return null;
    }
  }

  async updateActivitesDropdown(posteId, planningRow) {
    try {
      const response = await $.ajax({
        url: `/api/activites/by-poste/${posteId}`,
        method: 'GET'
      });

      const activiteSelect = $(planningRow).find('[data-field="ActiviteID"]');
      activiteSelect.empty().append('<option value="">-- Activité --</option>');

      response.forEach(activite => {
        activiteSelect.append(`<option value="${activite.ID}">${activite.Nom}</option>`);
      });

    } catch (error) {
      console.error('Erreur mise à jour activités:', error);
    }
  }

  clearActivitesDropdown(planningRow) {
    const activiteSelect = $(planningRow).find('[data-field="ActiviteID"]');
    activiteSelect.empty().append('<option value="">-- Activité --</option>');
  }

  async verifyUniquePlanning(planningData) {
    try {
      const response = await $.ajax({
        url: '/api/plannings/verify-unique',
        method: 'POST',
        data: {
          DatePlanning: planningData.DatePlanning,
          EmployeID: planningData.EmployeID,
          OuvrageID: planningData.OuvrageID,
          ActiviteID: planningData.ActiviteID,
          excludeId: planningData.ID // Pour exclure l'enregistrement en cours de modification
        }
      });
      return response.unique;
    } catch (error) {
      console.error('Erreur vérification unicité:', error);
      return true; // Par défaut, considérer comme unique en cas d'erreur
    }
  }

  checkDate(dateString) {
    const date = new Date(dateString);
    const today = new Date();

    // Vérifier que la date n'est pas trop ancienne (par exemple, plus de 1 an)
    const oneYearAgo = new Date();
    oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);

    // Vérifier que la date n'est pas trop future (par exemple, plus de 1 an)
    const oneYearFuture = new Date();
    oneYearFuture.setFullYear(oneYearFuture.getFullYear() + 1);

    return date >= oneYearAgo && date <= oneYearFuture && !isNaN(date.getTime());
  }

  reinitialiserColonnesVisibles(planningRow) {
    this.showField(planningRow, 'DateSignalement', true);
    this.showField(planningRow, 'Verif1', true);
    this.showField(planningRow, 'Verif1Commentaire', true);
    this.showField(planningRow, 'DebitOuNbCoup', true);
    this.showField(planningRow, 'Affectation', true);
  }

  showField(planningRow, fieldName, visible) {
    const field = $(planningRow).find(`[data-field="${fieldName}"]`).closest('td');
    if (visible) {
      field.show();
    } else {
      field.hide();
    }
  }

  setFieldValue(planningRow, fieldName, value) {
    const field = $(planningRow).find(`[data-field="${fieldName}"]`);
    field.val(value);
  }

  async activerDetails(activiteId, planningRow) {
    // Logique pour activer/désactiver la section des détails
    // selon le type d'activité
    if (activiteId) {
      $('#planningDetailsSection').show();
    }
  }

  // ========== LOGIQUE SPÉCIFIQUE DÉSIGNATIONS ==========

  async handleFraisDeplacementLogic(detailRow, planningData) {
    // Afficher les champs de trajet
    this.showDetailField(detailRow, 'PointA', true);
    this.showDetailField(detailRow, 'PointB', true);
    this.showDetailField(detailRow, 'MoyenTransport', true);

    // Si les points sont déjà sélectionnés, calculer le PU
    const pointA = this.getDetailFieldValue(detailRow, 'PointA');
    const pointB = this.getDetailFieldValue(detailRow, 'PointB');

    if (pointA && pointB) {
      await this.updatePUForDeplacementPoints(pointA, pointB, detailRow);
    }
  }

  async handlePaiementForfaitaireLogic(detailRow, planningData) {
    const ouvrageConstitutif = this.getDetailFieldValue(detailRow, 'OuvrageConstitutif');

    if (!ouvrageConstitutif) {
      this.showMessage('Remplir d\'abord ouvrage constitutif');
      return;
    }

    if (planningData.OuvrageID) {
      const pu = await this.getPUForPaiementForfaitaire(planningData.OuvrageID, ouvrageConstitutif);
      this.setDetailFieldValue(detailRow, 'PU', pu);
    }
  }

  async handleDefaultDesignationLogic(designationId, detailRow, planningData) {
    if (this.keltypeavancecaissiere === 'Bon de livraison') {
      this.setDetailFieldValue(detailRow, 'PU', null);
      this.setDetailFieldValue(detailRow, 'Quantite', 1);

      // Configurer le magasin par défaut
      await this.setDefaultMagasin(detailRow);
    } else {
      // Récupérer le PU standard pour cette désignation
      const pu = await this.getStandardPUForDesignation(designationId);
      this.setDetailFieldValue(detailRow, 'PU', pu);
      this.setDetailFieldValue(detailRow, 'Quantite', 1);
    }
  }

  async setAcheteurByPoste(kelposte, detailRow, planningData) {
    let acheteurId = null;

    switch (kelposte) {
      case 1: // Agent
        acheteurId = planningData.EmployeID;
        break;
      case 3: // Caisse
        acheteurId = await this.getCaisseEmployeId();
        break;
      case 17: // Chèque
        acheteurId = await this.getChequeEmployeId();
        break;
    }

    if (acheteurId) {
      this.setDetailFieldValue(detailRow, 'AcheteurID', acheteurId);
    }
  }

  async handleCompteLogic(designationId, detailRow) {
    if (this.keltypeavancecaissiere === 'Avance' || this.keltypeavancecaissiere === 'Recette') {
      const compte = await this.getCompteForDesignation(designationId);
      this.setDetailFieldValue(detailRow, 'Compte', compte);

      // Mettre à jour la source des comptes disponibles
      await this.updateComptesDropdown(designationId, detailRow);
    } else {
      this.setDetailFieldValue(detailRow, 'Compte', null);
    }
  }

  async verifieCoupure(detailRow, planningData) {
    const designationId = this.getDetailFieldValue(detailRow, 'DesignationID');
    const ouvrageConstitutif = this.getDetailFieldValue(detailRow, 'OuvrageConstitutif');

    if (!planningData.OuvrageID || !ouvrageConstitutif || !this.isNumeric(ouvrageConstitutif)) {
      return false;
    }

    switch (parseInt(designationId)) {
      case 1205: // Coupure d'eau
        return await this.handleCoupureEau(ouvrageConstitutif, planningData);

      case 1206: // Remise en eau
        return await this.handleRemiseEnEau(ouvrageConstitutif, planningData);
    }

    return false;
  }

  // ========== MÉTHODES UTILITAIRES DÉTAILS ==========

  showDetailField(detailRow, fieldName, visible) {
    const field = $(detailRow).find(`[data-field="${fieldName}"]`).closest('td');
    if (visible) {
      field.show();
    } else {
      field.hide();
    }
  }

  getDetailFieldValue(detailRow, fieldName) {
    return $(detailRow).find(`[data-field="${fieldName}"]`).val();
  }

  setDetailFieldValue(detailRow, fieldName, value) {
    $(detailRow).find(`[data-field="${fieldName}"]`).val(value);
  }

  isNumeric(value) {
    return !isNaN(value) && !isNaN(parseFloat(value));
  }

  showMessage(message) {
    // Utiliser votre système de messages existant
    alert(message); // Remplacer par votre système de notification
  }

  // ========== MÉTHODES API ==========

  async updatePUForDeplacementPoints(pointA, pointB, detailRow) {
    try {
      const response = await $.ajax({
        url: '/api/deplacements/prix',
        method: 'GET',
        data: { pointA, pointB }
      });

      this.setDetailFieldValue(detailRow, 'PU', response.pu);

    } catch (error) {
      console.error('Erreur récupération PU déplacement:', error);
    }
  }

  async getPUForPaiementForfaitaire(ouvrageId, ouvrageConstitutif) {
    try {
      const response = await $.ajax({
        url: '/api/paiements-forfaitaires/prix',
        method: 'GET',
        data: { ouvrageId, ouvrageConstitutif }
      });

      return response.pu;

    } catch (error) {
      console.error('Erreur récupération PU paiement forfaitaire:', error);
      return 0;
    }
  }

  async getStandardPUForDesignation(designationId) {
    try {
      const response = await $.ajax({
        url: `/api/designations/${designationId}/prix-standard`,
        method: 'GET'
      });

      return response.pu;

    } catch (error) {
      console.error('Erreur récupération PU standard:', error);
      return 0;
    }
  }

  async getCaisseEmployeId() {
    try {
      const response = await $.ajax({
        url: '/api/employes/caisse',
        method: 'GET'
      });

      return response.employeId;

    } catch (error) {
      console.error('Erreur récupération employé caisse:', error);
      return null;
    }
  }

  async getChequeEmployeId() {
    try {
      const response = await $.ajax({
        url: '/api/employes/cheque',
        method: 'GET'
      });

      return response.employeId;

    } catch (error) {
      console.error('Erreur récupération employé chèque:', error);
      return null;
    }
  }

  async getCompteForDesignation(designationId) {
    try {
      const response = await $.ajax({
        url: `/api/designations/${designationId}/compte`,
        method: 'GET'
      });

      return response.compteId;

    } catch (error) {
      console.error('Erreur récupération compte:', error);
      return null;
    }
  }

  async updateComptesDropdown(designationId, detailRow) {
    try {
      const response = await $.ajax({
        url: `/api/designations/${designationId}/comptes-autorises`,
        method: 'GET'
      });

      const compteSelect = $(detailRow).find('[data-field="Compte"]');
      compteSelect.empty().append('<option value="">-- Compte --</option>');

      response.forEach(compte => {
        compteSelect.append(`<option value="${compte.ID}">${compte.Titre}</option>`);
      });

    } catch (error) {
      console.error('Erreur mise à jour comptes:', error);
    }
  }

  async handleCoupureEau(ouvrageConstitutif, planningData) {
    try {
      const response = await $.ajax({
        url: '/api/branchements/coupure',
        method: 'POST',
        data: {
          ouvrageConstitutif,
          ouvrageId: planningData.OuvrageID,
          datePlanning: planningData.DatePlanning
        }
      });

      if (response.success) {
        this.showMessage(`Le point d'eau ${ouvrageConstitutif} est coupé le ${planningData.DatePlanning}`);
        return true;
      } else {
        this.showMessage(response.message || 'Il y a déjà une coupure d\'eau');
        return false;
      }

    } catch (error) {
      console.error('Erreur coupure eau:', error);
      return false;
    }
  }

  async handleRemiseEnEau(ouvrageConstitutif, planningData) {
    try {
      const response = await $.ajax({
        url: '/api/branchements/remise-en-eau',
        method: 'POST',
        data: {
          ouvrageConstitutif,
          ouvrageId: planningData.OuvrageID,
          datePlanning: planningData.DatePlanning
        }
      });

      if (response.success) {
        this.showMessage(`Le point d'eau ${ouvrageConstitutif} est remis en eau le ${planningData.DatePlanning}`);
        return true;
      } else {
        this.showMessage(response.message || 'Il n\'y a pas eu de coupure');
        return false;
      }

    } catch (error) {
      console.error('Erreur remise en eau:', error);
      return false;
    }
  }
}

// ========== INTÉGRATION DANS L'INTERFACE ==========

// Instance globale des règles métier
const businessRules = new PlanningBusinessRules();

// Événements pour l'interface de planning
$(document).ready(function () {

  // Changement d'activité
  $(document).on('change', '[data-field="ActiviteID"]', async function () {
    const activiteId = $(this).val();
    const planningRow = $(this).closest('tr');

    await businessRules.onActiviteChange(activiteId, planningRow);
  });

  // Changement d'employé
  $(document).on('change', '[data-field="EmployeID"]', async function () {
    const employeId = $(this).val();
    const planningRow = $(this).closest('tr');

    await businessRules.onEmployeChange(employeId, planningRow);
  });

  // Validation avant sauvegarde
  $(document).on('submit', '#planningForm', async function (e) {
    e.preventDefault();

    const planningData = {
      DatePlanning: $('#newDate').val(),
      EmployeID: $('#newEmploye').val(),
      ActiviteID: $('#newActivite').val(),
      OuvrageID: $('#newOuvrage').val(),
      Remarques: $('#newRemarque').val()
    };

    const errors = await businessRules.validatePlanningBeforeUpdate(planningData);

    if (errors.length > 0) {
      alert(errors.join('\n'));
      return false;
    }

    // Continuer avec la sauvegarde normale
    saveNewPlanning();
  });

  // Changement de désignation dans les détails
  $(document).on('change', '[data-field="DesignationID"]', async function () {
    const designationId = $(this).val();
    const detailRow = $(this).closest('tr');

    // Récupérer les données du planning parent
    const planningData = {
      ID: currentSelectedPlanning,
      EmployeID: $('.planning-row.selected [data-field="EmployeID"]').val(),
      OuvrageID: $('.planning-row.selected [data-field="OuvrageID"]').val(),
      DatePlanning: $('.planning-row.selected [data-field="Date"]').val()
    };

    await businessRules.onDesignationChange(designationId, detailRow, planningData);
  });

  // Changement de points pour frais de déplacement
  $(document).on('change', '[data-field="PointA"], [data-field="PointB"]', async function () {
    const detailRow = $(this).closest('tr');
    const pointA = detailRow.find('[data-field="PointA"]').val();
    const pointB = detailRow.find('[data-field="PointB"]').val();

    if (pointA && pointB) {
      await businessRules.updatePUForDeplacementPoints(pointA, pointB, detailRow);
    }
  });

  // Auto-calcul du montant
  $(document).on('change', '[data-field="Quantite"], [data-field="PrixUnitaire"]', function () {
    const detailRow = $(this).closest('tr');
    const quantite = parseFloat(detailRow.find('[data-field="Quantite"]').val()) || 0;
    const pu = parseFloat(detailRow.find('[data-field="PrixUnitaire"]').val()) || 0;
    const montant = (quantite * pu).toFixed(2);

    detailRow.find('[data-field="Montant"]').val(montant);
  });

});

// Export pour utilisation dans d'autres fichiers
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PlanningBusinessRules;
}