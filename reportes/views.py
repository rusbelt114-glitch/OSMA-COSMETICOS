import os
import tempfile
import zipfile
import openpyxl
from io import BytesIO, StringIO
from decimal import Decimal
from datetime import datetime, time
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
from django.core.management import call_command
from productos.models import Producto
from inventario.models import EntradaMercancia
from .services import obtener_resumen_periodo, generar_excel_completo

def parse_fecha_filtro(fecha_str, fin_del_dia=False):
    if not fecha_str:
        return None
    try:
        dt = datetime.strptime(fecha_str.strip(), "%Y-%m-%d")
        t = time.max if fin_del_dia else time.min
        dt_full = datetime.combine(dt.date(), t)
        return timezone.make_aware(dt_full, timezone.get_current_timezone())
    except Exception:
        return None

@login_required
@require_http_methods(["GET"])
def api_reporte_resumen(request):
    desde_str = request.GET.get('desde')
    hasta_str = request.GET.get('hasta')

    desde_dt = parse_fecha_filtro(desde_str, fin_del_dia=False)
    hasta_dt = parse_fecha_filtro(hasta_str, fin_del_dia=True)

    resumen = obtener_resumen_periodo(desde_dt, hasta_dt)

    ventas_data = []
    for v in resumen['ventas_listado']:
        articulos_str = ", ".join(f"{d.cantidad}x {d.producto.nombre}" for d in v.detalles.all())
        medios_str = " + ".join(p.get_metodo_display() for p in v.pagos.all())
        t_v = v.tasa_usd_bcv if v.tasa_usd_bcv > 0 else Decimal('1.00')
        tot_u = float(v.total_usd) if v.total_usd > 0 else float((v.total_bs / t_v).quantize(Decimal('0.01')))
        gan_u = float(v.ganancia_bruta_usd) if v.ganancia_bruta_usd > 0 else float((v.ganancia_bruta_bs / t_v).quantize(Decimal('0.01')))
        ventas_data.append({
            'codigo': v.codigo,
            'fecha': timezone.localtime(v.fecha).strftime("%d/%m/%Y %I:%M %p"),
            'total_bs': float(v.total_bs),
            'total_usd': tot_u,
            'costo_total_bs': float(v.costo_total_bs),
            'ganancia_bruta_bs': float(v.ganancia_bruta_bs),
            'ganancia_bruta_usd': gan_u,
            'vuelto_total_bs': float(v.vuelto_total_bs),
            'anulada': v.anulada,
            'articulos': articulos_str,
            'medios': medios_str
        })

    cobros_json = []
    for c in resumen['cobros_por_medio']:
        cobros_json.append({
            'metodo': c['metodo'],
            'moneda': c['moneda'],
            'monto_recibido': float(c.get('monto_recibido') or c['total_neto_orig']),
            'vuelto_entregado_bs': float(c.get('vuelto_entregado_bs') or 0),
            'total_original': float(c['total_neto_orig']),
            'total_bs': float(c['total_neto_bs']),
            'transacciones': c['cantidad_transacciones']
        })

    return JsonResponse({
        'total_ingresos': float(resumen['total_ingresos']),
        'total_ingresos_usd': float(resumen.get('total_ingresos_usd', 0)),
        'total_costos': float(resumen['total_costos']),
        'total_costos_usd': float(resumen.get('total_costos_usd', 0)),
        'total_ganancia': float(resumen['total_ganancia']),
        'total_ganancia_usd': float(resumen.get('total_ganancia_usd', 0)),
        'total_gastos_tienda': float(resumen['total_gastos_tienda']),
        'total_gastos_tienda_usd': float(resumen.get('total_gastos_tienda_usd', 0)),
        'total_gastos_personal': float(resumen['total_gastos_personal']),
        'total_gastos_personal_usd': float(resumen.get('total_gastos_personal_usd', 0)),
        'total_gastos_general': float(resumen['total_gastos_general']),
        'total_gastos_general_usd': float(resumen.get('total_gastos_general_usd', 0)),
        'resultado_despues_gastos': float(resumen['resultado_despues_gastos']),
        'resultado_despues_gastos_usd': float(resumen.get('resultado_despues_gastos_usd', 0)),
        'ganancia_neta_real': float(resumen['resultado_despues_gastos']),
        'ganancia_neta_real_usd': float(resumen.get('resultado_despues_gastos_usd', 0)),
        'saldo_caja_real': float(resumen.get('saldo_caja_real', 0)),
        'saldo_caja_real_usd': float(resumen.get('saldo_caja_real_usd', 0)),
        'tasa_usd_bcv': float(resumen.get('tasa_usd_bcv', 1)),
        'inventario_actual': {
            'fecha_consulta': resumen['inventario_actual']['fecha_consulta'],
            'total_productos_activos': resumen['inventario_actual']['total_productos_activos'],
            'unidades_disponibles': resumen['inventario_actual']['unidades_disponibles'],
            'inversion_existencias': float(resumen['inventario_actual']['inversion_existencias']),
            'inversion_existencias_usd': float(resumen['inventario_actual'].get('inversion_existencias_usd', 0)),
            'venta_potencial': float(resumen['inventario_actual']['venta_potencial']),
            'venta_potencial_usd': float(resumen['inventario_actual'].get('venta_potencial_usd', 0)),
            'ganancia_potencial': float(resumen['inventario_actual'].get('ganancia_potencial', 0)),
            'ganancia_potencial_usd': float(resumen['inventario_actual'].get('ganancia_potencial_usd', 0)),
            'nota': resumen['inventario_actual']['nota']
        },
        'total_unidades_vendidas': resumen['total_unidades_vendidas'],
        'num_ventas': resumen['num_ventas'],
        'productos_vendidos': [{
            'nombre': p['producto__nombre'],
            'unidades': p['unidades'],
            'ingresos': float(p['ingresos']),
            'costo': float(p['costo']),
            'ganancia': float(p['ganancia'])
        } for p in resumen['productos_vendidos']],
        'cobros_por_medio': cobros_json,
        'productos_alerta': resumen['productos_alerta'],
        'ventas': ventas_data
    })


