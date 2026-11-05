from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Venta, DetalleVenta, DesgloseLoteVenta
from inventario.models import EntradaMercancia
from productos.models import Producto
from pagos.models import PagoVenta

@transaction.atomic
def registrar_venta_fifo(items_carrito, lista_pagos, tasa_usd_bcv, tasa_usdt, observaciones=""):
    """
    Registra una venta atómica con control de concurrencia (select_for_update)
    y deducción automática de inventario mediante FIFO (Primeras Entradas, Primeras Salidas).

    items_carrito: lista de dicts:
        [{'producto_id': 1, 'cantidad': 2, 'precio_unitario_bs': Decimal('150.00')}]
    
    lista_pagos: lista de dicts:
        [{'metodo': 'EFECTIVO_USD', 'monto_original': Decimal('5.00'), 'moneda': 'USD', 'referencia': ''}]
    """
    if not items_carrito:
        raise ValidationError("El carrito de venta no puede estar vacío.")

    tasa_usd_bcv = Decimal(str(tasa_usd_bcv))
    tasa_usdt = Decimal(str(tasa_usdt))

    # 1. Crear el encabezado de la venta preliminar
    venta = Venta(
        fecha=timezone.now(),
        tasa_usd_bcv=tasa_usd_bcv,
        tasa_usdt=tasa_usdt,
        observaciones=observaciones
    )
    venta.save()

    total_venta_bs = Decimal('0.00')
    costo_total_venta_bs = Decimal('0.00')

    # 2. Procesar cada artículo del carrito
    for item in items_carrito:
        producto_id = item.get('producto_id')
        lote_id = item.get('lote_id')
        cantidad_solicitada = int(item['cantidad'])
        precio_unitario = Decimal(str(item['precio_unitario_bs']))

        if cantidad_solicitada <= 0:
            raise ValidationError(f"Cantidad inválida para el producto ID {producto_id}")

        # Si se seleccionó un lote específico
        if lote_id:
            entrada = EntradaMercancia.objects.select_for_update().select_related('producto').get(id=lote_id)
            producto = entrada.producto

            if entrada.cantidad_disponible < cantidad_solicitada:
                raise ValidationError(
                    f"Stock insuficiente para '{producto.nombre}' en esta entrada. "
                    f"Disponible: {entrada.cantidad_disponible}, solicitado: {cantidad_solicitada}."
                )

            subtotal_item_bs = precio_unitario * cantidad_solicitada
            total_venta_bs += subtotal_item_bs

            costo_linea_bs = cantidad_solicitada * entrada.costo_unitario
            costo_total_venta_bs += costo_linea_bs

            entrada.cantidad_disponible -= cantidad_solicitada
            entrada.save(update_fields=['cantidad_disponible'])

            detalle = DetalleVenta.objects.create(
                venta=venta,
                producto=producto,
                cantidad=cantidad_solicitada,
                precio_unitario_bs=precio_unitario,
                subtotal_bs=subtotal_item_bs,
                costo_total_bs=costo_linea_bs,
                ganancia_bruta_bs=subtotal_item_bs - costo_linea_bs
            )

            DesgloseLoteVenta.objects.create(
                detalle_venta=detalle,
                entrada=entrada,
                cantidad_descontada=cantidad_solicitada,
                costo_unitario_aplicado=entrada.costo_unitario
            )

        else:
            # Descuento automático por FIFO
            producto = Producto.objects.select_for_update().get(id=producto_id)
            entradas_disponibles = list(
                EntradaMercancia.objects.select_for_update()
                .filter(producto=producto, cantidad_disponible__gt=0)
                .order_by('fecha_entrada', 'id')
            )

            stock_disponible_total = sum(e.cantidad_disponible for e in entradas_disponibles)
            if stock_disponible_total < cantidad_solicitada:
                raise ValidationError(
                    f"Stock insuficiente para '{producto.nombre}'. "
                    f"Disponible: {stock_disponible_total}, solicitado: {cantidad_solicitada}."
                )

            subtotal_item_bs = precio_unitario * cantidad_solicitada
            total_venta_bs += subtotal_item_bs

            detalle = DetalleVenta.objects.create(
                venta=venta,
                producto=producto,
                cantidad=cantidad_solicitada,
                precio_unitario_bs=precio_unitario,
                subtotal_bs=subtotal_item_bs,
                costo_total_bs=Decimal('0.00'),
                ganancia_bruta_bs=Decimal('0.00')
            )

            unidades_por_descontar = cantidad_solicitada
            costo_linea_bs = Decimal('0.00')

            for entrada in entradas_disponibles:
                if unidades_por_descontar <= 0:
                    break

                descontar = min(entrada.cantidad_disponible, unidades_por_descontar)
                entrada.cantidad_disponible -= descontar
                entrada.save(update_fields=['cantidad_disponible'])

                costo_desglose = descontar * entrada.costo_unitario
                costo_linea_bs += costo_desglose

                DesgloseLoteVenta.objects.create(
                    detalle_venta=detalle,
                    entrada=entrada,
                    cantidad_descontada=descontar,
                    costo_unitario_aplicado=entrada.costo_unitario
                )

                unidades_por_descontar -= descontar

            costo_total_venta_bs += costo_linea_bs
            detalle.costo_total_bs = costo_linea_bs
            detalle.ganancia_bruta_bs = subtotal_item_bs - costo_linea_bs
            detalle.save(update_fields=['costo_total_bs', 'ganancia_bruta_bs'])

    # 3. Procesar y verificar pagos
    total_pagado_bs = Decimal('0.00')

    for p in lista_pagos:
        monto_orig = Decimal(str(p.get('monto_original', 0)))
        if monto_orig <= Decimal('0.00'):
            continue

        metodo = p['metodo']
        referencia = p.get('referencia', '').strip()

        # Determinar moneda y tasa correspondiente
        if metodo == 'EFECTIVO_USD':
            moneda = 'USD'
            tasa = tasa_usd_bcv
            equiv_bs = monto_orig * tasa
        elif metodo == 'USDT':
            moneda = 'USDT'
            tasa = tasa_usdt
            equiv_bs = monto_orig * tasa
        else: # EFECTIVO_BS o PAGO_MOVIL
            moneda = 'BS'
            tasa = Decimal('1.0000')
            equiv_bs = monto_orig

        PagoVenta.objects.create(
            venta=venta,
            metodo=metodo,
            moneda=moneda,
            monto_original=monto_orig,
            tasa_aplicada=tasa,
            monto_equivalente_bs=equiv_bs,
            referencia=referencia
        )

        total_pagado_bs += equiv_bs

    # Verificar que el pago cubra el total (con tolerancia de 0.5 Bs por redondeos en divisas)
    diferencia = total_venta_bs - total_pagado_bs
    if diferencia > Decimal('0.50'):
        raise ValidationError(
            f"El total pagado (Bs {total_pagado_bs:.2f}) es menor al total de la venta (Bs {total_venta_bs:.2f}). "
            f"Faltan Bs {diferencia:.2f}."
        )

    # 4. Actualizar totales finales de la venta
    venta.total_bs = total_venta_bs
    venta.costo_total_bs = costo_total_venta_bs
    venta.ganancia_bruta_bs = total_venta_bs - costo_total_venta_bs
    venta.save(update_fields=['total_bs', 'costo_total_bs', 'ganancia_bruta_bs'])

    return venta

