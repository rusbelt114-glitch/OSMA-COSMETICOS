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
    # Monto neto cobrado aplicado a la venta
    monto_original = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Monto neto en moneda original"
    )
    # Auditoría de billete/monto entregado por el cliente y vuelto
    monto_recibido = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Monto entregado por cliente"
    )
    vuelto_entregado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Vuelto entregado en moneda original"
    )
    vuelto_entregado_bs = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Vuelto equivalente en Bs"
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
