module.exports = (sequelize, DataTypes) => {
  const Releves = sequelize.define("Releves", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    PointEauID: { type: DataTypes.INTEGER, allowNull: false },
    DateReleve: { type: DataTypes.DATE, allowNull: false },
    IndexCompteur: { type: DataTypes.FLOAT, allowNull: false },
    VolumeNonFacture: { type: DataTypes.FLOAT, defaultValue: 0 },
    DatePrecedente: { type: DataTypes.DATE },
    IndexPrecedent: { type: DataTypes.FLOAT },
    VolumeConsomme: { type: DataTypes.FLOAT },
    MoisFacture: { type: DataTypes.DATE },
    MontantFacture: { type: DataTypes.FLOAT },
    DateEditionFacture: { type: DataTypes.DATE },
    DatePaiementFacture: { type: DataTypes.DATE },
    NumeroDiameX: { type: DataTypes.STRING },
    BaseDiameX: { type: DataTypes.STRING }
  });
  Releves.associate = function (models) {
    Releves.belongsTo(models.PointsEau, {
      foreignKey: 'PointEauID',
      as: 'PointEau'
    });
  };

  return Releves;
};
