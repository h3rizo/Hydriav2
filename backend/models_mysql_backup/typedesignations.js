module.exports = (sequelize, DataTypes) => {
  const TypeDesignations = sequelize.define("TypeDesignations", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomType: { type: DataTypes.STRING, allowNull: false }
  });

  TypeDesignations.associate = function (models) {
    TypeDesignations.hasMany(models.Designations, {
      foreignKey: 'TypeDesignationID',
      as: 'Designations'
    });
  };
  return TypeDesignations;
};
