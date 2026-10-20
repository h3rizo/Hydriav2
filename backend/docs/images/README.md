# Captures d'écran - Manuel d'Utilisateur

Ce répertoire contient les captures d'écran pour la documentation du manuel d'utilisateur.

## 📸 Captures à ajouter

Pour enrichir la documentation, vous pouvez ajouter les captures d'écran suivantes :

### 1. `manuel_desktop_interface.png`
**Description** : Vue d'ensemble de l'interface desktop
- Afficher la page complète avec sidebar + contenu
- Résolution recommandée : 1920x1080
- Format : PNG

### 2. `manuel_sidebar_navigation.png`
**Description** : Détail de la sidebar avec table des matières
- Zoomer sur la zone de navigation
- Montrer les badges numérotés
- Résolution recommandée : 400x800
- Format : PNG

### 3. `manuel_search_highlight.png`
**Description** : Fonction de recherche avec highlighting
- Saisir un terme de recherche (ex: "planning")
- Montrer les résultats surlignés en jaune
- Résolution recommandée : 1200x800
- Format : PNG

### 4. `manuel_print_preview.png`
**Description** : Aperçu d'impression (Ctrl+P)
- Montrer la boîte de dialogue d'impression
- Contenu sans éléments d'interface
- Résolution recommandée : 1920x1080
- Format : PNG

### 5. `manuel_mobile_interface.png`
**Description** : Version mobile/tablette
- Utiliser les DevTools du navigateur (mode responsive)
- Largeur : 375px (iPhone) ou 768px (iPad)
- Résolution recommandée : 375x812 ou 768x1024
- Format : PNG

## 🔧 Comment capturer les écrans

### Depuis le navigateur

1. **Accéder au manuel** : `http://localhost:8000/systeme/manuel/`
2. **Ouvrir DevTools** : F12 ou Clic droit > Inspecter
3. **Mode responsive** : Ctrl+Shift+M (Chrome/Edge) ou Ctrl+Shift+M (Firefox)
4. **Capturer** :
   - Windows : Win+Shift+S (Outil Capture d'écran)
   - Chrome DevTools : Ctrl+Shift+P → "Capture screenshot"
   - Extensions navigateur : "Full Page Screen Capture", "Awesome Screenshot"

### Depuis Python/Selenium (automatique)

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

# Configuration
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--window-size=1920,1080')

driver = webdriver.Chrome(options=chrome_options)

# Se connecter (adapter les credentials)
driver.get('http://localhost:8000/accounts/login/')
driver.find_element('name', 'username').send_keys('admin')
driver.find_element('name', 'password').send_keys('password')
driver.find_element('css selector', 'button[type="submit"]').click()
time.sleep(2)

# Capturer le manuel
driver.get('http://localhost:8000/systeme/manuel/')
time.sleep(3)  # Attendre chargement complet
driver.save_screenshot('backend/docs/images/manuel_desktop_interface.png')

# Version mobile
driver.set_window_size(375, 812)
time.sleep(1)
driver.save_screenshot('backend/docs/images/manuel_mobile_interface.png')

driver.quit()
```

## 📝 Intégration dans la documentation

Une fois les captures ajoutées, mettre à jour `MANUEL_INTERFACE_WEB.md` :

```markdown
## 📸 Captures d'écran

### Interface principale

![Interface Desktop](images/manuel_desktop_interface.png)
*Vue d'ensemble de l'interface avec sidebar navigation et contenu*

### Navigation par sections

![Sidebar Navigation](images/manuel_sidebar_navigation.png)
*Table des matières interactive avec badges numérotés*

### Recherche en temps réel

![Search Highlighting](images/manuel_search_highlight.png)
*Résultats de recherche avec surlignage automatique*

### Mode impression

![Print Preview](images/manuel_print_preview.png)
*Aperçu d'impression optimisé (sans éléments d'interface)*

### Version mobile

![Mobile Interface](images/manuel_mobile_interface.png)
*Interface responsive adaptée aux mobiles et tablettes*
```

## ✅ Checklist

- [ ] Capture interface desktop complète
- [ ] Capture sidebar navigation détaillée
- [ ] Capture recherche avec highlighting
- [ ] Capture aperçu d'impression
- [ ] Capture version mobile
- [ ] Intégration dans MANUEL_INTERFACE_WEB.md
- [ ] Vérification de la taille des fichiers (<500 KB par image recommandé)
- [ ] Optimisation des images (compression PNG)

## 🎨 Conseils de qualité

- **Résolution** : Privilégier les résolutions 1920x1080 pour desktop
- **Format** : PNG pour conserver la netteté du texte
- **Compression** : Utiliser TinyPNG ou ImageOptim pour réduire la taille
- **Cohérence** : Utiliser le même thème (dark/light) pour toutes les captures
- **Annotations** : Ajouter des flèches/encadrés si nécessaire avec un outil comme Skitch ou Greenshot
