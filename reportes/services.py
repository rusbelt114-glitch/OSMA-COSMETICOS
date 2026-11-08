from decimal import Decimal
from datetime import datetime, time
from django.utils import timezone
from django.db.models import Sum, Count, F, Q
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from productos.models import Producto
from inventario.models import EntradaMercancia
from ventas.models import Venta, DetalleVenta
from pagos.models import PagoVenta, Gasto
from tasas.models import HistorialTasa

def obtener_resumen_periodo(desde_dt=None, hasta_dt=None):
    """
    Calcula las métricas financieras y operativas del negocio:
    - Ganancia bruta = Ventas − Costo de lo vendido (FIFO)
    - Gastos operativos del negocio (Tienda)
    - Resultado después de gastos operativos = Ganancia bruta − Gastos operativos
    - Retiros personales del dueño (informados por separado)
    - Inversión en existencias y venta potencial del inventario actual
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

    # Cobros agrupados por medio y moneda (distinguiendo recibido, vuelto y cobro neto)
    pagos_qs = PagoVenta.objects.filter(venta__in=ventas_qs)
    cobros_por_medio = (
        pagos_qs.values('metodo', 'moneda')
        .annotate(
            monto_recibido=Sum(F('monto_recibido')),
            vuelto_entregado_bs=Sum('vuelto_entregado_bs'),
            total_neto_orig=Sum('monto_original'),
            total_neto_bs=Sum('monto_equivalente_bs'),
            cantidad_transacciones=Count('id')
        )
        .order_by('metodo')
    )

    # Gastos y retiros del período (Tienda vs Personal)
    gastos_qs = Gasto.objects.all()
    if desde_dt:
        gastos_qs = gastos_qs.filter(fecha__gte=desde_dt)
    if hasta_dt:
        gastos_qs = gastos_qs.filter(fecha__lte=hasta_dt)

    total_gastos_tienda = gastos_qs.filter(categoria='TIENDA').aggregate(total=Sum('monto_equivalente_bs'))['total'] or Decimal('0.00')
    total_gastos_personal = gastos_qs.filter(categoria='PERSONAL').aggregate(total=Sum('monto_equivalente_bs'))['total'] or Decimal('0.00')
    total_gastos_general = total_gastos_tienda + total_gastos_personal

    # Resultado después de gastos operativos (Ganancia de ventas menos gastos de la tienda)
    resultado_despues_gastos = total_ganancia - total_gastos_tienda
    # Saldo final real del negocio / caja (después de gastos de tienda y retiros personales del dueño)
    saldo_caja_real = resultado_despues_gastos - total_gastos_personal

    # Tasa actual para valoración del inventario presente en almacén
    tasa_bcv = HistorialTasa.obtener_ultima_tasa('USD_BCV') or Decimal('896.12')
    if tasa_bcv <= Decimal('0.00'):
        tasa_bcv = Decimal('1.00')

    # TOTALES EN USD CONGELADOS HISTÓRICAMENTE:
    # Cada venta y pago en efectivo USD respeta su valor original sin sufrir recálculos por tasas futuras.
    total_ingresos_usd = Decimal('0.00')
    total_costos_usd = Decimal('0.00')
    total_ganancia_usd = Decimal('0.00')
    for v in ventas_qs:
        if v.total_usd and v.total_usd > Decimal('0.00'):
            total_ingresos_usd += v.total_usd
            total_costos_usd += v.costo_total_usd
            total_ganancia_usd += v.ganancia_bruta_usd
        else:
            t_v = v.tasa_usd_bcv if v.tasa_usd_bcv > Decimal('0.00') else tasa_bcv
            ing_u = (v.total_bs / t_v).quantize(Decimal('0.01'))
            cos_u = (v.costo_total_bs / t_v).quantize(Decimal('0.01'))
            total_ingresos_usd += ing_u
            total_costos_usd += cos_u
            total_ganancia_usd += (ing_u - cos_u)

    # GASTOS EN USD HISTÓRICOS:
    total_gastos_tienda_usd = Decimal('0.00')
    total_gastos_personal_usd = Decimal('0.00')
    for g in gastos_qs:
        if g.moneda in ('USD', 'USDT'):
            m_usd = g.monto_original
        else:
            t_g = g.tasa_aplicada if g.tasa_aplicada > Decimal('0.00') else tasa_bcv
            m_usd = (g.monto_original / t_g).quantize(Decimal('0.01'))
        if g.categoria == 'TIENDA':
            total_gastos_tienda_usd += m_usd
        else:
            total_gastos_personal_usd += m_usd

    resultado_despues_gastos_usd = total_ganancia_usd - total_gastos_tienda_usd
    saldo_caja_real_usd = resultado_despues_gastos_usd - total_gastos_personal_usd

    def a_usd(monto_bs):
        return (Decimal(str(monto_bs)) / tasa_bcv).quantize(Decimal('0.01'))

    # Inventario actual (a la fecha y hora de la consulta, independiente del período de ventas)
    entradas_activas = EntradaMercancia.objects.filter(cantidad_disponible__gt=0, producto__activo=True)
    inv_agregados = entradas_activas.aggregate(
        total_uds=Sum('cantidad_disponible'),
        inversion_costo=Sum(F('cantidad_disponible') * F('costo_unitario')),
        venta_potencial=Sum(F('cantidad_disponible') * F('precio_venta'))
    )
    total_uds_inv = inv_agregados['total_uds'] or 0
    inversion_existencias = inv_agregados['inversion_costo'] or Decimal('0.00')
    venta_potencial = inv_agregados['venta_potencial'] or Decimal('0.00')
    ganancia_potencial = venta_potencial - inversion_existencias

    inversion_existencias_usd = a_usd(inversion_existencias)
    venta_potencial_usd = a_usd(venta_potencial)
    ganancia_potencial_usd = a_usd(ganancia_potencial)

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

    fecha_consulta_inv = timezone.localtime(timezone.now()).strftime("%d/%m/%Y %I:%M %p")

    return {
        'total_ingresos': total_ingresos,
        'total_ingresos_usd': total_ingresos_usd,
        'total_costos': total_costos,
        'total_costos_usd': total_costos_usd,
        'total_ganancia': total_ganancia,
        'total_ganancia_usd': total_ganancia_usd,
        'total_gastos_tienda': total_gastos_tienda,
        'total_gastos_tienda_usd': total_gastos_tienda_usd,
        'total_gastos_personal': total_gastos_personal,
        'total_gastos_personal_usd': total_gastos_personal_usd,
        'total_gastos_general': total_gastos_general,
        'total_gastos_general_usd': a_usd(total_gastos_general),
        'resultado_despues_gastos': resultado_despues_gastos,
        'resultado_despues_gastos_usd': resultado_despues_gastos_usd,
        'saldo_caja_real': saldo_caja_real,
        'saldo_caja_real_usd': saldo_caja_real_usd,
        'tasa_usd_bcv': tasa_bcv,
        'num_ventas': num_ventas,
        'total_unidades_vendidas': total_unidades_vendidas,
        'productos_vendidos': list(productos_vendidos),
        'cobros_por_medio': list(cobros_por_medio),
        'productos_alerta': productos_alerta,
        'inventario_actual': {
            'fecha_consulta': fecha_consulta_inv,
            'total_productos_activos': productos_activos.count(),
            'unidades_disponibles': total_uds_inv,
            'inversion_existencias': inversion_existencias,
            'inversion_existencias_usd': inversion_existencias_usd,
            'venta_potencial': venta_potencial,
            'venta_potencial_usd': venta_potencial_usd,
            'ganancia_potencial': ganancia_potencial,
            'ganancia_potencial_usd': ganancia_potencial_usd,
            'nota': 'La venta total esperada es el valor a precio de venta registrado, y la ganancia esperada es lo que dejará este inventario cuando se venda por completo.'
        },
        'ventas_listado': ventas_qs.prefetch_related('detalles__producto', 'pagos')[:100],
    }


def generar_excel_completo(desde_dt=None, hasta_dt=None):
    """
    Genera un libro Excel profesional con 5 pestañas completas y auditables:
    1. Inventario actual (inversión en existencias y venta potencial)
    2. Entradas de mercancía (lotes y trazabilidad histórica)
    3. Ventas y ganancia bruta (FIFO, fecha/hora 12h Caracas)
    4. Cobros y pagos (recibido, vuelto y cobro neto)
    5. Gastos y retiros (Gastos operativos de tienda vs Retiros personales del dueño)
    """
    wb = openpyxl.Workbook()
    
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
    # Hoja 1: Inventario Actual
    # ----------------------------------------------------
    ws_inv = wb.active
    ws_inv.title = "Inventario Actual"

    headers_inv = [
        "ID", "Producto", "Stock Actual", "Mínimo Alerta", 
        "Estado", "Último Costo (Bs)", "Último Precio Venta (Bs)", 
        "Inversión en Existencias (Bs)", "Venta Potencial (Bs)"
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
        
        # Inversión exacta en existencias basada en lotes vigentes
        inv_costo = EntradaMercancia.objects.filter(producto=p, cantidad_disponible__gt=0).aggregate(
            tot=Sum(F('cantidad_disponible') * F('costo_unitario'))
        )['tot'] or Decimal('0.00')
        
        inv_venta = EntradaMercancia.objects.filter(producto=p, cantidad_disponible__gt=0).aggregate(
            tot=Sum(F('cantidad_disponible') * F('precio_venta'))
        )['tot'] or Decimal('0.00')

        ultimo_costo = p.entradas.order_by('-fecha_entrada', '-id').values_list('costo_unitario', flat=True).first() or Decimal('0.00')
        ultimo_precio = p.ultimo_precio_venta or Decimal('0.00')

        row = [
            p.id,
            p.nombre,
            st,
            p.stock_minimo,
            estado_label,
            float(ultimo_costo),
            float(ultimo_precio),
            float(inv_costo),
            float(inv_venta)
        ]
        ws_inv.append(row)

    # ----------------------------------------------------
    # Hoja 2: Entradas de Mercancía
    # ----------------------------------------------------
    ws_ent = wb.create_sheet(title="Entradas de Mercancía")
    headers_ent = [
        "ID", "Fecha y Hora (Caracas)", "Producto", "Cant. Recibida", 
        "Cant. Disponible", "Costo Unit. (Bs)", "Precio Venta (Bs)", 
        "Inversión Inicial (Bs)", "Observaciones"
    ]
    ws_ent.append(headers_ent)
    for col_num in range(1, len(headers_ent) + 1):
        cell = ws_ent.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    entradas = EntradaMercancia.objects.all().select_related('producto').order_by('-fecha_entrada', '-id')
    if desde_dt:
        entradas = entradas.filter(fecha_entrada__gte=desde_dt)
    if hasta_dt:
        entradas = entradas.filter(fecha_entrada__lte=hasta_dt)

    for e in entradas:
        ws_ent.append([
            e.id,
            timezone.localtime(e.fecha_entrada).strftime("%d/%m/%Y %I:%M %p"),
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
        "Código Venta", "Fecha y Hora (Caracas)", "Total Venta (Bs)", "Total Venta ($)",
        "Costo Mercancía (Bs)", "Costo ($)", "Ganancia Bruta (Bs)", "Ganancia Bruta ($)",
        "Vuelto Entregado (Bs)", "Tasa USD BCV", "Tasa USDT", "Observaciones"
    ]
    ws_ven.append(headers_ven)
    for col_num in range(1, len(headers_ven) + 1):
        cell = ws_ven.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ventas = Venta.objects.filter(anulada=False).order_by('-fecha', '-id')
    if desde_dt:
        ventas = ventas.filter(fecha__gte=desde_dt)
    if hasta_dt:
        ventas = ventas.filter(fecha__lte=hasta_dt)

    for v in ventas:
        t_v = v.tasa_usd_bcv if v.tasa_usd_bcv > 0 else Decimal('1.00')
        tot_u = float(v.total_usd) if v.total_usd > 0 else float((v.total_bs / t_v).quantize(Decimal('0.01')))
        cos_u = float(v.costo_total_usd) if v.costo_total_usd > 0 else float((v.costo_total_bs / t_v).quantize(Decimal('0.01')))
        gan_u = float(v.ganancia_bruta_usd) if v.ganancia_bruta_usd > 0 else float(tot_u - cos_u)

        ws_ven.append([
            v.codigo,
            timezone.localtime(v.fecha).strftime("%d/%m/%Y %I:%M %p"),
            float(v.total_bs),
            tot_u,
            float(v.costo_total_bs),
            cos_u,
            float(v.ganancia_bruta_bs),
            gan_u,
            float(v.vuelto_total_bs),
            float(v.tasa_usd_bcv),
            float(v.tasa_usdt),
            v.observaciones
        ])

    # ----------------------------------------------------
    # Hoja 4: Cobros y Pagos
    # ----------------------------------------------------
    ws_pag = wb.create_sheet(title="Cobros y Pagos")
    headers_pag = [
        "Venta", "Fecha y Hora", "Medio", "Moneda", 
        "Monto Recibido", "Vuelto Entregado", "Cobro Neto (Orig)", 
        "Tasa Aplicada", "Cobro Neto (Bs)", "Referencia"
    ]
    ws_pag.append(headers_pag)
    for col_num in range(1, len(headers_pag) + 1):
        cell = ws_pag.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    pagos = PagoVenta.objects.filter(venta__anulada=False).select_related('venta').order_by('-venta__fecha', '-id')
    if desde_dt:
        pagos = pagos.filter(venta__fecha__gte=desde_dt)
    if hasta_dt:
        pagos = pagos.filter(venta__fecha__lte=hasta_dt)

    for p in pagos:
        ws_pag.append([
            p.venta.codigo,
            timezone.localtime(p.venta.fecha).strftime("%d/%m/%Y %I:%M %p"),
            p.get_metodo_display(),
            p.moneda,
            float(p.monto_recibido or p.monto_original),
            float(p.vuelto_entregado),
            float(p.monto_original),
            float(p.tasa_aplicada),
            float(p.monto_equivalente_bs),
            p.referencia
        ])

    # ----------------------------------------------------
    # Hoja 5: Gastos y Retiros
    # ----------------------------------------------------
    ws_gas = wb.create_sheet(title="Gastos y Retiros")
    headers_gas = [
        "ID", "Fecha y Hora", "Categoría", "Descripción / Concepto", 
        "Monto Original", "Moneda", "Tasa Aplicada", "Monto Equivalente (Bs)", 
        "Medio Pago", "Comprobante", "Observaciones"
    ]
    ws_gas.append(headers_gas)
    for col_num in range(1, len(headers_gas) + 1):
        cell = ws_gas.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    gastos_list = Gasto.objects.all().order_by('-fecha', '-id')
    if desde_dt:
        gastos_list = gastos_list.filter(fecha__gte=desde_dt)
    if hasta_dt:
        gastos_list = gastos_list.filter(fecha__lte=hasta_dt)

    for g in gastos_list:
        ws_gas.append([
            g.id,
            timezone.localtime(g.fecha).strftime("%d/%m/%Y %I:%M %p"),
            g.get_categoria_display(),
            g.descripcion,
            float(g.monto_original),
            g.moneda,
            float(g.tasa_aplicada),
            float(g.monto_equivalente_bs),
            g.get_metodo_display(),
            g.comprobante,
            g.observaciones
        ])

    # Formato numérico profesional con separador de miles y decimales en todas las hojas
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, (float, Decimal)):
                    cell.number_format = '#,##0.00'
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif isinstance(cell.value, int) and cell.column != 1:  # Ignorar columna de ID
                    cell.number_format = '#,##0'
                    cell.alignment = Alignment(horizontal="right", vertical="center")

    # Autoajuste de anchos de columna en todas las hojas
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            sheet.column_dimensions[col_letter].width = max(max_len + 3, 12)

    return wb
