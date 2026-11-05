from .models import HistorialTasa

def tasas_globales(request):
    """
    Inyecta las últimas tasas activas de USD BCV y USDT en todas las vistas de plantillas.
    """
    tasa_usd = HistorialTasa.obtener_ultima_tasa('USD_BCV')
    tasa_usdt = HistorialTasa.obtener_ultima_tasa('USDT')
    return {
        'TASA_USD_BCV': tasa_usd,
        'TASA_USDT': tasa_usdt,
    }

