import json
from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User

from productos.models import Producto
from inventario.models import EntradaMercancia
from ventas.services import registrar_venta_fifo
from ventas.views import api_ventas
from pagos.models import PagoVenta, Gasto
from pagos.views import api_gastos, api_eliminar_gasto
from reportes.services import obtener_resumen_periodo

class GastosYPuntoDeVentaTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='cajero_test', password='clave123')

    def test_01_venta_con_punto_de_venta_debito(self):
        """
        Verifica que se pueda registrar una venta cobrada con Punto de Venta (tarjeta de débito).
        """
        prod = Producto.objects.create(nombre="Labial Mate Punto", stock_minimo=2)
        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=10,
            cantidad_disponible=10,
            costo_unitario=Decimal('20.00'),
            precio_venta=Decimal('50.00')
        )

        payload = {
            'items': [{'producto_id': prod.id, 'cantidad': 2, 'precio_unitario_bs': 50.00}],
            'pagos': [{'metodo': 'PUNTO_VENTA', 'monto_original': 100.00, 'referencia': 'POS-BANCARIO-9821'}],
            'tasa_usd': 900.00,
            'tasa_usdt': 1000.00,
            'idempotency_key': 'TOKEN-PUNTO-001'
        }

        req = self.factory.post('/api/ventas/', data=json.dumps(payload), content_type='application/json')
        req.user = self.user
        resp = api_ventas(req)
        self.assertEqual(resp.status_code, 200)

        data = json.loads(resp.content.decode('utf-8'))
        self.assertIn('V-', data['codigo'])

        # Verificar en base de datos
        pago = PagoVenta.objects.filter(venta__codigo=data['codigo']).first()
        self.assertIsNotNone(pago)
        self.assertEqual(pago.metodo, 'PUNTO_VENTA')
        self.assertEqual(pago.moneda, 'BS')
        self.assertEqual(pago.monto_original, Decimal('100.00'))
        self.assertEqual(pago.referencia, 'POS-BANCARIO-9821')

    def test_02_registro_gastos_tienda_y_personales(self):
        """
        Verifica el registro de gastos de la tienda y retiros personales del dueño.
        """
        # Gasto de la tienda (Bolsas plásticas en Bs)
        req_t = self.factory.post('/api/gastos/', data=json.dumps({
            'descripcion': 'Bolsas para despacho tienda',
            'categoria': 'TIENDA',
            'moneda': 'BS',
            'monto': 150.00,
            'metodo': 'PAGO_MOVIL'
        }), content_type='application/json')
        req_t.user = self.user
        resp_t = api_gastos(req_t)
        self.assertEqual(resp_t.status_code, 200)

        # Gasto personal / retiro del dueño (en USD efectivo)
        req_p = self.factory.post('/api/gastos/', data=json.dumps({
            'descripcion': 'Almuerzo personal Jevardi',
            'categoria': 'PERSONAL',
            'moneda': 'USD',
            'monto': 10.00,
            'tasa': 900.00,
            'metodo': 'EFECTIVO_USD'
        }), content_type='application/json')
        req_p.user = self.user
        resp_p = api_gastos(req_p)
        self.assertEqual(resp_p.status_code, 200)

        # Listar y verificar totales diferenciados
        req_list = self.factory.get('/api/gastos/')
        req_list.user = self.user
        resp_list = api_gastos(req_list)
        self.assertEqual(resp_list.status_code, 200)

        datos = json.loads(resp_list.content.decode('utf-8'))
        self.assertEqual(datos['total_tienda_bs'], 150.00)
        self.assertEqual(datos['total_personal_bs'], 9000.00) # 10 USD * 900
        self.assertEqual(datos['total_general_bs'], 9150.00)
        self.assertEqual(len(datos['gastos']), 2)

    def test_03_calculo_ganancia_neta_real_con_gastos(self):
        """
        Verifica que el resumen financiero deduzca correctamente los gastos y retiros:
        Ganancia Neta Real = Ganancia Bruta (Ventas - Costos) - Gastos Tienda - Retiros Personales.
        """
        prod = Producto.objects.create(nombre="Perfume Floral", stock_minimo=1)
        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=5,
            cantidad_disponible=5,
            costo_unitario=Decimal('100.00'),
            precio_venta=Decimal('300.00')
        )

        # Vender 1 perfume: Ingreso 300, Costo 100, Ganancia Bruta 200 Bs
        registrar_venta_fifo(
            items_carrito=[{'producto_id': prod.id, 'cantidad': 1, 'precio_unitario_bs': '300.00'}],
            lista_pagos=[{'metodo': 'EFECTIVO_BS', 'monto_original': '300.00'}],
            tasa_usd_bcv=Decimal('900.00'),
            tasa_usdt=Decimal('1000.00')
        )

        # Registrar gasto tienda de 50 Bs y retiro personal de 30 Bs (Total gastos 80 Bs)
        Gasto.objects.create(
            descripcion="Bombillos local",
            categoria="TIENDA",
            monto_original=Decimal('50.00'),
            moneda="BS",
            monto_equivalente_bs=Decimal('50.00'),
            metodo="EFECTIVO_BS"
        )
        Gasto.objects.create(
            descripcion="Café personal",
            categoria="PERSONAL",
            monto_original=Decimal('30.00'),
            moneda="BS",
            monto_equivalente_bs=Decimal('30.00'),
            metodo="EFECTIVO_BS"
        )

        resumen = obtener_resumen_periodo()
        self.assertEqual(resumen['total_ingresos'], Decimal('300.00'))
        self.assertEqual(resumen['total_costos'], Decimal('100.00'))
        self.assertEqual(resumen['total_ganancia'], Decimal('200.00')) # Ganancia Bruta
        self.assertEqual(resumen['total_gastos_tienda'], Decimal('50.00'))
        self.assertEqual(resumen['total_gastos_personal'], Decimal('30.00'))
        self.assertEqual(resumen['resultado_despues_gastos'], Decimal('150.00')) # 200 - 50 = 150 Bs
