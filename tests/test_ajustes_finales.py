from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

from productos.models import Producto
from inventario.models import EntradaMercancia
from ventas.models import Venta
from ventas.services import registrar_venta_fifo, anular_venta_fifo
from pagos.models import PagoVenta, Gasto
from reportes.services import obtener_resumen_periodo, generar_excel_completo

class TestAjustesFinalesOsma(TestCase):
    """
    Suite de verificación integral para los Ajustes Finales de Osma Cosmetics:
    - Cobro mixto con tasas ficticias controladas (BCV 900,00 Bs/$, USDT 1.050,00 Bs/USDT).
    - Vuelto real solo en efectivo y rechazo en medios electrónicos.
    - Separación estricta de gastos operativos vs retiros personales.
    - Inversión en existencias y venta potencial.
    - Protección de anulación de entradas con ventas asociadas.
    - Idempotencia en ventas y gastos.
    - Exportación a Excel con 5 pestañas.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='tienda_test', password='password123')
        self.client = Client()
        self.client.login(username='tienda_test', password='password123')

        # Tasas controladas identificadas expresamente como FICTICIAS para los tests
        self.tasa_usd_ficticia = Decimal('900.0000')
        self.tasa_usdt_ficticia = Decimal('1050.0000')

    def test_01_venta_unicamente_en_bolivares(self):
        """Venta de 2 unidades pagadas 100% en efectivo y punto de venta en Bs."""
        prod = Producto.objects.create(nombre="Polvo Traslúcido Mate 10g", stock_minimo=2)
        entrada = EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=10,
            cantidad_disponible=10,
            costo_unitario=Decimal('100.00'),
            precio_venta=Decimal('250.00')
        )

        items = [{'producto_id': prod.id, 'cantidad': 2, 'precio_unitario_bs': 250.00}]
        pagos = [
            {'metodo': 'EFECTIVO_BS', 'monto_original': 200.00},
            {'metodo': 'PUNTO_VENTA', 'monto_original': 300.00}
        ]

        venta = registrar_venta_fifo(
            items_carrito=items,
            lista_pagos=pagos,
            tasa_usd_bcv=self.tasa_usd_ficticia,
            tasa_usdt=self.tasa_usdt_ficticia
        )

        self.assertEqual(venta.total_bs, Decimal('500.00'))
        self.assertEqual(venta.costo_total_bs, Decimal('200.00'))
        self.assertEqual(venta.ganancia_bruta_bs, Decimal('300.00'))
        self.assertEqual(venta.vuelto_total_bs, Decimal('0.00'))

        entrada.refresh_from_db()
        self.assertEqual(entrada.cantidad_disponible, 8)

    def test_02_pago_mixto_bolivares_y_dolares_bcv_con_saldo_dual(self):
        """
        Venta con pago mixto: Pago Móvil + Dólares en efectivo.
        Verifica conversión estricta a tasa BCV y que no use tasa USDT.
        """
        prod = Producto.objects.create(nombre="Labial Cremoso Tono 04", stock_minimo=3)
        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=5,
            cantidad_disponible=5,
            costo_unitario=Decimal('50.00'),
            precio_venta=Decimal('1800.00')
        )

        # Total venta: 1.800 Bs. Pagado: 900 Bs Pago Móvil + 1 USD (a tasa BCV 900 = 900 Bs)
        items = [{'producto_id': prod.id, 'cantidad': 1, 'precio_unitario_bs': 1800.00}]
        pagos = [
            {'metodo': 'PAGO_MOVIL', 'monto_original': 900.00},
            {'metodo': 'EFECTIVO_USD', 'monto_original': 1.00}
        ]

        venta = registrar_venta_fifo(
            items_carrito=items,
            lista_pagos=pagos,
            tasa_usd_bcv=self.tasa_usd_ficticia,
            tasa_usdt=self.tasa_usdt_ficticia
        )

        pago_usd = venta.pagos.get(metodo='EFECTIVO_USD')
        self.assertEqual(pago_usd.tasa_aplicada, self.tasa_usd_ficticia)
        self.assertEqual(pago_usd.monto_equivalente_bs, Decimal('900.00'))
        self.assertEqual(venta.total_bs, Decimal('1800.00'))

    def test_03_pago_usdt_con_tasa_propia_independiente(self):
        """El pago con USDT debe liquidarse exclusivamente con tasa USDT, separada de USD BCV."""
        prod = Producto.objects.create(nombre="Sombra Ojos Paleta Neon", stock_minimo=1)
        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=5,
            cantidad_disponible=5,
            costo_unitario=Decimal('200.00'),
            precio_venta=Decimal('2100.00')
        )

        items = [{'producto_id': prod.id, 'cantidad': 1, 'precio_unitario_bs': 2100.00}]
        pagos = [{'metodo': 'USDT', 'monto_original': 2.00}] # 2 * 1050 = 2100 Bs

        venta = registrar_venta_fifo(
            items_carrito=items,
            lista_pagos=pagos,
            tasa_usd_bcv=self.tasa_usd_ficticia,
            tasa_usdt=self.tasa_usdt_ficticia
        )

        pago_usdt = venta.pagos.get(metodo='USDT')
        self.assertEqual(pago_usdt.tasa_aplicada, self.tasa_usdt_ficticia)
        self.assertEqual(pago_usdt.monto_equivalente_bs, Decimal('2100.00'))

    def test_04_vuelto_en_efectivo_y_rechazo_en_medios_electronicos(self):
        """
        Sobrepago en efectivo genera vuelto real.
        Sobrepago sin efectivo (ej. solo por Punto de Venta) debe ser rechazado.
        """
        prod = Producto.objects.create(nombre="Delineador Negro Plumon", stock_minimo=2)
        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=5,
            cantidad_disponible=5,
            costo_unitario=Decimal('40.00'),
            precio_venta=Decimal('100.00')
        )

        # Caso A: Pago en efectivo de Bs 150 para cuenta de 100 -> Vuelto Bs 50
        items = [{'producto_id': prod.id, 'cantidad': 1, 'precio_unitario_bs': 100.00}]
        pagos_efectivo = [{'metodo': 'EFECTIVO_BS', 'monto_original': 150.00}]

        venta = registrar_venta_fifo(
            items_carrito=items,
            lista_pagos=pagos_efectivo,
            tasa_usd_bcv=self.tasa_usd_ficticia,
            tasa_usdt=self.tasa_usdt_ficticia
        )
        self.assertEqual(venta.vuelto_total_bs, Decimal('50.00'))
        pago = venta.pagos.first()
        self.assertEqual(pago.monto_recibido, Decimal('150.00'))
        self.assertEqual(pago.vuelto_entregado, Decimal('50.00'))
        self.assertEqual(pago.monto_original, Decimal('100.00'))

        # Caso B: Pago en Punto de Venta con sobrepago -> Debe arrojar ValidationError
        pagos_punto_excedente = [{'metodo': 'PUNTO_VENTA', 'monto_original': 150.00}]
        with self.assertRaises(ValidationError):
            registrar_venta_fifo(
                items_carrito=items,
                lista_pagos=pagos_punto_excedente,
                tasa_usd_bcv=self.tasa_usd_ficticia,
                tasa_usdt=self.tasa_usdt_ficticia
            )

    def test_05_idempotencia_en_ventas_y_gastos(self):
        """Reintentos con la misma clave no duplican registros en BD."""
        prod = Producto.objects.create(nombre="Mascara Pestanas Waterproof", stock_minimo=2)
        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=10,
            cantidad_disponible=10,
            costo_unitario=Decimal('50.00'),
            precio_venta=Decimal('120.00')
        )

        key_venta = "IDEM-TEST-VENTA-001"
        items = [{'producto_id': prod.id, 'cantidad': 1, 'precio_unitario_bs': 120.00}]
        pagos = [{'metodo': 'EFECTIVO_BS', 'monto_original': 120.00}]

        v1 = registrar_venta_fifo(items, pagos, self.tasa_usd_ficticia, self.tasa_usdt_ficticia, idempotency_key=key_venta)
        v2 = registrar_venta_fifo(items, pagos, self.tasa_usd_ficticia, self.tasa_usdt_ficticia, idempotency_key=key_venta)
        self.assertEqual(v1.id, v2.id)
        self.assertEqual(Venta.objects.filter(idempotency_key=key_venta).count(), 1)

        # Idempotencia en gastos
        key_gasto = "IDEM-TEST-GASTO-001"
        res1 = self.client.post('/api/gastos/', data={
            'descripcion': 'Bolsas Kraft Medianas',
            'categoria': 'TIENDA',
            'monto': 50.00,
            'moneda': 'BS',
            'idempotency_key': key_gasto
        }, content_type='application/json')
        self.assertEqual(res1.status_code, 200)

        res2 = self.client.post('/api/gastos/', data={
            'descripcion': 'Bolsas Kraft Medianas',
            'categoria': 'TIENDA',
            'monto': 50.00,
            'moneda': 'BS',
            'idempotency_key': key_gasto
        }, content_type='application/json')
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(Gasto.objects.filter(idempotency_key=key_gasto).count(), 1)

    def test_06_separacion_contable_gastos_tienda_vs_retiros_personales(self):
        """
        Los retiros personales NO deben restar de la ganancia operativa del negocio.
        Ganancia bruta = 500
        Gastos operativos tienda = 100
        Resultado después de gastos operativos = 400
        Retiros personales = 200 (reportados aparte)
        """
        prod = Producto.objects.create(nombre="Agua Micelar Desmaquillante 200ml", stock_minimo=2)
        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=10,
            cantidad_disponible=10,
            costo_unitario=Decimal('50.00'),
            precio_venta=Decimal('100.00')
        )

        items = [{'producto_id': prod.id, 'cantidad': 10, 'precio_unitario_bs': 100.00}] # Venta 1000, costo 500, ganancia 500
        pagos = [{'metodo': 'EFECTIVO_BS', 'monto_original': 1000.00}]
        registrar_venta_fifo(items, pagos, self.tasa_usd_ficticia, self.tasa_usdt_ficticia)

        # Registrar gasto operativo de tienda
        Gasto.objects.create(
            descripcion="Pago de luz comercial",
            categoria="TIENDA",
            monto_original=Decimal('100.00'),
            moneda="BS",
            monto_equivalente_bs=Decimal('100.00')
        )

        # Registrar retiro personal del dueño
        Gasto.objects.create(
            descripcion="Retiro para gastos personales",
            categoria="PERSONAL",
            monto_original=Decimal('200.00'),
            moneda="BS",
            monto_equivalente_bs=Decimal('200.00')
        )

        resumen = obtener_resumen_periodo()
        self.assertEqual(resumen['total_ganancia'], Decimal('500.00')) # Ganancia bruta
        self.assertEqual(resumen['total_gastos_tienda'], Decimal('100.00'))
        self.assertEqual(resumen['total_gastos_personal'], Decimal('200.00'))
        self.assertEqual(resumen['resultado_despues_gastos'], Decimal('400.00')) # 500 - 100 = 400

    def test_07_inversion_existencias_y_venta_potencial_inventario(self):
        """El resumen debe calcular inversión en existencias y venta potencial del inventario actual."""
        prod1 = Producto.objects.create(nombre="Serum Vitamina C 30ml", stock_minimo=1)
        EntradaMercancia.objects.create(
            producto=prod1,
            cantidad_recibida=5,
            cantidad_disponible=5,
            costo_unitario=Decimal('60.00'),
            precio_venta=Decimal('150.00')
        )
        # Inversión = 5 * 60 = 300 Bs. Venta potencial = 5 * 150 = 750 Bs.

        resumen = obtener_resumen_periodo()
        inv = resumen['inventario_actual']
        self.assertEqual(inv['unidades_disponibles'], 5)
        self.assertEqual(inv['inversion_existencias'], Decimal('300.00'))
        self.assertEqual(inv['venta_potencial'], Decimal('750.00'))

    def test_08_bloqueo_anulacion_entrada_con_unidades_vendidas(self):
        """Si una entrada tiene unidades ya vendidas, la anulación directa debe ser bloqueada."""
        prod = Producto.objects.create(nombre="Corrector Liquido Tono 02", stock_minimo=2)
        entrada = EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=10,
            cantidad_disponible=10,
            costo_unitario=Decimal('30.00'),
            precio_venta=Decimal('70.00')
        )

        # Vender 3 unidades
        items = [{'producto_id': prod.id, 'lote_id': entrada.id, 'cantidad': 3, 'precio_unitario_bs': 70.00}]
        pagos = [{'metodo': 'EFECTIVO_BS', 'monto_original': 210.00}]
        registrar_venta_fifo(items, pagos, self.tasa_usd_ficticia, self.tasa_usdt_ficticia)

        # Intentar anular la entrada vía API
        res = self.client.post(f'/api/entradas/{entrada.id}/eliminar/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('ya tiene ventas asociadas', res.json()['error'])

    def test_09_advertencia_coincidencia_nombres_catalogo(self):
        """Si se crea un producto con nombre similar sin mayúsculas/acentos, advierte sin fusionar."""
        Producto.objects.create(nombre="Polvo Iluminador Dorado", stock_minimo=2)

        # Intentar registrar uno idéntico fonéticamente / sin acentos
        payload = {
            'nombre': 'polvo iluminador dorado',
            'cantidad': 5,
            'costo_unitario': 40.00,
            'precio_venta': 90.00,
            'confirmar_coincidencia': False
        }
        res = self.client.post('/api/productos/', data=payload, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('advertencia_coincidencia'))

    def test_10_generacion_excel_5_pestanas_completas(self):
        """El Excel generado debe contener 5 pestañas exactas con sus encabezados auditables."""
        wb = generar_excel_completo()
        self.assertEqual(len(wb.sheetnames), 5)
        self.assertIn("Inventario Actual", wb.sheetnames)
        self.assertIn("Entradas de Mercancía", wb.sheetnames)
        self.assertIn("Ventas y Ganancia", wb.sheetnames)
        self.assertIn("Cobros y Pagos", wb.sheetnames)
        self.assertIn("Gastos y Retiros", wb.sheetnames)

