import os
import tempfile
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
        ventas_data.append({
            'codigo': v.codigo,
            'fecha': v.fecha.strftime("%d/%m/%Y %H:%M"),
            'total_bs': float(v.total_bs),
            'costo_total_bs': float(v.costo_total_bs),
            'ganancia_bruta_bs': float(v.ganancia_bruta_bs),
            'articulos': articulos_str,
            'medios': medios_str
        })

    cobros_json = []
    for c in resumen['cobros_por_medio']:
        cobros_json.append({
            'metodo': c['metodo'],
            'moneda': c['moneda'],
            'total_original': float(c['total_original']),
            'total_bs': float(c['total_bs']),
            'transacciones': c['cantidad_transacciones']
        })

    return JsonResponse({
        'total_ingresos': float(resumen['total_ingresos']),
        'total_costos': float(resumen['total_costos']),
        'total_ganancia': float(resumen['total_ganancia']),
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
    """Restaura todas las tablas del sistema desde un archivo .json de dumpdata."""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json')
    try:
        with open(tmp_fd, 'wb') as tmp_file:
            for chunk in archivo.chunks():
                tmp_file.write(chunk)
        call_command('loaddata', tmp_path)
        return JsonResponse({
            'exito': True,
            'mensaje': f'¡Copia de seguridad "{archivo.name}" restaurada con éxito! Todos los productos, existencias y ventas han sido recuperados.'
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
    prods, entradas = 0, 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or len(row) < 7 or not row[2]:
            continue
        prod_nombre = str(row[2]).strip()
        try:
            cant_recibida = int(row[3] or 0)
            cant_disponible = int(row[4] or cant_recibida)
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

        EntradaMercancia.objects.create(
            producto=prod,
            cantidad_recibida=cant_recibida,
            cantidad_disponible=cant_disponible,
            costo_unitario=costo_unit,
            precio_venta=precio_venta,
            observaciones=obs
        )
        entradas += 1
    return prods, entradas


def _procesar_hoja_inventario(ws):
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

        if stock > 0:
            EntradaMercancia.objects.create(
                producto=prod,
                cantidad_recibida=stock,
                cantidad_disponible=stock,
                costo_unitario=costo,
                precio_venta=precio,
                observaciones="Recuperado desde Excel"
            )
            entradas += 1
    return prods, entradas


def _restaurar_desde_excel(archivo):
    """Carga y procesa productos y entradas desde un reporte o catálogo Excel."""
    try:
        wb = openpyxl.load_workbook(archivo, data_only=True)
        if "Entradas de Mercancía" in wb.sheetnames:
            prods, entradas = _procesar_hoja_entradas(wb["Entradas de Mercancía"])
        elif "Inventario Actual" in wb.sheetnames or len(wb.sheetnames) > 0:
            sheet_name = "Inventario Actual" if "Inventario Actual" in wb.sheetnames else wb.sheetnames[0]
            prods, entradas = _procesar_hoja_inventario(wb[sheet_name])
        else:
            return JsonResponse({'error': 'El archivo Excel no tiene hojas de inventario reconocibles.'}, status=400)

        return JsonResponse({
            'exito': True,
            'mensaje': f'¡Excel "{archivo.name}" procesado con éxito! Se cargaron/actualizaron {prods} productos y {entradas} registros de existencias.'
        })
    except Exception as e:
        return JsonResponse({'error': f'Error al leer archivo Excel: {str(e)}'}, status=400)


@login_required
@require_http_methods(["POST"])
def api_restaurar_copia(request):
    """
    Punto de entrada para restaurar copias de seguridad sin usar la terminal.
    Soporta archivos .json y archivos .xlsx.
    """
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

