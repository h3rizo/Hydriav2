module.exports = (sequelize, DataTypes) => {
  const TypesOuvrages = sequelize.define("TypesOuvrages", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomType: { type: DataTypes.STRING, allowNull: false }
  });
  TypesOuvrages.associate = function (models) {
    TypesOuvrages.hasMany(models.Ouvrages, {
      foreignKey: 'TypeOuvrageID',
      as: 'Ouvrages'
    });
  };
  return TypesOuvrages;
};
