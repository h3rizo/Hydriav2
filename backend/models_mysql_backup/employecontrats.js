module.exports = (sequelize, DataTypes) => {
  const EmployeContrats = sequelize.define("EmployeContrats", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    EmployeID: { type: DataTypes.INTEGER, allowNull: false },
    DateDebutContrat: { type: DataTypes.DATE, allowNull: false },
    DateFinContrat: { type: DataTypes.DATE },
    CategorieProfessionnelle: { type: DataTypes.ENUM("3A", "M1", "OS2", "OP2B", "OP3", "HC") },
    TypeContrat: { type: DataTypes.ENUM("Temps plein", "Mi-temps", "Temps partiel", "Journalier") }
  });

  EmployeContrats.associate = function (models) {
    EmployeContrats.belongsTo(models.Employes, {
      foreignKey: 'EmployeID',
      as: 'Employe'
    });
  };


  return EmployeContrats;
};
