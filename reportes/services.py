from decimal import Decimal
from datetime import datetime, time
from django.utils import timezone
from django.db.models import Sum, Count, F
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from productos.models import Producto
from inventario.models import EntradaMercancia
from ventas.models import Venta, DetalleVenta
from pagos.models import PagoVenta

def obtener_resumen_periodo(desde_dt=None, hasta_dt=None):
    """
    Calcula las métricas financieras y operativas para el rango de fechas especificado.
    """
    ventas_qs = Venta.objects.filter(anulada=False)
    if desde_dt:
        ventas_qs = ventas_qs.filter(fecha__gte=desde_dt)
    if hasta_dt:
        ventas_qs = ventas_qs.filter(fecha__lte=hasta_dt)

    totales_ventas = ventas_qs.aggregate(
        total_ingresos=Sum('total_bs'),
        total_costos=Sum('costo_total_bs'),
        total_ganancia=Sum('ganancia_bruta_bs'),
        num_ventas=Count('id')
    )

    total_ingresos = totales_ventas['total_ingresos'] or Decimal('0.00')
    total_costos = totales_ventas['total_costos'] or Decimal('0.00')
    total_ganancia = totales_ventas['total_ganancia'] or Decimal('0.00')
    num_ventas = totales_ventas['num_ventas'] or 0

    # Total unidades vendidas
    detalles_qs = DetalleVenta.objects.filter(venta__in=ventas_qs)
    total_unidades_vendidas = detalles_qs.aggregate(total_uds=Sum('cantidad'))['total_uds'] or 0

    # Productos más vendidos
    productos_vendidos = (
        detalles_qs.values('producto__nombre')
        .annotate(
            unidades=Sum('cantidad'),
            ingresos=Sum('subtotal_bs'),
            costo=Sum('costo_total_bs'),
            ganancia=Sum('ganancia_bruta_bs')
        )
        .order_by('-unidades')
    )

    # Cobros agrupados por medio de pago
    pagos_qs = PagoVenta.objects.filter(venta__in=ventas_qs)
    cobros_por_medio = (
        pagos_qs.values('metodo', 'moneda')
        .annotate(
            total_original=Sum('monto_original'),
            total_bs=Sum('monto_equivalente_bs'),
            cantidad_transacciones=Count('id')
        )
        .order_by('metodo')
    )

    # Inventario actual y alertas
    productos_activos = Producto.objects.filter(activo=True)
    productos_alerta = []
    for prod in productos_activos:
        estado = prod.estado_stock
        if estado in ('agotado', 'minimo'):
            productos_alerta.append({
                'nombre': prod.nombre,
                'stock_actual': prod.stock_total,
                'stock_minimo': prod.stock_minimo,
                'estado': estado,
            })

    return {
        'total_ingresos': total_ingresos,
        'total_costos': total_costos,
        'total_ganancia': total_ganancia,
        'num_ventas': num_ventas,
        'total_unidades_vendidas': total_unidades_vendidas,
        'productos_vendidos': list(productos_vendidos),
        'cobros_por_medio': list(cobros_por_medio),
        'productos_alerta': productos_alerta,
        'ventas_listado': ventas_qs.prefetch_related('detalles__producto', 'pagos')[:100],
    }


