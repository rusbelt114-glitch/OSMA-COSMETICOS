from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Cambia la contraseña de acceso único de la tienda de forma rápida'

    def add_arguments(self, parser):
        parser.add_argument('nueva_clave', type=str, help='La nueva contraseña para el personal de la tienda')

    def handle(self, *args, **options):
        nueva_clave = options['nueva_clave'].strip()
        if not nueva_clave:
            self.stdout.write(self.style.ERROR("Error: La clave no puede estar vacía."))
            return

        user, _ = User.objects.get_or_create(username='tienda')
        user.set_password(nueva_clave)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"¡Listo! La clave de la tienda ha sido cambiada a: '{nueva_clave}'"))

