from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Venta, DetalleVenta, DesgloseLoteVenta
from inventario.models import EntradaMercancia
from productos.models import Producto
from pagos.models import PagoVenta

@transaction.atomic
def registrar_venta_fifo(items_carrito, lista_pagos, tasa_usd_bcv, tasa_usdt, observaciones="", idempotency_key=None):
    """
    Registra una venta atómica con control de concurrencia (select_for_update),
    deducción automática de inventario mediante FIFO, desglose de vuelto/cambio neto
    y clave de idempotencia contra doble clic / reenvíos duplicados.
    """
    # 0. Control de Idempotencia: Si ya se procesó con esta clave, devolver la venta existente
    if idempotency_key:
        venta_existente = Venta.objects.filter(idempotency_key=idempotency_key).first()
        if venta_existente:
            return venta_existente

    if not items_carrito:
        raise ValidationError("El carrito de venta no puede estar vacío.")

    tasa_usd_bcv = Decimal(str(tasa_usd_bcv))
    tasa_usdt = Decimal(str(tasa_usdt))

    # 1. Crear el encabezado de la venta preliminar
    venta = Venta(
        fecha=timezone.now(),
        tasa_usd_bcv=tasa_usd_bcv,
        tasa_usdt=tasa_usdt,
        idempotency_key=idempotency_key or None,
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
    pagos_preparados = []
    total_recibido_bs = Decimal('0.00')

    for p in lista_pagos:
        monto_ingresado = Decimal(str(p.get('monto_original', 0)))
        if monto_ingresado <= Decimal('0.00'):
            continue

        metodo = p['metodo']
        referencia = p.get('referencia', '').strip()

        if metodo == 'EFECTIVO_USD':
            moneda = 'USD'
            tasa = tasa_usd_bcv
            equiv_bs = (monto_ingresado * tasa).quantize(Decimal('0.01'))
        elif metodo == 'USDT':
            moneda = 'USDT'
            tasa = tasa_usdt
            equiv_bs = (monto_ingresado * tasa).quantize(Decimal('0.01'))
        else: # EFECTIVO_BS o PAGO_MOVIL
            moneda = 'BS'
            tasa = Decimal('1.0000')
            equiv_bs = monto_ingresado

        pagos_preparados.append({
            'metodo': metodo,
            'moneda': moneda,
            'tasa': tasa,
            'monto_recibido': monto_ingresado,
            'equiv_recibido_bs': equiv_bs,
            'monto_neto_orig': monto_ingresado,
            'monto_neto_bs': equiv_bs,
            'vuelto_orig': Decimal('0.00'),
            'vuelto_bs': Decimal('0.00'),
            'referencia': referencia
        })
        total_recibido_bs += equiv_bs

    # Verificar que el pago cubra el total (con tolerancia de 0.5 Bs por redondeos en divisas)
    diferencia = total_venta_bs - total_recibido_bs
    if diferencia > Decimal('0.50'):
        raise ValidationError(
            f"El total pagado (Bs {total_recibido_bs:.2f}) es menor al total de la venta (Bs {total_venta_bs:.2f}). "
            f"Faltan Bs {diferencia:.2f}."
        )

    # Calcular y asignar vuelto/cambio si el cliente pagó de más
    sobrante_por_asignar_bs = max(Decimal('0.00'), total_recibido_bs - total_venta_bs)
    vuelto_total_bs = sobrante_por_asignar_bs

    # Distribuir el vuelto preferentemente en pagos en efectivo
    if sobrante_por_asignar_bs > Decimal('0.00'):
        # Orden de preferencia para descontar vuelto: EFECTIVO_BS, EFECTIVO_USD, USDT, otros
        orden_metodos = ['EFECTIVO_BS', 'EFECTIVO_USD', 'USDT', 'PAGO_MOVIL']
        pagos_ordenados = sorted(
            pagos_preparados,
            key=lambda x: orden_metodos.index(x['metodo']) if x['metodo'] in orden_metodos else 99
        )

        for p_item in pagos_ordenados:
            if sobrante_por_asignar_bs <= Decimal('0.00'):
                break
            descuento_bs = min(p_item['monto_neto_bs'], sobrante_por_asignar_bs)
            p_item['monto_neto_bs'] -= descuento_bs
            p_item['vuelto_bs'] += descuento_bs

            # Convertir vuelto a la moneda original del pago
            if p_item['moneda'] != 'BS' and p_item['tasa'] > 0:
                p_item['vuelto_orig'] = (p_item['vuelto_bs'] / p_item['tasa']).quantize(Decimal('0.01'))
                p_item['monto_neto_orig'] = p_item['monto_recibido'] - p_item['vuelto_orig']
            else:
                p_item['vuelto_orig'] = p_item['vuelto_bs']
                p_item['monto_neto_orig'] = p_item['monto_neto_bs']

            sobrante_por_asignar_bs -= descuento_bs

    # Guardar registros de PagoVenta con auditoría de cobro neto y vuelto entregado
    for p_item in pagos_preparados:
        PagoVenta.objects.create(
            venta=venta,
            metodo=p_item['metodo'],
            moneda=p_item['moneda'],
            monto_original=p_item['monto_neto_orig'],
            monto_recibido=p_item['monto_recibido'],
            vuelto_entregado=p_item['vuelto_orig'],
            vuelto_entregado_bs=p_item['vuelto_bs'],
            tasa_aplicada=p_item['tasa'],
            monto_equivalente_bs=p_item['monto_neto_bs'],
            referencia=p_item['referencia']
        )

    # 4. Actualizar totales finales de la venta
    venta.total_bs = total_venta_bs
    venta.costo_total_bs = costo_total_venta_bs
    venta.ganancia_bruta_bs = total_venta_bs - costo_total_venta_bs
    venta.vuelto_total_bs = vuelto_total_bs
    venta.save(update_fields=['total_bs', 'costo_total_bs', 'ganancia_bruta_bs', 'vuelto_total_bs'])

    return venta


@transaction.atomic
def anular_venta_fifo(identificador, motivo=""):
    """
    Anula una venta y devuelve con precisión matemática cada unidad
    descontada a su entrada/lote original mediante DesgloseLoteVenta.
    """
    try:
        if str(identificador).isdigit():
            venta = Venta.objects.select_for_update().get(id=int(identificador))
        else:
            venta = Venta.objects.select_for_update().get(codigo=str(identificador).strip())
    except Venta.DoesNotExist:
        raise ValidationError(f"No existe ninguna venta con identificador '{identificador}'")

    if venta.anulada:
        raise ValidationError(f"La venta {venta.codigo} ya fue anulada previamente.")

    # Reintegrar existencias a cada lote por el desglose original de la venta
    for detalle in venta.detalles.select_related('producto').all():
        for desglose in detalle.desgloses_lote.select_related('entrada').all():
            entrada = EntradaMercancia.objects.select_for_update().get(id=desglose.entrada_id)
            entrada.cantidad_disponible += desglose.cantidad_descontada
            entrada.save(update_fields=['cantidad_disponible'])

    venta.anulada = True
    venta.motivo_anulacion = motivo or "Anulación de venta y reversión de inventario"
    venta.anulada_el = timezone.now()
    venta.save(update_fields=['anulada', 'motivo_anulacion', 'anulada_el'])

    return venta

