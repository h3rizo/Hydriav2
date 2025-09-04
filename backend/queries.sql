-- Voir tous les employés
SELECT * FROM Employes;

-- Voir les plannings avec employés
SELECT p.date, p.titre, e.prenom, e.nom 
FROM Plannings p 
JOIN Employes e ON p.employe_id = e.id;

-- Compter les ouvrages par type
SELECT type, COUNT(*) as nombre 
FROM Ouvrages 
GROUP BY type;

-- Voir les dernières connexions (à implémenter)
SELECT email, date_creation 
FROM Employes 
ORDER BY date_creation DESC;