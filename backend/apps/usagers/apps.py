from django.apps import AppConfig


class UsagersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.usagers'
    verbose_name = 'Gestion des usagers'

    def ready(self):
        """
        Filet de securite: certaines references legacy utilisent encore
        reverse('representants_avis_evolution_dashboard') sans namespace.
        Si la route n'est pas resolvable, renvoyer une URL stable pour eviter
        un crash en NoReverseMatch dans les templates.
        """
        from django.urls import NoReverseMatch
        import django.urls as django_urls
        import django.urls.base as django_urls_base
        import django.template.defaulttags as defaulttags

        if getattr(django_urls_base, '_hydria_usagers_reverse_patched', False):
            return

        original_reverse = django_urls_base.reverse

        def reverse_with_usagers_fallback(viewname, *args, **kwargs):
            try:
                return original_reverse(viewname, *args, **kwargs)
            except NoReverseMatch:
                route_name = str(viewname or '')
                if route_name in {
                    'representants_avis_evolution_dashboard',
                    'usagers:representants_avis_evolution_dashboard',
                }:
                    return '/usagers/representants-evolution/'
                raise

        django_urls_base.reverse = reverse_with_usagers_fallback
        django_urls.reverse = reverse_with_usagers_fallback
        defaulttags.reverse = reverse_with_usagers_fallback
        django_urls_base._hydria_usagers_reverse_patched = True
