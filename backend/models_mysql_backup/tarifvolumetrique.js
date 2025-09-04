module.exports = (sequelize, DataTypes) => {
  const TarifVolumetrique = sequelize.define("TarifVolumetrique", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    OuvrageID: { type: DataTypes.INTEGER, allownull: false },
    DateDebutTarif: { type: DataTypes.DATE },
    DateFinTarif: { type: DataTypes.DATE },
    PrixAbonnement: { type: DataTypes.FLOAT },
    TypePointEauID: { type: DataTypes.INTEGER, allowNull: false },
    VolumeMinimumFacturer: { type: DataTypes.FLOAT }
  });
  TarifVolumetrique.associate = function (models) {
    TarifVolumetrique.belongsTo(models.Ouvrages, {
      foreignKey: 'OuvrageID',
      as: 'Ouvrage'
    });
    TarifVolumetrique.belongsTo(models.TypesPointsEau, {
      foreignKey: 'TypePointEauID',
      as: 'TypePointEau'
    });
    TarifVolumetrique.hasMany(models.TarifVolumetrique2, {
      foreignKey: 'TarifVolumetriqueID',
      as: 'TarifVolumetrique2'
    });
  };
  return TarifVolumetrique;
};
