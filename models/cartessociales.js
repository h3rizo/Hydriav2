module.exports = (sequelize, DataTypes) => {
  const CartesSociales = sequelize.define("CartesSociales", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomBeneficiaire: { type: DataTypes.STRING, allowNull: false },
    PointEauID: { type: DataTypes.INTEGER, allowNull: false }
  });

  CartesSociales.associate = function (models) {
    CartesSociales.belongsTo(models.PointsEau, {
      foreignKey: 'PointEauID',
      as: 'PointEau'
    });
    CartesSociales.hasMany(models.ConsosCarteSociale, {
      foreignKey: 'CarteSocialeID',
      as: 'ConsosCarteSociale'
    });
  };

  return CartesSociales;
};