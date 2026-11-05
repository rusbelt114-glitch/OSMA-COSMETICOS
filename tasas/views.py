import json
from decimal import Decimal
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import HistorialTasa
from .services import sincronizar_tasas_en_linea

@login_required
@require_http_methods(["GET"])
def api_tasas(request):
    tasa_bcv = HistorialTasa.obtener_ultima_tasa('USD_BCV')
    tasa_usdt = HistorialTasa.obtener_ultima_tasa('USDT')

    ultima_bcv_obj = HistorialTasa.objects.filter(tipo='USD_BCV').order_by('-fecha').first()
    fecha_bcv = timezone.localtime(ultima_bcv_obj.fecha).strftime("%d/%m/%Y %H:%M") if ultima_bcv_obj else ""

    return JsonResponse({
        'usd_bcv': float(tasa_bcv),
        'usdt': float(tasa_usdt),
        'fecha_actualizacion': fecha_bcv
    })

@login_required
@require_http_methods(["POST"])
def api_actualizar_tasas(request):
    try:
        body = json.loads(request.body) if request.body else {}
        es_manual = body.get('manual', False)

        if es_manual:
            nueva_usd = body.get('usd_bcv')
            nueva_usdt = body.get('usdt')

            if nueva_usd:
                HistorialTasa.objects.create(
                    tipo='USD_BCV',
                    valor=Decimal(str(nueva_usd)),
                    fuente='Ajuste Manual',
                    es_manual=True
                )
            if nueva_usdt:
                HistorialTasa.objects.create(
                    tipo='USDT',
                    valor=Decimal(str(nueva_usdt)),
                    fuente='Ajuste Manual',
                    es_manual=True
                )
            return JsonResponse({'mensaje': 'Tasas ajustadas manualmente con éxito.'})
        else:
            res = sincronizar_tasas_en_linea()
            return JsonResponse(res)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
