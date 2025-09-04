module.exports = (sequelize, DataTypes) => {
  const Magasins = sequelize.define("Magasins", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    BaseID: { type: DataTypes.INTEGER, allowNull: false }
  });
  Magasins.associate = function (models) {
    Magasins.belongsTo(models.Bases, {
      foreignKey: 'BaseID',
      as: 'Base'
    });
    Magasins.hasMany(models.PlanningsDetails, {
      foreignKey: 'MagasinID',
      as: 'PlanningsDetails'
    });

  };
  return Magasins;
};