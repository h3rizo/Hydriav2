module.exports = (sequelize, DataTypes) => {
  const CompteurTetes = sequelize.define("CompteurTetes", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    OuvrageID: { type: DataTypes.INTEGER, allowNull: false },
    NumeroCompteur: { type: DataTypes.STRING, allowNull: false }
  });

  CompteurTetes.associate = function (models) {
    CompteurTetes.belongsTo(models.Ouvrages, {
      foreignKey: 'OuvrageID',
      as: 'Ouvrage'
    });
    CompteurTetes.hasMany(models.PointsEau, {
      foreignKey: 'CompteurTeteID',
      as: 'PointsEau'
    });
    CompteurTetes.hasMany(models.RelevesCompteurTetes, {
      foreignKey: 'CompteurTeteID',
      as: 'RelevesCompteurTetes'
    });
  };

  return CompteurTetes;
};
