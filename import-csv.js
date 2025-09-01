const fs = require('fs');
const path = require('path');
const { parse } = require('csv-parse');
const { supabase } = require('./supabaseClient');
require('dotenv').config();

const importConfig = {
  // Tables de base (sans dépendances)
  'organisations': {
    tableName: 'organisations',
    mapping: {
      'ID': 'id',
      'Nom': 'nom',
      'Adresse': 'adresse',
      'Localite': 'localite',
      'Province': 'province',
      'NIF': 'nif',
      'STAT': 'stat',
      'NumeroCnaPS': 'numerocnaps',
      'SalaireMinimal': 'salaireminimal'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      if (row.nif !== undefined && row.nif !== null && row.nif !== '') {
        row.nif = parseInt(row.nif);
      }
      if (row.salaireminimal !== undefined && row.salaireminimal !== null && row.salaireminimal !== '') {
        row.salaireminimal = parseInt(row.salaireminimal);
      }
      return row;
    }
  },

  'typesactivites': {
    tableName: 'typesactivites',
    mapping: {
      'ID': 'id',
      'NomType': 'nomtype'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      return row;
    }
  },

  'typesouvrages': {
    tableName: 'typesouvrages',
    mapping: {
      'ID': 'id',
      'NomType': 'nomtype'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      return row;
    }
  },

  'regions': {
    tableName: 'regions',
    mapping: {
      'ID': 'id',
      'Nom': 'nom'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      return row;
    }
  },

  'postes': {
    tableName: 'postes',
    mapping: {
      'NomPoste': 'nomposte',
      'NiveauMenu': 'niveaumenu'
    },
    preprocess: (row) => {
      if (row.niveaumenu !== undefined && row.niveaumenu !== null && row.niveaumenu !== '') {
        row.niveaumenu = parseInt(row.niveaumenu) || 1;
      }
      return row;
    }
  },

  'typesouvragesconstitutifs': {
    tableName: 'typesouvragesconstitutifs',
    mapping: {
      'ID': 'id',
      'NomType': 'nomtype'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      return row;
    }
  },

  'typedesignations': {
    tableName: 'typedesignations',
    mapping: {
      'ID': 'id',
      'NomType': 'nomtype'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      return row;
    }
  },

  'typespointseau': {
    tableName: 'typespointseau',
    mapping: {
      'ID': 'id',
      'NomType': 'nomtype'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      return row;
    }
  },

  'typestypesouvragesconstitutifs': {
    tableName: 'typestypesouvragesconstitutifs',
    mapping: {
      'TypeOuvrageConstitutifID': 'typeouvrageconstitutifid',
      'TypeTypeOuvrageConstitutifID': 'typetypeouvrageconstitutifid'
    },
    preprocess: (row) => {
      if (row.typeouvrageconstitutifid !== undefined && row.typeouvrageconstitutifid !== null && row.typeouvrageconstitutifid !== '') {
        row.typeouvrageconstitutifid = parseInt(row.typeouvrageconstitutifid);
      }
      if (row.typetypeouvrageconstitutifid !== undefined && row.typetypeouvrageconstitutifid !== null && row.typetypeouvrageconstitutifid !== '') {
        row.typetypeouvrageconstitutifid = parseInt(row.typetypeouvrageconstitutifid);
      }
      return row;
    }
  },

  // Tables géographiques (avec dépendances)
  'districts': {
    tableName: 'districts',
    mapping: {
      'ID': 'id',
      'Nom': 'nom',
      'RegionID': 'regionid'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      if (row.regionid !== undefined && row.regionid !== null && row.regionid !== '') {
        row.regionid = parseInt(row.regionid);
      }
      return row;
    }
  },

  'communes': {
    tableName: 'communes',
    mapping: {
      'ID': 'id',
      'Nom': 'nom',
      'DistrictID': 'districtid',
      'NomMaire': 'nommaire',
      'ContactMaire': 'contactmaire',
      'NomPresidentConseil': 'nompresidentconseil',
      'ContactPresidentConseil': 'contactpresidentconseil',
      'NomPremierConseiller': 'nompremierconseiller',
      'ContactPremierConseiller': 'contactpremierconseiller',
      'NomSecondConseiller': 'nomsecondconseiller',
      'ContactSecondConseiller': 'contactsecondconseiller',
      'NomTroisiemeConseiller': 'nomtroisiemeconseiller',
      'ContactTroisiemeConseiller': 'contacttroisiemeconseiller',
      'NomQuatriemeConseiller': 'nomquatriemeconseiller',
      'ContactQuatriemeConseiller': 'contactquatriemeconseiller',
      'NomCinquiemeConseiller': 'nomcinquiemeconseiller',
      'ContactCinquiemeConseiller': 'contactcinquiemeconseiller'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      if (row.districtid !== undefined && row.districtid !== null && row.districtid !== '') {
        row.districtid = parseInt(row.districtid);
      }
      return row;
    }
  },

  'villages': {
    tableName: 'villages',
    mapping: {
      'ID': 'id',
      'Nom': 'nom',
      'CommuneID': 'communeid',
      'ClasseAdmin': 'classeadmin',
      'Accessibilite': 'accessibilite',
      'DistanceKm': 'distancekm'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      if (row.communeid !== undefined && row.communeid !== null && row.communeid !== '') {
        row.communeid = parseInt(row.communeid);
      }
      if (row.distancekm !== undefined && row.distancekm !== null && row.distancekm !== '') {
        row.distancekm = parseFloat(row.distancekm) || 0;
      }
      return row;
    }
  },

  // Ouvrages et bases
  'ouvrages': {
    tableName: 'ouvrages',
    mapping: {
      'Nom': 'nom',
      'TypeOuvrageID': 'typeouvrageid',
      'OrganisationID': 'organisationid',
      'AnneeRealisation': 'anneerealisation',
      'AnneeReabilitation': 'anneereabilitation',
      'Intervenant': 'intervenant',
      'Remarque': 'remarque',
      'EstSaisonnier': 'estsaisonnier'
    },
    preprocess: (row) => {
      if (row.typeouvrageid !== undefined && row.typeouvrageid !== null && row.typeouvrageid !== '') {
        row.typeouvrageid = parseInt(row.typeouvrageid);
      }
      if (row.organisationid !== undefined && row.organisationid !== null && row.organisationid !== '') {
        row.organisationid = parseInt(row.organisationid);
      }
      if (row.anneerealisation !== undefined && row.anneerealisation !== null && row.anneerealisation !== '') {
        row.anneerealisation = parseInt(row.anneerealisation);
      }
      if (row.anneereabilitation !== undefined && row.anneereabilitation !== null && row.anneereabilitation !== '') {
        row.anneereabilitation = parseInt(row.anneereabilitation);
      }
      if (row.estsaisonnier !== undefined && row.estsaisonnier !== null) {
        const val = String(row.estsaisonnier).toLowerCase();
        row.estsaisonnier = val === 'true' || val === '1' || val === 'oui';
      }
      return row;
    }
  },

  'ouvragesconstitutifs': {
    tableName: 'ouvragesconstitutifs',
    mapping: {
      'Nom': 'nom',
      'OuvrageID': 'ouvrageid',
      'TypeOuvrageConstitutifID': 'typeouvrageconstitutifid'
    },
    preprocess: (row) => {
      if (row.ouvrageid !== undefined && row.ouvrageid !== null && row.ouvrageid !== '') {
        row.ouvrageid = parseInt(row.ouvrageid);
      }
      if (row.typeouvrageconstitutifid !== undefined && row.typeouvrageconstitutifid !== null && row.typeouvrageconstitutifid !== '') {
        row.typeouvrageconstitutifid = parseInt(row.typeouvrageconstitutifid);
      }
      return row;
    }
  },

  'bases': {
    tableName: 'bases',
    mapping: {
      'Nom': 'nom',
      'OrganisationID': 'organisationid',
      'OuvrageID': 'ouvrageid',
      'Volet': 'volet',
      'CheminBaseDiameX': 'cheminbasediamex',
      'ProgDiameX': 'progdiamex'
    },
    preprocess: (row) => {
      if (row.organisationid !== undefined && row.organisationid !== null && row.organisationid !== '') {
        row.organisationid = parseInt(row.organisationid);
      }
      if (row.ouvrageid !== undefined && row.ouvrageid !== null && row.ouvrageid !== '') {
        row.ouvrageid = parseInt(row.ouvrageid);
      }
      return row;
    }
  },

  'activites': {
    tableName: 'activites',
    mapping: {
      'Nom': 'nom',
      'TypeActiviteID': 'typeactiviteid',
      'Verrou': 'verrou'
    },
    preprocess: (row) => {
      if (row.typeactiviteid !== undefined && row.typeactiviteid !== null && row.typeactiviteid !== '') {
        row.typeactiviteid = parseInt(row.typeactiviteid);
      }
      if (row.verrou !== undefined && row.verrou !== null) {
        const val = String(row.verrou).toLowerCase();
        row.verrou = val === 'true' || val === '1' || val === 'oui';
      }
      return row;
    }
  },

  'activitespostes': {
    tableName: 'activitespostes',
    mapping: {
      'ActiviteID': 'activiteid',
      'PosteID': 'posteid'
    },
    preprocess: (row) => {
      if (row.activiteid !== undefined && row.activiteid !== null && row.activiteid !== '') {
        row.activiteid = parseInt(row.activiteid);
      }
      if (row.posteid !== undefined && row.posteid !== null && row.posteid !== '') {
        row.posteid = parseInt(row.posteid);
      }
      return row;
    }
  },

  'adresses': {
    tableName: 'adresses',
    mapping: {
      'NomAdresse': 'nomadresse',
      'OuvrageID': 'ouvrageid'
    },
    preprocess: (row) => {
      if (row.ouvrageid !== undefined && row.ouvrageid !== null && row.ouvrageid !== '') {
        row.ouvrageid = parseInt(row.ouvrageid);
      }
      return row;
    }
  },

  'cartessociales': {
    tableName: 'cartessociales',
    mapping: {
      'NumeroCarte': 'numerocarte',
      'NomBeneficiaire': 'nombeneficiaire',
      'TypeCarte': 'typecarte',
      'DateEmission': 'dateemission',
      'DateExpiration': 'dateexpiration',
      'Statut': 'statut'
    },
    preprocess: (row) => {
      if (row.dateemission && row.dateemission !== '') {
        row.dateemission = new Date(row.dateemission);
      }
      if (row.dateexpiration && row.dateexpiration !== '') {
        row.dateexpiration = new Date(row.dateexpiration);
      }
      return row;
    }
  },

  'consoscartesociale': {
    tableName: 'consoscartesociale',
    mapping: {
      'CarteSocialeID': 'cartesocialeid',
      'PointEauID': 'pointeauid',
      'DateConsommation': 'dateconsommation',
      'VolumeConsomme': 'volumeconsomme',
      'PrixUnitaire': 'prixunitaire',
      'Remise': 'remise'
    },
    preprocess: (row) => {
      if (row.cartesocialeid !== undefined && row.cartesocialeid !== null && row.cartesocialeid !== '') {
        row.cartesocialeid = parseInt(row.cartesocialeid);
      }
      if (row.pointeauid !== undefined && row.pointeauid !== null && row.pointeauid !== '') {
        row.pointeauid = parseInt(row.pointeauid);
      }
      if (row.dateconsommation && row.dateconsommation !== '') {
        row.dateconsommation = new Date(row.dateconsommation);
      }
      if (row.volumeconsomme !== undefined && row.volumeconsomme !== null && row.volumeconsomme !== '') {
        row.volumeconsomme = parseInt(row.volumeconsomme);
      }
      if (row.prixunitaire !== undefined && row.prixunitaire !== null && row.prixunitaire !== '') {
        row.prixunitaire = parseInt(row.prixunitaire);
      }
      if (row.remise !== undefined && row.remise !== null && row.remise !== '') {
        row.remise = parseFloat(row.remise);
      }
      return row;
    }
  },

  'comptes': {
    tableName: 'comptes',
    mapping: {
      'NumeroCompte': 'numerocompte',
      'NomCompte': 'nomcompte',
      'BaseID': 'baseid'
    },
    preprocess: (row) => {
      if (row.baseid !== undefined && row.baseid !== null && row.baseid !== '') {
        row.baseid = parseInt(row.baseid);
      }
      return row;
    }
  },

  'compteurtetes': {
    tableName: 'compteurtetes',
    mapping: {
      'OuvrageID': 'ouvrageid',
      'NumeroCompteur': 'numerocompteur'
    },
    preprocess: (row) => {
      if (row.ouvrageid !== undefined && row.ouvrageid !== null && row.ouvrageid !== '') {
        row.ouvrageid = parseInt(row.ouvrageid);
      }
      return row;
    }
  },

  'deplacements': {
    tableName: 'deplacements',
    mapping: {
      'EmployeID': 'employeid',
      'DateDeplacement': 'datedeplacement',
      'LieuDepart': 'lieudepart',
      'LieuArrivee': 'lieuarrivee',
      'MotifDeplacement': 'motifdeplacement',
      'MoyenTransport': 'moyentransport',
      'DistanceKm': 'distancekm',
      'CoutTransport': 'couttransport'
    },
    preprocess: (row) => {
      if (row.employeid !== undefined && row.employeid !== null && row.employeid !== '') {
        row.employeid = parseInt(row.employeid);
      }
      if (row.datedeplacement && row.datedeplacement !== '') {
        row.datedeplacement = new Date(row.datedeplacement);
      }
      if (row.distancekm !== undefined && row.distancekm !== null && row.distancekm !== '') {
        row.distancekm = parseInt(row.distancekm);
      }
      if (row.couttransport !== undefined && row.couttransport !== null && row.couttransport !== '') {
        row.couttransport = parseInt(row.couttransport);
      }
      return row;
    }
  },

  'designations': {
    tableName: 'designations',
    mapping: {
      'Nom': 'nom',
      'TypeDesignationID': 'typedesignationid',
      'Description': 'description',
      'DateCreation': 'datecreation',
      'DateModification': 'datemodification',
      'Verrou': 'verrou'
    },
    preprocess: (row) => {
      if (row.typedesignationid !== undefined && row.typedesignationid !== null && row.typedesignationid !== '') {
        row.typedesignationid = parseInt(row.typedesignationid);
      }
      if (row.datecreation && row.datecreation !== '') {
        row.datecreation = new Date(row.datecreation);
      }
      if (row.datemodification && row.datemodification !== '') {
        row.datemodification = new Date(row.datemodification);
      }
      if (row.verrou !== undefined && row.verrou !== null) {
        const val = String(row.verrou).toLowerCase();
        row.verrou = val === 'true' || val === '1' || val === 'oui';
      }
      return row;
    }
  },

  'designationscomptes': {
    tableName: 'designationscomptes',
    mapping: {
      'DesignationID': 'designationid',
      'CompteID': 'compteid'
    },
    preprocess: (row) => {
      if (row.designationid !== undefined && row.designationid !== null && row.designationid !== '') {
        row.designationid = parseInt(row.designationid);
      }
      if (row.compteid !== undefined && row.compteid !== null && row.compteid !== '') {
        row.compteid = parseInt(row.compteid);
      }
      return row;
    }
  },

  'designationstypeactivites': {
    tableName: 'designationstypeactivites',
    mapping: {
      'DesignationID': 'designationid',
      'TypeActiviteID': 'typeactiviteid'
    },
    preprocess: (row) => {
      if (row.designationid !== undefined && row.designationid !== null && row.designationid !== '') {
        row.designationid = parseInt(row.designationid);
      }
      if (row.typeactiviteid !== undefined && row.typeactiviteid !== null && row.typeactiviteid !== '') {
        row.typeactiviteid = parseInt(row.typeactiviteid);
      }
      return row;
    }
  },

  'employecontrats': {
    tableName: 'employecontrats',
    mapping: {
      'EmployeID': 'employeid',
      'TypeContrat': 'typecontrat',
      'DateDebut': 'datedebut',
      'DateFin': 'datefin',
      'SalaireBase': 'salairebase',
      'Statut': 'statut'
    },
    preprocess: (row) => {
      if (row.employeid !== undefined && row.employeid !== null && row.employeid !== '') {
        row.employeid = parseInt(row.employeid);
      }
      if (row.datedebut && row.datedebut !== '') {
        row.datedebut = new Date(row.datedebut);
      }
      if (row.datefin && row.datefin !== '') {
        row.datefin = new Date(row.datefin);
      }
      if (row.salairebase !== undefined && row.salairebase !== null && row.salairebase !== '') {
        row.salairebase = parseInt(row.salairebase);
      }
      return row;
    }
  },

  'employegrillesalaires': {
    tableName: 'employegrillesalaires',
    mapping: {
      'PosteID': 'posteid',
      'Niveau': 'niveau',
      'AncienneteMin': 'anciennetemin',
      'AncienneteMax': 'anciennetemax',
      'SalaireBase': 'salairebase',
      'IndemniteLogement': 'indemnitelogement',
      'IndemniteTransport': 'indemnitetransport',
      'IndemniteRepas': 'indemniterepas'
    },
    preprocess: (row) => {
      if (row.posteid !== undefined && row.posteid !== null && row.posteid !== '') {
        row.posteid = parseInt(row.posteid);
      }
      if (row.niveau !== undefined && row.niveau !== null && row.niveau !== '') {
        row.niveau = parseInt(row.niveau);
      }
      if (row.anciennetemin !== undefined && row.anciennetemin !== null && row.anciennetemin !== '') {
        row.anciennetemin = parseInt(row.anciennetemin);
      }
      if (row.anciennetemax !== undefined && row.anciennetemax !== null && row.anciennetemax !== '') {
        row.anciennetemax = parseInt(row.anciennetemax);
      }
      if (row.salairebase !== undefined && row.salairebase !== null && row.salairebase !== '') {
        row.salairebase = parseInt(row.salairebase);
      }
      if (row.indemnitelogement !== undefined && row.indemnitelogement !== null && row.indemnitelogement !== '') {
        row.indemnitelogement = parseInt(row.indemnitelogement);
      }
      if (row.indemnitetransport !== undefined && row.indemnitetransport !== null && row.indemnitetransport !== '') {
        row.indemnitetransport = parseInt(row.indemnitetransport);
      }
      if (row.indemniterepas !== undefined && row.indemniterepas !== null && row.indemniterepas !== '') {
        row.indemniterepas = parseInt(row.indemniterepas);
      }
      return row;
    }
  },

  'employesalaires': {
    tableName: 'employesalaires',
    mapping: {
      'EmployeID': 'employeid',
      'Mois': 'mois',
      'Annee': 'annee',
      'SalaireBase': 'salairebase',
      'IndemniteLogement': 'indemnitelogement',
      'IndemniteTransport': 'indemnitetransport',
      'IndemniteRepas': 'indemniterepas',
      'HeuresSupplementaires': 'heuressupplementaires',
      'PrimePerformance': 'primeperformance',
      'TotalBrut': 'totalbrut',
      'TotalNet': 'totalnet'
    },
    preprocess: (row) => {
      if (row.employeid !== undefined && row.employeid !== null && row.employeid !== '') {
        row.employeid = parseInt(row.employeid);
      }
      if (row.mois !== undefined && row.mois !== null && row.mois !== '') {
        row.mois = parseInt(row.mois);
      }
      if (row.annee !== undefined && row.annee !== null && row.annee !== '') {
        row.annee = parseInt(row.annee);
      }
      if (row.salairebase !== undefined && row.salairebase !== null && row.salairebase !== '') {
        row.salairebase = parseInt(row.salairebase);
      }
      if (row.indemnitelogement !== undefined && row.indemnitelogement !== null && row.indemnitelogement !== '') {
        row.indemnitelogement = parseInt(row.indemnitelogement);
      }
      if (row.indemnitetransport !== undefined && row.indemnitetransport !== null && row.indemnitetransport !== '') {
        row.indemnitetransport = parseInt(row.indemnitetransport);
      }
      if (row.indemniterepas !== undefined && row.indemniterepas !== null && row.indemniterepas !== '') {
        row.indemniterepas = parseInt(row.indemniterepas);
      }
      if (row.heuressupplementaires !== undefined && row.heuressupplementaires !== null && row.heuressupplementaires !== '') {
        row.heuressupplementaires = parseInt(row.heuressupplementaires);
      }
      if (row.primeperformance !== undefined && row.primeperformance !== null && row.primeperformance !== '') {
        row.primeperformance = parseInt(row.primeperformance);
      }
      if (row.totalbrut !== undefined && row.totalbrut !== null && row.totalbrut !== '') {
        row.totalbrut = parseInt(row.totalbrut);
      }
      if (row.totalnet !== undefined && row.totalnet !== null && row.totalnet !== '') {
        row.totalnet = parseInt(row.totalnet);
      }
      return row;
    }
  },

  'gestionnaires': {
    tableName: 'gestionnaires',
    mapping: {
      'ID': 'id',
      'Nom': 'nom',
      'Description': 'description'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      return row;
    }
  },

  'gradings': {
    tableName: 'gradings',
    mapping: {
      'Nom': 'nom',
      'Niveau': 'niveau',
      'Description': 'description'
    },
    preprocess: (row) => {
      if (row.niveau !== undefined && row.niveau !== null && row.niveau !== '') {
        row.niveau = parseInt(row.niveau);
      }
      return row;
    }
  },

  'indemnites': {
    tableName: 'indemnites',
    mapping: {
      'Nom': 'nom',
      'Type': 'type',
      'Montant': 'montant',
      'Description': 'description'
    },
    preprocess: (row) => {
      if (row.montant !== undefined && row.montant !== null && row.montant !== '') {
        row.montant = parseInt(row.montant);
      }
      return row;
    }
  },

  'journaux': {
    tableName: 'journaux',
    mapping: {
      'ID': 'id',
      'Nom': 'nom',
      'Description': 'description'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      return row;
    }
  },

  'magasins': {
    tableName: 'magasins',
    mapping: {
      'ID': 'id',
      'Nom': 'nom',
      'Description': 'description'
    },
    preprocess: (row) => {
      if (row.id !== undefined && row.id !== null && row.id !== '') {
        row.id = parseInt(row.id);
      }
      return row;
    }
  },

  'modalitesgestion': {
    tableName: 'modalitesgestions',
    mapping: {
      'OuvrageID': 'ouvrageid',
      'DateDebutGestion': 'datedebutgestion',
      'DateFinGestion': 'datefingestion',
      'ModeGestion': 'modegestion',
      'ModalitePaiement': 'modalitepaiement',
      'GestionnaireID': 'gestionnaireid',
      'EmployeID': 'employeid'
    },
    preprocess: (row) => {
      if (row.ouvrageid !== undefined && row.ouvrageid !== null && row.ouvrageid !== '') {
        row.ouvrageid = parseInt(row.ouvrageid);
      }
      if (row.datedebutgestion && row.datedebutgestion !== '') {
        row.datedebutgestion = new Date(row.datedebutgestion);
      }
      if (row.datefingestion && row.datefingestion !== '') {
        row.datefingestion = new Date(row.datefingestion);
      }
      if (row.gestionnaireid !== undefined && row.gestionnaireid !== null && row.gestionnaireid !== '') {
        row.gestionnaireid = parseInt(row.gestionnaireid);
      }
      if (row.employeid !== undefined && row.employeid !== null && row.employeid !== '') {
        row.employeid = parseInt(row.employeid);
      }
      return row;
    }
  },

  'pointseau': {
    tableName: 'pointseau',
    mapping: {
      'Nom': 'nom',
      'VillageID': 'villageid',
      'TypePointEauID': 'typepointeauid',
      'GestionnaireID': 'gestionnaireid',
      'DateMiseEnService': 'datemiseenservice',
      'EstActif': 'estactif'
    },
    preprocess: (row) => {
      if (row.villageid) row.villageid = parseInt(row.villageid);
      if (row.typepointeauid) row.typepointeauid = parseInt(row.typepointeauid);
      if (row.gestionnaireid) row.gestionnaireid = parseInt(row.gestionnaireid);
      if (row.datemiseenservice) row.datemiseenservice = new Date(row.datemiseenservice);
      if (row.estactif !== undefined && row.estactif !== null) {
        const val = String(row.estactif).toLowerCase();
        row.estactif = val === 'true' || val === '1';
      }
      return row;
    }
  },

  // Table des employés avec hachage de mot de passe
  'employes': {
    tableName: 'employes',
    mapping: {
      'Nom': 'nom',
      'Prenom': 'prenom',
      'Surnom': 'surnom',
      'MotDePasse': 'motdepasse',
      'PosteID': 'posteid',
      'BaseID': 'baseid',
      'DateEmbauche': 'dateembauche',
      'NumeroCNaPS': 'numerocnaps',
      'NumeroCIN': 'numerocin',
      'NumeroTelephone': 'numerotelephone',
      'AdresseMail': 'adressemail',
      'NombreEnfantsCharge': 'nombreenfantscharge',
      'EstSalarie': 'estsalarie'
    },
    preprocess: async (row) => {
      const bcrypt = require('bcrypt');
      if (row.posteid) row.posteid = parseInt(row.posteid);
      if (row.baseid) row.baseid = parseInt(row.baseid);

      // Gérer le format de date DD/MM/YYYY et autres formats
      if (row.dateembauche && typeof row.dateembauche === 'string') {
        const parts = row.dateembauche.split('/');
        if (parts.length === 3) {
          // new Date(year, monthIndex, day)
          // Le mois est 0-indexé dans le constructeur Date de JS
          row.dateembauche = new Date(parts[2], parts[1] - 1, parts[0]);
        } else {
          // Fallback pour d'autres formats, au cas où
          row.dateembauche = new Date(row.dateembauche);
        }
      } else if (row.dateembauche) {
        // Si ce n'est pas une chaîne (peut-être déjà une date), on s'assure que c'est un objet Date valide
        row.dateembauche = new Date(row.dateembauche);
      }

      if (row.nombreenfantscharge) row.nombreenfantscharge = parseInt(row.nombreenfantscharge);
      if (row.estsalarie !== undefined && row.estsalarie !== null) {
        const val = String(row.estsalarie).toLowerCase();
        row.estsalarie = val === 'true' || val === '1';
      }
      // Hacher le mot de passe s'il est présent et n'est pas déjà un hash
      if (row.motdepasse && !row.motdepasse.startsWith('$2b$')) {
        row.motdepasse = await bcrypt.hash(row.motdepasse, 12);
      }
      return row;
    }
  },

  // Tables manquantes ajoutées
  'parcelles': {
    tableName: 'parcelles',
    mapping: {
      'Nom': 'nom',
      'VillageID': 'villageid',
      'NombreHabitants': 'nombrehabitants',
      'NombreMenages': 'nombremenages',
      'SourceDonnees': 'sourcedonnees'
    },
    preprocess: (row) => {
      if (row.villageid !== undefined && row.villageid !== null && row.villageid !== '') {
        row.villageid = parseInt(row.villageid);
      }
      if (row.nombrehabitants !== undefined && row.nombrehabitants !== null && row.nombrehabitants !== '') {
        row.nombrehabitants = parseInt(row.nombrehabitants);
      }
      if (row.nombremenages !== undefined && row.nombremenages !== null && row.nombremenages !== '') {
        row.nombremenages = parseInt(row.nombremenages);
      }
      return row;
    }
  },

  'plannings': {
    tableName: 'plannings',
    mapping: {
      'Date': 'date',
      'OuvrageID': 'ouvrageid',
      'EmployeID': 'employeid',
      'ActiviteID': 'activiteid',
      'Remarque': 'remarque',
      'DateSignalementActivite': 'datesignalementactivite',
      'EstValide': 'estvalide',
      'DebitMesure': 'debitmesure'
    },
    preprocess: (row) => {
      if (row.date && row.date !== '') {
        row.date = new Date(row.date);
      }
      if (row.ouvrageid !== undefined && row.ouvrageid !== null && row.ouvrageid !== '') {
        row.ouvrageid = parseInt(row.ouvrageid);
      }
      if (row.employeid !== undefined && row.employeid !== null && row.employeid !== '') {
        row.employeid = parseInt(row.employeid);
      }
      if (row.activiteid !== undefined && row.activiteid !== null && row.activiteid !== '') {
        row.activiteid = parseInt(row.activiteid);
      }
      if (row.datesignalementactivite && row.datesignalementactivite !== '') {
        row.datesignalementactivite = new Date(row.datesignalementactivite);
      }
      if (row.estvalide !== undefined && row.estvalide !== null) {
        const val = String(row.estvalide).toLowerCase();
        row.estvalide = val === 'true' || val === '1' || val === 'oui';
      }
      if (row.debitmesure !== undefined && row.debitmesure !== null && row.debitmesure !== '') {
        row.debitmesure = parseFloat(row.debitmesure);
      }
      return row;
    }
  },

  'planningsdetails': {
    tableName: 'planningsdetails',
    mapping: {
      'PlanningID': 'planningid',
      'OuvrageConstitutif': 'ouvrageconstitutif',
      'DesignationID': 'designationid',
      'Quantite': 'quantite',
      'PrixUnitaire': 'prixunitaire',
      'Montant': 'montant',
      'AcheteurID': 'acheteurid',
      'MagasinID': 'magasinid',
      'CompteID': 'compteid',
      'EstLivre': 'estlivre',
      'EstRetourne': 'estretourne',
      'NumeroDiameX': 'numerodiamex',
      'BaseDiameX': 'basediamex',
      'Bilan': 'bilan',
      'SuiteADonner': 'suiteadonner'
    },
    preprocess: (row) => {
      if (row.planningid !== undefined && row.planningid !== null && row.planningid !== '') {
        row.planningid = parseInt(row.planningid);
      }
      if (row.designationid !== undefined && row.designationid !== null && row.designationid !== '') {
        row.designationid = parseInt(row.designationid);
      }
      if (row.quantite !== undefined && row.quantite !== null && row.quantite !== '') {
        row.quantite = parseFloat(row.quantite);
      }
      if (row.prixunitaire !== undefined && row.prixunitaire !== null && row.prixunitaire !== '') {
        row.prixunitaire = parseFloat(row.prixunitaire);
      }
      if (row.montant !== undefined && row.montant !== null && row.montant !== '') {
        row.montant = parseFloat(row.montant);
      }
      if (row.acheteurid !== undefined && row.acheteurid !== null && row.acheteurid !== '') {
        row.acheteurid = parseInt(row.acheteurid);
      }
      if (row.magasinid !== undefined && row.magasinid !== null && row.magasinid !== '') {
        row.magasinid = parseInt(row.magasinid);
      }
      if (row.compteid !== undefined && row.compteid !== null && row.compteid !== '') {
        row.compteid = parseInt(row.compteid);
      }
      if (row.estlivre !== undefined && row.estlivre !== null) {
        const val = String(row.estlivre).toLowerCase();
        row.estlivre = val === 'true' || val === '1' || val === 'oui';
      }
      if (row.estretourne !== undefined && row.estretourne !== null) {
        const val = String(row.estretourne).toLowerCase();
        row.estretourne = val === 'true' || val === '1' || val === 'oui';
      }
      return row;
    }
  },

  'postescomptes': {
    tableName: 'postescomptes',
    mapping: {
      'PosteID': 'posteid',
      'TarifIndemnite': 'tarifindemnite',
      'CompteSalaire': 'comptesalaire',
      'CompteIRSA': 'compteirsa',
      'CompteCNaPS': 'comptecnaps',
      'PrefixePoste': 'prefixeposte'
    },
    preprocess: (row) => {
      if (row.posteid !== undefined && row.posteid !== null && row.posteid !== '') {
        row.posteid = parseInt(row.posteid);
      }
      if (row.tarifindemnite !== undefined && row.tarifindemnite !== null && row.tarifindemnite !== '') {
        row.tarifindemnite = parseFloat(row.tarifindemnite);
      }
      return row;
    }
  },

  'releves': {
    tableName: 'releves',
    mapping: {
      'PointEauID': 'pointeauid',
      'DateReleve': 'datereleve',
      'IndexCompteur': 'indexcompteur',
      'VolumeNonFacture': 'volumenonfacture',
      'DatePrecedente': 'dateprecedente',
      'IndexPrecedent': 'indexprecedent',
      'VolumeConsomme': 'volumeconsomme',
      'MoisFacture': 'moisfacture',
      'MontantFacture': 'montantfacture',
      'DateEditionFacture': 'dateeditionfacture',
      'DatePaiementFacture': 'datepaiementfacture',
      'NumeroDiameX': 'numerodiamex',
      'BaseDiameX': 'basediamex'
    },
    preprocess: (row) => {
      if (row.pointeauid !== undefined && row.pointeauid !== null && row.pointeauid !== '') {
        row.pointeauid = parseInt(row.pointeauid);
      }
      if (row.datereleve && row.datereleve !== '') {
        row.datereleve = new Date(row.datereleve);
      }
      if (row.indexcompteur !== undefined && row.indexcompteur !== null && row.indexcompteur !== '') {
        row.indexcompteur = parseFloat(row.indexcompteur);
      }
      if (row.volumenonfacture !== undefined && row.volumenonfacture !== null && row.volumenonfacture !== '') {
        row.volumenonfacture = parseFloat(row.volumenonfacture);
      }
      if (row.dateprecedente && row.dateprecedente !== '') {
        row.dateprecedente = new Date(row.dateprecedente);
      }
      if (row.indexprecedent !== undefined && row.indexprecedent !== null && row.indexprecedent !== '') {
        row.indexprecedent = parseFloat(row.indexprecedent);
      }
      if (row.volumeconsomme !== undefined && row.volumeconsomme !== null && row.volumeconsomme !== '') {
        row.volumeconsomme = parseFloat(row.volumeconsomme);
      }
      if (row.moisfacture && row.moisfacture !== '') {
        row.moisfacture = new Date(row.moisfacture);
      }
      if (row.montantfacture !== undefined && row.montantfacture !== null && row.montantfacture !== '') {
        row.montantfacture = parseFloat(row.montantfacture);
      }
      if (row.dateeditionfacture && row.dateeditionfacture !== '') {
        row.dateeditionfacture = new Date(row.dateeditionfacture);
      }
      if (row.datepaiementfacture && row.datepaiementfacture !== '') {
        row.datepaiementfacture = new Date(row.datepaiementfacture);
      }
      return row;
    }
  },

  'relevescompteurtetes': {
    tableName: 'relevescompteurtetes',
    mapping: {
      'CompteurTeteID': 'compteurteteid',
      'DateReleve': 'datereleve',
      'IndexCompteur': 'indexcompteur',
      'DatePrecedente': 'dateprecedente',
      'IndexPrecedent': 'indexprecedent',
      'VolumeConsomme': 'volumeconsomme',
      'MoisFacture': 'moisfacture'
    },
    preprocess: (row) => {
      if (row.compteurteteid !== undefined && row.compteurteteid !== null && row.compteurteteid !== '') {
        row.compteurteteid = parseInt(row.compteurteteid);
      }
      if (row.datereleve && row.datereleve !== '') {
        row.datereleve = new Date(row.datereleve);
      }
      if (row.indexcompteur !== undefined && row.indexcompteur !== null && row.indexcompteur !== '') {
        row.indexcompteur = parseFloat(row.indexcompteur);
      }
      if (row.dateprecedente && row.dateprecedente !== '') {
        row.dateprecedente = new Date(row.dateprecedente);
      }
      if (row.indexprecedent !== undefined && row.indexprecedent !== null && row.indexprecedent !== '') {
        row.indexprecedent = parseFloat(row.indexprecedent);
      }
      if (row.volumeconsomme !== undefined && row.volumeconsomme !== null && row.volumeconsomme !== '') {
        row.volumeconsomme = parseFloat(row.volumeconsomme);
      }
      if (row.moisfacture && row.moisfacture !== '') {
        row.moisfacture = new Date(row.moisfacture);
      }
      return row;
    }
  },

  'tarifvolumetrique': {
    tableName: 'tarifvolumetrique',
    mapping: {
      'OuvrageID': 'ouvrageid',
      'DateDebutTarif': 'datedebuttarif',
      'DateFinTarif': 'datefintarif',
      'PrixAbonnement': 'prixabonnement',
      'TypePointEauID': 'typepointeauid',
      'VolumeMinimumFacturer': 'volumeminimumfacturer'
    },
    preprocess: (row) => {
      if (row.ouvrageid !== undefined && row.ouvrageid !== null && row.ouvrageid !== '') {
        row.ouvrageid = parseInt(row.ouvrageid);
      }
      if (row.datedebuttarif && row.datedebuttarif !== '') {
        row.datedebuttarif = new Date(row.datedebuttarif);
      }
      if (row.datefintarif && row.datefintarif !== '') {
        row.datefintarif = new Date(row.datefintarif);
      }
      if (row.prixabonnement !== undefined && row.prixabonnement !== null && row.prixabonnement !== '') {
        row.prixabonnement = parseFloat(row.prixabonnement);
      }
      if (row.typepointeauid !== undefined && row.typepointeauid !== null && row.typepointeauid !== '') {
        row.typepointeauid = parseInt(row.typepointeauid);
      }
      if (row.volumeminimumfacturer !== undefined && row.volumeminimumfacturer !== null && row.volumeminimumfacturer !== '') {
        row.volumeminimumfacturer = parseFloat(row.volumeminimumfacturer);
      }
      return row;
    }
  },

  'tarifvolumetrique2': {
    tableName: 'tarifvolumetrique2',
    mapping: {
      'TarifVolumetriqueID': 'tarifvolumetriqueid',
      'MaxTranche': 'maxtranche',
      'TarifTranche': 'tariftranche'
    },
    preprocess: (row) => {
      if (row.tarifvolumetriqueid !== undefined && row.tarifvolumetriqueid !== null && row.tarifvolumetriqueid !== '') {
        row.tarifvolumetriqueid = parseInt(row.tarifvolumetriqueid);
      }
      if (row.maxtranche !== undefined && row.maxtranche !== null && row.maxtranche !== '') {
        row.maxtranche = parseFloat(row.maxtranche);
      }
      if (row.tariftranche !== undefined && row.tariftranche !== null && row.tariftranche !== '') {
        row.tariftranche = parseFloat(row.tariftranche);
      }
      return row;
    }
  }
};

