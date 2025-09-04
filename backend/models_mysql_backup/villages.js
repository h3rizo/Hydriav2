module.exports = (sequelize, DataTypes) => {
  const Villages = sequelize.define("Villages", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    CommuneID: { type: DataTypes.INTEGER, allowNull: false },
    ClasseAdmin: {
      type: DataTypes.ENUM(
        "Village",
        "Chef-lieu de Fokontany",
        "Chef-lieu de Commune",
        "Chef-lieu de District",
        "Chef-lieu de Region"
      )
    },
    Accessibilite: {
      type: DataTypes.ENUM(
        "Pied",
        "Voiture",
        "Moto",
        "Pirogue"
      )
    },
    DistanceKm: { type: DataTypes.FLOAT }
  });
  Villages.associate = function (models) {
    Villages.belongsTo(models.Communes, {
      foreignKey: 'CommuneID',
      as: 'Commune'
    });
    Villages.hasMany(models.Parcelles, {
      foreignKey: 'VillageID',
      as: 'Parcelles'
    });
    Villages.hasMany(models.Deplacements, {
      foreignKey: 'PointA_VillageID',
      as: 'DepartsDeplacement'
    });
    Villages.hasMany(models.Deplacements, {
      foreignKey: 'PointB_VillageID',
      as: 'ArriveesDeplacement'
    });
  };
  return Villages;
};