@login_required
@require_http_methods(["GET"])
def descargar_excel_reporte(request):
    desde_str = request.GET.get('desde')
    hasta_str = request.GET.get('hasta')

    desde_dt = parse_fecha_filtro(desde_str, fin_del_dia=False)
    hasta_dt = parse_fecha_filtro(hasta_str, fin_del_dia=True)

    wb = generar_excel_completo(desde_dt, hasta_dt)
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"Osma-Reporte-{timezone.now().strftime('%Y%m%d')}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_http_methods(["GET"])
def descargar_copia_seguridad(request):
    """
    Genera y descarga un archivo JSON completo con todas las tablas del sistema:
    productos, inventario, ventas, pagos y tasas de cambio.
    """
    buf = StringIO()
    call_command(
        'dumpdata',
        'productos', 'inventario', 'ventas', 'pagos', 'tasas',
        natural_foreign=True,
        natural_primary=True,
        indent=2,
        stdout=buf
    )
    json_data = buf.getvalue()
    filename = f"Osma-Copia-Seguridad-{timezone.now().strftime('%Y%m%d_%H%M')}.json"
    response = HttpResponse(json_data, content_type="application/json")
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _guardar_respaldo_preventivo():
    """Genera una copia de seguridad automática antes de alterar datos."""
    try:
        backup_dir = settings.BASE_DIR / 'backups'
        backup_dir.mkdir(exist_ok=True)
        ts = timezone.now().strftime('%Y%m%d_%H%M%S')
        preventivo = backup_dir / f"respaldo_preventivo_antes_de_restaurar_{ts}.json"
        with open(preventivo, 'w', encoding='utf-8') as f:
            call_command(
                'dumpdata',
                'productos', 'inventario', 'ventas', 'pagos', 'tasas',
                natural_foreign=True, natural_primary=True, indent=2, stdout=f
            )
    except Exception:
        pass


