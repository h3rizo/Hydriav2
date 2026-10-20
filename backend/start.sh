#!/bin/bash

# Script de démarrage pour le déploiement
echo "Starting Hydria Django Backend..."

# Appliquer les migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Créer un superuser si nécessaire (en mode développement uniquement)
if [ "$DEBUG" = "True" ]; then
    echo "Creating superuser (dev mode)..."
    python manage.py shell -c "
from django.contrib.auth.models import User;
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@hydria.mg', 'admin123');
    print('Superuser créé: admin/admin123')
"
fi

# Collecter les fichiers statiques
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Vérification de santé
echo "Health check..."
python manage.py check --deploy

# Démarrer le serveur
echo "Starting Gunicorn server..."
exec gunicorn hydria.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-3} \
    --timeout 120 \
    --keep-alive 2 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --log-level info \
    --access-logfile - \
    --error-logfile -