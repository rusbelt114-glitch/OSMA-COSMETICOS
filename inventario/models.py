from django.db import models
from django.utils import timezone
from decimal import Decimal

class EntradaMercancia(models.Model):
    producto = models.ForeignKey(
        'productos.Producto',
        on_delete=models.PROTECT,
        related_name='entradas',
        verbose_name="Producto"
    )
    cantidad_recibida = models.PositiveIntegerField(
        verbose_name="Cantidad recibida"
    )
    cantidad_disponible = models.PositiveIntegerField(
        verbose_name="Cantidad disponible",
        help_text="Unidades restantes de este lote (disminuye con ventas FIFO)"
    )
    costo_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Costo de compra unitario (Bs)"
    )
    precio_venta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Precio de venta unitario (Bs)"
    )
    precio_mayor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Precio al mayor unitario (Bs)"
    )
    precio_gran_mayor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Precio al gran mayor unitario (Bs)"
    )
    precio_promo_divisa = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Precio promo divisa unitario (Bs)"
    )
    precio_promo_mayor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Precio promo divisa mayor unitario (Bs)"
    )
    precio_promo_gran_mayor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Precio promo divisa gran mayor unitario (Bs)"
    )
    fecha_entrada = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name="Fecha de entrada"
    )
    observaciones = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Observaciones"
    )
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Entrada de mercancía"
        verbose_name_plural = "Entradas de mercancía"
        ordering = ['-fecha_entrada', '-id']

    def save(self, *args, **kwargs):
        if self._state.adding and self.cantidad_disponible is None:
            self.cantidad_disponible = self.cantidad_recibida
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.producto.nombre} (+{self.cantidad_recibida} uds el {self.fecha_entrada.strftime('%d/%m/%Y')})"

    @property
    def valor_costo_total_inicial(self):
        return self.cantidad_recibida * self.costo_unitario

    @property
    def valor_venta_disponible(self):
        return self.cantidad_disponible * self.precio_venta

    @property
    def valor_costo_disponible(self):
        return self.cantidad_disponible * self.costo_unitario
