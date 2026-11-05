import json
from decimal import Decimal
from django.utils import timezone
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import Venta
from .services import registrar_venta_fifo, anular_venta_fifo

@login_required
@require_http_methods(["GET", "POST"])
def api_ventas(request):
    if request.method == "GET":
        ventas = Venta.objects.all().prefetch_related('detalles__producto', 'pagos').order_by('-fecha', '-id')[:50]
        data = []
        for v in ventas:
            data.append({
                'codigo': v.codigo,
                'fecha': timezone.localtime(v.fecha).strftime("%d/%m/%Y %H:%M"),
                'total_bs': float(v.total_bs),
                'costo_total_bs': float(v.costo_total_bs),
                'ganancia_bruta_bs': float(v.ganancia_bruta_bs),
                'vuelto_total_bs': float(v.vuelto_total_bs),
                'tasa_usd_bcv': float(v.tasa_usd_bcv),
                'tasa_usdt': float(v.tasa_usdt),
                'anulada': v.anulada,
                'motivo_anulacion': v.motivo_anulacion,
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
                    'monto_recibido': float(p.monto_recibido or p.monto_original),
                    'monto_original': float(p.monto_original),
                    'vuelto_entregado': float(p.vuelto_entregado),
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
            idempotency_key = payload.get('idempotency_key') or payload.get('client_token')
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
                observaciones=observaciones,
                idempotency_key=idempotency_key
            )

            return JsonResponse({
                'mensaje': f'Venta {venta.codigo} registrada con éxito. Inventario actualizado por FIFO.',
                'codigo': venta.codigo,
                'total_bs': float(venta.total_bs),
                'vuelto_total_bs': float(venta.vuelto_total_bs),
                'ganancia_bruta_bs': float(venta.ganancia_bruta_bs)
            })
        except ValidationError as ve:
            msg = ve.message if hasattr(ve, 'message') else str(ve)
            return JsonResponse({'error': msg}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def api_anular_venta(request, codigo):
    """
    Anula una venta y restituye todas las existencias descontadas a sus lotes originales.
    """
    try:
        payload = json.loads(request.body) if request.body else {}
        motivo = payload.get('motivo', 'Anulación manual desde punto de venta')
        venta = anular_venta_fifo(codigo, motivo=motivo)
        return JsonResponse({
            'exito': True,
            'mensaje': f'Venta {venta.codigo} anulada exitosamente. Las existencias han sido reintegradas al inventario.',
            'codigo': venta.codigo
        })
    except ValidationError as ve:
        msg = ve.message if hasattr(ve, 'message') else str(ve)
        return JsonResponse({'error': msg}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
