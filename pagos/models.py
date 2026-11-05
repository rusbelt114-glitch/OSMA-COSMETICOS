from django.db import models
from django.utils import timezone
from decimal import Decimal

class PagoVenta(models.Model):
    METODO_CHOICES = [
        ('EFECTIVO_BS', 'Efectivo en Bs'),
        ('PAGO_MOVIL', 'Pago Móvil en Bs'),
        ('PUNTO_VENTA', 'Punto de Venta / Débito'),
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


class Gasto(models.Model):
    CATEGORIA_CHOICES = [
        ('TIENDA', 'Tienda / Operativo (Alquiler, bolsas, servicios)'),
        ('PERSONAL', 'Personal / Retiro del Dueño'),
    ]

    METODO_CHOICES = PagoVenta.METODO_CHOICES

    descripcion = models.CharField(max_length=255, verbose_name="Descripción del gasto")
    categoria = models.CharField(
        max_length=20,
        choices=CATEGORIA_CHOICES,
        default='TIENDA',
        db_index=True,
        verbose_name="Categoría"
    )
    monto_original = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Monto")
    moneda = models.CharField(
        max_length=10,
        choices=[('BS', 'Bolívares (Bs)'), ('USD', 'Dólares (USD)'), ('USDT', 'USDT')],
        default='BS'
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
    metodo = models.CharField(
        max_length=30,
        choices=METODO_CHOICES,
        default='EFECTIVO_BS',
        verbose_name="Medio de pago utilizado"
    )
    comprobante = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Nro. Recibo / Referencia"
    )
    observaciones = models.TextField(blank=True, verbose_name="Notas adicionales")
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gasto / Egreso"
        verbose_name_plural = "Gastos y Egresos"
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f"[{self.get_categoria_display()}] {self.descripcion} · {self.moneda} {self.monto_original} (= Bs {self.monto_equivalente_bs})"