// Ordre d'importation pour respecter les dépendances (clés étrangères)
const importOrder = [
  // Niveau 1: Pas de dépendances externes
  'organisations', 'regions', 'postes', 'typesactivites', 'typesouvrages',
  'typesouvragesconstitutifs', 'typedesignations', 'typespointseau',
  'typestypesouvragesconstitutifs', 'gestionnaires', 'gradings', 'indemnites',
  'journaux', 'magasins',

  // Niveau 2: Dépendances géographiques
  'districts', // dépend de regions
  'communes',  // dépend de districts
  'villages',  // dépend de communes
  'parcelles', // dépend de villages

  // Niveau 3: Dépendances structurelles
  'ouvrages', // dépend de organisations, typesouvrages
  'ouvragesconstitutifs', // dépend de ouvrages, typesouvragesconstitutifs
  'bases',    // dépend de organisations, ouvrages
  'activites',// dépend de typesactivites
  'pointseau',// dépend de villages, typespointseau, gestionnaires
  'comptes',  // dépend de bases
  'compteurtetes', // dépend de ouvrages

  // Niveau 4: Dépendances sur les employés et postes
  'employes', // dépend de postes, bases
  'employecontrats', // dépend de employes
  'employegrillesalaires', // dépend de postes
  'employesalaires', // dépend de employes
  'postescomptes', // dépend de postes

  // Niveau 5: Tables de transactions et de liens
  'activitespostes', // dépend de activites, postes
  'adresses', // dépend de ouvrages
  'cartessociales',
  'consoscartesociale', // dépend de cartessociales, pointseau
  'deplacements', // dépend de employes
  'designations', // dépend de typedesignations
  'designationscomptes', // dépend de designations, comptes
  'designationstypeactivites', // dépend de designations, typesactivites
  'modalitesgestion', // dépend de ouvrages, gestionnaires, employes
  'plannings', // dépend de ouvrages, employes, activites
  'planningsdetails', // dépend de plannings, designations, employes, magasins, comptes
  'releves', // dépend de pointseau
  'relevescompteurtetes', // dépend de compteurtetes
  'tarifvolumetrique', // dépend de ouvrages, typespointseau
  'tarifvolumetrique2' // dépend de tarifvolumetrique
];


