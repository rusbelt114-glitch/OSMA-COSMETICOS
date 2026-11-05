import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tasas.services import sincronizar_tasas_en_linea
from tasas.models import HistorialTasa
from decimal import Decimal

class Command(BaseCommand):
    help = 'Inicializa usuario único de tienda y tasas de cambio'

    def handle(self, *args, **options):
        self.stdout.write("Iniciando configuración base...")
        
        # 1. Crear / actualizar superusuario administrador de Django
        admin_user, _ = User.objects.get_or_create(username="admin")
        admin_user.set_password("admin1234")
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.is_active = True
        admin_user.save()
        self.stdout.write(self.style.SUCCESS("-> Superusuario Django asegurado: 'admin' (clave: 'admin1234')"))

        # 2. Crear / actualizar usuario único de tienda
        username = "tienda"
        password = os.getenv("TIENDA_PASSWORD", "1234")
        user, created = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.is_active = True
        user.save()
        self.stdout.write(self.style.SUCCESS(f"-> Usuario único de tienda asegurado: '{username}' (clave: '{password}')"))

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

