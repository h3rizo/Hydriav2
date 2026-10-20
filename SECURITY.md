# 🔒 Politique de Sécurité - Hydria

## Vue d'ensemble

La sécurité de l'application **Hydria** est une priorité absolue, particulièrement important pour une application gérant des données d'infrastructure critique à Madagascar.

## 🎯 Principes de sécurité

### 1. Défense en profondeur
- **Authentification multi-facteurs** via Supabase
- **Autorisation granulaire** par rôles utilisateur
- **Chiffrement** des données sensibles
- **Validation** côté client et serveur

### 2. Sécurité des données
- **Chiffrement en transit** (HTTPS/TLS 1.3)
- **Chiffrement au repos** via Supabase
- **Pseudonymisation** des données personnelles
- **Sauvegarde sécurisée** automatique

### 3. Architecture sécurisée
- **Séparation des couches** (Frontend/Backend/DB)
- **Principe du moindre privilège**
- **Isolation des environnements**
- **Audit trail** complet

## 🚨 Signalement de vulnérabilités

### Contact sécurité
- **Email** : security@hydria.mg
- **Délai de réponse** : 48h maximum
- **Coordonnées** : PGP Key disponible sur demande

### Processus de signalement

1. **Identification** d'une vulnérabilité
2. **Documentation** détaillée (étapes, impact)
3. **Signalement confidentiel** via email sécurisé
4. **Confirmation** de réception sous 48h
5. **Investigation** et correctif sous 7 jours
6. **Publication** d'un advisory si nécessaire

### Ce qu'il faut inclure
```
- Description de la vulnérabilité
- Étapes de reproduction
- Impact potentiel
- Environnement affecté (prod/staging)
- Screenshots ou logs (si pertinents)
- Coordonnées pour suivi
```

## 🛡️ Mesures de sécurité implémentées

### Backend Django

#### Configuration sécurisée
```python
# settings.py
DEBUG = False
SECRET_KEY = env('SECRET_KEY')  # 50+ caractères aléatoires
ALLOWED_HOSTS = ['.onrender.com']

# Headers de sécurité
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Session sécurisée
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# CSRF Protection
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'
```

#### Authentification et autorisation
```python
# Authentification via Supabase
AUTHENTICATION_BACKENDS = [
    'apps.core.backends.SupabaseAuthBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Permissions par rôle
ROLE_PERMISSIONS = {
    'admin': ['*'],
    'supervisor': ['view_*', 'add_inspection', 'change_inspection'],
    'technician': ['view_inspection', 'add_resultat'],
    'viewer': ['view_*'],
}
```

#### Validation et sanitisation
```python
# Validation stricte des entrées
from django.core.validators import RegexValidator, MaxLengthValidator
from django.utils.html import escape

# Sanitisation des données
def sanitize_input(data):
    if isinstance(data, str):
        return escape(data.strip())
    return data
```

### Frontend Nuxt.js

#### Configuration sécurisée
```typescript
// nuxt.config.ts
export default defineNuxtConfig({
  // Headers de sécurité
  routeRules: {
    '/**': {
      headers: {
        'X-Frame-Options': 'DENY',
        'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'geolocation=(), microphone=(), camera=()'
      }
    }
  },
  
  // CSP (Content Security Policy)
  security: {
    headers: {
      contentSecurityPolicy: {
        'default-src': ["'self'"],
        'script-src': ["'self'", "'unsafe-inline'", 'ytqvyihgztdnwkgvozqn.supabase.co'],
        'style-src': ["'self'", "'unsafe-inline'"],
        'img-src': ["'self'", 'data:', 'ytqvyihgztdnwkgvozqn.supabase.co'],
        'connect-src': ["'self'", 'ytqvyihgztdnwkgvozqn.supabase.co', 'hydria-backend.onrender.com']
      }
    }
  }
})
```

