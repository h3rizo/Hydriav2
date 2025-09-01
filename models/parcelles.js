module.exports = (sequelize, DataTypes) => {
  const Parcelles = sequelize.define("Parcelles", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    VillageID: { type: DataTypes.INTEGER, allowNull: false },
    NombreHabitants: { type: DataTypes.INTEGER },
    NombreMenages: { type: DataTypes.INTEGER },
    SourceDonnees: { type: DataTypes.STRING, allowNull: true }
  });
  Parcelles.associate = function (models) {
    Parcelles.belongsTo(models.Villages, {
      foreignKey: 'VillageID',
      as: 'Village'
    });
    Parcelles.hasMany(models.PointsEau, {
      foreignKey: 'ParcellesID',
      as: 'PointsEau'
    });
  };
  return Parcelles;
};