module.exports = (sequelize, DataTypes) => {
  const Districts = sequelize.define("Districts", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    RegionID: { type: DataTypes.INTEGER, allowNull: false }
  });
  Districts.associate = function (models) {
    Districts.belongsTo(models.Regions, {
      foreignKey: 'RegionID',
      as: 'Region'
    });
    Districts.hasMany(models.Communes, {
      foreignKey: 'DistrictID',
      as: 'Communes'
    });
  };

  return Districts;
};