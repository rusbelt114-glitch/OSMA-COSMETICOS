import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import Producto, normalizar_texto

from django.db.models import Sum, Subquery, OuterRef, Value, IntegerField, DecimalField, Q
from django.db.models.functions import Coalesce
from inventario.models import EntradaMercancia

def _listar_productos(request):
    """
    Consulta y serializa los productos optimizado en 1 SOLA CONSULTA SQL
    eliminando por completo el problema N+1.
    """
    q = request.GET.get('q', '').strip()
    solo_activos = request.GET.get('activos', 'true').lower() in ('true', '1')

    ultimas_entradas = EntradaMercancia.objects.filter(producto=OuterRef('pk')).order_by('-fecha_entrada', '-id')
    sub_precio = Subquery(ultimas_entradas.values('precio_venta')[:1], output_field=DecimalField())
    sub_costo = Subquery(ultimas_entradas.values('costo_unitario')[:1], output_field=DecimalField())
    sub_precio_mayor = Subquery(ultimas_entradas.values('precio_mayor')[:1], output_field=DecimalField())
    sub_precio_gran_mayor = Subquery(ultimas_entradas.values('precio_gran_mayor')[:1], output_field=DecimalField())
    sub_precio_promo = Subquery(ultimas_entradas.values('precio_promo_divisa')[:1], output_field=DecimalField())

    productos_qs = Producto.objects.all()
    if solo_activos:
        productos_qs = productos_qs.filter(activo=True)

    if q:
        productos_qs = productos_qs.filter(nombre_busqueda__icontains=normalizar_texto(q))

    productos = productos_qs.annotate(
        stock_disp=Coalesce(
            Sum('entradas__cantidad_disponible', filter=Q(entradas__cantidad_disponible__gt=0)),
            Value(0),
            output_field=IntegerField()
        ),
        ult_precio=sub_precio,
        ult_costo=sub_costo,
        ult_precio_mayor=sub_precio_mayor,
        ult_precio_gran_mayor=sub_precio_gran_mayor,
        ult_precio_promo=sub_precio_promo
    )

    data = []
    for p in productos:
        st = p.stock_disp or 0
        if st == 0:
            estado = 'agotado'
        elif st <= p.stock_minimo:
            estado = 'minimo'
        else:
            estado = 'normal'

        data.append({
            'id': p.id,
            'nombre': p.nombre,
            'stock_minimo': p.stock_minimo,
            'stock_total': st,
            'estado': estado,
            'activo': p.activo,
            'ultimo_precio': float(p.ult_precio or 0),
            'ultimo_costo': float(p.ult_costo or 0),
            'ultimo_precio_mayor': float(p.ult_precio_mayor or 0),
            'ultimo_precio_gran_mayor': float(p.ult_precio_gran_mayor or 0),
            'ultimo_precio_promo': float(p.ult_precio_promo or 0),
        })

    return JsonResponse({'productos': data})

def _retirar_producto(prod_id):
    producto = Producto.objects.get(id=prod_id)
    producto.activo = False
    producto.save(update_fields=['activo'])
    return JsonResponse({'mensaje': f'Producto "{producto.nombre}" retirado del catálogo activo.'})

def _reactivar_producto(prod_id):
    producto = Producto.objects.get(id=prod_id)
    producto.activo = True
    producto.save()
    return JsonResponse({'mensaje': f'Producto "{producto.nombre}" reactivado en el catálogo.'})

def _eliminar_producto_total(prod_id, forzar=False):
    producto = Producto.objects.get(id=prod_id)
    tiene_ventas = producto.ventas_detalle.exists()
    if tiene_ventas and not forzar:
        return JsonResponse({
            'error': f'"{producto.nombre}" ya tiene ventas registradas en el historial.',
            'puede_forzar': True,
            'mensaje': f'"{producto.nombre}" ya tiene ventas registradas. ¿Deseas forzar su eliminación eliminando también sus ventas y existencias de prueba?'
        }, status=400)
    
    # Si se fuerza o no tiene ventas:
    for item in producto.ventas_detalle.all():
        item.desgloses_lote.all().delete()
        item.delete()
    producto.entradas.all().delete()
    nombre = producto.nombre
    producto.delete()
    return JsonResponse({'mensaje': f'Producto "{nombre}" y sus registros asociados fueron eliminados correctamente.'})

def _guardar_producto(payload):
    nombre = payload.get('nombre', '').strip()
    stock_minimo = int(payload.get('stock_minimo', 3))
    confirmar_coincidencia = payload.get('confirmar_coincidencia', False)

    if not nombre:
        return JsonResponse({'error': 'El nombre del producto es obligatorio.'}, status=400)

    nombre_norm = normalizar_texto(nombre)

    # Advertencia ante nombres similares ignorando mayúsculas y acentos
    coincidencias = list(
        Producto.objects.filter(nombre_busqueda=nombre_norm).values('id', 'nombre', 'activo')
    )
    if not coincidencias and len(nombre_norm) >= 4:
        coincidencias = list(
            Producto.objects.filter(nombre_busqueda__icontains=nombre_norm).exclude(nombre=nombre)[:3].values('id', 'nombre', 'activo')
        )

    if coincidencias and not confirmar_coincidencia:
        nombres_similares = [c['nombre'] for c in coincidencias]
        if nombre not in nombres_similares:
            return JsonResponse({
                'advertencia_coincidencia': True,
                'coincidencias': nombres_similares,
                'mensaje': f'Ya existe en catálogo un producto con nombre similar: "{", ".join(nombres_similares)}". Confirma si se trata de un tono, marca o presentación diferente.'
            })

    producto, created = Producto.objects.get_or_create(
        nombre=nombre,
        defaults={'stock_minimo': stock_minimo, 'activo': True}
    )
    if not created and not producto.activo:
        producto.activo = True
        producto.stock_minimo = stock_minimo
        producto.save()

    return JsonResponse({
        'id': producto.id,
        'nombre': producto.nombre,
        'stock_minimo': producto.stock_minimo,
        'nuevo': created
    })

@login_required
@require_http_methods(["GET", "POST"])
def api_productos(request):
    if request.method == "GET":
        return _listar_productos(request)

    try:
        payload = json.loads(request.body)
        accion = payload.get('accion')
        prod_id = payload.get('producto_id')
        forzar = payload.get('forzar', False)

        acciones = {
            'retirar': lambda: _retirar_producto(prod_id),
            'reactivar': lambda: _reactivar_producto(prod_id),
            'eliminar_total': lambda: _eliminar_producto_total(prod_id, forzar=forzar),
        }

        manejador = acciones.get(accion)
        if manejador:
            return manejador()

        return _guardar_producto(payload)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