def _restaurar_desde_json(archivo):
    """
    Restaura tablas del sistema desde un archivo .json validando
    estrictamente que solo contenga datos de negocio autorizados
    (productos, inventario, ventas, pagos, tasas) y nunca usuarios ni permisos.
    """
    import json
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json')
    try:
        contenido_bytes = archivo.read()
        try:
            datos_json = json.loads(contenido_bytes.decode('utf-8'))
        except Exception as e:
            return JsonResponse({'error': f'Archivo JSON inválido o dañado: {str(e)}'}, status=400)

        if not isinstance(datos_json, list):
            return JsonResponse({'error': 'Estructura de copia de seguridad JSON inválida.'}, status=400)

        # Tablas de negocio permitidas
        TABLAS_PERMITIDAS = {
            'productos.producto',
            'inventario.entradamercancia',
            'ventas.venta',
            'ventas.detalleventa',
            'ventas.desgloseloteventa',
            'pagos.pagoventa',
            'pagos.gasto',
            'tasas.historialtasa',
        }

        # Validar cada registro
        registros_seguros = []
        for obj in datos_json:
            modelo = str(obj.get('model', '')).lower()
            if modelo.startswith(('auth.', 'contenttypes.', 'sessions.', 'admin.')):
                return JsonResponse({
                    'error': f'Acceso denegado: El archivo contiene datos restringidos de seguridad ({modelo}).'
                }, status=400)
            if modelo in TABLAS_PERMITIDAS:
                registros_seguros.append(obj)

        if not registros_seguros:
            return JsonResponse({'error': 'El archivo no contiene registros de inventario o ventas válidos.'}, status=400)

        with open(tmp_fd, 'w', encoding='utf-8') as tmp_file:
            json.dump(registros_seguros, tmp_file)

        call_command('loaddata', tmp_path)
        return JsonResponse({
            'exito': True,
            'mensaje': f'¡Copia de seguridad "{archivo.name}" restaurada con éxito! Se recuperaron {len(registros_seguros)} registros verificados.'
        })
    except Exception as e:
        return JsonResponse({'error': f'Error al restaurar archivo JSON: {str(e)}'}, status=400)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _procesar_hoja_entradas(ws):
    """
    Procesa la hoja de entradas reconociendo la identidad única de cada lote.
    Lotes distintos del mismo producto (ej: 5 y 7 unidades) se registran de forma
    independiente sumando al stock total (12 unidades).
    Solo actualiza si la fila indica un ID de lote ya existente en el sistema.
    """
    prods, entradas = 0, 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or len(row) < 7 or not row[2]:
            continue
        prod_nombre = str(row[2]).strip()
        try:
            cant_recibida = int(row[3] or 0)
            cant_disponible = int(row[4] if row[4] is not None else cant_recibida)
            costo_unit = Decimal(str(row[5] or 0))
            precio_venta = Decimal(str(row[6] or 0))
            obs = str(row[8] or '') if len(row) > 8 and row[8] else ''
        except Exception:
            continue

        if not prod_nombre or cant_recibida <= 0:
            continue

        prod, created = Producto.objects.get_or_create(
            nombre=prod_nombre,
            defaults={'activo': True, 'stock_minimo': 3}
        )
        if created:
            prods += 1

        # Identidad estricta por ID de Entrada si está presente en la columna 0
        entrada_existente = None
        if row[0] and str(row[0]).isdigit():
            entrada_existente = EntradaMercancia.objects.filter(id=int(row[0]), producto=prod).first()

        if entrada_existente:
            # En importación ordinaria de mercancía, NO se sobreescribe la cantidad_disponible viva del lote
            # para evitar reponer mercancía que ya fue vendida por FIFO.
            # Solo se actualizan precios, costos y observaciones.
            entrada_existente.costo_unitario = costo_unit
            entrada_existente.precio_venta = precio_venta
            if obs:
                entrada_existente.observaciones = obs
            entrada_existente.save(update_fields=['costo_unitario', 'precio_venta', 'observaciones'])
        else:
            # Nuevo lote independiente (conserva lotes múltiples: 5 + 7 = 12)
            # Para un lote nuevo, su stock disponible inicial es la cantidad recibida
            disp_inicial = min(cant_disponible, cant_recibida) if cant_disponible > 0 else cant_recibida
            EntradaMercancia.objects.create(
                producto=prod,
                cantidad_recibida=cant_recibida,
                cantidad_disponible=disp_inicial,
                costo_unitario=costo_unit,
                precio_venta=precio_venta,
                observaciones=obs
            )
        entradas += 1
    return prods, entradas


