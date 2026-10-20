"""Settings de travail local uniquement (vérifications / benchmarks).

Le venv local n'a ni ``daphne`` ni ``channels`` : ce module les retire de
``INSTALLED_APPS`` pour pouvoir lancer ``manage.py check``, ``test`` ou le client de
test Django. Il n'est pas utilisé en production (le VPS a les paquets complets).

Usage : ``python manage.py check --settings=hydria.settings_sans_channels``
"""

from .settings import *  # noqa: F401,F403

INSTALLED_APPS = [  # noqa: F405
    app for app in INSTALLED_APPS  # noqa: F405
    if app not in {'daphne', 'channels'}
]
