const fs = require("fs");
const path = require("path");

// Configuration des modèles à générer
const modelsConfig = {
  poste: {
    tableName: "Postes",
    attributes: {
      NomPoste: { type: "STRING(255)", allowNull: false },
      Verrou: { type: "BOOLEAN", defaultValue: false },
      NiveauMenu: { type: "INTEGER", allowNull: true }
    },
    associations: [{ type: "hasMany", model: "Employes", foreignKey: "PosteID", as: "Employes" }]
  },


  organisation: {
    tableName: "Organisations",
    attributes: {
      Nom: { type: "STRING(255)", allowNull: false },
      Adresse: { type: "STRING(255)", allowNull: true },
      ComplementAdresse: { type: "STRING(255)", allowNull: true },
      CodePostal: { type: "STRING(3)", allowNull: true },
      Localite: { type: "INTEGER", allowNull: true },
      NIF: { type: "STRING(10)", allowNull: true },
      STAT: { type: "STRING(19)", allowNull: true },
      Telephone: { type: "STRING(10)", allowNull: true },
      mail: { type: "STRING(255)", allowNull: true }
    },
    associations: [
      { type: "hasMany", model: "Ouvrages", foreignKey: "OrganisationID", as: "Ouvrages" },
      { type: "hasMany", model: "Bases", foreignKey: "OrganisationID", as: "Bases" }
    ]
  },

  region: {
    tableName: "Regions",
    attributes: {
      Nom: { type: "STRING(255)", allowNull: false }
    },
    associations: [{ type: "hasMany", model: "Districts", foreignKey: "RegionID", as: "Districts" }]
  },

  district: {
    tableName: "Districts",
    attributes: {
      Nom: { type: "STRING(255)", allowNull: false },
      RegionID: { type: "INTEGER", references: { model: "Regions", key: "ID" } }
    },
    associations: [
      { type: "belongsTo", model: "Regions", foreignKey: "RegionID", as: "Region" },
      { type: "hasMany", model: "Communes", foreignKey: "DistrictID", as: "Communes" }
    ]
  },

  commune: {
    tableName: "Communes",
    attributes: {
      Nom: { type: "STRING(255)", allowNull: false },
      DistrictID: { type: "INTEGER", references: { model: "Districts", key: "ID" } },
      NomMaire: { type: "STRING(255)", allowNull: true },
      ContactMaire: { type: "STRING(255)", allowNull: true }
    },
    associations: [
      { type: "belongsTo", model: "Districts", foreignKey: "DistrictID", as: "District" },
      { type: "hasMany", model: "Villages", foreignKey: "CommuneID", as: "Villages" }
    ]
  },

  village: {
    tableName: "Villages",
    attributes: {
      Nom: { type: "STRING(255)", allowNull: false },
      CommuneID: { type: "INTEGER", references: { model: "Communes", key: "ID" } },
      ClasseAdmin: {
        type: "ENUM",
        values: [
          "Village",
          "Chef-lieu Fokontany",
          "Chef-lieu Commune",
          "Chef-lieu District",
          "Chef-lieu Région"
        ]
      },
      Accessibilite: { type: "ENUM", values: ["Voiture", "Moto", "Pirogue", "Pied"] },
      DistanceKm: { type: "FLOAT", allowNull: true }
    },
    associations: [
      { type: "belongsTo", model: "Communes", foreignKey: "CommuneID", as: "Commune" },
      { type: "hasMany", model: "Parcelles", foreignKey: "VillageID", as: "Parcelles" }
    ]
  },

  parcelle: {
    tableName: "Parcelles",
    attributes: {
      Nom: { type: "STRING(255)", allowNull: false },
      VillageID: { type: "INTEGER", references: { model: "Villages", key: "ID" } },
      NombreHabitants: { type: "INTEGER", allowNull: true },
      NombreMenages: { type: "INTEGER", allowNull: true }
    },
    associations: [
      { type: "belongsTo", model: "Villages", foreignKey: "VillageID", as: "Village" },
      { type: "hasMany", model: "PointsEaus", foreignKey: "ParcelleID", as: "PointsEaus" }
    ]
  },

  typeouvrage: {
    tableName: "TypesOuvrages",
    attributes: {
      NomType: { type: "STRING(255)", allowNull: false }
    },
    associations: [{ type: "hasMany", model: "Ouvrages", foreignKey: "TypeOuvrageID", as: "Ouvrages" }]
  },

  ouvrage: {
    tableName: "Ouvrages",
    attributes: {
      Nom: { type: "STRING(255)", allowNull: false },
      TypeOuvrageID: { type: "INTEGER", allowNull: false, references: { model: "TypesOuvrages", key: "ID" } },
      OrganisationID: { type: "INTEGER", allowNull: false, references: { model: "Organisations", key: "ID" } },
      AnneeRealisation: { type: "INTEGER", allowNull: true },
      Intervenant: { type: "STRING(255)", allowNull: true },
      EstSaisonnier: { type: "BOOLEAN", defaultValue: false },
      Photos: { type: "TEXT", allowNull: true }
    },
    associations: [
      { type: "belongsTo", model: "TypesOuvrages", foreignKey: "TypeOuvrageID", as: "TypeOuvrage" },
      { type: "belongsTo", model: "Organisations", foreignKey: "OrganisationID", as: "Organisation" },
      { type: "hasMany", model: "PointsEaus", foreignKey: "OuvrageID", as: "PointsEaus" },
      { type: "hasMany", model: "Plannings", foreignKey: "OuvrageID", as: "Plannings" }
    ]
  }
};

