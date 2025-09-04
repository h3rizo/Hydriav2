module.exports = (sequelize, DataTypes) => {
  const ActivitesPostes = sequelize.define("ActivitesPostes", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    ActiviteID: { type: DataTypes.INTEGER, allowNull: false },
    PosteID: { type: DataTypes.INTEGER, allowNull: false }
  });

  // Définir les associations ici plutôt que dans les références
  ActivitesPostes.associate = function (models) {
    ActivitesPostes.belongsTo(models.Activites, {
      foreignKey: 'ActiviteID',
      as: 'Activite'
    });
    ActivitesPostes.belongsTo(models.Postes, {
      foreignKey: 'PosteID',
      as: 'Poste'
    });
  };

  return ActivitesPostes;
};
