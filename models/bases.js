module.exports = (sequelize, DataTypes) => {
  const Bases = sequelize.define("Bases", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    OrganisationID: { type: DataTypes.INTEGER, allowNull: false },
    OuvrageID: { type: DataTypes.INTEGER, allowNull: false },
    Volet: { type: DataTypes.STRING },
    CheminBaseDiameX: { type: DataTypes.STRING },
    ProgDiameX: { type: DataTypes.STRING }
  });

  // Définir les associations ici plutôt que dans les références
  Bases.associate = function (models) {
    Bases.belongsTo(models.Organisations, {
      foreignKey: "OrganisationID",
      as: "Organisation"
    });
    Bases.belongsTo(models.Ouvrages, {
      foreignKey: "OuvrageID",
      as: "Ouvrage"
    });
    Bases.hasMany(models.Journaux, {
      foreignKey: "BaseID",
      as: "Journaux"
    });
    Bases.hasMany(models.Magasins, {
      foreignKey: "BaseID",
      as: "Magasins"
    });
    Bases.hasMany(models.Comptes, {
      foreignKey: "BaseID",
      as: "Comptes"
    });
    Bases.hasMany(models.Employes, {
      foreignKey: "BaseID",
      as: "Employes"
    });
  };
  return Bases;
};
