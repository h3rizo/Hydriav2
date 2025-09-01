module.exports = (sequelize, DataTypes) => {
  const PointsEau = sequelize.define("PointsEau", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    NomPE: { type: DataTypes.STRING, allowNull: false },
    NomAbonne: { type: DataTypes.STRING },
    ContactAbonne: { type: DataTypes.STRING },
    CompteurTeteID: { type: DataTypes.INTEGER },
    TypePointEauID: { type: DataTypes.INTEGER, allowNull: false },
    OuvrageID: { type: DataTypes.INTEGER, allowNull: false },
    ParcelleID: { type: DataTypes.INTEGER, allowNull: false },
    DateBranchement: { type: DataTypes.DATE },
    DateArretBranchement: { type: DataTypes.DATE },
    Latitude: { type: DataTypes.FLOAT },
    Longitude: { type: DataTypes.FLOAT },
    TypeAbonne: { type: DataTypes.ENUM("Boutique", "Particulier") },
    EstBranchementInstitutionnel: { type: DataTypes.BOOLEAN, defaultValue: false },
    TarifForfaitaire: { type: DataTypes.FLOAT },
    NumeroDiameXDemande: { type: DataTypes.STRING },
    NumeroDiameXPaiementDevis: { type: DataTypes.STRING },
    BaseDiameXDemande: { type: DataTypes.STRING },
    BaseDiameXPaiementDevis: { type: DataTypes.STRING },
    MontantDemandePaye: { type: DataTypes.FLOAT },
    MontantDevisPaye: { type: DataTypes.FLOAT },
    NbConsommateursDirects: { type: DataTypes.INTEGER },
    NbMenagesConsommateursIndirects: { type: DataTypes.INTEGER },
    NumeroTel: { type: DataTypes.STRING },
    Distance: { type: DataTypes.FLOAT },
    IDXls: { type: DataTypes.INTEGER },
    Etat: { type: DataTypes.STRING }
  });
  PointsEau.associate = function (models) {
    PointsEau.belongsTo(models.CompteurTetes, {
      foreignKey: 'CompteurTeteID',
      as: 'CompteurTete'
    });
    PointsEau.belongsTo(models.TypesPointsEau, {
      foreignKey: 'TypePointEauID',
      as: 'TypePointEau'
    });
    PointsEau.belongsTo(models.Ouvrages, {
      foreignKey: 'OuvrageID',
      as: 'Ouvrage'
    });
    PointsEau.belongsTo(models.Parcelles, {
      foreignKey: 'ParcelleID',
      as: 'Parcelle'
    });
    PointsEau.hasMany(models.Releves, {
      foreignKey: 'PointEauID',
      as: 'Releves'
    });
    PointsEau.hasMany(models.CartesSociales, {
      foreignKey: 'PointEauID',
      as: 'CartesSociales'
    });

  };
  return PointsEau;
};