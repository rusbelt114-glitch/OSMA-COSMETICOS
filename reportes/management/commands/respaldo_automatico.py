import os
import glob
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from django.conf import settings

class Command(BaseCommand):
    help = 'Genera un respaldo automático de la base de datos de Osma y limpia copias antiguas'

    def handle(self, *args, **options):
        backup_dir = settings.BASE_DIR / 'backups'
        backup_dir.mkdir(exist_ok=True)

        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = backup_dir / f"respaldo_osma_{timestamp}.json"

        self.stdout.write(f"Iniciando respaldo automático en: {filename.name}...")

        with open(filename, 'w', encoding='utf-8') as f:
            call_command(
                'dumpdata',
                'productos', 'inventario', 'ventas', 'pagos', 'tasas',
                natural_foreign=True,
                natural_primary=True,
                indent=2,
                stdout=f
            )

        self.stdout.write(self.style.SUCCESS(f"OK: Respaldo completado con exito: {filename}"))

        # Mantener solo los últimos 30 respaldos para optimizar almacenamiento
        archivos = sorted(glob.glob(str(backup_dir / "respaldo_osma_*.json")), key=os.path.getmtime)
        if len(archivos) > 30:
            for antiguo in archivos[:-30]:
                try:
                    os.remove(antiguo)
                    self.stdout.write(f"Copia antigua rotada: {os.path.basename(antiguo)}")
                except Exception:
                    pass
