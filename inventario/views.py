import json
import math
from decimal import Decimal
from datetime import datetime, time
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F
from django.utils import timezone
import zoneinfo

from productos.models import Producto, normalizar_texto
from .models import EntradaMercancia
from tasas.models import HistorialTasa

CARACAS_TZ = zoneinfo.ZoneInfo("America/Caracas")

def _parse_fecha_caracas(fecha_str, fin_del_dia=False):
    if not fecha_str:
        return None
    try:
        dt_naive = datetime.strptime(fecha_str.strip(), "%Y-%m-%d")
        t = time.max if fin_del_dia else time.min
        dt_aware = datetime.combine(dt_naive.date(), t, tzinfo=CARACAS_TZ)
        return dt_aware
    except (ValueError, TypeError):
        return None

def _aplicar_filtros_entradas(qs, request):
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(producto__nombre_busqueda__icontains=normalizar_texto(q))

    filtro_fecha = request.GET.get('filtro_fecha', '').strip()
    if not filtro_fecha or filtro_fecha == 'all':
        return qs

    ahora_caracas = timezone.now().astimezone(CARACAS_TZ)
    if filtro_fecha == 'hoy':
        inicio = datetime.combine(ahora_caracas.date(), time.min, tzinfo=CARACAS_TZ)
        fin = datetime.combine(ahora_caracas.date(), time.max, tzinfo=CARACAS_TZ)
        return qs.filter(fecha_entrada__gte=inicio, fecha_entrada__lte=fin)

    if filtro_fecha == 'dia':
        f_str = request.GET.get('fecha')
        inicio = _parse_fecha_caracas(f_str, fin_del_dia=False)
        fin = _parse_fecha_caracas(f_str, fin_del_dia=True)
        if inicio and fin:
            return qs.filter(fecha_entrada__gte=inicio, fecha_entrada__lte=fin)

    if filtro_fecha == 'mes':
        mes_str = request.GET.get('mes')
        if mes_str and '-' in mes_str:
            try:
                y, m = map(int, mes_str.split('-'))
                import calendar
                ultimo_dia = calendar.monthrange(y, m)[1]
                inicio = datetime(y, m, 1, 0, 0, 0, tzinfo=CARACAS_TZ)
                fin = datetime(y, m, ultimo_dia, 23, 59, 59, tzinfo=CARACAS_TZ)
                return qs.filter(fecha_entrada__gte=inicio, fecha_entrada__lte=fin)
            except Exception:
                pass

    if filtro_fecha == 'rango':
        desde_dt = _parse_fecha_caracas(request.GET.get('desde'), fin_del_dia=False)
        hasta_dt = _parse_fecha_caracas(request.GET.get('hasta'), fin_del_dia=True)
        if desde_dt:
            qs = qs.filter(fecha_entrada__gte=desde_dt)
        if hasta_dt:
            qs = qs.filter(fecha_entrada__lte=hasta_dt)

    return qs


def _serializar_entrada(e):
    puede_anular = (e.cantidad_disponible == e.cantidad_recibida) and (not e.desgloses_venta.exists())
    fecha_caracas = timezone.localtime(e.fecha_entrada, CARACAS_TZ)
    return {
        'id': e.id,
        'producto_id': e.producto.id,
        'producto_nombre': e.producto.nombre,
        'cantidad_recibida': e.cantidad_recibida,
        'cantidad_disponible': e.cantidad_disponible,
        'costo_unitario': float(e.costo_unitario),
        'precio_venta': float(e.precio_venta),
        'precio_mayor': float(e.precio_mayor or 0),
        'precio_gran_mayor': float(e.precio_gran_mayor or 0),
        'precio_promo_divisa': float(e.precio_promo_divisa or 0),
        'fecha': fecha_caracas.strftime("%d/%m/%Y"),
        'fecha_hora_12h': fecha_caracas.strftime("%d/%m/%Y %I:%M %p"),
        'observaciones': e.observaciones,
        'puede_anular': puede_anular,
        'unidades_vendidas': e.cantidad_recibida - e.cantidad_disponible
    }


