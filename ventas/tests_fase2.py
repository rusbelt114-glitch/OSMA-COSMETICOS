from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from productos.models import Producto
from inventario.models import EntradaMercancia
from ventas.models import Venta
from pagos.models import PagoVenta
from ventas.services import registrar_venta_fifo, anular_venta_fifo

class Fase2VentasVueltoAnulacionesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tienda', password='1234')
        self.client = Client()
        self.client.force_login(self.user)

        # Crear producto y lote inicial
        self.producto = Producto.objects.create(nombre="Labial Mate Rosa", stock_minimo=3)
        self.lote = EntradaMercancia.objects.create(
            producto=self.producto,
            cantidad_recibida=10,
            cantidad_disponible=10,
            costo_unitario=Decimal('50.00'),
            precio_venta=Decimal('100.00')
        )

    def test_01_idempotencia_evita_ventas_duplicadas(self):
        """Prueba que enviar dos veces la misma venta con el mismo token solo descuente una vez."""
        token = "IDEM-TEST-VENTA-001"
        items = [{'producto_id': self.producto.id, 'cantidad': 3, 'precio_unitario_bs': Decimal('100.00')}]
        pagos = [{'metodo': 'EFECTIVO_BS', 'monto_original': Decimal('300.00')}]

        # 1. Primer registro
        v1 = registrar_venta_fifo(items, pagos, Decimal('100.00'), Decimal('100.00'), idempotency_key=token)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_disponible, 7) # 10 - 3

        # 2. Reintento con la misma clave (simulando doble clic o reenvío)
        v2 = registrar_venta_fifo(items, pagos, Decimal('100.00'), Decimal('100.00'), idempotency_key=token)
        self.assertEqual(v1.id, v2.id)
        self.assertEqual(v1.codigo, v2.codigo)

        # 3. Comprobar que el inventario NO se volvió a descontar
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_disponible, 7)

    def test_02_vuelto_no_infla_caja_y_registra_neto(self):
        """Prueba que el vuelto entregado no infle el total cobrado en caja."""
        # Venta total: 100 Bs (1 labial). Cliente paga con billete de $20 (a tasa 10 Bs/$ = 200 Bs)
        items = [{'producto_id': self.producto.id, 'cantidad': 1, 'precio_unitario_bs': Decimal('100.00')}]
        pagos = [{'metodo': 'EFECTIVO_USD', 'monto_original': Decimal('20.00')}]

        venta = registrar_venta_fifo(items, pagos, tasa_usd_bcv=Decimal('10.00'), tasa_usdt=Decimal('10.00'))

        self.assertEqual(venta.total_bs, Decimal('100.00'))
        self.assertEqual(venta.vuelto_total_bs, Decimal('100.00'))

        # Comprobar desglose del pago
        pago = venta.pagos.first()
        self.assertEqual(pago.monto_recibido, Decimal('20.00'))
        self.assertEqual(pago.vuelto_entregado, Decimal('10.00')) # $10 de vuelto
        self.assertEqual(pago.monto_original, Decimal('10.00')) # $10 netos cobrados
        self.assertEqual(pago.monto_equivalente_bs, Decimal('100.00')) # 100 Bs netos a caja (NO 200)

    def test_03_anulacion_de_venta_restaura_stock_exacto(self):
        """Prueba que anular una venta devuelva las unidades exactas a la entrada original."""
        items = [{'producto_id': self.producto.id, 'cantidad': 4, 'precio_unitario_bs': Decimal('100.00')}]
        pagos = [{'metodo': 'EFECTIVO_BS', 'monto_original': Decimal('400.00')}]

        venta = registrar_venta_fifo(items, pagos, Decimal('10.00'), Decimal('10.00'))
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_disponible, 6) # 10 - 4

        # Anular la venta
        anular_venta_fifo(venta.codigo, motivo="Cliente cambió de opinión")
        
        # Comprobar que el inventario regresó a 10 unidades
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_disponible, 10)

        # Comprobar estado de la venta
        venta.refresh_from_db()
        self.assertTrue(venta.anulada)
        self.assertEqual(venta.motivo_anulacion, "Cliente cambió de opinión")
        self.assertIsNotNone(venta.anulada_el)