def _procesar_hoja_inventario(ws):
    """
    Procesa catálogo general respetando ceros y protegiendo el stock vivo:
    - Si el producto ya tiene historial de ventas o entradas, NO sobreescribe sus
      existencias con saldos antiguos de un Excel viejo (evita reponer mercancía vendida).
    - Si es un producto nuevo sin entradas previas, crea su lote inicial.
    """
    prods, entradas = 0, 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or len(row) < 3:
            continue
        prod_nombre = ""
        stock = 0
        costo = Decimal('0.00')
        precio = Decimal('0.00')

        if row[1] and isinstance(row[1], str) and not str(row[1]).isdigit():
            prod_nombre = str(row[1]).strip()
            try:
                stock = int(row[2] or 0)
                if len(row) > 5 and row[5] is not None:
                    costo = Decimal(str(row[5]))
                if len(row) > 6 and row[6] is not None:
                    precio = Decimal(str(row[6]))
            except Exception:
                pass
        elif row[0] and isinstance(row[0], str):
            prod_nombre = str(row[0]).strip()
            try:
                stock = int(row[1] or 0)
                if len(row) > 2 and row[2] is not None:
                    costo = Decimal(str(row[2]))
                if len(row) > 3 and row[3] is not None:
                    precio = Decimal(str(row[3]))
            except Exception:
                pass

        if not prod_nombre or prod_nombre.lower() in ('producto', 'nombre', 'id'):
            continue

        prod, created = Producto.objects.get_or_create(
            nombre=prod_nombre,
            defaults={'activo': True, 'stock_minimo': 3}
        )
        if created:
            prods += 1

        # Protección de existencias vivas:
        # Si el producto ya tiene entradas registradas, NO pisar sus existencias con el Excel viejo
        tiene_entradas_previas = EntradaMercancia.objects.filter(producto=prod).exists()
        if not tiene_entradas_previas and stock > 0:
            EntradaMercancia.objects.create(
                producto=prod,
                cantidad_recibida=stock,
                cantidad_disponible=stock,
                costo_unitario=costo,
                precio_venta=precio,
                observaciones="Carga inicial desde catálogo Excel"
            )
            entradas += 1
    return prods, entradas


def _restaurar_desde_excel(archivo):
    """
    Carga y procesa productos y entradas desde un reporte o catálogo Excel
    con transacción atómica y control de re-importación accidental del mismo archivo.
    """
    import hashlib
    from django.db import transaction
    try:
        # Leer y verificar hash del archivo para evitar importarlo dos veces por accidente
        contenido = archivo.read()
        archivo.seek(0)
        file_hash = hashlib.sha256(contenido).hexdigest()

        hash_file = settings.BASE_DIR / 'backups' / '.imported_excel_hashes'
        hash_file.parent.mkdir(parents=True, exist_ok=True)
        hashes_previos = set(hash_file.read_text(encoding='utf-8').splitlines()) if hash_file.exists() else set()

        if file_hash in hashes_previos:
            return JsonResponse({
                'error': f'El archivo "{archivo.name}" ya fue procesado anteriormente. Para evitar duplicaciones accidentales, no se permite volver a importar el mismo archivo exacto.'
            }, status=400)

        wb = openpyxl.load_workbook(archivo, data_only=True)
        with transaction.atomic():
            if "Entradas de Mercancía" in wb.sheetnames:
                prods, entradas = _procesar_hoja_entradas(wb["Entradas de Mercancía"])
            elif "Inventario Actual" in wb.sheetnames or len(wb.sheetnames) > 0:
                sheet_name = "Inventario Actual" if "Inventario Actual" in wb.sheetnames else wb.sheetnames[0]
                prods, entradas = _procesar_hoja_inventario(wb[sheet_name])
            else:
                return JsonResponse({'error': 'El archivo Excel no tiene hojas de inventario reconocibles.'}, status=400)

        # Registrar hash para proteger contra reenvíos accidentales
        with open(hash_file, 'a', encoding='utf-8') as hf:
            hf.write(file_hash + '\n')

        return JsonResponse({
            'exito': True,
            'mensaje': f'¡Excel "{archivo.name}" procesado con éxito! Se verificaron {prods} productos y se registraron {entradas} lotes correctamente.'
        })
    except Exception as e:
        return JsonResponse({'error': f'Error al leer archivo Excel: {str(e)}'}, status=400)


