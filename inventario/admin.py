from django.contrib import admin
from .models import EntradaMercancia

@admin.register(EntradaMercancia)
class EntradaMercanciaAdmin(admin.ModelAdmin):
    list_display = ('id', 'producto', 'cantidad_recibida', 'cantidad_disponible', 'costo_unitario', 'precio_venta', 'fecha_entrada')
    list_filter = ('fecha_entrada', 'producto')
    search_fields = ('producto__nombre', 'observaciones')
