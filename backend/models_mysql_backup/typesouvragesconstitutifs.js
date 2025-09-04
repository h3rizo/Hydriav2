module.exports = (sequelize, DataTypes) => {
  const TypesOuvragesConstitutifs = sequelize.define("TypesOuvragesConstitutifs", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomType: { type: DataTypes.STRING, allowNull: false },
    TypeTypeOuvrageConstitutifID: {
      type: DataTypes.INTEGER, allowNull: false
    }
  });
  TypesOuvragesConstitutifs.associate = function (models) {
    TypesOuvragesConstitutifs.belongsTo(models.TypesOuvragesConstitutifs, {
      foreignKey: 'TypeTypeOuvrageConstitutifID',
      as: 'TypeTypeOuvrageConstitutif'
    });
    TypesOuvragesConstitutifs.hasMany(models.OuvragesConstitutifs, {
      foreignKey: 'TypeOuvrageConstitutifID',
      as: 'OuvragesConstitutifs'
    });
  };
  return TypesOuvragesConstitutifs;
};