@login_required
@require_http_methods(["POST"])
def api_restaurar_copia(request):
    """
    Punto de entrada para restaurar copias de seguridad sin usar la terminal.
    Soporta archivos .json y archivos .xlsx.
    RESTRINGIDO: Solo administradores pueden ejecutar restauraciones.
    """
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({
            'error': 'Acceso denegado: Solo el administrador del negocio puede restaurar copias de seguridad.'
        }, status=403)

    archivo = request.FILES.get('archivo')
    if not archivo:
        return JsonResponse({'error': 'Debes seleccionar un archivo para restaurar.'}, status=400)

    nombre = archivo.name.lower()
    _guardar_respaldo_preventivo()

    if nombre.endswith('.json'):
        return _restaurar_desde_json(archivo)
    elif nombre.endswith('.xlsx'):
        return _restaurar_desde_excel(archivo)
    else:
        return JsonResponse({
            'error': 'Formato no admitido. Selecciona un archivo de copia de seguridad .json o un reporte .xlsx.'
        }, status=400)



@login_required
@require_http_methods(["POST"])
def api_reiniciar_sistema(request):
    """
    Permite limpiar datos de prueba y empezar de 0 de forma segura.
    Opciones:
    - 'solo_ventas_gastos': Elimina ventas, cobros y gastos de prueba, restituyendo el stock original de las entradas.
    - 'todo_a_cero': Elimina todas las ventas, cobros, gastos, entradas y productos para iniciar el inventario 100% limpio.
    """
    try:
        import json
        from ventas.models import Venta, DetalleVenta, DesgloseLoteVenta
        from pagos.models import PagoVenta, Gasto
        from inventario.models import EntradaMercancia
        from productos.models import Producto

        data = json.loads(request.body) if request.body else {}
        modo = data.get('modo', 'todo_a_cero')

        # Eliminar siempre movimientos de prueba
        DesgloseLoteVenta.objects.all().delete()
        DetalleVenta.objects.all().delete()
        PagoVenta.objects.all().delete()
        Venta.objects.all().delete()
        Gasto.objects.all().delete()

        if modo == 'solo_ventas_gastos':
            for e in EntradaMercancia.objects.all():
                e.cantidad_disponible = e.cantidad_recibida
                e.save(update_fields=['cantidad_disponible'])
            return JsonResponse({
                'ok': True,
                'mensaje': 'Se limpiaron todas las ventas y gastos de prueba. El catálogo y las existencias originales fueron restituidos.'
            })

        elif modo == 'todo_a_cero':
            EntradaMercancia.objects.all().delete()
            Producto.objects.all().delete()
            from django.db import connection
            if connection.vendor == 'postgresql':
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("VACUUM;")
                except Exception:
                    pass
            return JsonResponse({
                'ok': True,
                'mensaje': 'Sistema reiniciado con éxito. Todos los productos, entradas, ventas y gastos fueron eliminados. La base de datos está en 0.'
            })

        return JsonResponse({'error': 'Modo de reinicio no válido.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error al reiniciar: {str(e)}'}, status=500)


