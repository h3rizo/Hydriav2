module.exports = (sequelize, DataTypes) => {
  const DesignationsComptes = sequelize.define("DesignationsComptes", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    DesignationID: { type: DataTypes.INTEGER, allowNull: false },
    CompteID: { type: DataTypes.INTEGER, allowNull: false }
  });

  DesignationsComptes.associate = function (models) {
    DesignationsComptes.belongsTo(models.Designations, {
      foreignKey: "DesignationID",
      as: "Designation"
    });
    DesignationsComptes.belongsTo(models.Comptes, {
      foreignKey: "CompteID",
      as: "Compte"
    });
  };
  return DesignationsComptes;
};
