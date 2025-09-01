module.exports = (sequelize, DataTypes) => {
  const Communes = sequelize.define("Communes", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    DistrictID: { type: DataTypes.INTEGER, allowNull: false },
    NomMaire: { type: DataTypes.STRING },
    ContactMaire: { type: DataTypes.STRING },
    NomPresidentConseil: { type: DataTypes.STRING },
    ContactPresidentConseil: { type: DataTypes.STRING },
    NomPremierConseiller: { type: DataTypes.STRING },
    ContactPremierConseiller: { type: DataTypes.STRING },
    NomSecondConseiller: { type: DataTypes.STRING },
    ContactSecondConseiller: { type: DataTypes.STRING },
    NomTroisiemeConseiller: { type: DataTypes.STRING },
    ContactTroisiemeConseiller: { type: DataTypes.STRING },
    NomQuatriemeConseiller: { type: DataTypes.STRING },
    ContactQuatriemeConseiller: { type: DataTypes.STRING },
    NomCinquiemeConseiller: { type: DataTypes.STRING },
    ContactCinquiemeConseiller: { type: DataTypes.STRING }
  });

  Communes.associate = function (models) {
    Communes.belongsTo(models.Districts, {
      foreignKey: 'DistrictID',
      as: 'District'
    });
    Communes.hasMany(models.Villages, {
      foreignKey: 'CommuneID',
      as: 'Villages'
    });
  };

  return Communes;
};