// Template de base pour un modèle
function generateModelTemplate(modelName, config) {
  const className = modelName.charAt(0).toUpperCase() + modelName.slice(1);

  return `module.exports = (sequelize, DataTypes) => {
  const ${className} = sequelize.define('${config.tableName}', {
    ID: {
      type: DataTypes.INTEGER,
      primaryKey: true,
      autoIncrement: true,
      allowNull: false
    },
${generateAttributes(config.attributes)},
    createdAt: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW
    },
    updatedAt: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW
    }
  }, {
    tableName: '${config.tableName}',
    timestamps: true,
    charset: 'utf8mb4',
    collate: 'utf8mb4_unicode_ci',
    indexes: [
      ${generateIndexes(config.attributes)}
    ]
  });

  // Associations
  ${className}.associate = (models) => {
${generateAssociations(config.associations)}
  };

  // Méthodes personnalisées
  ${className}.prototype.toString = function() {
    return \`\${this.constructor.name}#\${this.ID}\`;
  };

  return ${className};
};`;
}

// Générer les attributs
function generateAttributes(attributes) {
  return Object.entries(attributes)
    .map(([name, config]) => {
      let attr = `    ${name}: {\n`;

      // Type
      if (config.type.includes("ENUM")) {
        attr += `      type: DataTypes.ENUM(${config.values.map((v) => `'${v}'`).join(", ")}),\n`;
      } else {
        attr += `      type: DataTypes.${config.type},\n`;
      }

      // Null/Not null
      if (config.allowNull !== undefined) {
        attr += `      allowNull: ${config.allowNull},\n`;
      }

      // Default value
      if (config.defaultValue !== undefined) {
        attr += `      defaultValue: ${typeof config.defaultValue === "string" ? `'${config.defaultValue}'` : config.defaultValue},\n`;
      }

      // References
      if (config.references) {
        attr += `      references: {\n`;
        attr += `        model: '${config.references.model}',\n`;
        attr += `        key: '${config.references.key}'\n`;
        attr += `      },\n`;
      }

      // Validation
      attr += `      validate: {\n`;
      if (config.allowNull === false) {
        attr += `        notEmpty: true,\n`;
      }
      if (config.type.includes("STRING")) {
        const maxLength = config.type.match(/\((\d+)\)/)?.[1] || 255;
        attr += `        len: [1, ${maxLength}]\n`;
      }
      attr += `      }\n`;

      attr += `    }`;
      return attr;
    })
    .join(",\n");
}

// Générer les index
function generateIndexes(attributes) {
  const indexes = [];

  Object.entries(attributes).forEach(([name, config]) => {
    if (config.references) {
      indexes.push(`      {
        name: 'idx_${name.toLowerCase()}',
        fields: ['${name}']
      }`);
    }
  });

  return indexes.join(",\n");
}

// Générer les associations
function generateAssociations(associations) {
  if (!associations) return "    // Pas d'associations définies";

  return associations
    .map((assoc) => {
      return `    ${assoc.type === "belongsTo" ? `// ${assoc.model} parent` : `// ${assoc.model} enfants`}
    ${assoc.type === "belongsTo"
          ? `${assoc.model.slice(0, -1)}`
          : assoc.model.charAt(0).toUpperCase() + assoc.model.slice(1)
        }.${assoc.type}(models.${assoc.model}, {
      foreignKey: '${assoc.foreignKey}',
      as: '${assoc.as}'
    });`;
    })
    .join("\n\n");
}

// Générer tous les modèles
function generateAllModels() {
  const modelsDir = path.join(__dirname, "models");

  // Créer le dossier models s'il n'existe pas
  if (!fs.existsSync(modelsDir)) {
    fs.mkdirSync(modelsDir);
    console.log("📁 Dossier models/ créé");
  }

  // Générer chaque modèle
  Object.entries(modelsConfig).forEach(([modelName, config]) => {
    const content = generateModelTemplate(modelName, config);
    const filename = path.join(modelsDir, `${modelName}.js`);

    fs.writeFileSync(filename, content);
    console.log(`✅ Modèle généré: ${filename}`);
  });

  console.log(`🎉 ${Object.keys(modelsConfig).length} modèles générés avec succès !`);
  console.log("📝 N'oubliez pas de :");
  console.log("   1. Vérifier et ajuster les modèles générés");
  console.log("   2. Ajouter les validations métier spécifiques");
  console.log("   3. Compléter les associations manquantes");
  console.log("   4. Tester avec npm start");
}

// Exécuter le script
if (require.main === module) {
  console.log("🚀 Génération des modèles Sequelize...");
  generateAllModels();
}

module.exports = { generateAllModels, modelsConfig };
