from django.core.management.base import BaseCommand
from ventas.models import Venta, DetalleVenta, DesgloseLoteVenta
from pagos.models import PagoVenta, Gasto
from inventario.models import EntradaMercancia
from productos.models import Producto

class Command(BaseCommand):
    help = 'Limpia ventas, gastos o inventario de prueba para empezar de 0'

    def add_arguments(self, parser):
        parser.add_argument(
            '--todo',
            action='store_true',
            help='Elimina todos los productos, entradas, ventas y gastos (Reinicio total a 0).',
        )
        parser.add_argument(
            '--solo-ventas',
            action='store_true',
            help='Elimina solo ventas y gastos de prueba, restituyendo las existencias al 100%.',
        )

    def handle(self, *args, **options):
        self.stdout.write("Procesando limpieza de datos de prueba...")
        
        # Eliminar siempre transacciones financieras de prueba
        DesgloseLoteVenta.objects.all().delete()
        DetalleVenta.objects.all().delete()
        PagoVenta.objects.all().delete()
        Venta.objects.all().delete()
        Gasto.objects.all().delete()

        if options.get('todo'):
            EntradaMercancia.objects.all().delete()
            Producto.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("-> Reinicio total completado: Catálogo, entradas, ventas y gastos en 0."))
        else:
            for e in EntradaMercancia.objects.all():
                e.cantidad_disponible = e.cantidad_recibida
                e.save(update_fields=['cantidad_disponible'])
            self.stdout.write(self.style.SUCCESS("-> Limpieza completada: Se borraron ventas y gastos de prueba, y se restauró el stock de las entradas."))

