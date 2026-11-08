from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views

from config.views import dashboard_view, logout_view, custom_login_view
from productos.views import api_productos
from inventario.views import api_entradas, api_metricas_inventario, api_eliminar_entrada, api_lotes_disponibles
from ventas.views import api_ventas, api_anular_venta
from tasas.views import api_tasas, api_actualizar_tasas
from pagos.views import api_gastos, api_eliminar_gasto
from reportes.views import (
    api_reporte_resumen, descargar_excel_reporte, descargar_copia_seguridad, 
    api_restaurar_copia, api_reiniciar_sistema, api_almacenamiento, descargar_respaldo_zip
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Autenticación de tienda (Login y Logout seguro sin fallos CSRF)
    path('login/', custom_login_view, name='login'),
    path('logout/', logout_view, name='logout'),

    # Panel principal (SPA)
    path('', dashboard_view, name='dashboard'),

    # API Endpoints
    path('api/productos/', api_productos, name='api_productos'),
    path('api/entradas/', api_entradas, name='api_entradas'),
    path('api/entradas/<int:entrada_id>/eliminar/', api_eliminar_entrada, name='api_eliminar_entrada'),
    path('api/lotes/disponibles/', api_lotes_disponibles, name='api_lotes_disponibles'),
    path('api/inventario/lotes/', api_lotes_disponibles, name='api_inventario_lotes'),
    path('api/sistema/reiniciar/', api_reiniciar_sistema, name='api_reiniciar_sistema'),
    path('api/inventario/metricas/', api_metricas_inventario, name='api_metricas_inventario'),
    path('api/ventas/', api_ventas, name='api_ventas'),
    path('api/ventas/<str:codigo>/anular/', api_anular_venta, name='api_anular_venta'),
    path('api/gastos/', api_gastos, name='api_gastos'),
    path('api/gastos/<int:gasto_id>/eliminar/', api_eliminar_gasto, name='api_eliminar_gasto'),
    path('api/tasas/', api_tasas, name='api_tasas'),
    path('api/tasas/actualizar/', api_actualizar_tasas, name='api_actualizar_tasas'),
    path('api/reportes/resumen/', api_reporte_resumen, name='api_reporte_resumen'),
    path('api/reportes/restaurar/', api_restaurar_copia, name='api_restaurar_copia'),
    
    # Descargas y Almacenamiento
    path('api/sistema/almacenamiento/', api_almacenamiento, name='api_almacenamiento'),
    path('reportes/excel/', descargar_excel_reporte, name='descargar_excel_reporte'),
    path('reportes/copia-seguridad/', descargar_copia_seguridad, name='descargar_copia_seguridad'),
    path('reportes/respaldo-zip/', descargar_respaldo_zip, name='descargar_respaldo_zip'),
]
