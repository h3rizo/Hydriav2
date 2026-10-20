"""
Commande pour lier un utilisateur Django à un employé
Usage: python manage.py link_user_to_employee <username> <surnom_employe>
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from apps.employees.models import Employe


class Command(BaseCommand):
    help = 'Lie un utilisateur Django à un employé par son surnom'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Nom d\'utilisateur Django')
        parser.add_argument('surnom', type=str, help='Surnom de l\'employé', nargs='?', default=None)

    def handle(self, *args, **options):
        username = options['username']
        surnom = options['surnom'] or username  # Utiliser le username si surnom non fourni

        try:
            # Rechercher l'utilisateur
            user = User.objects.get(username=username)
            self.stdout.write(self.style.SUCCESS(f'[OK] Utilisateur trouve: {user.username}'))

            # Rechercher l'employé par surnom (insensible à la casse)
            employe = Employe.objects.filter(surnom__iexact=surnom).first()

            if not employe:
                self.stdout.write(self.style.ERROR(f'[ERREUR] Aucun employe trouve avec le surnom "{surnom}"'))
                self.stdout.write(self.style.WARNING('Employes disponibles:'))
                for emp in Employe.objects.filter(surnom__isnull=False).order_by('surnom')[:10]:
                    self.stdout.write(f'  - {emp.surnom} ({emp.prenom} {emp.nom})')
                return

            self.stdout.write(self.style.SUCCESS(f'[OK] Employe trouve: {employe.prenom} {employe.nom} (surnom: {employe.surnom})'))

            # Vérifier si l'employé est déjà lié à un utilisateur
            if employe.user:
                self.stdout.write(self.style.WARNING(f'[ATTENTION] Cet employe est deja lie a l\'utilisateur "{employe.user.username}"'))
                response = input('Voulez-vous remplacer cette liaison? (oui/non): ')
                if response.lower() not in ['oui', 'o', 'yes', 'y']:
                    self.stdout.write(self.style.ERROR('Operation annulee'))
                    return

            # Créer la liaison
            employe.user = user
            employe.save()

            self.stdout.write(self.style.SUCCESS(f'\n[OK] Liaison creee avec succes!'))
            self.stdout.write(f'  Utilisateur: {user.username}')
            self.stdout.write(f'  Employe: {employe.prenom} {employe.nom} ({employe.surnom})')
            self.stdout.write(f'  Base: {employe.base.nom_base if employe.base else "N/A"}')
            self.stdout.write(f'  Poste: {employe.poste.nom_poste if employe.poste else "N/A"}')

        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'[ERREUR] Utilisateur "{username}" introuvable'))
            self.stdout.write(self.style.WARNING('Utilisateurs disponibles:'))
            for u in User.objects.all()[:10]:
                self.stdout.write(f'  - {u.username}')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'[ERREUR] Erreur: {str(e)}'))
