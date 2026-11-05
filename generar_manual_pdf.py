import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#666666"))
        
        # Header en páginas 2 en adelante
        if self._pageNumber > 1:
            self.drawString(40, 755, "OSMA COSMETICS · Manual Operativo del Sistema")
            self.setStrokeColor(colors.HexColor("#DCEAE0"))
            self.setLineWidth(0.5)
            self.line(40, 747, 572, 747)

        # Footer en todas las páginas
        texto = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(572, 35, texto)
        self.drawString(40, 35, "Documento confidencial para uso operativo de tienda · 04/11/2026")
        self.setStrokeColor(colors.HexColor("#DCEAE0"))
        self.setLineWidth(0.5)
        self.line(40, 48, 572, 48)
        self.restoreState()

def build_pdf():
    pdf_filename = "MANUAL_Y_RESUMEN_OPERATIVO_OSMA.pdf"
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=50,
        bottomMargin=55
    )

    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    brand_primary = colors.HexColor("#222320")
    brand_green = colors.HexColor("#376d5e")
    brand_light_green = colors.HexColor("#e8efe9")
    text_color = colors.HexColor("#2d312e")
    muted_color = colors.HexColor("#666666")

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=brand_primary,
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=brand_green,
        spaceAfter=15
    )
    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=brand_green,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=brand_primary,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=text_color,
        spaceAfter=5
    )
    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=text_color,
        leftIndent=14,
        spaceAfter=3
    )
    badge_style = ParagraphStyle(
        'Badge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=text_color
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11.5,
        textColor=brand_primary
    )
    table_head = ParagraphStyle(
        'TableHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )

    story = []

    # ENCABEZADO PRINCIPAL
    story.append(Paragraph("OSMA COSMETICS", title_style))
    story.append(Paragraph("MANUAL DE USUARIO, FUNCIONES DEL SISTEMA Y RESUMEN OPERATIVO", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=brand_green, spaceAfter=12))

    # RESUMEN EJECUTIVO
    resumen_text = (
        "El presente documento detalla la arquitectura, características y la función exacta de cada botón y módulo "
        "del sistema web de punto de venta e inventario desarrollado para <b>Osma Cosmetics</b>. El sistema opera de forma "
        "local en la computadora de la tienda con base de datos SQLite de alta velocidad y cero costos de alojamiento, "
        "blindado contra fallas de conexión o recargas accidentales, y con arquitectura lista para PostgreSQL en la nube."
    )
    story.append(Paragraph(resumen_text, body_style))
    story.append(Spacer(1, 8))

    # SECCIÓN 1: ARQUITECTURA Y DECISIONES TÉCNICAS CLAVE
    story.append(Paragraph("1. Arquitectura y Reglas de Negocio Implementadas", h1_style))
    story.append(Paragraph("<b>• Acceso Simplificado de Tienda:</b> Pantalla de bloqueo rápida con clave compartida del equipo, botón para visualizar la contraseña (ojo de mostrar/ocultar) y apertura instantánea.", bullet_style))
    story.append(Paragraph("<b>• Cobro Multi-moneda con Tasa Congelada:</b> Cada venta permite cobrar combinando Efectivo Bs, Pago Móvil, Efectivo USD y USDT. La tasa de cambio vigente se congela en el ticket de venta para auditorías contables exactas.", bullet_style))
    story.append(Paragraph("<b>• Valuación de Costo y Ganancia Real por FIFO (PEPS):</b> El sistema descuenta primero la mercancía de las entradas más antiguas, garantizando que la ganancia bruta refleje el costo real en que se compró cada lote.", bullet_style))
    story.append(Paragraph("<b>• Flexibilidad Comercial por Lotes:</b> En el punto de venta, el comerciante puede optar por la deducción automática FIFO o seleccionar un lote específico, permitiendo decidir si vende inventario antiguo a precio anterior o a precio actualizado.", bullet_style))
    story.append(Paragraph("<b>• Respaldos y Restauración sin Terminal:</b> Descarga directa de respaldo en archivo JSON y restauración en 1 clic tanto desde archivos de respaldo (.json) como desde hojas de cálculo Excel (.xlsx).", bullet_style))
    story.append(Spacer(1, 8))

    # SECCIÓN 2: GUÍA BOTÓN POR BOTÓN
    story.append(Paragraph("2. Guía Detallada de Botones y Acciones en Pantalla", h1_style))

    # TABLA DE BARRA SUPERIOR
    story.append(Paragraph("A) Barra Superior Permanente (Header)", h2_style))
    header_data = [
        [Paragraph("Control / Botón", table_head), Paragraph("Ubicación", table_head), Paragraph("Función Exacta y Comportamiento", table_head)],
        [
            Paragraph("<b>💾 Copia de seguridad</b>", table_cell_bold),
            Paragraph("Superior derecha (Verde)", table_cell),
            Paragraph("Genera y descarga al instante a tu carpeta de Descargas un archivo <code>.json</code> completo con el 100% de la base de datos (productos, entradas, ventas, pagos y tasas).", table_cell)
        ],
        [
            Paragraph("<b>↻ Restaurar copia</b>", table_cell_bold),
            Paragraph("Superior derecha", table_cell),
            Paragraph("Abre el selector de archivos de Windows para recuperar los datos. Acepta tanto archivos de respaldo <code>.json</code> como hojas de cálculo <code>.xlsx</code>. Crea un respaldo preventivo de seguridad antes de procesar.", table_cell)
        ],
        [
            Paragraph("<b>Bloquear / Salir</b>", table_cell_bold),
            Paragraph("Superior derecha", table_cell),
            Paragraph("Cierra la sesión activa de la tienda de forma segura e inmediata, bloqueando la pantalla con el candado de acceso.", table_cell)
        ],
        [
            Paragraph("<b>⟳ Actualizar tasas BCV</b>", table_cell_bold),
            Paragraph("Barra de tasas", table_cell),
            Paragraph("Consulta en tiempo real la API oficial del Banco Central de Venezuela y USDT. Si no hay internet, preserva la última tasa válida sin interrumpir las ventas.", table_cell)
        ],
        [
            Paragraph("<i>Actualización automática</i>", table_cell_bold),
            Paragraph("En segundo plano", table_cell),
            Paragraph("Temporizador invisible que consulta y refresca las tasas de cambio automáticamente cada 15 minutos.", table_cell)
        ]
    ]
    t_header = Table(header_data, colWidths=[120, 100, 312])
    t_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), brand_green),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#DCEAE0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, brand_light_green]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_header)
    story.append(Spacer(1, 10))

    # TABLA PESTAÑA 01: ENTRADA DE MERCANCÍA
    story.append(Paragraph("B) Pestaña 01 · Registro de Entrada de Mercancía", h2_style))
    entrada_data = [
        [Paragraph("Campo / Botón", table_head), Paragraph("Tipo", table_head), Paragraph("Función y Reglas de Negocio", table_head)],
        [
            Paragraph("<b>Buscar producto guardado</b>", table_cell_bold),
            Paragraph("Buscador reactivo", table_cell),
            Paragraph("Filtra el catálogo guardado ignorando mayúsculas y tildes. Al hacer clic en un producto sugerido, autorrellena nombre, costo y precio sugerido.", table_cell)
        ],
        [
            Paragraph("<b>Guardar entrada</b>", table_cell_bold),
            Paragraph("Botón primario", table_cell),
            Paragraph("Guarda el lote de mercancía en inventario. Valida que cantidad sea > 0 y precios válidos. Nunca recarga la pantalla ni borra datos por error.", table_cell)
        ],
        [
            Paragraph("<b>Producto nuevo</b>", table_cell_bold),
            Paragraph("Botón secundario", table_cell),
            Paragraph("Aparece cuando se selecciona un producto existente. Al pulsarlo, limpia los campos y desbloquea el nombre para escribir un artículo totalmente nuevo.", table_cell)
        ],
        [
            Paragraph("<b>✕ Anular esta entrada</b>", table_cell_bold),
            Paragraph("Enlace por entrada", table_cell),
            Paragraph("Ubicado en la lista 'Últimas entradas'. Permite anular una entrada errónea de prueba, descontando las unidades del stock. Si la entrada ya tiene ventas registradas, protege la contabilidad impidiendo su borrado.", table_cell)
        ]
    ]
    t_entrada = Table(entrada_data, colWidths=[120, 100, 312])
    t_entrada.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), brand_green),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#DCEAE0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, brand_light_green]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_entrada)
    story.append(Spacer(1, 10))

    # TABLA PESTAÑA 02: VENTAS
    story.append(Paragraph("C) Pestaña 02 · Registro de Ventas (Punto de Cobro)", h2_style))
    ventas_data = [
        [Paragraph("Control / Botón", table_head), Paragraph("Tipo", table_head), Paragraph("Función y Reglas de Negocio", table_head)],
        [
            Paragraph("<b>Desplegable de Productos y Lotes</b>", table_cell_bold),
            Paragraph("Selector híbrido", table_cell),
            Paragraph("Ofrece la opción general FIFO (todo el stock acumulado) y, si hay múltiples entradas, desglosa los lotes individuales con fecha y precio histórico.", table_cell)
        ],
        [
            Paragraph("<b>Precio venta (Bs)</b>", table_cell_bold),
            Paragraph("Campo editable", table_cell),
            Paragraph("Carga el precio sugerido del producto o lote, pero permite al comerciante modificarlo libremente para la venta que está cobrando.", table_cell)
        ],
        [
            Paragraph("<b>Agregar a la venta</b>", table_cell_bold),
            Paragraph("Botón primario", table_cell),
            Paragraph("Valida que haya existencia disponible en la tienda y añade la línea al ticket de compra actual.", table_cell)
        ],
        [
            Paragraph("<b>Quitar</b>", table_cell_bold),
            Paragraph("Enlace en ticket", table_cell),
            Paragraph("Elimina un artículo del ticket actual antes de procesar el cobro.", table_cell)
        ],
        [
            Paragraph("<b>Campos de Cobro (Bs / USD / USDT)</b>", table_cell_bold),
            Paragraph("Inputs dinámicos", table_cell),
            Paragraph("Permite ingresar pagos parciales o totales en Efectivo Bs, Pago Móvil, Dólares en efectivo y USDT. Calcula en vivo el vuelto o monto faltante.", table_cell)
        ],
        [
            Paragraph("<b>Confirmar y registrar venta</b>", table_cell_bold),
            Paragraph("Botón final", table_cell),
            Paragraph("Bloquea registros concurrentes, deduce el inventario por FIFO o por lote específico, genera el código correlativo de ticket y actualiza ganancias.", table_cell)
        ]
    ]
    t_ventas = Table(ventas_data, colWidths=[120, 100, 312])
    t_ventas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), brand_green),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#DCEAE0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, brand_light_green]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_ventas)
    story.append(Spacer(1, 10))

    # TABLA PESTAÑAS 03 Y 04: INVENTARIO Y ANÁLISIS
    story.append(Paragraph("D) Pestañas 03 (Inventario) y 04 (Análisis y Reportes)", h2_style))
    inv_data = [
        [Paragraph("Control / Botón", table_head), Paragraph("Pestaña", table_head), Paragraph("Función y Reglas de Negocio", table_head)],
        [
            Paragraph("<b>Métricas de Inventario</b>", table_cell_bold),
            Paragraph("03 · Inventario", table_cell),
            Paragraph("Indica en tiempo real el total de productos únicos, unidades físicas disponibles y valoración total a precio de venta.", table_cell)
        ],
        [
            Paragraph("<b>Borrar (Producto)</b>", table_cell_bold),
            Paragraph("03 · Inventario", table_cell),
            Paragraph("Permite eliminar un producto y sus existencias de prueba. Si el producto ya tiene ventas históricas, el sistema impide su borrado para proteger auditorías.", table_cell)
        ],
        [
            Paragraph("<b>Filtros de Período</b>", table_cell_bold),
            Paragraph("04 · Análisis", table_cell),
            Paragraph("Botones rápidos: 'Todo', 'Hoy', 'Últimos 7 días', 'Quincena calendario' y 'Mes', además de selector de fechas Desde/Hasta.", table_cell)
        ],
        [
            Paragraph("<b>↓ Descargar Excel</b>", table_cell_bold),
            Paragraph("04 · Análisis", table_cell),
            Paragraph("Genera un libro oficial <code>.xlsx</code> con 4 hojas: 1. Inventario Actual, 2. Entradas de Mercancía, 3. Ventas y Ganancia Bruta, 4. Detalle de Pagos.", table_cell)
        ],
        [
            Paragraph("<b>↻ Restaurar desde archivo</b>", table_cell_bold),
            Paragraph("04 · Análisis", table_cell),
            Paragraph("Acceso directo alternativo al restaurador universal de archivos (.json o .xlsx) sin salir de la sección de análisis.", table_cell)
        ]
    ]
    t_inv = Table(inv_data, colWidths=[120, 100, 312])
    t_inv.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), brand_green),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#DCEAE0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, brand_light_green]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_inv)
    story.append(Spacer(1, 10))

    # SECCIÓN 3: PROTOCOLO DE SEGURIDAD Y RESPALDOS
    story.append(Paragraph("3. Protocolo de Seguridad y Recuperación ante Emergencias", h1_style))
    story.append(Paragraph("<b>• ¿Dónde están los respaldos automáticos?</b> Cada ejecución o comando genera una copia en <code>OSMA COSMETICOS\\backups\\</code> conservando las últimas 30 copias con fecha y hora.", bullet_style))
    story.append(Paragraph("<b>• ¿Cómo restaurar si se formatea la PC o se cambia de máquina?</b>", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;1. <b>Método Web (Recomendado):</b> Abre el sistema en el navegador, haz clic en <b>↻ Restaurar copia</b> y selecciona el archivo <code>.json</code> o el reporte <code>.xlsx</code> que guardaste. ¡Listo en 2 segundos!", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;2. <b>Método Consola:</b> En la terminal de la carpeta del proyecto, ejecuta: <code>python manage.py loaddata backups/respaldo_osma_*.json</code>.", bullet_style))
    story.append(Paragraph("<b>• Recomendación semanal para el comerciante:</b> Cada sábado o al final del día de inventario, presionar el botón verde <b>💾 Copia de seguridad</b> y guardar el archivo descargado en un pendrive o en Google Drive personal.", bullet_style))
    story.append(Spacer(1, 10))

    # FIRMA Y CIERRE
    story.append(HRFlowable(width="100%", thickness=0.8, color=brand_green, spaceAfter=8))
    story.append(Paragraph("<b>Sistema Osma Cosmetics · Versión 1.0 Estable y Operativa</b>", table_cell_bold))
    story.append(Paragraph("Desarrollado con Django 5.x, SQLite local de alto rendimiento y arquitectura desacoplada para PostgreSQL.", table_cell))

    # Construir documento
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF generado con exito: {os.path.abspath(pdf_filename)}")

if __name__ == '__main__':
    build_pdf()

