from pathlib import Path
import apps

from hydria.settings import *  # noqa: F401,F403

PATCH_ROOT = Path(__file__).resolve().parent
apps.__path__.insert(0, str(PATCH_ROOT / 'apps'))
INSTALLED_APPS = [*INSTALLED_APPS, 'apps.navigation_terrain']
ROOT_URLCONF = 'test_urls'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': PATCH_ROOT / 'navigation_test.sqlite3'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
TEST_RUNNER = 'django.test.runner.DiscoverRunner'
