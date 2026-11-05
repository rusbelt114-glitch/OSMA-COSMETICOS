from django.contrib import admin
from .models import Producto

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'stock_total_admin', 'stock_minimo', 'estado_admin', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'nombre_busqueda')

    def stock_total_admin(self, obj):
        return obj.stock_total
    stock_total_admin.short_description = 'Existencias'

    def estado_admin(self, obj):
        return obj.estado_stock.upper()
    estado_admin.short_description = 'Estado Stock'
