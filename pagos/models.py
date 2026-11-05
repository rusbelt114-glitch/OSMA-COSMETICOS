from django.db import models
from django.utils import timezone
from decimal import Decimal

class PagoVenta(models.Model):
    METODO_CHOICES = [
        ('EFECTIVO_BS', 'Efectivo en Bs'),
        ('PAGO_MOVIL', 'Pago Móvil en Bs'),
        ('EFECTIVO_USD', 'Efectivo en USD'),
        ('USDT', 'USDT'),
    ]

    venta = models.ForeignKey(
        'ventas.Venta',
        on_delete=models.CASCADE,
        related_name='pagos',
        verbose_name="Venta"
    )
    metodo = models.CharField(
        max_length=30,
        choices=METODO_CHOICES,
        verbose_name="Medio de pago"
    )
    moneda = models.CharField(
        max_length=10,
        default='BS',
        help_text="BS, USD o USDT"
    )
    monto_original = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Monto en moneda original"
    )
    tasa_aplicada = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal('1.0000'),
        verbose_name="Tasa de cambio aplicada"
    )
    monto_equivalente_bs = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Equivalente en Bs"
    )
    referencia = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Nro. referencia o notas"
    )
    fecha_pago = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Pago de Venta"
        verbose_name_plural = "Pagos de Ventas"
        ordering = ['id']

    def __str__(self):
        return f"{self.get_metodo_display()}: {self.monto_original} {self.moneda} (= Bs {self.monto_equivalente_bs})"
