module.exports = (sequelize, DataTypes) => {
  const Adresses = sequelize.define("Adresses", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomAdresse: { type: DataTypes.STRING, allowNull: false },
    OuvrageID: { type: DataTypes.INTEGER, allowNull: false }
  });

  // Définir les associations ici plutôt que dans les références
  Adresses.associate = function (models) {
    Adresses.belongsTo(models.Ouvrages, {
      foreignKey: 'OuvrageID',
      as: 'Ouvrage'
    });
  };

  return Adresses;
};