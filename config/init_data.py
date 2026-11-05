import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from tasas.services import sincronizar_tasas_en_linea
from tasas.models import HistorialTasa
from decimal import Decimal

def inicializar():
    print("Iniciando configuración base...")
    # 1. Crear usuario de tienda único
    username = "tienda"
    password = os.getenv("TIENDA_PASSWORD", "osma1234")
    user, created = User.objects.get_or_create(username=username)
    if created:
        user.set_password(password)
        user.save()
        print(f"-> Usuario único de tienda creado: '{username}' con contraseña '{password}'")
    else:
        print(f"-> Usuario de tienda '{username}' ya existe.")

    # 2. Sincronizar tasas iniciales
    print("-> Sincronizando tasas iniciales...")
    res = sincronizar_tasas_en_linea()
    if res['exito']:
        print(f"-> Tasas obtenidas: BCV={res['usd_bcv']} Bs | USDT={res['usdt']} Bs")
    else:
        # Asegurar tasas de respaldo
        HistorialTasa.objects.get_or_create(
            tipo='USD_BCV',
            defaults={'valor': Decimal('893.2000'), 'fuente': 'Resguardo Inicial'}
        )
        HistorialTasa.objects.get_or_create(
            tipo='USDT',
            defaults={'valor': Decimal('1010.5000'), 'fuente': 'Resguardo Inicial'}
        )
        print("-> Se establecieron tasas de resguardo iniciales.")

    print("Configuración completada con éxito.")

if __name__ == '__main__':
    inicializar()