#### Gestion sécurisée des tokens
```typescript
// composables/useAuth.ts
export const useAuth = () => {
  // Tokens stockés de manière sécurisée
  const accessToken = useCookie('access_token', {
    httpOnly: true,
    secure: true,
    sameSite: 'strict',
    maxAge: 60 * 60 // 1 heure
  })
  
  // Validation côté client
  const validateInput = (input: string, type: 'email' | 'text' | 'number') => {
    const patterns = {
      email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
      text: /^[a-zA-Z0-9\s\-_.,]+$/,
      number: /^\d+$/
    }
    return patterns[type].test(input)
  }
}
```

#### Mode hors ligne sécurisé
```typescript
// stores/offline.ts - Chiffrement des données sensibles
import CryptoJS from 'crypto-js'

const encryptData = (data: any, key: string) => {
  return CryptoJS.AES.encrypt(JSON.stringify(data), key).toString()
}

const decryptData = (encryptedData: string, key: string) => {
  const bytes = CryptoJS.AES.decrypt(encryptedData, key)
  return JSON.parse(bytes.toString(CryptoJS.enc.Utf8))
}
```

### Base de données Supabase

#### Row Level Security (RLS)
```sql
-- Politique pour les inspections
CREATE POLICY "Users can view inspections from their organization" 
ON inspections FOR SELECT 
USING (organization_id IN (
  SELECT organization_id FROM user_organizations 
  WHERE user_id = auth.uid()
));

-- Politique pour les modifications
CREATE POLICY "Supervisors can modify inspections" 
ON inspections FOR UPDATE 
USING (
  organization_id IN (
    SELECT organization_id FROM user_organizations 
    WHERE user_id = auth.uid() AND role IN ('admin', 'supervisor')
  )
);
```

#### Audit et logging
```sql
-- Trigger d'audit automatique
CREATE OR REPLACE FUNCTION audit_trigger()
RETURNS trigger AS $$
BEGIN
  INSERT INTO audit_log (
    table_name, operation, user_id, 
    old_values, new_values, timestamp
  ) VALUES (
    TG_TABLE_NAME, TG_OP, auth.uid(),
    row_to_json(OLD), row_to_json(NEW), now()
  );
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
```

## 🔐 Chiffrement et secrets

### Gestion des secrets
```bash
# Variables d'environnement sécurisées
SECRET_KEY=$(openssl rand -hex 32)
DATABASE_ENCRYPTION_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)

# Rotation automatique des secrets (mensuelle)
# Via GitHub Actions et Render API
```

### Chiffrement des données sensibles
```python
# Champs chiffrés dans les modèles
from cryptography.fernet import Fernet

class EncryptedField(models.TextField):
    def __init__(self, *args, **kwargs):
        self.cipher = Fernet(settings.FIELD_ENCRYPTION_KEY)
        super().__init__(*args, **kwargs)
    
    def from_db_value(self, value, expression, connection):
        if value is not None:
            return self.cipher.decrypt(value.encode()).decode()
        return value
    
    def to_python(self, value):
        return value
    
    def get_prep_value(self, value):
        if value is not None:
            return self.cipher.encrypt(value.encode()).decode()
        return value
```

## 🚫 Menaces identifiées et mitigations

### 1. Injection SQL
- **Mitigation** : ORM Django + Requêtes paramétrées
- **Tests** : Sqlmap automatisés dans CI/CD
- **Monitoring** : Logs des requêtes suspectes

### 2. Cross-Site Scripting (XSS)
- **Mitigation** : CSP strict + Validation entrées
- **Tests** : Tests automatisés OWASP ZAP
- **Sanitisation** : Escape automatique des templates

### 3. Cross-Site Request Forgery (CSRF)
- **Mitigation** : Tokens CSRF Django
- **Configuration** : SameSite cookies
- **Validation** : Headers Origin/Referer

### 4. Accès non autorisé
- **Mitigation** : Authentification MFA
- **Autorisation** : Permissions granulaires
- **Monitoring** : Tentatives de connexion suspectes

### 5. Exposition de données
- **Mitigation** : Chiffrement bout en bout
- **Minimisation** : Principe du moindre privilège
- **Audit** : Logs d'accès complets

