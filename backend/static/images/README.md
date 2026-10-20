# 📸 Guide pour ajouter des images personnalisées à la page d'accueil

## Emplacement des images

Les images pour la page d'accueil doivent être placées dans ce répertoire :
```
backend/static/images/
```

## Images recommandées

### 1. Bannière Hero (Banner principal)
- **Nom du fichier** : `hero-banner.jpg` ou `hero-banner.png`
- **Dimensions recommandées** : 1920 x 600 pixels
- **Format** : JPG ou PNG
- **Taille maximale** : 500 KB (compressée)
- **Utilisation** : Bannière principale en haut de la page

**Comment l'ajouter :**
1. Placez votre image dans `backend/static/images/hero-banner.jpg`
2. Modifiez le fichier `backend/templates/home_launcher.html` ligne 12-13
3. Décommentez et modifiez :
```html
<img src="{% static 'images/hero-banner.jpg' %}" class="w-full h-full object-cover" alt="Hero Banner">
```

### 2. Image Dashboard
- **Nom du fichier** : `dashboard.jpg` ou `dashboard.png`
- **Dimensions recommandées** : 600 x 400 pixels
- **Format** : JPG ou PNG
- **Taille maximale** : 200 KB
- **Utilisation** : Image de la grande carte Dashboard

**Comment l'ajouter :**
1. Placez votre image dans `backend/static/images/dashboard.jpg`
2. Modifiez le fichier `backend/templates/home_launcher.html` ligne 107
3. Remplacez le commentaire par :
```html
<img src="{% static 'images/dashboard.jpg' %}" alt="Dashboard" class="object-cover w-full h-full">
```

### 3. Image Plannings
- **Nom du fichier** : `plannings.jpg` ou `plannings.png`
- **Dimensions recommandées** : 600 x 400 pixels
- **Format** : JPG ou PNG
- **Taille maximale** : 200 KB
- **Utilisation** : Image de la grande carte Plannings

**Comment l'ajouter :**
1. Placez votre image dans `backend/static/images/plannings.jpg`
2. Modifiez le fichier `backend/templates/home_launcher.html` ligne 177
3. Remplacez le commentaire par :
```html
<img src="{% static 'images/plannings.jpg' %}" alt="Plannings" class="object-cover w-full h-full">
```

## Images supplémentaires possibles

Vous pouvez également ajouter des images pour les autres cartes si vous le souhaitez :
- `carte-interactive.jpg` - Pour la carte géographique
- `inspections.jpg` - Pour le module inspections
- `facturation.jpg` - Pour le module facturation
- `comptabilite.jpg` - Pour la comptabilité
- `chantiers.jpg` - Pour les chantiers
- `employes.jpg` - Pour les RH

## Recommandations techniques

### Optimisation des images
1. **Compresser vos images** avant de les uploader :
   - Utilisez [TinyPNG](https://tinypng.com/) pour compresser PNG
   - Utilisez [JPEGmini](https://www.jpegmini.com/) pour compresser JPG
   - Ou utilisez un outil en ligne comme [Squoosh](https://squoosh.app/)

2. **Format recommandé** :
   - JPG pour les photos réelles
   - PNG pour les illustrations avec transparence
   - WebP pour une meilleure compression (navigateurs modernes)

3. **Résolution** :
   - Utilisez 2x la taille d'affichage pour les écrans Retina
   - Exemple : Si affiché à 600x400px, uploadez 1200x800px

### Structure du dossier images

```
backend/static/images/
├── README.md (ce fichier)
├── hero-banner.jpg (1920x600px)
├── dashboard.jpg (600x400px)
├── plannings.jpg (600x400px)
├── carte-interactive.jpg (optionnel)
├── inspections.jpg (optionnel)
├── facturation.jpg (optionnel)
└── ... (autres images)
```

## Comment tester vos images

1. **Ajoutez votre image** dans `backend/static/images/`
2. **Modifiez le template** `backend/templates/home_launcher.html`
3. **Rechargez Django** avec Ctrl+C puis `python manage.py runserver`
4. **Videz le cache du navigateur** avec Ctrl+F5
5. **Visitez** `http://localhost:8000/accueil/`

## Alternative : Images dynamiques via Django Admin

Pour permettre le changement d'images sans modifier le code, vous pouvez :

1. Créer un modèle Django pour les images :
```python
class PageImage(models.Model):
    name = models.CharField(max_length=100)  # ex: "hero-banner"
    image = models.ImageField(upload_to='pages/')
    description = models.TextField(blank=True)
```

2. Ajouter ce modèle dans l'admin Django
3. Utiliser dans le template :
```html
{% load static %}
<img src="{{ page_image.image.url }}" alt="{{ page_image.description }}">
```

Cela permettra de changer les images via l'interface d'administration Django sans toucher au code.

## Besoin d'aide ?

Si vous avez des questions ou besoin d'aide pour personnaliser les images, n'hésitez pas à consulter la documentation Django sur les fichiers statiques :
https://docs.djangoproject.com/en/5.2/howto/static-files/
