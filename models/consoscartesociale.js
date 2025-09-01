module.exports = (sequelize, DataTypes) => {
  const ConsosCarteSociale = sequelize.define("ConsosCarteSociale", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    CarteSocialeID: { type: DataTypes.INTEGER, allowNull: false },
    MoisFacture: { type: DataTypes.DATE },
    ConsommationBidons20L: { type: DataTypes.INTEGER },
    MontantFacture: { type: DataTypes.FLOAT, defaultValue: 100 },
    NumeroDiameX: { type: DataTypes.STRING },
    BaseDiameX: { type: DataTypes.STRING }
  });

  ConsosCarteSociale.associate = function (models) {
    ConsosCarteSociale.belongsTo(models.CartesSociales, {
      foreignKey: 'CarteSocialeID',
      as: 'CarteSociale'
    });
  };

  return ConsosCarteSociale;
};
