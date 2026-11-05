from django.contrib import admin
from .models import PagoVenta

@admin.register(PagoVenta)
class PagoVentaAdmin(admin.ModelAdmin):
    list_display = ('venta', 'metodo', 'moneda', 'monto_original', 'tasa_aplicada', 'monto_equivalente_bs', 'fecha_pago')
    list_filter = ('metodo', 'moneda', 'fecha_pago')
    search_fields = ('venta__codigo', 'referencia')
