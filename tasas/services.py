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

    # 1. Intentar obtener USDT real de Binance P2P
    tasa_usdt_real = None
    fuente_usdt = ""
    try:
        binance_payload = json.dumps({
            'asset': 'USDT',
            'fiat': 'VES',
            'merchantCheck': True,
            'page': 1,
            'rows': 5,
            'tradeType': 'BUY'
        }).encode('utf-8')
        req_b = urllib.request.Request(
            'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search',
            data=binance_payload,
            headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req_b, timeout=4) as b_resp:
            if b_resp.status == 200:
                b_data = json.loads(b_resp.read().decode('utf-8'))
                advs = b_data.get('data', [])
                if advs and advs[0].get('adv', {}).get('price'):
                    tasa_usdt_real = Decimal(str(advs[0]['adv']['price']))
                    fuente_usdt = 'Binance P2P (USDT)'
    except Exception as e_binance:
        logger.info(f"Binance P2P no disponible ({e_binance}), se usará mercado alternativo para USDT.")

    # 2. Consultar DolarApi para BCV Oficial y fallback de mercado
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

                # Registrar USDT: priorizar Binance P2P real sobre DolarApi paralelo
                if tasa_usdt_real:
                    HistorialTasa.objects.create(
                        tipo='USDT',
                        valor=tasa_usdt_real,
                        fuente=fuente_usdt,
                        es_manual=False
                    )
                    resultados['usdt'] = tasa_usdt_real
                else:
                    paralelo = next((item for item in data if item.get('fuente') == 'paralelo'), None)
                    if paralelo and paralelo.get('promedio'):
                        tasa_val = Decimal(str(paralelo['promedio']))
                        HistorialTasa.objects.create(
                            tipo='USDT',
                            valor=tasa_val,
                            fuente='Mercado Paralelo (DolarApi - Contingencia)',
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

