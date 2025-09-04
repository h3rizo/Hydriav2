module.exports = (sequelize, DataTypes) => {
  const DesignationsTypeActivites = sequelize.define("DesignationsTypeActivites", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    DesignationID: { type: DataTypes.INTEGER, allowNull: false },
    TypeActiviteID: { type: DataTypes.INTEGER, allowNull: false }
  });

  DesignationsTypeActivites.associate = function (models) {
    DesignationsTypeActivites.belongsTo(models.Designations, {
      foreignKey: 'DesignationID',
      as: 'Designation'
    });
    DesignationsTypeActivites.belongsTo(models.TypesActivites, {
      foreignKey: 'TypeActiviteID',
      as: 'TypeActivite'
    });
  };
  return DesignationsTypeActivites;
};
