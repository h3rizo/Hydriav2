Comment utiliser ces styles :

Dans vos fichiers EJS, ajoutez après votre style.css :

html<link rel="stylesheet" href="/css/style.css">


procédure pour debbuger mysql qui ne démarre pas
Voici les étapes à suivre pour résoudre ce problème, en commençant par la plus probable.

## Solution : Réparer la corruption de données
Arrêtez MySQL et Apache dans le panneau de contrôle XAMPP. S ils ne s arrêtent pas, quittez XAMPP complètement.
Ouvrez l explorateur de fichiers et allez dans votre dossier d'installation de XAMPP, puis dans le dossier mysql. Le chemin est probablement : C:\xampp\mysql\
Renommez le dossier data en data_old. C'est votre sauvegarde. Ne le supprimez pas !
Créez un nouveau dossier vide et nommez-le data.
Allez dans le dossier C:\xampp\mysql\backup\. Copiez tout son contenu et collez-le dans le nouveau dossier data que vous venez de créer.
Maintenant, allez dans votre dossier de sauvegarde data_old. Copiez les dossiers de vos bases de données personnelles (ceux qui portent le nom de vos projets, comme wordpress, magasin, etc.) et collez-les dans le nouveau dossier data.
IMPORTANT : Ne copiez PAS les dossiers mysql, performance_schema, et phpmyadmin de data_old. Ils sont la source du problème.
Enfin, copiez le fichier ibdata1 depuis data_old et collez-le dans le nouveau dossier data. Ce fichier contient les données de vos tables.
Retournez sur le panneau de contrôle XAMPP et essayez de démarrer MySQL.
Le serveur devrait maintenant démarrer correctement. Vous avez remplacé les fichiers système corrompus par une version saine tout en restaurant vos données intactes.
-- Script complet pour créer toutes les tables de hydriav2_db
-- À exécuter dans phpMyAdmin > SQL

--requetes pour créer une colonne date
ALTER TABLE votre_table ADD COLUMN nouvelle_colonne_date DATE;

--requête pour remplir la nouvelle colonne avec une colone en format VarChar
UPDATE regions 
SET createdAt2 = DATE(STR_TO_DATE(createdAt, '%d/%m/%Y'));

--pour supprimer l ancienne colonne et la remplacer par la nouvelle
ALTER TABLE regions 
DROP COLUMN createdAt,
CHANGE createdAt2 createdAt DATETIME;


solution pour faire transaction en une etape
START TRANSACTION;

ALTER TABLE regions ADD COLUMN createdAt2 DATETIME;

UPDATE regions 
SET createdAt2 = DATE(STR_TO_DATE(createdAt, '%d/%m/%Y'));

ALTER TABLE regions 
DROP COLUMN createdAt,
CHANGE createdAt2 createdAt DATETIME;

COMMIT;

pour importer des références vides

créer un staging point
CREATE TABLE modalitesgestions_stg LIKE modalitesgestions;
-- Cette forme ne recopie pas les clés étrangères. 
-- (CREATE TABLE ... LIKE ne préserve pas les FK). 

puis y importer les donnees

INSERT INTO planningsdetails (
  ID, PlanningID, OuvrageCOnstitutif, DesignationID, Quantite, PrixUnitaire, Montant, AcheteurID,
    MagasinID, CompteID, EstLivre, EstRetourne, NumeroDiameX, BaseDiameX, createdAt, updatedAt
)
SELECT
  p.ID,
  s.ID AS PlanningID,
  p.OuvrageConstitutif,
  d.ID AS DesignationID,
  CAST(NULLIF(TRIM(p.Quantite), '') AS DECIMAL(10, 2)),
  p.PrixUnitaire,
  p.Montant,
  e.ID AS AcheteurID,
  m.ID AS MagasinID,
  c.ID AS CompteID,
  p.EstLivre,
  p.EstRetourne,
  p.NumeroDiameX,
  p.BaseDiameX,
  NULLIF(NULLIF(TRIM(p.createdAt), '\\N'), ''),
  NULLIF(NULLIF(TRIM(p.updatedAt), '\\N'), '')
FROM planningsdetails_stg p
LEFT JOIN plannings s ON s.ID = CAST(NULLIF(NULLIF(TRIM(p.PlanningID), '\\N'), '') AS UNSIGNED)
LEFT JOIN designations d ON d.ID = CAST(NULLIF(NULLIF(TRIM(p.DesignationID), '\\N'), '') AS UNSIGNED)
LEFT JOIN employes e ON e.ID = CAST(NULLIF(NULLIF(TRIM(p.AcheteurID), '\\N'), '') AS UNSIGNED)
LEFT JOIN magasins m ON m.ID = CAST(NULLIF(NULLIF(TRIM(p.MagasinID), '\\N'), '') AS UNSIGNED)
LEFT JOIN comptes c ON c.ID = CAST(NULLIF(NULLIF(TRIM(p.CompteID), '\\N'), '') AS UNSIGNED);

pour mettre à jour les valeurs d une colonne à partir d une table stagging
UPDATE activites
JOIN activites_stg ON activites.ID = activites_stg.ID
SET activites.Verrou = activites_stg.Verrou;

pour créer une colonne date et le remplir de date : 
-- Étape 1 : Ajouter la nouvelle colonne de type DATE
ALTER TABLE EmployeContrats
ADD DateDebutContrat2 DATE,
ADD DateFinContrat2 DATE;

-- Étape 2 : Mettre à jour la nouvelle colonne avec les valeurs converties
UPDATE EmployeContrats
SET DateDebutContrat2 = STR_TO_DATE(DateDebutContrat, '%d/%m/%Y'),
 DateFinContrat2 = STR_TO_DATE(DateFinContrat, '%d/%m/%Y')
;

-- Étape 3 : Vérifier les résultats
SELECT MoisFacture, MoisFacture2
FROM ConsosCarteSociale
LIMIT 10;

