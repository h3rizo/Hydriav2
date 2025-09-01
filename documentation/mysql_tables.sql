-- Script MySQL corrigé avec le bon ordre des tables
-- Remplacez votre mysql_tables.sql par ce fichier

CREATE DATABASE IF NOT EXISTS `hydriav2_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `hydriav2_db`;

SET FOREIGN_KEY_CHECKS = 0;

-- =============================================
-- 1. TABLES DE BASE (aucune dépendance)
-- =============================================

-- Organisations (PREMIÈRE TABLE - référencée par beaucoup d'autres)
CREATE TABLE `Organisations` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `Adresse` VARCHAR(255),
    `ComplementAdresse` VARCHAR(255),
    `CodePostal` VARCHAR(3),
    `Localite` INT,
    `NIF` VARCHAR(10),
    `STAT` VARCHAR(19),
    `NumeroCnaPS` VARCHAR(6),
    `Province` VARCHAR(50),
    `TarifDemandeBP` INT,
    `TarifMinimumBP` INT,
    `SalaireMinimal` FLOAT,
    `Telephone` VARCHAR(10),
    `mail` VARCHAR(255),
    `DeductionIRSA` INT,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Types d'ouvrages
CREATE TABLE `TypesOuvrages` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `NomType` VARCHAR(255) NOT NULL,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Ouvrages (dépend de Organisations et TypesOuvrages)
CREATE TABLE `Ouvrages` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `TypeOuvrageID` INT NOT NULL,
    `AnneeRealisation` INT,
    `AnneeRealisationAvant` INT,
    `Intervenant` VARCHAR(255),
    `Remarque` TEXT,
    `IDXls` INT,
    `OrganisationID` INT NOT NULL,
    `EstSaisonnier` BOOLEAN DEFAULT FALSE,
    `Photos` TEXT,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`TypeOuvrageID`) REFERENCES `TypesOuvrages`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`OrganisationID`) REFERENCES `Organisations`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Bases (dépend d'Organisations et Ouvrages)
CREATE TABLE `Bases` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `OrganisationID` INT NOT NULL,
    `OuvrageID` INT NOT NULL,
    `Volet` VARCHAR(255),
    `BaseDiameX` VARCHAR(255),
    `CheminBaseDiameX` VARCHAR(255),
    `ProgDiameX` VARCHAR(255),
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`OrganisationID`) REFERENCES `Organisations`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`OuvrageID`) REFERENCES `Ouvrages`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Postes
CREATE TABLE `Postes` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `NomPoste` VARCHAR(255) NOT NULL,
    `Verrou` BOOLEAN DEFAULT FALSE,
    `NiveauMenu` INT,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 2. GÉOGRAPHIE (Regions -> Districts -> Communes -> Villages -> Parcelles)
-- =============================================

-- Régions (indépendant)
CREATE TABLE `Regions` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Districts (dépend de Regions)
CREATE TABLE `Districts` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `RegionID` INT,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`RegionID`) REFERENCES `Regions`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Communes (dépend de Districts)
CREATE TABLE `Communes` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `DistrictID` INT,
    `NomMaire` VARCHAR(255),
    `ContactMaire` VARCHAR(255),
    `NomPresidentConseil` VARCHAR(255),
    `ContactPresidentConseil` VARCHAR(255),
    `NomPremierConseiller` VARCHAR(255),
    `ContactPremierConseiller` VARCHAR(255),
    `NomSecondConseiller` VARCHAR(255),
    `ContactSecondConseiller` VARCHAR(255),
    `NomTroisiemeConseiller` VARCHAR(255),
    `ContactTroisiemeConseiller` VARCHAR(255),
    `NomQuatriemeConseiller` VARCHAR(255),
    `ContactQuatriemeConseiller` VARCHAR(255),
    `NomCinquiemeConseiller` VARCHAR(255),
    `ContactCinquiemeConseiller` VARCHAR(255),
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`DistrictID`) REFERENCES `Districts`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Villages (dépend de Communes)
CREATE TABLE `Villages` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `CommuneID` INT,
    `ClasseAdmin` ENUM('Village', 'Chef-lieu Fokontany', 'Chef-lieu Commune', 'Chef-lieu District', 'Chef-lieu Région'),
    `Accessibilite` ENUM('Voiture', 'Moto', 'Pirogue', 'Pied'),
    `DistanceKm` FLOAT,
    `DepartPourTaxiBrousse` VARCHAR(50),
    `NbHeuresMarche` FLOAT,
    `IDXls` INT,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`CommuneID`) REFERENCES `Communes`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Parcelles (dépend de Villages)
CREATE TABLE `Parcelles` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `VillageID` INT,
    `NombreHabitants` INT,
    `NombreMenages` INT,
    `SourceDonnees` VARCHAR(255),
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`VillageID`) REFERENCES `Villages`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 3. EMPLOYÉS (dépend de Postes et Bases)
-- =============================================

CREATE TABLE `Employes` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `Prenom` VARCHAR(255),
    `PosteID` INT NOT NULL,
    `DateEmbauche` DATETIME,
    `DateDebauchage` DATETIME,
    `MotDePasse` VARCHAR(255),
    `Surnom` VARCHAR(50) NOT NULL UNIQUE,
    `BaseID` INT,
    `ReferentID` INT,
    `NumeroCNaPS` VARCHAR(12),
    `NumeroCIN` VARCHAR(12),
    `NumeroTelephone` VARCHAR(9),
    `AdresseMail` VARCHAR(255),
    `NombreEnfantsCharge` INT DEFAULT 0,
    `EstSalarie` BOOLEAN DEFAULT FALSE,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`PosteID`) REFERENCES `Postes`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`BaseID`) REFERENCES `Bases`(`ID`) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (`ReferentID`) REFERENCES `Employes`(`ID`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 4. TABLES FINANCIÈRES
-- =============================================

CREATE TABLE `Comptes` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `NumeroCompte` INT NOT NULL,
    `NomCompte` VARCHAR(255) NOT NULL,
    `Detail` BOOLEAN DEFAULT FALSE,
    `Verrou` BOOLEAN DEFAULT FALSE,
    `OrganisationID` INT,
    `ARecouperHydriaDiameX` BOOLEAN DEFAULT FALSE,
    `Achat` BOOLEAN DEFAULT FALSE,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`OrganisationID`) REFERENCES `Organisations`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `Journaux` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `BaseID` INT,
    `Compte` INT NOT NULL,
    `Code` VARCHAR(6) NOT NULL,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`BaseID`) REFERENCES `Bases`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `Magasins` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `Compte` INT,
    `Code` VARCHAR(6),
    `BaseID` INT,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`BaseID`) REFERENCES `Bases`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 5. GESTIONNAIRES
-- =============================================

CREATE TABLE `Gestionnaires` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `Contact` VARCHAR(255),
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 6. TYPES D'ACTIVITÉS ET ACTIVITÉS
-- =============================================

CREATE TABLE `TypesActivites` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `NomType` VARCHAR(255) NOT NULL,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `Activites` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Nom` VARCHAR(255) NOT NULL,
    `TypeActiviteID` INT,
    `Verrou` BOOLEAN DEFAULT FALSE,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`TypeActiviteID`) REFERENCES `TypesActivites`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 7. PLANNINGS (dépend d'Ouvrages, Employes, Activites)
-- =============================================

CREATE TABLE `Plannings` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `Date` DATETIME NOT NULL,
    `OuvrageID` INT,
    `EmployeID` INT NOT NULL,
    `ActiviteID` INT NOT NULL,
    `Remarque` TEXT,
    `DateSignalementActivite` DATETIME,
    `EstValide` BOOLEAN DEFAULT FALSE,
    `DebitMesure` FLOAT,
    `Bilan` LONGTEXT,
    `SuiteADonner` LONGTEXT,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`OuvrageID`) REFERENCES `Ouvrages`(`ID`) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (`EmployeID`) REFERENCES `Employes`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`ActiviteID`) REFERENCES `Activites`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Détails des plannings
