from datetime import datetime
from pathlib import Path
import shutil


ROOT = Path('/home/soakoja/hydria/backend')
SETTINGS = ROOT / 'hydria/settings.py'
URLS = ROOT / 'hydria/urls.py'


def backup(path):
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target = path.with_name(f'{path.name}.navigation-{stamp}.bak')
    shutil.copy2(path, target)
    print(f'backup={target}')


def insert_once(path, marker, anchor, addition):
    text = path.read_text(encoding='utf-8')
    if marker in text:
        print(f'already_configured={path}')
        return
    if anchor not in text:
        raise RuntimeError(f'Anchor introuvable dans {path}: {anchor}')
    backup(path)
    path.write_text(text.replace(anchor, addition + anchor, 1), encoding='utf-8')
    print(f'updated={path}')


insert_once(
    SETTINGS,
    "'apps.navigation_terrain'",
    "    'apps.infrastructure',",
    "    'apps.navigation_terrain',  # Navigation terrain Android\n",
)
insert_once(
    URLS,
    "include('apps.navigation_terrain.urls')",
    "    path('plannings/', include('apps.planning.urls')),",
    "    path('navigation-terrain/', include('apps.navigation_terrain.urls')),\n",
)
