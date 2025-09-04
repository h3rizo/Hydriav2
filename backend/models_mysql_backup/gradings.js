module.exports = (sequelize, DataTypes) => {
  const Gradings = sequelize.define("Gradings", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    OuvrageID: { type: DataTypes.INTEGER, allowNull: false },
    Annee: { type: DataTypes.INTEGER, allowNull: false },
    Grading: { type: DataTypes.ENUM("A", "B", "C", "D", "E", "X") },
    MotifGrading: { type: DataTypes.STRING }
  });

  Gradings.associate = function (models) {
    Gradings.belongsTo(models.Ouvrages, {
      foreignKey: 'OuvrageID',
      as: 'Ouvrage'
    });
  };
  return Gradings;
};
