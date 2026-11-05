from django.contrib import admin
from django.contrib import messages
from .models import Venta, DetalleVenta, DesgloseLoteVenta

class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    readonly_fields = ('producto', 'cantidad', 'precio_unitario_bs', 'subtotal_bs', 'costo_total_bs', 'ganancia_bruta_bs')

@admin.action(description="Anular ventas seleccionadas (devolviendo inventario a lotes FIFO)")
def anular_ventas_action(modeladmin, request, queryset):
    anuladas = 0
    for venta in queryset:
        if not venta.anulada:
            venta.anulada = True
            venta.motivo_anulacion = f"Anulada desde Django Admin por {request.user.username}"
            venta.save()
            anuladas += 1
    modeladmin.message_user(
        request,
        f"Se anularon exitosamente {anuladas} ventas y se reintegraron sus inventarios a los lotes originales.",
        messages.SUCCESS
    )

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'fecha', 'total_bs', 'costo_total_bs', 'ganancia_bruta_bs', 'tasa_usd_bcv', 'anulada')
    list_filter = ('fecha', 'anulada')
    search_fields = ('codigo', 'observaciones')
    readonly_fields = ('codigo', 'anulada_el', 'creado_el')
    actions = [anular_ventas_action]
    inlines = [DetalleVentaInline]

@admin.register(DetalleVenta)
class DetalleVentaAdmin(admin.ModelAdmin):
    list_display = ('venta', 'producto', 'cantidad', 'precio_unitario_bs', 'subtotal_bs', 'ganancia_bruta_bs')
    search_fields = ('venta__codigo', 'producto__nombre')

@admin.register(DesgloseLoteVenta)
class DesgloseLoteVentaAdmin(admin.ModelAdmin):
    list_display = ('detalle_venta', 'entrada', 'cantidad_descontada', 'costo_unitario_aplicado')