### 6. Attaques hors ligne
- **Mitigation** : Chiffrement local
- **Validation** : Signature des données
- **Synchronisation** : Authentification requise

## 📊 Monitoring et détection

### Métriques de sécurité
```python
# Métriques surveillées
SECURITY_METRICS = {
    'failed_logins': 'Tentatives de connexion échouées',
    'suspicious_requests': 'Requêtes suspectes',
    'data_access_anomalies': 'Anomalies d\'accès aux données',
    'encryption_errors': 'Erreurs de chiffrement',
    'csrf_violations': 'Violations CSRF',
    'rate_limit_exceeded': 'Dépassements de limites'
}
```

### Alertes automatiques
- **Seuils** : > 10 tentatives de connexion échouées/minute
- **Géolocalisation** : Connexions depuis pays non autorisés
- **Horaires** : Accès hors heures normales (22h-6h)
- **Patterns** : Requêtes d'injection identifiées

### SIEM intégration
```yaml
# Configuration logging sécurisé
logging:
  formatters:
    security:
      format: '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
  handlers:
    security_file:
      class: logging.handlers.RotatingFileHandler
      filename: /var/log/hydria/security.log
      maxBytes: 10485760  # 10MB
      backupCount: 5
      formatter: security
```

## ✅ Tests de sécurité

### Tests automatisés
```yaml
# .github/workflows/security-tests.yml
- name: OWASP ZAP Baseline Scan
  uses: zaproxy/action-baseline@v0.7.0
  with:
    target: 'https://hydria-frontend.onrender.com'

- name: Snyk Security Scan
  uses: snyk/actions/node@master
  with:
    command: test
    args: --severity-threshold=medium

- name: Semgrep Security Scan
  uses: returntocorp/semgrep-action@v1
  with:
    config: p/security-audit
```

### Tests manuels réguliers
- **Pentest** trimestriel par équipe externe
- **Code review** sécurisé obligatoire
- **Audit** des permissions mensuel
- **Test** de récupération après incident

## 🏥 Plan de réponse aux incidents

### 1. Détection (0-30 minutes)
- Monitoring automatique 24/7
- Alertes temps réel équipe sécurité
- Évaluation initiale de l'impact

### 2. Confinement (30 minutes - 2 heures)
- Isolation des systèmes affectés
- Préservation des preuves
- Communication équipe de crise

### 3. Éradication (2-24 heures)
- Identification de la cause racine
- Suppression de la menace
- Correctifs de sécurité

### 4. Récupération (24-72 heures)
- Restauration des services
- Tests de validation
- Monitoring renforcé

### 5. Leçons apprises (1 semaine)
- Analyse post-incident
- Amélioration des processus
- Formation équipe

## 📞 Contacts d'urgence

### Équipe sécurité
- **Responsable sécurité** : security-lead@hydria.mg
- **Équipe technique** : tech-team@hydria.mg
- **Urgences** : +261 XX XXX XXX (24/7)

### Partenaires externes
- **Hébergement Render** : Support prioritaire
- **Base de données Supabase** : Support enterprise
- **Audit sécurité** : Partenaire certifié CISSP

---

## 📋 Checklist sécurité

### Développement
- [ ] Code review sécurisé obligatoire
- [ ] Tests de sécurité automatisés
- [ ] Validation des entrées stricte
- [ ] Chiffrement des données sensibles
- [ ] Gestion sécurisée des secrets

### Déploiement
- [ ] HTTPS/TLS 1.3 obligatoire
- [ ] Headers de sécurité configurés
- [ ] Permissions minimales
- [ ] Monitoring de sécurité actif
- [ ] Sauvegardes chiffrées

### Opérations
- [ ] Mises à jour sécurité automatiques
- [ ] Rotation des secrets mensuelle
- [ ] Audit des accès trimestriel
- [ ] Formation équipe continue
- [ ] Tests de pénétration réguliers

**🔐 La sécurité est l'affaire de tous - Signalez tout comportement suspect !**