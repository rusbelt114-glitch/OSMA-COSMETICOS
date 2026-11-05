from django.db import models
from django.utils.text import slugify
import unicodedata

def normalizar_texto(texto):
    """Elimina acentos y pasa a minúsculas para búsquedas flexibles."""
    if not texto:
        return ""
    texto = unicodedata.normalize('NFD', texto)
    return "".join(c for c in texto if unicodedata.category(c) != 'Mn').lower()

class Producto(models.Model):
    nombre = models.CharField(
        max_length=120, 
        unique=True,
        verbose_name="Nombre y presentación",
        help_text="Ej: Corrector · tono 01"
    )
    nombre_busqueda = models.CharField(
        max_length=150, 
        blank=True, 
        editable=False, 
        db_index=True
    )
    stock_minimo = models.PositiveIntegerField(
        default=3, 
        verbose_name="Alerta al quedar"
    )
    activo = models.BooleanField(
        default=True, 
        verbose_name="En catálogo activo"
    )
    creado_el = models.DateTimeField(auto_now_add=True)
    actualizado_el = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['nombre']

    def save(self, *args, **kwargs):
        self.nombre_busqueda = normalizar_texto(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

    @property
    def stock_total(self):
        """Suma de unidades disponibles en todos los lotes vigentes."""
        total = self.entradas.filter(cantidad_disponible__gt=0).aggregate(
            total=models.Sum('cantidad_disponible')
        )['total']
        return total or 0

    @property
    def estado_stock(self):
        """Retorna 'agotado', 'minimo' o 'normal'"""
        st = self.stock_total
        if st == 0:
            return 'agotado'
        if st <= self.stock_minimo:
            return 'minimo'
        return 'normal'

    @property
    def ultimo_precio_venta(self):
        """Último precio de venta registrado en una entrada."""
        ultima_entrada = self.entradas.order_by('-fecha_entrada', '-id').first()
        return ultima_entrada.precio_venta if ultima_entrada else None

    @property
    def ultimo_costo(self):
        """Último costo de compra registrado en una entrada."""
        ultima_entrada = self.entradas.order_by('-fecha_entrada', '-id').first()
        return ultima_entrada.costo_unitario if ultima_entrada else None
