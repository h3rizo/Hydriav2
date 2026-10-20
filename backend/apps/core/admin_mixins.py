"""
Mixins pour l'administration Django avec gestion des contraintes de suppression
"""
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.html import format_html


class DeletionConstraintMixin:
    """
    Mixin pour les ModelAdmin Django qui vérifie les contraintes de suppression
    et affiche des messages d'erreur informatifs à l'utilisateur.
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
                    messages.error(request, constraint)
                return HttpResponseRedirect(request.get_full_path())

        return super().delete_view(request, object_id, extra_context)

    def _check_deletion_constraints(self, obj):
        """
        Vérifie les contraintes empêchant la suppression.
        À surcharger dans chaque ModelAdmin pour définir les contraintes spécifiques.
        """
        return []

    def _format_constraint_message(self, title, reason, items_list, solutions):
        """
        Formate un message de contrainte de suppression

        Args:
            title: Titre de l'erreur
            reason: Raison de l'impossibilité de suppression
            items_list: Liste des éléments concernés
            solutions: Liste des solutions possibles
        """
        solutions_html = "<br>".join([f"&nbsp;&nbsp;• {solution}" for solution in solutions])

        return format_html(
            "ERREUR: <strong>{title}</strong><br>"
            "RAISON: {reason}<br>"
            "SOLUTIONS:<br>"
            "{solutions}",
            title=title,
            reason=reason,
            solutions=solutions_html
        )

    def _get_related_objects_info(self, obj, field_name, display_attr='__str__', max_display=5):
        """
        Récupère les informations sur les objets liés

        Args:
            obj: L'objet à vérifier
            field_name: Nom du champ de relation (ex: 'employes')
            display_attr: Attribut à utiliser pour l'affichage (ex: 'nom_complet')
            max_display: Nombre maximum d'éléments à afficher dans la liste

        Returns:
            dict: {'count': int, 'list': str, 'objects': QuerySet}
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


class ProtectedDeletionMixin(DeletionConstraintMixin):
    """
    Mixin spécialisé pour les modèles avec relations protégées
    Utilise la configuration PROTECTED_RELATIONS pour définir automatiquement les contraintes
    """

    # À définir dans chaque ModelAdmin utilisant ce mixin
    PROTECTED_RELATIONS = {
        # 'field_name': {
        #     'verbose_name': 'nom affiché',
        #     'display_attr': 'attribut_affichage',
        #     'solutions': ['Solution 1', 'Solution 2']
        # }
    }

    def _check_deletion_constraints(self, obj):
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

                reason = f"{info['count']} {verbose_name} y sont rattaché(s) : {info['list']}"

                constraint = self._format_constraint_message(
                    title="Impossible de supprimer cet enregistrement.",
                    reason=reason,
                    items_list=info['list'],
                    solutions=solutions
                )
                constraints.append(constraint)

        return constraints