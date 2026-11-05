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
        username = "tienda"
        password = os.getenv("TIENDA_PASSWORD", "osma1234")
        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"-> Usuario único de tienda creado: '{username}' (clave: '{password}')"))
        else:
            self.stdout.write(f"-> Usuario de tienda '{username}' ya existe.")

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