async function importCsv(tableName, filePath) {
  const config = importConfig[tableName];
  if (!config) {
    console.error(`❌ Configuration d'import non trouvée pour la table "${tableName}"`);
    return;
  }

  console.log(`\n🔄 Importation de "${filePath}" vers la table "${config.tableName}"...`);

  const records = [];
  const parser = fs.createReadStream(filePath).pipe(parse({
    columns: true,
    skip_empty_lines: true,
    trim: true,
    bom: true, // Gérer le caractère BOM en début de fichier
  }));

  for await (const record of parser) {
    const mappedRecord = {};
    for (const csvHeader in config.mapping) {
      const dbColumn = config.mapping[csvHeader];
      if (record[csvHeader] !== undefined) {
        mappedRecord[dbColumn] = record[csvHeader];
      }
    }
    records.push(mappedRecord);
  }

  if (records.length === 0) {
    console.log('🟡 Aucun enregistrement trouvé dans le fichier CSV.');
    return;
  }

  const processedRecords = [];
  for (const record of records) {
    let processed = record;
    if (config.preprocess) {
      processed = await config.preprocess(record);
    }
    processedRecords.push(processed);
  }

  const { data, error } = await supabase.from(config.tableName).insert(processedRecords, { upsert: true });

  if (error) {
    console.error(`❌ Erreur lors de l'importation dans "${config.tableName}":`, error.message);
    if (error.details) console.error('   Détails:', error.details);
  } else {
    console.log(`✅ ${processedRecords.length} enregistrements importés/mis à jour dans "${config.tableName}".`);
  }
}

