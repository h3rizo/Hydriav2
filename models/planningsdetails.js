module.exports = (sequelize, DataTypes) => {
  const PlanningsDetails = sequelize.define("PlanningsDetails", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    PlanningID: { type: DataTypes.INTEGER, allowNull: false },
    OuvrageConstitutif: { type: DataTypes.STRING }, // Référence vers OuvragesConstitutifs + PointsEau
    DesignationID: { type: DataTypes.INTEGER, allowNull: false },
    Quantite: { type: DataTypes.FLOAT },
    PrixUnitaire: { type: DataTypes.FLOAT },
    Montant: { type: DataTypes.FLOAT },
    AcheteurID: { type: DataTypes.INTEGER },
    MagasinID: { type: DataTypes.INTEGER },
    CompteID: { type: DataTypes.INTEGER },
    EstLivre: { type: DataTypes.BOOLEAN, defaultValue: false },
    EstRetourne: { type: DataTypes.BOOLEAN, defaultValue: false },
    NumeroDiameX: { type: DataTypes.STRING },
    BaseDiameX: { type: DataTypes.STRING },
    Bilan: { type: DataTypes.TEXT('long') },
    SuiteADonner: { type: DataTypes.TEXT('long') },

  });
  PlanningsDetails.associate = function (models) {
    PlanningsDetails.belongsTo(models.Plannings, {
      foreignKey: 'PlanningID',
      as: 'Planning'
    });
    PlanningsDetails.belongsTo(models.Designations, {
      foreignKey: 'DesignationID',
      as: 'Designation'
    });
    PlanningsDetails.belongsTo(models.Employes, {
      foreignKey: 'AcheteurID',
      as: 'Acheteur'
    });
    PlanningsDetails.belongsTo(models.Magasins, {
      foreignKey: 'MagasinID',
      as: 'Magasin'
    });
    PlanningsDetails.belongsTo(models.Comptes, {
      foreignKey: 'CompteID',
      as: 'Compte'
    });
  };
  return PlanningsDetails;
};
