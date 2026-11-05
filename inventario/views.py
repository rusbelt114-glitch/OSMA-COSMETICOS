import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F
from productos.models import Producto
from .models import EntradaMercancia

@login_required
@require_http_methods(["GET", "POST"])
def api_entradas(request):
    if request.method == "GET":
        entradas = EntradaMercancia.objects.select_related('producto').order_by('-fecha_entrada', '-id')[:20]
        data = [{
            'id': e.id,
            'producto_id': e.producto.id,
            'producto_nombre': e.producto.nombre,
            'cantidad_recibida': e.cantidad_recibida,
            'cantidad_disponible': e.cantidad_disponible,
            'costo_unitario': float(e.costo_unitario),
            'precio_venta': float(e.precio_venta),
            'fecha': e.fecha_entrada.strftime("%d/%m/%Y"),
            'observaciones': e.observaciones,
        } for e in entradas]
        return JsonResponse({'entradas': data})

    elif request.method == "POST":
        try:
            payload = json.loads(request.body)
            prod_id = payload.get('producto_id')
            nombre = payload.get('nombre', '').strip()
            cantidad = int(payload.get('cantidad', 0))
            minimo = int(payload.get('stock_minimo', 3))
            costo = Decimal(str(payload.get('costo_unitario', 0)))
            precio = Decimal(str(payload.get('precio_venta', 0)))
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
@require_http_methods(["POST"])
def api_eliminar_entrada(request, entrada_id):
    """
    Permite anular/borrar una entrada de mercancía (por ejemplo, errores de carga o pruebas).
    Si ya tiene ventas asociadas, se protege la integridad contable.
    """
    try:
        entrada = EntradaMercancia.objects.get(id=entrada_id)
        if entrada.desgloses_venta.exists():
            return JsonResponse({
                'error': f'Esta entrada ya tiene ventas registradas. Para anularla primero debes anular la venta correspondiente en el panel de administración.'
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
        from productos.models import normalizar_texto
        q_norm = normalizar_texto(q)
        entradas = entradas.filter(producto__nombre_busqueda__icontains=q_norm)

    data = [{
        'lote_id': e.id,
        'producto_id': e.producto.id,
        'producto_nombre': e.producto.nombre,
        'cantidad_disponible': e.cantidad_disponible,
        'precio_venta': float(e.precio_venta),
        'costo_unitario': float(e.costo_unitario),
        'fecha': e.fecha_entrada.strftime("%d/%m/%Y"),
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

    return JsonResponse({
        'total_productos': total_prods,
        'unidades_disponibles': total_uds,
        'valor_venta_disponible': total_valor_venta,
        'valor_costo_disponible': total_valor_costo
    })
