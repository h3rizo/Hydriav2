module.exports = (sequelize, DataTypes) => {
  const Regions = sequelize.define("Regions", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false }
  });
  Regions.associate = function (models) {
    Regions.hasMany(models.Districts, {
      foreignKey: 'RegionID',
      as: 'Districts'
    });
  };
  return Regions;
};