def _listar_entradas(request):
    qs = EntradaMercancia.objects.select_related('producto').order_by('-fecha_entrada', '-id')
    qs = _aplicar_filtros_entradas(qs, request)
    total_entradas = qs.count()

    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        page_size = min(100, max(1, int(request.GET.get('page_size', 10))))
    except (ValueError, TypeError):
        page_size = 10

    limite = request.GET.get('limite')
    if limite:
        try:
            page_size = max(1, int(limite))
            page = 1
        except Exception:
            pass

    total_paginas = max(1, math.ceil(total_entradas / page_size))
    offset = (page - 1) * page_size
    entradas = qs[offset:offset + page_size]

    return JsonResponse({
        'entradas': [_serializar_entrada(e) for e in entradas],
        'total_entradas': total_entradas,
        'total_paginas': total_paginas,
        'pagina_actual': page,
        'page_size': page_size
    })


def _crear_entrada(request):
    try:
        payload = json.loads(request.body)
        prod_id = payload.get('producto_id')
        nombre = payload.get('nombre', '').strip()
        cantidad = int(payload.get('cantidad', 0))
        minimo = int(payload.get('stock_minimo', 3))
        costo = Decimal(str(payload.get('costo_unitario', 0)))
        precio = Decimal(str(payload.get('precio_venta', 0)))
        precio_mayor = Decimal(str(payload.get('precio_mayor', 0) or 0))
        precio_gran_mayor = Decimal(str(payload.get('precio_gran_mayor', 0) or 0))
        precio_promo = Decimal(str(payload.get('precio_promo_divisa', 0) or 0))
        observaciones = payload.get('observaciones', '').strip()

        if cantidad <= 0 or cantidad > 10000:
            return JsonResponse({'error': 'La cantidad debe ser mayor a 0 y menor a 10.000.'}, status=400)
        if costo < 0 or precio <= 0:
            return JsonResponse({'error': 'El costo no puede ser negativo y el precio debe ser mayor a 0.'}, status=400)
        if precio < costo and not payload.get('permitir_perdida', False):
            return JsonResponse({'error': f'El precio de venta (Bs {precio:.2f}) es menor al costo unitario (Bs {costo:.2f}). Corrige el precio antes de guardar.'}, status=400)

        if prod_id:
            producto = Producto.objects.get(id=prod_id)
        else:
            if not nombre:
                return JsonResponse({'error': 'Debes indicar un nombre para el producto.'}, status=400)
            producto, _ = Producto.objects.get_or_create(nombre=nombre)

        producto.activo = True
        producto.stock_minimo = minimo
        producto.save()

        entrada = EntradaMercancia.objects.create(
            producto=producto,
            cantidad_recibida=cantidad,
            cantidad_disponible=cantidad,
            costo_unitario=costo,
            precio_venta=precio,
            precio_mayor=precio_mayor,
            precio_gran_mayor=precio_gran_mayor,
            precio_promo_divisa=precio_promo,
            observaciones=observaciones
        )

        return JsonResponse({
            'mensaje': f'Entrada registrada con éxito para "{producto.nombre}" (+{cantidad} unidades).',
            'entrada_id': entrada.id,
            'producto_id': producto.id,
            'stock_actual': producto.stock_total
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def api_entradas(request):
    if request.method == "GET":
        return _listar_entradas(request)
    return _crear_entrada(request)


@login_required
@require_http_methods(["POST"])
def api_eliminar_entrada(request, entrada_id):
    """
    Permite anular/borrar una entrada de mercancía.
    Si ya tiene unidades vendidas o ventas asociadas, se BLOQUEA la anulación directa
    para garantizar la integridad contable y los costos históricos de FIFO.
    """
    try:
        entrada = EntradaMercancia.objects.get(id=entrada_id)
        if entrada.cantidad_disponible < entrada.cantidad_recibida or entrada.desgloses_venta.exists():
            unidades_vendidas = entrada.cantidad_recibida - entrada.cantidad_disponible
            return JsonResponse({
                'error': f'No se puede anular esta entrada porque ya tiene ventas asociadas (se han vendido {unidades_vendidas} unidades de este lote). Para anularla primero debes anular las ventas correspondientes en el panel.'
            }, status=400)
        
        producto = entrada.producto
        entrada.delete()
        return JsonResponse({
            'mensaje': f'Entrada eliminada. Se actualizaron las existencias de "{producto.nombre}".',
            'producto_id': producto.id,
            'stock_actual': producto.stock_total
        })
    except EntradaMercancia.DoesNotExist:
        return JsonResponse({'error': 'Entrada no encontrada.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def api_lotes_disponibles(request):
    """
    Retorna cada lote/entrada disponible con su propio precio, costo y cantidad restante.
    Permite a la tienda vender de un lote específico (viejo o nuevo) o ajustar el precio.
    """
    q = request.GET.get('q', '').strip()
    entradas = EntradaMercancia.objects.filter(
        cantidad_disponible__gt=0,
        producto__activo=True
    ).select_related('producto').order_by('fecha_entrada', 'id')

    if q:
        q_norm = normalizar_texto(q)
        entradas = entradas.filter(producto__nombre_busqueda__icontains=q_norm)

    data = [{
        'lote_id': e.id,
        'producto_id': e.producto.id,
        'producto_nombre': e.producto.nombre,
        'cantidad_disponible': e.cantidad_disponible,
        'precio_venta': float(e.precio_venta),
        'precio_mayor': float(e.precio_mayor or 0),
        'precio_gran_mayor': float(e.precio_gran_mayor or 0),
        'precio_promo_divisa': float(e.precio_promo_divisa or 0),
        'costo_unitario': float(e.costo_unitario),
        'fecha': timezone.localtime(e.fecha_entrada, CARACAS_TZ).strftime("%d/%m/%Y"),
        'fecha_hora_12h': timezone.localtime(e.fecha_entrada, CARACAS_TZ).strftime("%d/%m/%Y %I:%M %p"),
    } for e in entradas]

    return JsonResponse({'lotes': data})


@login_required
@require_http_methods(["GET"])
def api_metricas_inventario(request):
    prods = Producto.objects.filter(activo=True)
    total_prods = prods.count()

    entradas_activas = EntradaMercancia.objects.filter(cantidad_disponible__gt=0, producto__activo=True)
    agregados = entradas_activas.aggregate(
        total_uds=Sum('cantidad_disponible'),
        total_valor_venta=Sum(F('cantidad_disponible') * F('precio_venta')),
        total_valor_costo=Sum(F('cantidad_disponible') * F('costo_unitario'))
    )

    total_uds = agregados['total_uds'] or 0
    total_valor_venta = float(agregados['total_valor_venta'] or 0)
    total_valor_costo = float(agregados['total_valor_costo'] or 0)

    tasa_bcv = HistorialTasa.obtener_ultima_tasa('USD_BCV') or Decimal('896.12')
    if tasa_bcv <= Decimal('0.00'):
        tasa_bcv = Decimal('1.00')

    val_venta_dec = Decimal(str(total_valor_venta))
    val_costo_dec = Decimal(str(total_valor_costo))
    valor_venta_usd = float((val_venta_dec / tasa_bcv).quantize(Decimal('0.01')))
    valor_costo_usd = float((val_costo_dec / tasa_bcv).quantize(Decimal('0.01')))

    return JsonResponse({
        'total_productos': total_prods,
        'unidades_disponibles': total_uds,
        'valor_venta_disponible': total_valor_venta,
        'valor_venta_disponible_usd': valor_venta_usd,
        'valor_costo_disponible': total_valor_costo,
        'valor_costo_disponible_usd': valor_costo_usd,
        'tasa_usd_bcv': float(tasa_bcv)
    })
