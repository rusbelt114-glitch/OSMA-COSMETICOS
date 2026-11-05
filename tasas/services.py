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
        logger.warning(f"No se pudo sincronizar la tasa en línea: {e}")
        resultados['mensaje'] = f'No se pudo conectar a la API ({e}). Usando última tasa guardada en el sistema.'
        resultados['usd_bcv'] = HistorialTasa.obtener_ultima_tasa('USD_BCV')
        resultados['usdt'] = HistorialTasa.obtener_ultima_tasa('USDT')

    return resultados

