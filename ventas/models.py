from django.db import models, transaction
from django.utils import timezone
from decimal import Decimal
import uuid

class Venta(models.Model):
    codigo = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    total_bs = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    costo_total_bs = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    ganancia_bruta_bs = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    
    # Tasas congeladas al momento exacto de la venta
    tasa_usd_bcv = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('1.0000'))
    tasa_usdt = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('1.0000'))
    
    anulada = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True)
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ['-fecha', '-id']

    def save(self, *args, **kwargs):
        if not self.codigo:
            timestamp = timezone.now().strftime('%Y%m%d%H%M')
            unique_part = uuid.uuid4().hex[:4].upper()
            self.codigo = f"V-{timestamp}-{unique_part}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} · Bs {self.total_bs} ({self.fecha.strftime('%d/%m/%Y %H:%M')})"


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey('productos.Producto', on_delete=models.PROTECT, related_name='ventas_detalle')
    cantidad = models.PositiveIntegerField()
    precio_unitario_bs = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal_bs = models.DecimalField(max_digits=14, decimal_places=2)
    
    # Costo y ganancia real calculados por FIFO
    costo_total_bs = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    ganancia_bruta_bs = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = "Detalle de Venta"
        verbose_name_plural = "Detalles de Venta"

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre} en {self.venta.codigo}"


class DesgloseLoteVenta(models.Model):
    """
    Rastreo exacto de qué entrada (lote) cubrió cada unidad vendida.
    Garantiza auditoría perfecta del inventario y del costo FIFO.
    """
    detalle_venta = models.ForeignKey(DetalleVenta, on_delete=models.CASCADE, related_name='desgloses_lote')
    entrada = models.ForeignKey('inventario.EntradaMercancia', on_delete=models.PROTECT, related_name='desgloses_venta')
    cantidad_descontada = models.PositiveIntegerField()
    costo_unitario_aplicado = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Desglose por Lote (FIFO)"
        verbose_name_plural = "Desgloses por Lote (FIFO)"

    def __str__(self):
        return f"{self.cantidad_descontada} uds de Entrada #{self.entrada.id} a Bs {self.costo_unitario_aplicado}"
