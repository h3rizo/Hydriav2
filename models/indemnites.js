module.exports = (sequelize, DataTypes) => {
  const Indemnites = sequelize.define("Indemnites", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    PlanningID: { type: DataTypes.INTEGER, allowNull: false },
    MoisFacture: { type: DataTypes.DATE },
    MontantIndemnite: { type: DataTypes.FLOAT, defaultValue: 10000 },
    NumeroDiameX: { type: DataTypes.STRING },
    BaseDiameX: { type: DataTypes.STRING }
  });

  Indemnites.associate = function (models) {
    Indemnites.belongsTo(models.Plannings, {
      foreignKey: 'PlanningID',
      as: 'Planning'
    });
  };

  return Indemnites;
};
