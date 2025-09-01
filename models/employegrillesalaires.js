module.exports = (sequelize, DataTypes) => {
  const EmployeGrilleSalaires = sequelize.define("EmployeGrilleSalaires", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    EmployeID: { type: DataTypes.INTEGER, allowNull: false, },
    DateSalaire: { type: DataTypes.DATE, allowNull: false },
    NombreJoursTravail: { type: DataTypes.INTEGER },
    NombreJoursFerie: { type: DataTypes.INTEGER },
    NombreHeuresRemplacement: { type: DataTypes.FLOAT },
    SalaireBrutBase: { type: DataTypes.FLOAT, allowNull: false },
    MontantRemplacement: { type: DataTypes.FLOAT },
    MontantJoursFeries: { type: DataTypes.FLOAT },
    MontantMajorationDimanches: { type: DataTypes.FLOAT },
    MontantMajorationNuit: { type: DataTypes.FLOAT },
    SalaireBrutTotal: { type: DataTypes.FLOAT },
    ChargeCNaPS: { type: DataTypes.FLOAT },
    ChargeFMFP: { type: DataTypes.FLOAT },
    BaseImposable: { type: DataTypes.FLOAT },
    DeductionImpots: { type: DataTypes.FLOAT },
    IRSA: { type: DataTypes.FLOAT },
    ChargeSante: { type: DataTypes.FLOAT },
    SalaireNet: { type: DataTypes.FLOAT }
  });

  EmployeGrilleSalaires.associate = function (models) {
    EmployeGrilleSalaires.belongsTo(models.Employes, {
      foreignKey: 'EmployeID',
      as: 'Employe'
    });
    EmployeGrilleSalaires.hasMany(models.EmployeSalaires, {
      foreignKey: 'EmployeGrilleSalaireID',
      as: 'EmployeSalaires'
    });
  };

  return EmployeGrilleSalaires;
};
