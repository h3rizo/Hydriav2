module.exports = (sequelize, DataTypes) => {
  const OuvragesConstitutifs = sequelize.define("OuvragesConstitutifs", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    OuvrageID: { type: DataTypes.INTEGER, allowNull: false },
    TypeOuvrageConstitutifID: { type: DataTypes.INTEGER, allowNull: false },
    Nom: { type: DataTypes.STRING, allowNull: false }
  });
  OuvragesConstitutifs.associate = function (models) {
    OuvragesConstitutifs.belongsTo(models.Ouvrages, {
      foreignKey: 'OuvrageID',
      as: 'Ouvrage'
    });
    OuvragesConstitutifs.belongsTo(models.TypesOuvragesConstitutifs, {
      foreignKey: 'TypeOuvrageConstitutifID',
      as: 'TypeOuvrageConstitutif'
    });
  };

  return OuvragesConstitutifs;
};

