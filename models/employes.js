module.exports = (sequelize, DataTypes) => {
  const Employes = sequelize.define("Employes", {
    ID: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
    Nom: { type: DataTypes.STRING, allowNull: false },
    Prenom: { type: DataTypes.STRING, allowNull: true },
    Surnom: { type: DataTypes.STRING(50), allowNull: false, unique: true },
    MotDePasse: { type: DataTypes.STRING(255), allowNull: true },
    PosteID: { type: DataTypes.INTEGER, allowNull: false },
    BaseID: { type: DataTypes.INTEGER, allowNull: true },
    DateEmbauche: { type: DataTypes.DATE, allowNull: true },
    DateDebauchage: { type: DataTypes.DATE, allowNull: true },
    ReferentID: { type: DataTypes.INTEGER, allowNull: true },
    NumeroCNaPS: { type: DataTypes.STRING(12), allowNull: true },
    NumeroCIN: { type: DataTypes.STRING(12), allowNull: true },
    NumeroTelephone: { type: DataTypes.STRING(9), allowNull: true },
    AdresseMail: { type: DataTypes.STRING(255), allowNull: true },
    NombreEnfantsCharge: { type: DataTypes.INTEGER, defaultValue: 0 },
    EstSalarie: { type: DataTypes.BOOLEAN, defaultValue: false }
  }, {
    tableName: 'Employes',
    timestamps: true
  });

  Employes.associate = function (models) {
    Employes.belongsTo(models.Postes, {
      foreignKey: 'PosteID',
      as: 'Poste'
    });
    Employes.belongsTo(models.Bases, {
      foreignKey: 'BaseID',
      as: 'Base'
    });
    Employes.belongsTo(models.Employes, {
      foreignKey: 'ReferentID',
      as: 'Referent'
    });
    Employes.hasMany(models.Employes, {
      foreignKey: 'ReferentID',
      as: 'Subordonnes'
    });
    Employes.hasMany(models.Plannings, {
      foreignKey: 'EmployeID',
      as: 'Plannings'
    });
  };

  return Employes;
};