module.exports = (sequelize, DataTypes) => {
  const Deplacements = sequelize.define("Deplacements", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    PointA_VillageID: { type: DataTypes.INTEGER, allowNull: false },
    PointB_VillageID: { type: DataTypes.INTEGER, allowNull: false },
    MoyenTransport: { type: DataTypes.ENUM("Taxi-brousse", "Pirogue", "Bac") }
  });

  Deplacements.associate = function (models) {
    Deplacements.belongsTo(models.Villages, {
      foreignKey: 'PointA_VillageID',
      as: 'VillagePointA'
    });
    Deplacements.belongsTo(models.Villages, {
      foreignKey: 'PointB_VillageID',
      as: 'VillagePointB'
    });
  };

  return Deplacements;
};