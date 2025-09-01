module.exports = (sequelize, DataTypes) => {
  const PostesComptes = sequelize.define("PostesComptes", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    PosteID: { type: DataTypes.INTEGER, allowNull: false },
    TarifIndemnite: { type: DataTypes.FLOAT },
    CompteSalaire: { type: DataTypes.STRING },
    CompteIRSA: { type: DataTypes.STRING },
    CompteCNaPS: { type: DataTypes.STRING },
    PrefixePoste: { type: DataTypes.STRING }
  });
  PostesComptes.associate = function (models) {
    PostesComptes.belongsTo(models.Postes, {
      foreignKey: 'PosteID',
      as: 'Poste'
    });
  };
  return PostesComptes;
};