def generar_excel_completo(desde_dt=None, hasta_dt=None):
    """
    Genera un libro Excel con 4 pestañas:
    1. Inventario actual
    2. Entradas de mercancía
    3. Ventas y ganancia bruta
    4. Pagos por medio
    """
    wb = openpyxl.Workbook()
    
    # Estilos elegantes basados en la paleta Osma
    header_fill = PatternFill(start_color="222320", end_color="222320", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    accent_fill = PatternFill(start_color="D6EBE5", end_color="D6EBE5", fill_type="solid")
    bold_font = Font(name="Calibri", size=11, bold=True)
    thin_border = Border(
        left=Side(style='thin', color='E0E0E0'),
        right=Side(style='thin', color='E0E0E0'),
        top=Side(style='thin', color='E0E0E0'),
        bottom=Side(style='thin', color='E0E0E0')
    )

    # ----------------------------------------------------
    # Hoja 1: Inventario
    # ----------------------------------------------------
    ws_inv = wb.active
    ws_inv.title = "Inventario Actual"

    headers_inv = [
        "ID", "Producto", "Stock Actual", "Mínimo Alerta", 
        "Estado", "Último Costo (Bs)", "Último Precio Venta (Bs)", 
        "Valor Venta Stock (Bs)"
    ]
    ws_inv.append(headers_inv)

    for col_num in range(1, len(headers_inv) + 1):
        cell = ws_inv.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    productos = Producto.objects.filter(activo=True).order_by('nombre')
    for p in productos:
        st = p.stock_total
        estado_label = "Agotado" if st == 0 else ("Bajo mínimo" if st <= p.stock_minimo else "Normal")
        ultimo_costo = p.ultimo_costo or Decimal('0.00')
        ultimo_precio = p.ultimo_precio_venta or Decimal('0.00')
        valor_venta = st * ultimo_precio

        row = [
            p.id,
            p.nombre,
            st,
            p.stock_minimo,
            estado_label,
            float(ultimo_costo),
            float(ultimo_precio),
            float(valor_venta)
        ]
        ws_inv.append(row)

    # ----------------------------------------------------
    # Hoja 2: Entradas de Mercancía
    # ----------------------------------------------------
    ws_ent = wb.create_sheet(title="Entradas de Mercancía")
    headers_ent = [
        "ID", "Fecha", "Producto", "Cant. Recibida", 
        "Cant. Disponible", "Costo Unit. (Bs)", "Precio Venta (Bs)", 
        "Costo Total (Bs)", "Observaciones"
    ]
    ws_ent.append(headers_ent)
    for col_num in range(1, len(headers_ent) + 1):
        cell = ws_ent.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    entradas = EntradaMercancia.objects.all().select_related('producto').order_by('-fecha_entrada')
    if desde_dt:
        entradas = entradas.filter(fecha_entrada__gte=desde_dt)
    if hasta_dt:
        entradas = entradas.filter(fecha_entrada__lte=hasta_dt)

    for e in entradas:
        ws_ent.append([
            e.id,
            e.fecha_entrada.strftime("%d/%m/%Y %H:%M"),
            e.producto.nombre,
            e.cantidad_recibida,
            e.cantidad_disponible,
            float(e.costo_unitario),
            float(e.precio_venta),
            float(e.valor_costo_total_inicial),
            e.observaciones
        ])

    # ----------------------------------------------------
    # Hoja 3: Ventas y Ganancia Bruta
    # ----------------------------------------------------
    ws_ven = wb.create_sheet(title="Ventas y Ganancia")
    headers_ven = [
        "Código Venta", "Fecha", "Total Venta (Bs)", 
        "Costo Mercancía (Bs)", "Ganancia Bruta (Bs)", 
        "Tasa USD BCV", "Tasa USDT", "Observaciones"
    ]
    ws_ven.append(headers_ven)
    for col_num in range(1, len(headers_ven) + 1):
        cell = ws_ven.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ventas = Venta.objects.filter(anulada=False).order_by('-fecha')
    if desde_dt:
        ventas = ventas.filter(fecha__gte=desde_dt)
    if hasta_dt:
        ventas = ventas.filter(fecha__lte=hasta_dt)

    for v in ventas:
        ws_ven.append([
            v.codigo,
            v.fecha.strftime("%d/%m/%Y %H:%M"),
            float(v.total_bs),
            float(v.costo_total_bs),
            float(v.ganancia_bruta_bs),
            float(v.tasa_usd_bcv),
            float(v.tasa_usdt),
            v.observaciones
        ])

    # ----------------------------------------------------
    # Hoja 4: Pagos
    # ----------------------------------------------------
    ws_pag = wb.create_sheet(title="Detalle de Pagos")
    headers_pag = [
        "Venta", "Fecha", "Medio", "Monto Original", 
        "Moneda", "Tasa Aplicada", "Equivalente Bs", "Referencia"
    ]
    ws_pag.append(headers_pag)
    for col_num in range(1, len(headers_pag) + 1):
        cell = ws_pag.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    pagos = PagoVenta.objects.filter(venta__anulada=False).select_related('venta').order_by('-venta__fecha')
    if desde_dt:
        pagos = pagos.filter(venta__fecha__gte=desde_dt)
    if hasta_dt:
        pagos = pagos.filter(venta__fecha__lte=hasta_dt)

    for p in pagos:
        ws_pag.append([
            p.venta.codigo,
            p.venta.fecha.strftime("%d/%m/%Y %H:%M"),
            p.get_metodo_display(),
            float(p.monto_original),
            p.moneda,
            float(p.tasa_aplicada),
            float(p.monto_equivalente_bs),
            p.referencia
        ])

    # Autoajuste de anchos de columna en todas las hojas
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            sheet.column_dimensions[col_letter].width = max(max_len + 3, 12)

    return wb

