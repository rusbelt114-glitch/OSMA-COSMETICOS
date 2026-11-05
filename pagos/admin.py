from django.contrib import admin
from .models import PagoVenta, Gasto

@admin.register(PagoVenta)
class PagoVentaAdmin(admin.ModelAdmin):
    list_display = ('venta', 'metodo', 'moneda', 'monto_original', 'tasa_aplicada', 'monto_equivalente_bs', 'fecha_pago')
    list_filter = ('metodo', 'moneda', 'fecha_pago')
    search_fields = ('venta__codigo', 'referencia')

@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    list_display = ('descripcion', 'categoria', 'monto_original', 'moneda', 'monto_equivalente_bs', 'metodo', 'fecha')
    list_filter = ('categoria', 'metodo', 'moneda', 'fecha')
    search_fields = ('descripcion', 'comprobante', 'observaciones')
