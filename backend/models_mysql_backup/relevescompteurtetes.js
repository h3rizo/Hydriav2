module.exports = (sequelize, DataTypes) => {
  const RelevesCompteurTetes = sequelize.define("RelevesCompteurTetes", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    CompteurTeteID: { type: DataTypes.INTEGER, allowNull: false },
    DateReleve: { type: DataTypes.DATE, allowNull: false },
    IndexCompteur: { type: DataTypes.FLOAT, allowNull: false },
    DatePrecedente: { type: DataTypes.DATE },
    IndexPrecedent: { type: DataTypes.FLOAT },
    VolumeConsomme: { type: DataTypes.FLOAT },
    MoisFacture: { type: DataTypes.DATE }
  });
  RelevesCompteurTetes.associate = function (models) {
    RelevesCompteurTetes.belongsTo(models.CompteurTetes, {
      foreignKey: 'CompteurTeteID',
      as: 'CompteurTete'
    });
  };
  return RelevesCompteurTetes;
};
