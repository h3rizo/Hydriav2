module.exports = (sequelize, DataTypes) => {
  const EmployeSalaires = sequelize.define("EmployeSalaires", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    EmployeGrilleSalaireID: { type: DataTypes.INTEGER, allowNull: false },
    DatePaiement: { type: DataTypes.DATE },
    MontantSalaireNet: { type: DataTypes.FLOAT },
    NumeroSalaireNetDiameX: { type: DataTypes.STRING },
    BaseSalaireNetDiameX: { type: DataTypes.STRING },
    MontantIRSA: { type: DataTypes.FLOAT },
    NumeroIRSADiameX: { type: DataTypes.STRING },
    BaseIRSADiameX: { type: DataTypes.STRING },
    MontantChargeCNaPS: { type: DataTypes.FLOAT },
    NumeroChargeCNaPSDiameX: { type: DataTypes.STRING },
    BaseChargeCNaPSDiameX: { type: DataTypes.STRING },
    MontantChargeFMFP: { type: DataTypes.FLOAT },
    NumeroChargeFMFPDiameX: { type: DataTypes.STRING },
    BaseChargeFMFPDiameX: { type: DataTypes.STRING },
    MontantChargeSante: { type: DataTypes.FLOAT },
    NumeroChargeSanteDiameX: { type: DataTypes.STRING },
    BaseChargeSanteDiameX: { type: DataTypes.STRING }
  });

  EmployeSalaires.associate = function (models) {
    EmployeSalaires.belongsTo(models.EmployeGrilleSalaires, {
      foreignKey: 'EmployeGrilleSalaireID',
      as: 'EmployeGrilleSalaire'
    });
  };

  return EmployeSalaires;
};
