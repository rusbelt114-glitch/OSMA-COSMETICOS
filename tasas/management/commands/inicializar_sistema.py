import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tasas.services import sincronizar_tasas_en_linea
from tasas.models import HistorialTasa
from decimal import Decimal

class Command(BaseCommand):
    help = 'Inicializa usuario único de tienda y tasas de cambio'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-passwords',
            action='store_true',
            help='Fuerza el restablecimiento de contraseñas por defecto (admin1234 / 1234)',
        )

    def handle(self, *args, **options):
        self.stdout.write("Iniciando configuración base...")
        reset_pwd = options.get('reset_passwords', False)
        
        # 1. Crear / actualizar superusuario administrador de Django
        admin_user, admin_created = User.objects.get_or_create(username="admin")
        if admin_created or reset_pwd:
            admin_user.set_password("admin1234")
            self.stdout.write(self.style.SUCCESS("-> Superusuario 'admin' configurado con clave inicial 'admin1234'."))
        else:
            self.stdout.write(self.style.NOTICE("-> Superusuario 'admin' ya existe (clave personalizada conservada)."))
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.is_active = True
        admin_user.save()

        # 2. Crear / actualizar usuario único de tienda
        username = "tienda"
        default_pwd = os.getenv("TIENDA_PASSWORD", "1234")
        user, user_created = User.objects.get_or_create(username=username)
        if user_created or reset_pwd:
            user.set_password(default_pwd)
            self.stdout.write(self.style.SUCCESS(f"-> Usuario '{username}' configurado con clave inicial '{default_pwd}'."))
        else:
            self.stdout.write(self.style.NOTICE(f"-> Usuario '{username}' ya existe (clave personalizada conservada)."))
        user.is_active = True
        user.save()

        self.stdout.write("-> Sincronizando tasas oficiales...")
        res = sincronizar_tasas_en_linea()
        if res['exito']:
            self.stdout.write(self.style.SUCCESS(f"-> Tasas obtenidas: BCV={res['usd_bcv']} Bs | USDT={res['usdt']} Bs"))
        else:
            HistorialTasa.objects.get_or_create(
                tipo='USD_BCV',
                defaults={'valor': Decimal('893.2000'), 'fuente': 'Resguardo Inicial'}
            )
            HistorialTasa.objects.get_or_create(
                tipo='USDT',
                defaults={'valor': Decimal('1010.5000'), 'fuente': 'Resguardo Inicial'}
            )
            self.stdout.write(self.style.WARNING("-> Se establecieron tasas de resguardo iniciales."))

        self.stdout.write(self.style.SUCCESS("Sistema inicializado correctamente."))

