module.exports = (sequelize, DataTypes) => {
  const TarifVolumetrique2 = sequelize.define("TarifVolumetrique2", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    TarifVolumetriqueID: { type: DataTypes.INTEGER, allowNull: false },
    MaxTranche: { type: DataTypes.FLOAT },
    TarifTranche: { type: DataTypes.FLOAT }
  });
  TarifVolumetrique2.associate = function (models) {
    TarifVolumetrique2.belongsTo(models.TarifVolumetrique, {
      foreignKey: 'TarifVolumetriqueID',
      as: 'TarifVolumetrique'
    });
  };
  return TarifVolumetrique2;
};
