module.exports = (sequelize, DataTypes) => {
  const Designations = sequelize.define("Designations", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomDesignation: { type: DataTypes.STRING, allowNull: false },
    TypeDesignationID: { type: DataTypes.INTEGER, allowNull: false },
    TypeActiviteID: { type: DataTypes.INTEGER, allowNull: false },
    TypeAvanceCaissiere: { type: DataTypes.ENUM("Bon de livraison", "Avance") },
    EstPrestation: { type: DataTypes.BOOLEAN, defaultValue: false },
    PosteAcheteur: { type: DataTypes.STRING }
  });

  Designations.associate = function (models) {
    Designations.belongsTo(models.TypeDesignations, {
      foreignKey: 'TypeDesignationID',
      as: 'TypeDesignation'
    });
    Designations.belongsTo(models.TypesActivites, {
      foreignKey: 'TypeActiviteID',
      as: 'TypeActivite'
    });
    Designations.hasMany(models.DesignationsTypeActivites, {
      foreignKey: 'DesignationID',
      as: 'DesignationsTypeActivites'
    });
    Designations.hasMany(models.DesignationsComptes, {
      foreignKey: 'DesignationID',
      as: 'DesignationsComptes'
    });
    Designations.hasMany(models.PlanningsDetails, {
      foreignKey: 'DesignationID',
      as: 'PlanningsDetails'
    });
  };

  return Designations;
};