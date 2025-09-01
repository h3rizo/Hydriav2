module.exports = (sequelize, DataTypes) => {
  const TypesTypesOuvragesConstitutifs = sequelize.define("TypesTypesOuvragesConstitutifs", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomType: { type: DataTypes.ENUM("Captage", "Citerne", "Point d'eau", "Autres") }
  });
  TypesTypesOuvragesConstitutifs.associate = function (models) {
    TypesTypesOuvragesConstitutifs.hasMany(models.TypesOuvragesConstitutifs, {
      foreignKey: 'TypeTypeOuvrageConstitutifID',
      as: 'TypesOuvragesConstitutifs'
    });
  };
  return TypesTypesOuvragesConstitutifs;
};
