module.exports = (sequelize, DataTypes) => {
  const TypesActivites = sequelize.define("TypesActivites", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomType: { type: DataTypes.STRING, allowNull: false }
  });

  // Définir les associations
  TypesActivites.associate = function (models) {
    TypesActivites.hasMany(models.Activites, {
      foreignKey: "TypeActiviteID",
      as: "Activites"
    });
    TypesActivites.hasMany(models.Designations, {
      foreignKey: "TypeDesignationID",
      as: "Designations"
    });
    TypesActivites.hasMany(models.DesignationsTypeActivites, {
      foreignKey: "TypeActiviteID",
      as: "DesignationsTypeActivites"
    });
  };

  return TypesActivites;
};
