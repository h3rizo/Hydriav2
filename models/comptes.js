module.exports = (sequelize, DataTypes) => {
  const PlanComptes = sequelize.define("Comptes", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NumeroCompte: { type: DataTypes.STRING, allowNull: false },
    NomCompte: { type: DataTypes.STRING, allowNull: false },
    BaseID: { type: DataTypes.INTEGER, allowNull: false }
  });
  PlanComptes.associate = function (models) {
    PlanComptes.belongsTo(models.Bases, {
      foreignKey: 'BaseID',
      as: 'Base'
    });
    PlanComptes.hasMany(models.DesignationsComptes, {
      foreignKey: 'CompteID',
      as: 'DesignationsComptes'
    });
    PlanComptes.hasMany(models.PlanningsDetails, {
      foreignKey: 'CompteID',
      as: 'PlanningsDetails'
    });

  };
  return PlanComptes;
};