CREATE TABLE `PlanningsDetails` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `PlanningID` INT NOT NULL,
    `OuvrageConstitutif` VARCHAR(255),
    `DesignationID` INT NOT NULL,
    `Quantite` FLOAT,
    `PrixUnitaire` FLOAT,
    `Montant` FLOAT,
    `AcheteurID` INT,
    `MagasinID` INT,
    `CompteID` INT,
    `EstLivre` BOOLEAN DEFAULT FALSE,
    `EstRetourne` BOOLEAN DEFAULT FALSE,
    `NumeroDiameX` VARCHAR(255),
    `BaseDiameX` VARCHAR(255),
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`PlanningID`) REFERENCES `Plannings`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`DesignationID`) REFERENCES `Designations`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`AcheteurID`) REFERENCES `Employes`(`ID`) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (`MagasinID`) REFERENCES `Magasins`(`ID`) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (`CompteID`) REFERENCES `Comptes`(`ID`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 8. POINTS D'EAU
-- =============================================

CREATE TABLE `TypesPointsEaus` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `NomType` VARCHAR(255) NOT NULL,
    `CategoriePointEau` ENUM('Public', 'Privé'),
    `ModalitePaiement` ENUM('Au volume', 'Forfaitaire', 'Cotisation annuelle'),
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `CompteurTetes` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `OuvrageID` INT,
    `NumeroCompteur` VARCHAR(255) NOT NULL,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`OuvrageID`) REFERENCES `Ouvrages`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `PointsEaus` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `NomAbonne` VARCHAR(255),
    `ContactAbonne` VARCHAR(255),
    `CompteurTeteID` INT,
    `TypePointEauID` INT,
    `OuvrageID` INT,
    `ParcelleID` INT,
    `DateBranchement` DATETIME,
    `DateArretBranchement` DATETIME,
    `Latitude` FLOAT,
    `Longitude` FLOAT,
    `TypeAbonne` TEXT,
    `EstBranchementInstitutionnel` BOOLEAN DEFAULT FALSE,
    `TarifForfaitaire` FLOAT,
    `NumeroDiameXDemande` INT,
    `NumeroDiameXPaiementDevis` VARCHAR(50),
    `BaseDiameXDemande` INT,
    `BaseDiameXPaiementDevis` VARCHAR(50),
    `MontantDemandePaye` FLOAT,
    `MontantDevisPaye` FLOAT,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`CompteurTeteID`) REFERENCES `CompteurTetes`(`ID`) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (`TypePointEauID`) REFERENCES `TypesPointsEaus`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`OuvrageID`) REFERENCES `Ouvrages`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`ParcelleID`) REFERENCES `Parcelles`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 9. CARTES SOCIALES
