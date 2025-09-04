module.exports = (sequelize, DataTypes) => {
  const ModalitesGestions = sequelize.define("ModalitesGestions", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    OuvrageID: { type: DataTypes.INTEGER, allowNull: false },
    DateDebutGestion: { type: DataTypes.DATE },
    DateFinGestion: { type: DataTypes.DATE },
    ModeGestion: { type: DataTypes.ENUM("Privé", "Comité eau", "Pas de gestion") },
    ModalitePaiement: { type: DataTypes.ENUM("Au volume", "Forfaitaire", "Cotisation annuelle", "Mixte") },
    GestionnaireID: { type: DataTypes.INTEGER },
    EmployeID: { type: DataTypes.INTEGER }
  });
  ModalitesGestions.associate = function (models) {
    ModalitesGestions.belongsTo(models.Ouvrages, {
      foreignKey: 'OuvrageID',
      as: 'Ouvrage'
    });
    ModalitesGestions.belongsTo(models.Gestionnaires, {
      foreignKey: 'GestionnaireID',
      as: 'Gestionnaire'
    });
    ModalitesGestions.belongsTo(models.Employes, {
      foreignKey: 'EmployeID',
      as: 'Employe'
    });
  };
  return ModalitesGestions;
};