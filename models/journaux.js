module.exports = (sequelize, DataTypes) => {
  const Journaux = sequelize.define("Journaux", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    BaseID: { type: DataTypes.INTEGER, allowNull: false },
    Compte: { type: DataTypes.INTEGER, allowNull: false },
    Code: { type: DataTypes.STRING, allowNull: false }
  });
  Journaux.associate = function (models) {
    Journaux.belongsTo(models.Bases, {
      foreignKey: 'BaseID',
      as: 'Base'
    });
  };
  return Journaux;
};
