module.exports = (sequelize, DataTypes) => {
  const Postes = sequelize.define("Postes", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomPoste: { type: DataTypes.STRING, allowNull: false },
    NiveauMenu: { type: DataTypes.INTEGER, validate: { min: 0, max: 4 } }
  });
  Postes.associate = function (models) {
    Postes.hasMany(models.Employes, {
      foreignKey: 'PosteID',
      as: 'Employes'
    });
    Postes.hasMany(models.PostesComptes, {
      foreignKey: 'PosteID',
      as: 'PostesComptes'
    });
    Postes.hasMany(models.ActivitesPostes, {
      foreignKey: 'PosteID',
      as: 'ActivitesPostes'
    });
  };

  return Postes;
};
