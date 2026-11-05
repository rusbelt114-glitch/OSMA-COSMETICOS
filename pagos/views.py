import json
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum, Count

from .models import Gasto, PagoVenta
from tasas.models import HistorialTasa
from reportes.views import parse_fecha_filtro

@login_required
@require_http_methods(["GET", "POST"])
def api_gastos(request):
    """
    Lista y registra gastos operativos de la tienda o retiros personales del dueño.
    Permite totalizar por categoría y calcular la ganancia neta real del negocio.
    """
    if request.method == "GET":
        desde_str = request.GET.get('desde')
        hasta_str = request.GET.get('hasta')

        desde_dt = parse_fecha_filtro(desde_str, fin_del_dia=False)
        hasta_dt = parse_fecha_filtro(hasta_str, fin_del_dia=True)

        gastos_qs = Gasto.objects.all().order_by('-fecha', '-id')
        if desde_dt:
            gastos_qs = gastos_qs.filter(fecha__gte=desde_dt)
        if hasta_dt:
            gastos_qs = gastos_qs.filter(fecha__lte=hasta_dt)

        total_tienda_bs = gastos_qs.filter(categoria='TIENDA').aggregate(total=Sum('monto_equivalente_bs'))['total'] or Decimal('0.00')
        total_personal_bs = gastos_qs.filter(categoria='PERSONAL').aggregate(total=Sum('monto_equivalente_bs'))['total'] or Decimal('0.00')
        total_general_bs = total_tienda_bs + total_personal_bs

        data = []
        for g in gastos_qs[:100]:
            data.append({
                'id': g.id,
                'fecha': timezone.localtime(g.fecha).strftime("%d/%m/%Y %H:%M"),
                'descripcion': g.descripcion,
                'categoria': g.categoria,
                'categoria_label': g.get_categoria_display(),
                'monto_original': float(g.monto_original),
                'moneda': g.moneda,
                'tasa_aplicada': float(g.tasa_aplicada),
                'monto_equivalente_bs': float(g.monto_equivalente_bs),
                'metodo': g.metodo,
                'metodo_label': g.get_metodo_display(),
                'comprobante': g.comprobante,
                'observaciones': g.observaciones,
            })

        return JsonResponse({
            'gastos': data,
            'total_tienda_bs': float(total_tienda_bs),
            'total_personal_bs': float(total_personal_bs),
            'total_general_bs': float(total_general_bs),
            'num_gastos': gastos_qs.count()
        })

    elif request.method == "POST":
        try:
            payload = json.loads(request.body)
            descripcion = payload.get('descripcion', '').strip()
            categoria = payload.get('categoria', 'TIENDA').strip().upper()
            moneda = payload.get('moneda', 'BS').strip().upper()
            metodo = payload.get('metodo', 'EFECTIVO_BS').strip().upper()
            comprobante = payload.get('comprobante', '').strip()
            observaciones = payload.get('observaciones', '').strip()

            if not descripcion:
                return JsonResponse({'error': 'La descripción o concepto del gasto es obligatoria.'}, status=400)

            if categoria not in ('TIENDA', 'PERSONAL'):
                return JsonResponse({'error': 'Categoría inválida. Debe ser Tienda o Personal.'}, status=400)

            try:
                monto_orig = Decimal(str(payload.get('monto', 0)))
            except (ValueError, TypeError, InvalidOperation):
                return JsonResponse({'error': 'El monto debe ser un valor numérico válido.'}, status=400)

            if monto_orig <= Decimal('0.00'):
                return JsonResponse({'error': 'El monto del gasto debe ser estrictamente mayor a cero.'}, status=400)

            # Tasa de cambio
            if moneda == 'USD':
                tasa_def = HistorialTasa.obtener_ultima_tasa('USD_BCV')
                try:
                    tasa = Decimal(str(payload.get('tasa', tasa_def)))
                except Exception:
                    tasa = tasa_def
                monto_bs = (monto_orig * tasa).quantize(Decimal('0.01'))
            elif moneda == 'USDT':
                tasa_def = HistorialTasa.obtener_ultima_tasa('USDT')
                try:
                    tasa = Decimal(str(payload.get('tasa', tasa_def)))
                except Exception:
                    tasa = tasa_def
                monto_bs = (monto_orig * tasa).quantize(Decimal('0.01'))
            else:
                moneda = 'BS'
                tasa = Decimal('1.0000')
                monto_bs = monto_orig

            gasto = Gasto.objects.create(
                descripcion=descripcion,
                categoria=categoria,
                monto_original=monto_orig,
                moneda=moneda,
                tasa_aplicada=tasa,
                monto_equivalente_bs=monto_bs,
                metodo=metodo,
                comprobante=comprobante,
                observaciones=observaciones
            )

            return JsonResponse({
                'mensaje': f'Gasto "{gasto.descripcion}" registrado con éxito (Bs {gasto.monto_equivalente_bs}).',
                'id': gasto.id,
                'monto_bs': float(gasto.monto_equivalente_bs)
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def api_eliminar_gasto(request, gasto_id):
    try:
        gasto = Gasto.objects.get(id=gasto_id)
        desc = gasto.descripcion
        gasto.delete()
        return JsonResponse({'mensaje': f'Gasto "{desc}" eliminado correctamente.'})
    except Gasto.DoesNotExist:
        return JsonResponse({'error': 'El gasto solicitado no existe.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
