# Osma Cosmetics · Sistema Central de Tienda

Sistema web interno para **Osma Cosmetics** desarrollado con **Python / Django**, con soporte para **PostgreSQL** en la nube y **SQLite** en desarrollo local.

Diseñado según la propuesta operativa:
* **Entrada de mercancía:** Registro de compras con costo y precio histórico por lote.
* **Venta (POS):** Carrito multi-producto con deducción automática de inventario por **FIFO (PEPS)** y cálculo de ganancia bruta real.
* **Control de concurrencia:** Bloqueo transaccional de filas (`select_for_update()`) para evitar ventas simultáneas que dejen stock negativo.
* **Pagos multi-moneda:** Pago móvil, efectivo en Bs, efectivo en USD y USDT.
* **Tasas en tiempo real:** Conexión automática con la tasa oficial del **Banco Central de Venezuela (BCV)** y mercado USDT, con respaldo local sin internet.
* **Reportes y Excel:** Resúmenes por período (diario, 7 días, quincena, mes o personalizado) y descarga de archivo `.xlsx` con 4 hojas (Inventario, Entradas, Ventas y Pagos).
* **Acceso protegido:** Sesión única protegida para el equipo de tienda.

---

## 1. Estructura del Proyecto

```text
config/         -> Configuración global de Django, conexión BD y URLs
productos/      -> Catálogo, presentaciones, búsqueda flexible sin acentos
inventario/     -> Entradas de mercancía, lotes y niveles de stock
ventas/         -> Registro de ventas, carrito, motor FIFO y control de concurrencia
pagos/          -> Métodos de pago mixtos, monedas y tasas aplicadas congeladas
reportes/       -> Métricas financieras, ganancia bruta y exportación Excel (.xlsx)
tasas/          -> Sincronización automática de tasa BCV y USDT
templates/      -> Vistas HTML (Login y Dashboard SPA)
static/         -> Estilos CSS (paleta Osma) y JavaScript cliente
tests/          -> Pruebas unitarias automatizadas
requirements.txt-> Dependencias del sistema
.env.example    -> Plantilla de variables de entorno
```

---

## 2. Puesta en marcha rápida (Local)

1. **Activar el entorno virtual:**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. **Aplicar migraciones:**
   ```bash
   python manage.py migrate
   ```

3. **Inicializar datos base (Usuario tienda y tasas):**
   ```bash
   python manage.py inicializar_sistema
   ```
   * **Usuario:** `tienda`
   * **Clave inicial:** `osma1234`

4. **Iniciar el servidor local:**
   ```bash
   python manage.py runserver
   ```
   Abrir en el navegador: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 3. Configuración para Producción (Nube y PostgreSQL)

Crea un archivo `.env` en la raíz (puedes basarte en `.env.example`):

```ini
DEBUG=False
SECRET_KEY=tu_clave_secreta_de_produccion_aqui
ALLOWED_HOSTS=osma-cosmetics.com,*.onrender.com,localhost

# Configuración de PostgreSQL
DB_ENGINE=django.db.backends.postgresql
DB_NAME=osma_db
DB_USER=osma_user
DB_PASSWORD=tu_contrasena_segura
DB_HOST=tu_host_de_postgresql
DB_PORT=5432

# Clave inicial de la tienda
TIENDA_PASSWORD=tu_clave_de_tienda
```

---

## 4. Ejecutar pruebas automatizadas

Para validar cálculos FIFO, ventas concurrentes y generación de Excel:

```bash
python manage.py test tests
```

