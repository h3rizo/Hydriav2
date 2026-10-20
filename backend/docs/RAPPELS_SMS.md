# Rappels SMS de paiement des factures

Code : `apps/billing/sms/` (gateway, echeances, messages, rappels), modèle `SmsLog` (`apps/billing/models_sms.py`, table `sms_log`),
vues `apps/billing/views_sms.py`, page `/facturation/sms/historique/`, commande `manage.py envoyer_rappels_sms`.

## Règles métier
- **Un SMS n'est envoyé que pour une facture NON pointée** : couple `numeroDiameX` + `baseDiameX` incomplet (règle du widget Hydria),
  hors relevés « coupé » et hors périodes de coupure. Revérifié en base juste avant chaque envoi et à chaque « Relancer ».
- Factures : `Releve` (volume, mois de facture = mois suivant le relevé) et `PaiementForfaitaire` (mois de `date_facture`),
  à partir du 01/01/2026 (même seuil comptable que le widget).
- **Date limite** : le **5** du mois de facture pour les **Kiosque**, le **15** pour **BP** et **BI volume**
  (`echeances.jour_limite_pour_type`). Autres types : aucun rappel tant qu'aucune règle n'est définie.
- Rappels à J-3 et J-1 (`SMS_RAPPEL_JOURS`). Un seul rappel par abonné et par échéance ; les **factures antérieures non pointées**
  du même abonné sont ajoutées (total cumulé).
- Points d'eau arrêtés (`datearretbranchement`) ou sans téléphone valide : ignorés. Numéros acceptés avec ou sans 0 initial (`347128573`).
- Message en GSM-7 sans accents, 160 caractères max. Si tout ne tient pas : **2 SMS** (1 = facture(s) + total + date limite,
  2 = consigne MVola). Motif MVola = `[type][IDXls] [Nom abonné]`. Numéro de facture vide (cas fréquent) → « mois MM/AAAA ».
- Anti-doublon : contrainte unique `(point_eau, date_echeance, type_rappel, partie)`. Une ligne « simulé » est réutilisée au passage en réel.
- Verrou PostgreSQL (`pg_try_advisory_lock`) : cron, bouton et autres workers ne peuvent pas s'exécuter en même temps.

## Configuration (.env)
```
SMS_DRY_RUN=True            # False = envoi réel
SMS_GATEWAY_URL=https://api.sms-gate.app/3rdparty/v1/message
SMS_GATEWAY_USER=...        # affichés dans l'app SMS Gateway
SMS_GATEWAY_PASS=...
SMS_NUMERO_MVOLA=034 xx xxx xx   # puce Telma du téléphone passerelle
SMS_RAPPEL_JOURS=3,1
SMS_DELAI_SECONDES=4
```

## Exploitation
- Test : `python manage.py envoyer_rappels_sms --dry-run [--date AAAA-MM-JJ] [--jours 3,1]`
- Cron VPS (8h Madagascar) : `CRON_TZ=Indian/Antananarivo` puis
  `0 8 * * * cd /home/soakoja/hydria/backend && ../venv/bin/python manage.py envoyer_rappels_sms >> /home/soakoja/hydria/logs/sms_rappels.log 2>&1`
- Page de suivi : filtres statut/période, « Relancer » (met à jour la ligne existante), « Lancer les rappels maintenant »
  (simulation = immédiat ; réel = en arrière-plan, suivi dans le tableau).
- Tests : `python manage.py test apps.billing.tests_sms` (sans base ni réseau).

## Passage en réel
1. Téléphone Android avec puce Telma + compte MVola actif, app SMS Gateway en mode Cloud, identifiants dans `.env`.
2. `SMS_NUMERO_MVOLA` = numéro de cette puce.
3. Vérifier le format de l'API sms-gate.app (endpoint/corps JSON) avec un envoi sur votre propre numéro.
4. `SMS_DRY_RUN=False`, redémarrer Gunicorn, tester d'abord avec `--jours` sur un point d'eau dont le téléphone est le vôtre.
