module.exports = (sequelize, DataTypes) => {
  const Organisations = sequelize.define("Organisations", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    Adresse: { type: DataTypes.STRING },
    ComplementAdresse: { type: DataTypes.STRING },
    CodePostal: { type: DataTypes.STRING },
    Localite: { type: DataTypes.STRING },
    Province: { type: DataTypes.STRING },
    NIF: { type: DataTypes.STRING },
    STAT: { type: DataTypes.STRING },
    NumeroCnaPS: { type: DataTypes.STRING },
    SalaireMinimal: { type: DataTypes.FLOAT }
  });
  Organisations.associate = function (models) {
    Organisations.hasMany(models.Bases, {
      foreignKey: 'OrganisationID',
      as: 'Bases'
    });
    Organisations.hasMany(models.Ouvrages, {
      foreignKey: 'OrganisationID',
      as: 'Ouvrages'
    });


  };
  return Organisations;
};