-- =============================================

CREATE TABLE `CartesSociales` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `NomBeneficiaire` VARCHAR(255) NOT NULL,
    `PointEauID` INT,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`PointEauID`) REFERENCES `PointsEaus`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- 10. AUTRES TABLES (ajoutez au besoin)
-- =============================================

CREATE TABLE `ActivitesPostes` (
    `ID` INT AUTO_INCREMENT PRIMARY KEY,
    `ActiviteID` INT,
    `PosteID` INT,
    `createdAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updatedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`ActiviteID`) REFERENCES `Activites`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`PosteID`) REFERENCES `Postes`(`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Réactiver les contraintes
SET FOREIGN_KEY_CHECKS = 1;

-- =============================================
-- DONNÉES DE TEST
-- =============================================

-- Organisation par défaut
INSERT INTO `Organisations` (`Nom`, `createdAt`, `updatedAt`) 
VALUES ('Soakoja', NOW(), NOW());

-- Type d'ouvrage par défaut
INSERT INTO `TypesOuvrages` (`NomType`, `createdAt`, `updatedAt`) 
VALUES ('AEPG', NOW(), NOW());

-- Ouvrage par défaut
INSERT INTO `Ouvrages` (`Nom`, `TypeOuvrageID`, `OrganisationID`, `createdAt`, `updatedAt`) 
VALUES ('Ouvrage principal', 1, 1, NOW(), NOW());

-- Base par défaut
INSERT INTO `Bases` (`Nom`, `OrganisationID`, `OuvrageID`, `createdAt`, `updatedAt`) 
VALUES ('Base principale', 1, 1, NOW(), NOW());

-- Poste par défaut
INSERT INTO `Postes` (`NomPoste`, `NiveauMenu`, `createdAt`, `updatedAt`) 
VALUES ('Administrateur', 4, NOW(), NOW());

-- Utilisateur administrateur par défaut (mot de passe hashé pour "IA")
INSERT INTO `Employes` (`Nom`, `Prenom`, `Surnom`, `MotDePasse`, `PosteID`, `BaseID`, `EstSalarie`, `DateEmbauche`, `createdAt`, `updatedAt`)
VALUES ('ANDRIATSILAVINA', 'Harijaona Antoine', 'Tsilavina', '$2b$12$vQrqE8WGlTJ7.kxJ1Y1j0u5h1FhKhG9Dq0v5o1d2O6h9H6O2D3f4G', 1, 1, TRUE, NOW(), NOW(), NOW());

-- Régions de Madagascar
INSERT INTO `Regions` (`Nom`) VALUES 
('Analamanga'), ('Analanjirofo'), ('Fitovinany'), ('Atsimo Atsinanana');

-- Types d'activités
INSERT INTO `TypesActivites` (`NomType`) VALUES 
('Maintenance'), ('Installation'), ('Contrôle'), ('Formation');

-- Activités de base
INSERT INTO `Activites` (`Nom`, `TypeActiviteID`) VALUES 
('Maintenance pompe', 1), ('Installation compteur', 2), ('Contrôle qualité eau', 3);

-- Types de points d'eau
INSERT INTO `TypesPointsEaus` (`NomType`, `CategoriePointEau`, `ModalitePaiement`) VALUES
('Borne fontaine', 'Public', 'Au volume'),
('Branchement privé', 'Privé', 'Au volume');

COMMIT;