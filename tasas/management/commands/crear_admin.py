from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Crea o actualiza el superusuario administrador para el panel /admin/'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, default='admin', help='Nombre de usuario admin')
        parser.add_argument('--password', type=str, default='admin1234', help='Contraseña para el admin')

    def handle(self, *args, **options):
        username = options['user']
        password = options['password']

        user, created = User.objects.get_or_create(username=username)
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Superusuario '{username}' creado con clave '{password}'."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Superusuario '{username}' actualizado con clave '{password}'."))

