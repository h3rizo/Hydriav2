module.exports = (sequelize, DataTypes) => {
  const Plannings = sequelize.define("Plannings", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Date: { type: DataTypes.DATE, allowNull: false },
    OuvrageID: { type: DataTypes.INTEGER },
    EmployeID: { type: DataTypes.INTEGER, allowNull: false },
    ActiviteID: { type: DataTypes.INTEGER, allowNull: false },
    Remarque: { type: DataTypes.TEXT },
    DateSignalementActivite: { type: DataTypes.DATE },
    EstValide: { type: DataTypes.BOOLEAN, defaultValue: false },
    DebitMesure: { type: DataTypes.FLOAT }
  });
  Plannings.associate = function (models) {
    Plannings.belongsTo(models.Ouvrages, {
      foreignKey: 'OuvrageID',
      as: 'Ouvrage'
    });
    Plannings.belongsTo(models.Employes, {
      foreignKey: 'EmployeID',
      as: 'Employe'
    });
    Plannings.belongsTo(models.Activites, {
      foreignKey: 'ActiviteID',
      as: 'Activite'
    });
    Plannings.hasMany(models.Indemnites, {
      foreignKey: 'PlanningID',
      as: 'Indemnites'
    });
    Plannings.hasMany(models.PlanningsDetails, {
      foreignKey: 'PlanningID',
      as: 'PlanningsDetails'
    });

  };
  return Plannings;
};