@login_required
@require_http_methods(["GET"])
def api_almacenamiento(request):
    """
    Monitorea el tamaño de la base de datos (PostgreSQL o SQLite)
    y alerta si supera el 95% de la capacidad de 1 GB.
    """
    from django.db import connection
    bytes_usados = 0
    motor = connection.vendor

    if motor == 'postgresql':
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_database_size(current_database());")
                row = cursor.fetchone()
                if row:
                    bytes_usados = int(row[0])
        except Exception:
            bytes_usados = 67 * 1024 * 1024  # Resguardo aproximado
    else:
        try:
            db_path = settings.DATABASES['default']['NAME']
            if os.path.exists(db_path):
                bytes_usados = os.path.getsize(db_path)
        except Exception:
            bytes_usados = 0

    limite_bytes = 1024 * 1024 * 1024  # 1 GB en bytes
    porcentaje = round((bytes_usados / limite_bytes) * 100, 2)
    mb_usados = round(bytes_usados / (1024 * 1024), 2)

    # Permitir prueba controlada (?simular=95) para validar visualmente la alerta
    simular = request.GET.get('simular')
    if simular:
        try:
            porcentaje = float(simular)
        except ValueError:
            pass

    alerta_critica = porcentaje >= 95.0

    return JsonResponse({
        'bytes_usados': bytes_usados,
        'mb_usados': mb_usados,
        'limite_mb': 1024,
        'porcentaje': porcentaje,
        'alerta_critica': alerta_critica
    })


@login_required
@require_http_methods(["GET"])
def descargar_respaldo_zip(request):
    """
    Genera y descarga un archivo .zip único con fecha y hora:
    1. Reporte Financiero Completo en Excel (.xlsx) con todas las hojas.
    2. Copia de Seguridad completa en JSON (.json) de productos, lotes, ventas, cobros, gastos y tasas.
    3. Documento de texto resumen explicativo.
    """
    ts = timezone.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. Excel completo con todas las pestañas
        try:
            wb = generar_excel_completo(None, None)
            excel_bytes = BytesIO()
            wb.save(excel_bytes)
            excel_bytes.seek(0)
            zf.writestr(f"Osma-Reporte-Completo_{ts}.xlsx", excel_bytes.getvalue())
        except Exception as e:
            zf.writestr("error_excel.txt", str(e))

        # 2. Copia de seguridad en JSON lista para restauración inmediata
        try:
            buf = StringIO()
            call_command(
                'dumpdata',
                'productos', 'inventario', 'ventas', 'pagos', 'tasas',
                natural_foreign=True, natural_primary=True, indent=2, stdout=buf
            )
            zf.writestr(f"Osma-Base-Datos_{ts}.json", buf.getvalue())
        except Exception as e:
            zf.writestr("error_json.txt", str(e))

        # 3. Archivo resumen de información
        info_txt = (
            f"=====================================================\n"
            f"RESPALDO COMPLETO DE SEGURIDAD - OSMA COSMETICS\n"
            f"Fecha y Hora: {timezone.now().strftime('%d/%m/%Y %I:%M:%S %p')}\n"
            f"=====================================================\n\n"
            f"Este archivo ZIP contiene:\n"
            f"1. Osma-Reporte-Completo_{ts}.xlsx:\n"
            f"   Libro de cálculo Excel con el resumen financiero, histórico de ventas,\n"
            f"   catálogo y existencias, y gastos del negocio.\n\n"
            f"2. Osma-Base-Datos_{ts}.json:\n"
            f"   Archivo de datos estructurado que puede restaurarse en cualquier momento\n"
            f"   desde el panel del sistema en 'Restaurar copia de seguridad'.\n"
        )
        zf.writestr(f"LEEME_{ts}.txt", info_txt)

    zip_buffer.seek(0)
    filename = f"Respaldo_Total_OSMA_{ts}.zip"
    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
