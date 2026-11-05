from django.contrib import admin
from .models import Venta, DetalleVenta, DesgloseLoteVenta

class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    readonly_fields = ('producto', 'cantidad', 'precio_unitario_bs', 'subtotal_bs', 'costo_total_bs', 'ganancia_bruta_bs')

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'fecha', 'total_bs', 'costo_total_bs', 'ganancia_bruta_bs', 'tasa_usd_bcv', 'anulada')
    list_filter = ('fecha', 'anulada')
    search_fields = ('codigo', 'observaciones')
    inlines = [DetalleVentaInline]

@admin.register(DetalleVenta)
class DetalleVentaAdmin(admin.ModelAdmin):
    list_display = ('venta', 'producto', 'cantidad', 'precio_unitario_bs', 'subtotal_bs', 'ganancia_bruta_bs')
    search_fields = ('venta__codigo', 'producto__nombre')

@admin.register(DesgloseLoteVenta)
class DesgloseLoteVentaAdmin(admin.ModelAdmin):
    list_display = ('detalle_venta', 'entrada', 'cantidad_descontada', 'costo_unitario_aplicado')
