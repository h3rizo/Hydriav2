"""
Utilitaires admin Django sans caractères Unicode pour compatibilité Windows
"""
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.html import format_html


class SafeAdminMixin:
    """
    Mixin admin sécurisé sans caractères Unicode
    Evite les erreurs UnicodeEncodeError sur Windows
    """

    def add_safe_message(self, request, level, message):
        """Ajoute un message sécurisé sans caractères spéciaux"""
        # Remplacer les caractères problématiques
        safe_message = message.replace('❌', 'ERREUR:').replace('✅', 'OK:').replace('📋', 'INFO:')

        if level == 'error':
            messages.error(request, safe_message)
        elif level == 'warning':
            messages.warning(request, safe_message)
        elif level == 'success':
            messages.success(request, safe_message)
        else:
            messages.info(request, safe_message)

    def format_safe_html(self, content):
        """Formate du HTML en remplaçant les caractères Unicode"""
        safe_content = content.replace('❌', '[ERREUR]').replace('✅', '[OK]').replace('📋', '[INFO]')
        return format_html(safe_content)


class SafeProtectedDeletionMixin(SafeAdminMixin):
    """
    Version sécurisée du mixin de protection de suppression
    """

    def delete_view(self, request, object_id, extra_context=None):
        """Override delete view to check constraints and show helpful messages"""
        try:
            obj = self.get_object(request, object_id)
        except self.model.DoesNotExist:
            return super().delete_view(request, object_id, extra_context)

        if request.method == 'POST':
            # Vérifier les contraintes avant suppression
            constraints = self._check_deletion_constraints(obj)
            if constraints:
                for constraint in constraints:
                    self.add_safe_message(request, 'error', constraint)
                return HttpResponseRedirect(request.get_full_path())

        return super().delete_view(request, object_id, extra_context)

    def _check_deletion_constraints(self, obj):
        """
        Vérifie les contraintes empêchant la suppression.
        À surcharger dans chaque ModelAdmin.
        """
        if hasattr(self, 'PROTECTED_RELATIONS'):
            return self._check_protected_relations(obj)
        return []

    def _check_protected_relations(self, obj):
        """Vérifie automatiquement toutes les relations protégées"""
        constraints = []

        for field_name, config in self.PROTECTED_RELATIONS.items():
            info = self._get_related_objects_info(
                obj,
                field_name,
                config.get('display_attr', '__str__')
            )

            if info['count'] > 0:
                verbose_name = config['verbose_name']
                solutions = config['solutions']

                reason = f"{info['count']} {verbose_name} y sont rattache(s) : {info['list']}"
                solutions_text = "\n".join([f"- {solution}" for solution in solutions])

                constraint = (
                    f"IMPOSSIBLE DE SUPPRIMER: {reason}\n"
                    f"SOLUTIONS:\n{solutions_text}"
                )
                constraints.append(constraint)

        return constraints

    def _get_related_objects_info(self, obj, field_name, display_attr='__str__', max_display=5):
        """
        Récupère les informations sur les objets liés
        """
        related_manager = getattr(obj, field_name)
        related_objects = related_manager.all()
        count = related_objects.count()

        if count == 0:
            return {'count': 0, 'list': '', 'objects': related_objects}

        # Créer la liste d'affichage
        items = []
        for related_obj in related_objects[:max_display]:
            if display_attr == '__str__':
                items.append(str(related_obj))
            else:
                items.append(getattr(related_obj, display_attr))

        items_list = ', '.join(items)
        if count > max_display:
            items_list += f' et {count - max_display} autre(s)'

        return {
            'count': count,
            'list': items_list,
            'objects': related_objects
        }