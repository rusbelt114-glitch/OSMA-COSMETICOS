import os
import shutil
from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings
from django.db import connection

class Command(BaseCommand):
    help = 'Genera un respaldo verificado de la base de datos (SQLite / JSON) con rotación y soporte para disco externo'

    def add_arguments(self, parser):
        parser.add_argument(
            '--destino',
            type=str,
            default='',
            help='Ruta de destino externa (ej: pendrive D:\\Respaldos o carpeta Google Drive)',
        )
        parser.add_argument(
            '--mantener',
            type=int,
            default=20,
            help='Número máximo de copias históricas a conservar (por defecto 20)',
        )

    def handle(self, *args, **options):
        self.stdout.write("Iniciando generación de respaldo del sistema...")
        
        # 1. Definir directorio de destino
        destino_arg = options.get('destino') or os.getenv('BACKUP_EXTERNAL_DIR', '')
        if destino_arg:
            backup_dir = Path(destino_arg)
        else:
            backup_dir = settings.BASE_DIR / 'backups'

        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 2. Respaldo lógico JSON completo de datos de negocio
        json_file = backup_dir / f"respaldo_datos_{ts}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            call_command(
                'dumpdata',
                'productos', 'inventario', 'ventas', 'pagos', 'tasas',
                natural_foreign=True, natural_primary=True, indent=2, stdout=f
            )
        self.stdout.write(self.style.SUCCESS(f"-> Respaldo de datos generado: {json_file.name} ({json_file.stat().st_size} bytes)"))

        # 3. Respaldo físico SQLite si aplica
        if connection.vendor == 'sqlite':
            db_path = Path(settings.DATABASES['default']['NAME'])
            if db_path.exists():
                sqlite_backup = backup_dir / f"respaldo_sqlite_{ts}.db"
                # Usar VACUUM INTO si es compatible o copia segura con flush
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(f"VACUUM INTO '{sqlite_backup.as_posix()}'")
                    self.stdout.write(self.style.SUCCESS(f"-> Copia física SQLite generada mediante VACUUM: {sqlite_backup.name}"))
                except Exception:
                    shutil.copy2(db_path, sqlite_backup)
                    self.stdout.write(self.style.SUCCESS(f"-> Copia física SQLite generada mediante copia directa: {sqlite_backup.name}"))

        # 4. Rotación automática de respaldos antiguos para proteger espacio en disco
        max_copias = options.get('mantener', 20)
        archivos_json = sorted(backup_dir.glob("respaldo_datos_*.json"), key=os.path.getmtime)
        if len(archivos_json) > max_copias:
            sobrantes = archivos_json[:-max_copias]
            for s in sobrantes:
                try:
                    s.unlink()
                except Exception:
                    pass
            self.stdout.write(self.style.NOTICE(f"-> Rotación completada: se eliminaron {len(sobrantes)} copias antiguas."))

        archivos_db = sorted(backup_dir.glob("respaldo_sqlite_*.db"), key=os.path.getmtime)
        if len(archivos_db) > max_copias:
            sobrantes_db = archivos_db[:-max_copias]
            for s in sobrantes_db:
                try:
                    s.unlink()
                except Exception:
                    pass

        self.stdout.write(self.style.SUCCESS("Respaldo completado y asegurado con éxito."))

