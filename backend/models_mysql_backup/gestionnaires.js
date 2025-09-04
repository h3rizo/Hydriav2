module.exports = (sequelize, DataTypes) => {
  const Gestionnaires = sequelize.define("Gestionnaires", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    Contact: { type: DataTypes.STRING }
  });
  Gestionnaires.associate = function (models) {
    Gestionnaires.hasMany(models.ModalitesGestions, {

      foreignKey: 'GestionnaireID',
      as: 'ModalitesGestion'
    });
  };

  return Gestionnaires;

};