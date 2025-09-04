module.exports = (sequelize, DataTypes) => {
  const Ouvrages = sequelize.define("Ouvrages", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    TypeOuvrageID: { type: DataTypes.INTEGER, allowNull: false },
    AnneeRealisation: { type: DataTypes.INTEGER },
    AnneeReabilitation: { type: DataTypes.INTEGER },
    Intervenant: { type: DataTypes.STRING },
    Remarque: { type: DataTypes.TEXT },
    OrganisationID: { type: DataTypes.INTEGER, allowNull: false },
    EstSaisonnier: { type: DataTypes.BOOLEAN, defaultValue: false },
    Photos: { type: DataTypes.TEXT }
  });
  Ouvrages.associate = function (models) {
    Ouvrages.belongsTo(models.Organisations, {
      foreignKey: 'OrganisationID',
      as: 'Organisation'
    });
    Ouvrages.belongsTo(models.TypesOuvrages, {
      foreignKey: 'TypeOuvrageID',
      as: 'TypeOuvrage'
    });
    Ouvrages.hasMany(models.Bases, {
      foreignKey: 'OuvrageID',
      as: 'Bases'
    });
    Ouvrages.hasMany(models.ModalitesGestions, {
      foreignKey: 'OuvrageID',
      as: 'ModalitesGestion'
    });
    Ouvrages.hasMany(models.Gradings, {
      foreignKey: 'OuvrageID',
      as: 'Gradings'
    });
    Ouvrages.hasMany(models.CompteurTetes, {
      foreignKey: 'OuvrageID',
      as: 'CompteurTetes'
    });
    Ouvrages.hasMany(models.PointsEau, {
      foreignKey: 'OuvrageID',
      as: 'PointsEau'
    });
    Ouvrages.hasMany(models.TarifVolumetrique, {
      foreignKey: 'OuvrageID',
      as: 'TarifVolumetrique'
    });
    Ouvrages.hasMany(models.OuvragesConstitutifs, {
      foreignKey: 'OuvrageID',
      as: 'OuvragesConstitutifs'
    });
    Ouvrages.hasMany(models.Plannings, {
      foreignKey: 'OuvrageID',
      as: 'Plannings'
    });
    Ouvrages.hasMany(models.Adresses, {
      foreignKey: 'OuvrageID',
      as: 'Adresses'
    });
  };
  return Ouvrages;
};