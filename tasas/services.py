import json
import logging
import urllib.request
from decimal import Decimal
from django.utils import timezone
from .models import HistorialTasa

logger = logging.getLogger(__name__)

DOLAR_API_URL = "https://ve.dolarapi.com/v1/dolares"

def sincronizar_tasas_en_linea():
    """
    Consulta la API oficial de tasas venezolanas (DolarApi - BCV y Paralelo/USDT).
    Actualiza la base de datos de manera resiliente: si no hay internet o la API falla,
    conserva la última tasa guardada.
    """
    resultados = {
        'exito': False,
        'usd_bcv': None,
        'usdt': None,
        'mensaje': ''
    }

    try:
        req = urllib.request.Request(
            DOLAR_API_URL, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) OsmaCosmetics/1.0'}
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                
                # Buscar BCV oficial
                oficial = next((item for item in data if item.get('fuente') == 'oficial'), None)
                if oficial and oficial.get('promedio'):
                    tasa_val = Decimal(str(oficial['promedio']))
                    HistorialTasa.objects.create(
                        tipo='USD_BCV',
                        valor=tasa_val,
                        fuente='BCV (DolarApi)',
                        es_manual=False
                    )
                    resultados['usd_bcv'] = tasa_val

                # Buscar paralelo como base de mercado / USDT
                paralelo = next((item for item in data if item.get('fuente') == 'paralelo'), None)
                if paralelo and paralelo.get('promedio'):
                    tasa_val = Decimal(str(paralelo['promedio']))
                    HistorialTasa.objects.create(
                        tipo='USDT',
                        valor=tasa_val,
                        fuente='Mercado/Paralelo (DolarApi)',
                        es_manual=False
                    )
                    resultados['usdt'] = tasa_val

                resultados['exito'] = True
                resultados['mensaje'] = 'Tasas actualizadas exitosamente desde el BCV y mercado.'
    except Exception as e:
        logger.warning(f"Falla con DolarApi ({e}). Intentando proveedor alternativo...")
        # Proveedor alternativo pyDolarVenezuela
        try:
            from pyDolarVenezuela.pages import BCV, CriptoDolar
            from pyDolarVenezuela import Monitor
            monitor_bcv = Monitor(BCV, 'USD')
            bcv_data = monitor_bcv.get_value()
            if bcv_data:
                tasa_val = Decimal(str(bcv_data))
                HistorialTasa.objects.create(tipo='USD_BCV', valor=tasa_val, fuente='BCV (pyDolarVenezuela)', es_manual=False)
                resultados['usd_bcv'] = tasa_val

            monitor_usdt = Monitor(CriptoDolar, 'USDT')
            usdt_data = monitor_usdt.get_value()
            if usdt_data:
                tasa_val = Decimal(str(usdt_data))
                HistorialTasa.objects.create(tipo='USDT', valor=tasa_val, fuente='USDT (CriptoDolar)', es_manual=False)
                resultados['usdt'] = tasa_val

            if resultados['usd_bcv']:
                resultados['exito'] = True
                resultados['mensaje'] = 'Tasas actualizadas mediante proveedor de contingencia.'
                return resultados
        except Exception as e2:
            logger.warning(f"Falla en proveedor de contingencia: {e2}")

        resultados['mensaje'] = f'No se pudo conectar a los servicios de tasa. Se conservó la última tasa válida.'
        resultados['usd_bcv'] = HistorialTasa.obtener_ultima_tasa('USD_BCV')
        resultados['usdt'] = HistorialTasa.obtener_ultima_tasa('USDT')

    return resultados

