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
    eliminando por completo el problema N+1 (de 4.003 queries a 1).
    """
    q = request.GET.get('q', '').strip()
    solo_activos = request.GET.get('activos', 'true').lower() in ('true', '1')

    # Subqueries optimizadas para obtener el último precio y costo en la misma consulta
    ultimas_entradas = EntradaMercancia.objects.filter(producto=OuterRef('pk')).order_by('-fecha_entrada', '-id')
    sub_precio = Subquery(ultimas_entradas.values('precio_venta')[:1], output_field=DecimalField())
    sub_costo = Subquery(ultimas_entradas.values('costo_unitario')[:1], output_field=DecimalField())

    productos_qs = Producto.objects.all()
    if solo_activos:
        productos_qs = productos_qs.filter(activo=True)

    if q:
        productos_qs = productos_qs.filter(nombre_busqueda__icontains=normalizar_texto(q))

    # Anotación agregada: suma de existencias activas y último precio/costo en 1 solo viaje a la BD
    productos = productos_qs.annotate(
        stock_disp=Coalesce(
            Sum('entradas__cantidad_disponible', filter=Q(entradas__cantidad_disponible__gt=0)),
            Value(0),
            output_field=IntegerField()
        ),
        ult_precio=sub_precio,
        ult_costo=sub_costo
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
        })

    return JsonResponse({'productos': data})

def _retirar_producto(prod_id):
    producto = Producto.objects.get(id=prod_id)
    if producto.stock_total > 0:
        return JsonResponse(
            {'error': 'Para retirar este producto del catálogo, primero debe quedar en 0 unidades.'},
            status=400
        )
    producto.activo = False
    producto.save()
    return JsonResponse({'mensaje': f'Producto "{producto.nombre}" retirado del catálogo activo.'})

def _reactivar_producto(prod_id):
    producto = Producto.objects.get(id=prod_id)
    producto.activo = True
    producto.save()
    return JsonResponse({'mensaje': f'Producto "{producto.nombre}" reactivado en el catálogo.'})

def _eliminar_producto_total(prod_id):
    producto = Producto.objects.get(id=prod_id)
    if producto.ventas_detalle.exists():
        return JsonResponse(
            {'error': f'"{producto.nombre}" ya tiene ventas registradas en el historial. Puedes retirarlo del catálogo pero no borrarlo para proteger las auditorías.'},
            status=400
        )
    nombre = producto.nombre
    producto.entradas.all().delete()
    producto.delete()
    return JsonResponse({'mensaje': f'Producto "{nombre}" eliminado por completo del sistema.'})

def _guardar_producto(payload):
    nombre = payload.get('nombre', '').strip()
    stock_minimo = int(payload.get('stock_minimo', 3))
    if not nombre:
        return JsonResponse({'error': 'El nombre del producto es obligatorio.'}, status=400)

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

        acciones = {
            'retirar': lambda: _retirar_producto(prod_id),
            'reactivar': lambda: _reactivar_producto(prod_id),
            'eliminar_total': lambda: _eliminar_producto_total(prod_id),
        }

        manejador = acciones.get(accion)
        if manejador:
            return manejador()

        return _guardar_producto(payload)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
