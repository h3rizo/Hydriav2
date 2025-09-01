module.exports = (sequelize, DataTypes) => {
  const Activites = sequelize.define("Activites", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    TypeActiviteID: {
      type: DataTypes.INTEGER,
      allowNull: true  // Correction: allowNull au lieu de allownull
    },
    Verrou: {
      type: DataTypes.BOOLEAN,
      defaultValue: false
    }
  }, {
    tableName: 'Activites',
    timestamps: true
  });

  // Définir les associations ici plutôt que dans les références
  Activites.associate = function (models) {
    Activites.belongsTo(models.TypesActivites, {
      foreignKey: 'TypeActiviteID',
      as: 'TypeActivite'
    });
    Activites.hasMany(models.ActivitesPostes, {
      foreignKey: 'ActiviteID',
      as: 'ActivitesPostes'
    });
    Activites.hasMany(models.Plannings, {
      foreignKey: 'ActiviteID',
      as: 'Plannings'
    });
  };
  return Activites;
};