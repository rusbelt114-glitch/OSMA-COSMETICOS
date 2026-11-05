import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import Producto, normalizar_texto

def _listar_productos(request):
    """Consulta y serializa los productos con filtros opcionales."""
    q = request.GET.get('q', '').strip()
    solo_activos = request.GET.get('activos', 'true').lower() in ('true', '1')

    productos = Producto.objects.filter(activo=True) if solo_activos else Producto.objects.all()

    if q:
        productos = productos.filter(nombre_busqueda__icontains=normalizar_texto(q))

    data = [
        {
            'id': p.id,
            'nombre': p.nombre,
            'stock_minimo': p.stock_minimo,
            'stock_total': p.stock_total,
            'estado': p.estado_stock,
            'activo': p.activo,
            'ultimo_precio': float(p.ultimo_precio_venta or 0),
            'ultimo_costo': float(p.ultimo_costo or 0),
        }
        for p in productos
    ]
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
