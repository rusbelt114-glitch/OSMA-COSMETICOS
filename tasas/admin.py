from django.contrib import admin
from .models import HistorialTasa

@admin.register(HistorialTasa)
class HistorialTasaAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'valor', 'fuente', 'fecha', 'es_manual')
    list_filter = ('tipo', 'es_manual', 'fecha')
