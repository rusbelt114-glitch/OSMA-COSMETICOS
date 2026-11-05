import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import Venta
from .services import registrar_venta_fifo

@login_required
@require_http_methods(["GET", "POST"])
def api_ventas(request):
    if request.method == "GET":
        ventas = Venta.objects.filter(anulada=False).prefetch_related('detalles__producto', 'pagos').order_by('-fecha', '-id')[:30]
        data = []
        for v in ventas:
            data.append({
                'codigo': v.codigo,
                'fecha': v.fecha.strftime("%d/%m/%Y %H:%M"),
                'total_bs': float(v.total_bs),
                'costo_total_bs': float(v.costo_total_bs),
                'ganancia_bruta_bs': float(v.ganancia_bruta_bs),
                'tasa_usd_bcv': float(v.tasa_usd_bcv),
                'tasa_usdt': float(v.tasa_usdt),
                'articulos': [{
                    'nombre': d.producto.nombre,
                    'cantidad': d.cantidad,
                    'precio_unitario': float(d.precio_unitario_bs),
                    'subtotal': float(d.subtotal_bs),
                    'ganancia_bruta': float(d.ganancia_bruta_bs)
                } for d in v.detalles.all()],
                'pagos': [{
                    'metodo': p.get_metodo_display(),
                    'moneda': p.moneda,
                    'monto_original': float(p.monto_original),
                    'monto_bs': float(p.monto_equivalente_bs),
                    'tasa': float(p.tasa_aplicada)
                } for p in v.pagos.all()]
            })
        return JsonResponse({'ventas': data})

    elif request.method == "POST":
        try:
            payload = json.loads(request.body)
            items = payload.get('items', [])
            pagos = payload.get('pagos', [])
            tasa_usd = payload.get('tasa_usd')
            tasa_usdt = payload.get('tasa_usdt')
            observaciones = payload.get('observaciones', '').strip()

            if not items:
                return JsonResponse({'error': 'Debes agregar al menos un producto a la venta.'}, status=400)
            if not pagos:
                return JsonResponse({'error': 'Debes registrar al menos un medio de pago.'}, status=400)

            venta = registrar_venta_fifo(
                items_carrito=items,
                lista_pagos=pagos,
                tasa_usd_bcv=tasa_usd,
                tasa_usdt=tasa_usdt,
                observaciones=observaciones
            )

            return JsonResponse({
                'mensaje': f'Venta {venta.codigo} registrada con éxito. Inventario actualizado por FIFO.',
                'codigo': venta.codigo,
                'total_bs': float(venta.total_bs),
                'ganancia_bruta_bs': float(venta.ganancia_bruta_bs)
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