async function showStatus() {
  console.log('📊 État actuel de la base de données Supabase:');
  try {
    const { error: connectionError } = await supabase.from('employes').select('id').limit(1);
    if (connectionError) throw connectionError;
    console.log('✅ Connexion à Supabase réussie');
  } catch (error) {
    console.error('❌ Impossible de se connecter à Supabase:', error.message);
    return;
  }

  for (const tableName of importOrder) {
    const config = importConfig[tableName];
    if (config && config.tableName) {
      try {
        const { count, error } = await supabase.from(config.tableName).select('*', { count: 'exact', head: true });
        if (error) throw error;
        console.log(`  - 📋 ${config.tableName.padEnd(30)}: ${count} enregistrements`);
      } catch (error) {
        console.log(`  - ⚠️ ${config.tableName.padEnd(30)}: Erreur (${error.message})`);
      }
    }
  }
}

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args[0] === 'all') {
    console.log('🚀 Démarrage de l\'importation de toutes les tables dans l\'ordre recommandé...');
    for (const tableName of importOrder) {
      const filePath = path.join(__dirname, 'csv-data', `${tableName}.csv`);
      if (fs.existsSync(filePath)) {
        await importCsv(tableName, filePath);
      } else {
        console.log(`🟡 Fichier non trouvé pour la table "${tableName}", ignoré: ${filePath}`);
      }
    }
    console.log('\n🎉 Importation de toutes les tables terminée.');
  } else if (args[0] === 'status') {
    await showStatus();
  } else if (args.length === 2) {
    const [tableName, filePath] = args;
    if (!importConfig[tableName]) {
      console.error(`❌ Nom de table invalide: "${tableName}". Tables valides: ${Object.keys(importConfig).join(', ')}`);
      return;
    }
    if (!fs.existsSync(filePath)) {
      console.error(`❌ Fichier non trouvé: ${filePath}`);
      return;
    }
    await importCsv(tableName, filePath);
  } else {
    console.log('--- Aide pour le script d\'importation Soakoja ---');
    console.log('Usage:');
    console.log('  - Importer toutes les tables (depuis le dossier csv-data):');
    console.log('    node import-csv.js');
    console.log('    node import-csv.js all');
    console.log('\n  - Importer une table spécifique:');
    console.log('    node import-csv.js [nom_de_la_table] [chemin/vers/le/fichier.csv]');
    console.log('    Exemple: node import-csv.js employes "C:\\data\\my_employes.csv"');
    console.log('\n  - Voir le statut de la base de données:');
    console.log('    node import-csv.js status');
    console.log('-------------------------------------------------');
  }
}

main().catch(error => {
  console.error('\n❌ Une erreur fatale est survenue:', error);
  process.exit(1);
});
