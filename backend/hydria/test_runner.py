from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test.runner import DiscoverRunner


class ProjectAppsDiscoverRunner(DiscoverRunner):
    """Discover tests from local project apps when no explicit labels are provided."""

    def build_suite(self, test_labels=None, **kwargs):
        labels = test_labels or ["."]
        if labels == ["."]:
            base_dir = Path(settings.BASE_DIR).resolve()
            labels = []
            for app_config in apps.get_app_configs():
                app_path = Path(app_config.path).resolve()
                if not str(app_path).startswith(str(base_dir)):
                    continue
                labels.append(app_config.name)
        return super().build_suite(labels, **kwargs)
