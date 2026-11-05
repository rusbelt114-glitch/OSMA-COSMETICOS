from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from productos.models import Producto, normalizar_texto
from inventario.models import EntradaMercancia
from ventas.models import Venta, DetalleVenta
from ventas.services import registrar_venta_fifo
from reportes.services import generar_excel_completo, obtener_resumen_periodo

class OsmaSistemaTestCase(TestCase):
    def setUp(self):
        # Crear usuario de tienda
        self.user = User.objects.create_user(username='tienda', password='password123')
        self.client = Client()
        self.client.login(username='tienda', password='password123')

    def test_normalizacion_busqueda(self):
        """Verifica que la búsqueda ignore mayúsculas, minúsculas y tildes."""
        self.assertEqual(normalizar_texto("Labial Rojo Pasión"), "labial rojo pasion")
        self.assertEqual(normalizar_texto("CORRECTOR TONO 01"), "corrector tono 01")

        p = Producto.objects.create(nombre="Corrector Café · Tono 02", stock_minimo=4)
        self.assertEqual(p.nombre_busqueda, "corrector cafe · tono 02")

    def test_flujo_fifo_y_ganancia_bruta_exacta(self):
        """
        Prueba crítica:
        - Lote 1: 10 unidades compradas a Bs 20 cada una (costo = 200).
        - Lote 2: 10 unidades compradas a Bs 30 cada una (costo = 300).
        - Venta de 15 unidades a Bs 50 cada una (total ingreso = 750).
        
        Resultado esperado por FIFO:
        - Descuenta 10 uds del Lote 1 (costo: 10 * 20 = 200).
        - Descuenta 5 uds del Lote 2 (costo: 5 * 30 = 150).
        - Costo total de mercancía vendida = 350 Bs.
        - Ganancia bruta = 750 - 350 = 400 Bs.
        - En inventario deben quedar 5 unidades (del Lote 2 a Bs 30).
        """
        prod = Producto.objects.create(nombre="Polvo Compacto 01")

        # Entrada 1
        e1 = EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=10,
            costo_unitario=Decimal('20.00'),
            precio_venta=Decimal('50.00')
        )

        # Entrada 2
        e2 = EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=10,
            costo_unitario=Decimal('30.00'),
            precio_venta=Decimal('50.00')
        )

        self.assertEqual(prod.stock_total, 20)

        # Registrar venta por servicio FIFO
        items = [{
            'producto_id': prod.id,
            'cantidad': 15,
            'precio_unitario_bs': Decimal('50.00')
        }]
        pagos = [{
            'metodo': 'EFECTIVO_USD',
            'monto_original': Decimal('15.00'), # 15 USD a tasa 50 = 750 Bs
        }]

        venta = registrar_venta_fifo(
            items_carrito=items,
            lista_pagos=pagos,
            tasa_usd_bcv=Decimal('50.0000'),
            tasa_usdt=Decimal('50.0000'),
            observaciones="Prueba FIFO"
        )

        self.assertEqual(venta.total_bs, Decimal('750.00'))
        self.assertEqual(venta.costo_total_bs, Decimal('350.00'))
        self.assertEqual(venta.ganancia_bruta_bs, Decimal('400.00'))

        # Verificar inventario restante
        e1.refresh_from_db()
        e2.refresh_from_db()
        self.assertEqual(e1.cantidad_disponible, 0)
        self.assertEqual(e2.cantidad_disponible, 5)
        self.assertEqual(prod.stock_total, 5)

    def test_pago_mixto_multimoneda(self):
        """Verifica combinación de Bolívares y Dólares a tasa congelada."""
        prod = Producto.objects.create(nombre="Mascara de Pestañas")
        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=5,
            costo_unitario=Decimal('50.00'),
            precio_venta=Decimal('100.00')
        )

        # Venta total 200 Bs
        # Pago: 50 Bs en Pago Móvil + 1.5 USD a tasa 100 (= 150 Bs) -> Total 200 Bs
        items = [{'producto_id': prod.id, 'cantidad': 2, 'precio_unitario_bs': Decimal('100.00')}]
        pagos = [
            {'metodo': 'PAGO_MOVIL', 'monto_original': Decimal('50.00')},
            {'metodo': 'EFECTIVO_USD', 'monto_original': Decimal('1.50')}
        ]

        venta = registrar_venta_fifo(
            items_carrito=items,
            lista_pagos=pagos,
            tasa_usd_bcv=Decimal('100.0000'),
            tasa_usdt=Decimal('100.0000')
        )
        self.assertEqual(venta.total_bs, Decimal('200.00'))
        self.assertEqual(venta.pagos.count(), 2)

    def test_generacion_excel_reporte(self):
        """Verifica que el generador de Excel produzca un archivo válido con 4 hojas."""
        wb = generar_excel_completo()
        self.assertEqual(len(wb.sheetnames), 4)
        self.assertIn("Inventario Actual", wb.sheetnames)
        self.assertIn("Entradas de Mercancía", wb.sheetnames)
        self.assertIn("Ventas y Ganancia", wb.sheetnames)
        self.assertIn("Detalle de Pagos", wb.sheetnames)

    def test_vistas_requieren_login(self):
        """Verifica que el sistema esté protegido y redirija al login si no hay sesión."""
        anon_client = Client()
        res = anon_client.get('/')
        self.assertEqual(res.status_code, 302)
        self.assertTrue('/login/' in res.url)

        res_login = self.client.get('/')
        self.assertEqual(res_login.status_code, 200)

    def test_restauracion_desde_excel(self):
        """Verifica que se pueda restaurar inventario y productos directamente subiendo un Excel."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        import openpyxl
        from io import BytesIO

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Entradas de Mercancía"
        ws.append(["ID", "Fecha", "Producto", "Cant. Recibida", "Cant. Disponible", "Costo Unit. (Bs)", "Precio Venta (Bs)", "Costo Total (Bs)", "Observaciones"])
        ws.append([1, "04/11/2026", "GLOSS LABIAL BRILLANTE", 25, 25, 150.0, 300.0, 3750.0, "Copia de prueba"])

        excel_io = BytesIO()
        wb.save(excel_io)
        excel_io.seek(0)

        uploaded_excel = SimpleUploadedFile(
            "Osma-Reporte-Prueba.xlsx",
            excel_io.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        res = self.client.post('/api/reportes/restaurar/', {'archivo': uploaded_excel})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get('exito'))

        p = Producto.objects.get(nombre="GLOSS LABIAL BRILLANTE")
        self.assertEqual(p.stock_total, 25)
        self.assertEqual(p.ultimo_precio_venta, Decimal('300.00'))

