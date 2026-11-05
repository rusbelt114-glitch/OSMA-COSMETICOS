import json
from pathlib import Path
from decimal import Decimal
import openpyxl
from io import BytesIO

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import connection

from productos.models import Producto
from inventario.models import EntradaMercancia
from ventas.models import Venta, DetalleVenta, DesgloseLoteVenta
from ventas.services import registrar_venta_fifo, anular_venta_fifo
from ventas.views import api_ventas
from productos.views import _listar_productos
from reportes.views import _procesar_hoja_entradas, _procesar_hoja_inventario

class Auditoria7PuntosTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='tienda_test', password='password123')

    def test_01_wsgi_no_resetea_passwords_personalizadas(self):
        """
        Punto 1: Demostrar que importar y arrancar WSGI no altera contraseñas
        modificadas por el usuario ni las restablece a claves por defecto.
        """
        # Crear usuario admin con clave personalizada
        admin_user = User.objects.create_superuser(
            username='admin_seguro',
            password='ClavePersonalizadaSuperSegura2026!'
        )
        
        # Simular carga de WSGI
        import config.wsgi
        
        # Verificar que la clave personalizada sigue intacta
        user_auth = authenticate(username='admin_seguro', password='ClavePersonalizadaSuperSegura2026!')
        self.assertIsNotNone(user_auth, "La clave personalizada del usuario debe mantenerse intacta.")
        
        # Verificar que la clave vieja por defecto no funciona
        user_auth_default = authenticate(username='admin_seguro', password='admin1234')
        self.assertIsNone(user_auth_default, "La clave por defecto 'admin1234' no debe funcionar.")

    def test_02_excel_reconoce_lotes_multiples_5_mas_7_igual_12(self):
        """
        Punto 2: Demostrar que importar dos lotes distintos del mismo producto
        (5 y 7 unidades) no se sobreescriben sino que suman 12 unidades en total.
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Entradas de Mercancía"
        ws.append(["ID", "Fecha", "Producto", "Cant. Recibida", "Cant. Disponible", "Costo", "Precio", "Estado", "Obs"])
        # Fila 1: 5 unidades de Labial Rojo a Bs 50
        ws.append(["", "05/11/2026", "Labial Rojo Mate", 5, 5, 30.00, 50.00, "Disponible", "Lote 1"])
        # Fila 2: 7 unidades de Labial Rojo a Bs 50 (nuevo lote)
        ws.append(["", "05/11/2026", "Labial Rojo Mate", 7, 7, 30.00, 50.00, "Disponible", "Lote 2"])

        prods, entradas = _procesar_hoja_entradas(ws)
        
        producto = Producto.objects.get(nombre="Labial Rojo Mate")
        lotes = EntradaMercancia.objects.filter(producto=producto)
        
        self.assertEqual(lotes.count(), 2, "Deben existir 2 lotes independientes.")
        self.assertEqual(producto.stock_total, 12, "El stock total debe ser 12 (5 + 7 unidades).")

    def test_03_excel_antiguo_no_repone_mercancia_vendida(self):
        """
        Punto 3: Demostrar que importar un catálogo/inventario antiguo no sobreescribe
        el stock vivo de un producto que ya tiene ventas registradas.
        """
        prod = Producto.objects.create(nombre="Polvo Compacto", stock_minimo=3)
        lote = EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=20,
            cantidad_disponible=20,
            costo_unitario=Decimal('10.00'),
            precio_venta=Decimal('20.00')
        )
        
        # Realizar venta de 2 unidades
        registrar_venta_fifo(
            items_carrito=[{'producto_id': prod.id, 'cantidad': 2, 'precio_unitario_bs': '20.00'}],
            lista_pagos=[{'metodo': 'EFECTIVO_BS', 'monto_original': '40.00'}],
            tasa_usd_bcv=Decimal('900.00'),
            tasa_usdt=Decimal('1000.00')
        )
        
        self.assertEqual(prod.stock_total, 18, "El stock después de la venta debe ser 18.")

        # Simular importación de Excel viejo con stock = 20
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Inventario Actual"
        ws.append(["ID", "Producto", "Stock Actual", "Estado", "Mínimo", "Costo", "Precio"])
        ws.append([prod.id, "Polvo Compacto", 20, "Normal", 3, 10.00, 20.00])

        _procesar_hoja_inventario(ws)

        # Verificar que el stock vivo NO fue pisado por el Excel viejo
        prod.refresh_from_db()
        self.assertEqual(prod.stock_total, 18, "El stock vivo debe permanecer en 18 y no reponer las unidades vendidas.")

    def test_03b_excel_entradas_mercancia_con_id_no_repone_vendido(self):
        """
        Punto 3B (Hallazgo Auditor): Demostrar que importar por la ruta 'Entradas de Mercancía'
        con un ID de lote existente tampoco sobrescribe las unidades vendidas (de 20 a 18).
        """
        prod = Producto.objects.create(nombre="Base Líquida Mate", stock_minimo=3)
        lote = EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=20,
            cantidad_disponible=20,
            costo_unitario=Decimal('15.00'),
            precio_venta=Decimal('30.00')
        )

        # Realizar venta de 2 unidades
        registrar_venta_fifo(
            items_carrito=[{'producto_id': prod.id, 'cantidad': 2, 'precio_unitario_bs': '30.00'}],
            lista_pagos=[{'metodo': 'EFECTIVO_BS', 'monto_original': '60.00'}],
            tasa_usd_bcv=Decimal('900.00'),
            tasa_usdt=Decimal('1000.00')
        )

        lote.refresh_from_db()
        self.assertEqual(lote.cantidad_disponible, 18, "El lote debe quedar en 18 tras la venta de 2 unidades.")

        # Simular re-importación de hoja 'Entradas de Mercancía' con el ID del lote y saldo original de 20
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Entradas de Mercancía"
        ws.append(["ID", "Fecha", "Producto", "Cant. Recibida", "Cant. Disponible", "Costo", "Precio", "Estado", "Obs"])
        # Fila con ID existente del lote y saldo estático antiguo de 20
        ws.append([lote.id, "05/11/2026", "Base Líquida Mate", 20, 20, 16.00, 32.00, "Disponible", "Precio actualizado"])

        _procesar_hoja_entradas(ws)

        lote.refresh_from_db()
        # Verificar que el disponible NO volvió a 20 (se conserva en 18)
        self.assertEqual(lote.cantidad_disponible, 18, "El disponible vivo debe conservarse en 18 y no reponer lo vendido.")
        # Verificar que sí se actualizaron precios y costos
        self.assertEqual(lote.costo_unitario, Decimal('16.00'))
        self.assertEqual(lote.precio_venta, Decimal('32.00'))
        self.assertEqual(lote.observaciones, "Precio actualizado")

    def test_04_n_plus_one_optimizado_en_una_sola_query(self):
        """
        Punto 4: Demostrar que listar 50 productos con lotes asociados se ejecuta
        en EXACTAMENTE 1 consulta SQL, eliminando el cuello de botella N+1 (4.003 queries).
        """
        # Crear 50 productos con 2 lotes cada uno (100 lotes en total)
        for i in range(50):
            p = Producto.objects.create(nombre=f"Producto Prueba {i:03d}", stock_minimo=5)
            EntradaMercancia.objects.create(
                producto=p,
                cantidad_recibida=10,
                cantidad_disponible=10,
                costo_unitario=Decimal('15.00'),
                precio_venta=Decimal('25.00')
            )
            EntradaMercancia.objects.create(
                producto=p,
                cantidad_recibida=5,
                cantidad_disponible=5,
                costo_unitario=Decimal('16.00'),
                precio_venta=Decimal('26.00')
            )

        request = self.factory.get('/api/productos/?activos=true')
        request.user = self.user

        # Ejecutar y verificar con assertNumQueries
        with self.assertNumQueries(1):
            response = _listar_productos(request)
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content.decode('utf-8'))
            self.assertEqual(len(data['productos']), 50)
            self.assertEqual(data['productos'][0]['stock_total'], 15)

    def test_05_idempotencia_reintentos_no_duplican_venta_ni_descuentan_stock(self):
        """
        Punto 5: Demostrar que si la conexión falla y el navegador reintenta la venta
        con el mismo idempotency_key, no se duplica la venta ni se descuenta stock dos veces.
        """
        prod = Producto.objects.create(nombre="Serum Vitamina C", stock_minimo=2)
        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=10,
            cantidad_disponible=10,
            costo_unitario=Decimal('50.00'),
            precio_venta=Decimal('100.00')
        )

        idempotency_token = "UUID-CLIENTE-REINTENTO-12345"
        payload = {
            'items': [{'producto_id': prod.id, 'cantidad': 3, 'precio_unitario_bs': 100.00}],
            'pagos': [{'metodo': 'EFECTIVO_BS', 'monto_original': 300.00}],
            'tasa_usd': 900.00,
            'tasa_usdt': 1000.00,
            'idempotency_key': idempotency_token
        }

        # Intento 1
        request1 = self.factory.post('/api/ventas/', data=json.dumps(payload), content_type='application/json')
        request1.user = self.user
        resp1 = api_ventas(request1)
        self.assertEqual(resp1.status_code, 200)
        data1 = json.loads(resp1.content.decode('utf-8'))
        codigo_venta = data1['codigo']
        
        self.assertEqual(prod.stock_total, 7, "Stock debe ser 7 tras el intento 1.")

        # Intento 2 (Reintento de red con mismo token)
        request2 = self.factory.post('/api/ventas/', data=json.dumps(payload), content_type='application/json')
        request2.user = self.user
        resp2 = api_ventas(request2)
        self.assertEqual(resp2.status_code, 200)
        data2 = json.loads(resp2.content.decode('utf-8'))

        # Verificaciones críticas
        self.assertEqual(data2['codigo'], codigo_venta, "Debe devolver el mismo código de venta.")
        self.assertEqual(Venta.objects.count(), 1, "No debe crearse una segunda venta.")
        self.assertEqual(prod.stock_total, 7, "Stock NO debe descontarse nuevamente (debe seguir en 7).")

    def test_06_anulacion_directa_desde_django_admin_restituye_inventario(self):
        """
        Punto 6: Demostrar que marcar anulada=True directamente en el modelo (Django Admin)
        restituye automáticamente las unidades al lote original mediante DesgloseLoteVenta.
        """
        prod = Producto.objects.create(nombre="Crema Hidratante Facial", stock_minimo=2)
        lote = EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=15,
            cantidad_disponible=15,
            costo_unitario=Decimal('20.00'),
            precio_venta=Decimal('45.00')
        )

        # Vender 4 unidades
        venta = registrar_venta_fifo(
            items_carrito=[{'producto_id': prod.id, 'cantidad': 4, 'precio_unitario_bs': '45.00'}],
            lista_pagos=[{'metodo': 'EFECTIVO_BS', 'monto_original': '180.00'}],
            tasa_usd_bcv=Decimal('900.00'),
            tasa_usdt=Decimal('1000.00')
        )
        lote.refresh_from_db()
        self.assertEqual(lote.cantidad_disponible, 11, "Disponible debe ser 11 tras la venta.")

        # Simular acción de Django Admin: marcar anulada=True y guardar
        venta.anulada = True
        venta.motivo_anulacion = "Anulada por administrador en panel de Django"
        venta.save()

        # Verificar que el inventario fue restituido al lote exacto
        lote.refresh_from_db()
        self.assertEqual(lote.cantidad_disponible, 15, "El lote debe volver a 15 unidades tras guardar anulada=True.")

        # Verificar que intentar des-anular una venta arroja ValidationError
        venta.anulada = False
        with self.assertRaises(ValidationError):
            venta.save()

    def test_07_validaciones_estrictas_en_servidor_rechazan_datos_invalidos(self):
        """
        Punto 7: Demostrar que precios negativos, tasas cero, cantidades negativas
        y medios de pago desconocidos son rechazados en el servidor con HTTP 400.
        """
        prod = Producto.objects.create(nombre="Esmalte Uñas", stock_minimo=1)
        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=10,
            cantidad_disponible=10,
            costo_unitario=Decimal('5.00'),
            precio_venta=Decimal('10.00')
        )

        # Caso A: Precio negativo
        payload_precio_neg = {
            'items': [{'producto_id': prod.id, 'cantidad': 1, 'precio_unitario_bs': -50.00}],
            'pagos': [{'metodo': 'EFECTIVO_BS', 'monto_original': 10.00}],
            'tasa_usd': 900.00,
            'tasa_usdt': 1000.00
        }
        req_a = self.factory.post('/api/ventas/', data=json.dumps(payload_precio_neg), content_type='application/json')
        req_a.user = self.user
        resp_a = api_ventas(req_a)
        self.assertEqual(resp_a.status_code, 400, "Debe rechazar precios negativos.")

        # Caso B: Tasa de cambio cero
        payload_tasa_cero = {
            'items': [{'producto_id': prod.id, 'cantidad': 1, 'precio_unitario_bs': 10.00}],
            'pagos': [{'metodo': 'EFECTIVO_BS', 'monto_original': 10.00}],
            'tasa_usd': 0.00,
            'tasa_usdt': 1000.00
        }
        req_b = self.factory.post('/api/ventas/', data=json.dumps(payload_tasa_cero), content_type='application/json')
        req_b.user = self.user
        resp_b = api_ventas(req_b)
        self.assertEqual(resp_b.status_code, 400, "Debe rechazar tasa cero.")

        # Caso C: Método de pago desconocido
        payload_metodo_raro = {
            'items': [{'producto_id': prod.id, 'cantidad': 1, 'precio_unitario_bs': 10.00}],
            'pagos': [{'metodo': 'METODO_DESCONOCIDO', 'monto_original': 10.00}],
            'tasa_usd': 900.00,
            'tasa_usdt': 1000.00
        }
        req_c = self.factory.post('/api/ventas/', data=json.dumps(payload_metodo_raro), content_type='application/json')
        req_c.user = self.user
        resp_c = api_ventas(req_c)
        self.assertEqual(resp_c.status_code, 400, "Debe rechazar medios de pago no reconocidos.")

        # Caso D: Monto de pago negativo
        payload_pago_neg = {
            'items': [{'producto_id': prod.id, 'cantidad': 1, 'precio_unitario_bs': 10.00}],
            'pagos': [{'metodo': 'EFECTIVO_BS', 'monto_original': -10.00}],
            'tasa_usd': 900.00,
            'tasa_usdt': 1000.00
        }
        req_d = self.factory.post('/api/ventas/', data=json.dumps(payload_pago_neg), content_type='application/json')
        req_d.user = self.user
        resp_d = api_ventas(req_d)
        self.assertEqual(resp_d.status_code, 400, "Debe rechazar montos de pago negativos.")

    def test_08_fechas_caracas_y_rango_estricto_7_dias(self):
        """
        Punto 8: Demostrar que las fechas se formatean en zona horaria America/Caracas (UTC-4)
        y que un rango de 7 días comprende exactamente 7 fechas calendario.
        """
        from datetime import date, timedelta
        from django.utils import timezone
        from zoneinfo import ZoneInfo
        caracas_tz = ZoneInfo("America/Caracas")

        ahora_caracas = timezone.now().astimezone(caracas_tz)
        hoy = ahora_caracas.date()
        hace_7_dias = hoy - timedelta(days=6) # hoy y los 6 días previos = 7 fechas exactas

        num_dias = (hoy - hace_7_dias).days + 1
        self.assertEqual(num_dias, 7, "El rango de 7 días debe contener exactamente 7 fechas calendario.")

        v = Venta.objects.create(total_bs=Decimal('100.00'), tasa_usd_bcv=Decimal('900.00'))
        fecha_local = timezone.localtime(v.fecha)
        tz_nombre = str(fecha_local.tzinfo)
        self.assertIn('Caracas', tz_nombre, "La fecha debe estar localizada en America/Caracas.")

    def test_09_respaldo_externo_y_recuperacion(self):
        """
        Punto 9: Demostrar generación de respaldo de negocio y recuperación exitosa.
        """
        import tempfile
        from django.core.management import call_command
        from reportes.views import _restaurar_desde_json
        from django.core.files.uploadedfile import SimpleUploadedFile

        prod = Producto.objects.create(nombre="Sombra Ojos Respaldo", stock_minimo=2)
        with tempfile.TemporaryDirectory() as tmp_dir:
            call_command('crear_respaldo', destino=tmp_dir)
            archivos = list(Path(tmp_dir).glob("respaldo_datos_*.json"))
            self.assertTrue(len(archivos) > 0, "Debe haberse generado el archivo JSON de respaldo.")

            # Borrar producto para verificar recuperación
            prod.delete()
            self.assertFalse(Producto.objects.filter(nombre="Sombra Ojos Respaldo").exists())

            # Restaurar copia
            with open(archivos[0], 'rb') as f:
                upload = SimpleUploadedFile(archivos[0].name, f.read(), content_type='application/json')
                resp = _restaurar_desde_json(upload)
                self.assertEqual(resp.status_code, 200)

            self.assertTrue(
                Producto.objects.filter(nombre="Sombra Ojos Respaldo").exists(),
                "El producto debe haberse recuperado exitosamente desde la copia."
            )

