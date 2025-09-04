module.exports = (sequelize, DataTypes) => {
  const TypesPointsEau = sequelize.define("TypesPointsEau", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomType: { type: DataTypes.STRING, allowNull: false },
    CategoriePointEau: { type: DataTypes.ENUM("Public", "Privé") },
    ModalitePaiement: { type: DataTypes.STRING }
  });
  TypesPointsEau.associate = function (models) {
    TypesPointsEau.hasMany(models.PointsEau, {
      foreignKey: 'TypePointEauID',
      as: 'PointsEau'
    });
    TypesPointsEau.hasMany(models.TarifVolumetrique, {
      foreignKey: 'TypePointEauID',
      as: 'TarifVolumetrique'
    });
  };

  return TypesPointsEau;
};
