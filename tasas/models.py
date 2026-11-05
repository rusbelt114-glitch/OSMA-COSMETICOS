from django.db import models
from django.utils import timezone
from decimal import Decimal

class HistorialTasa(models.Model):
    TIPO_CHOICES = [
        ('USD_BCV', 'Dólar BCV Oficial'),
        ('USDT', 'USDT / Cripto'),
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    valor = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Tasa en Bs")
    fuente = models.CharField(max_length=50, default="Sistema", help_text="BCV, DolarApi, Manual")
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    es_manual = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Tasa de cambio"
        verbose_name_plural = "Historial de tasas"
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.valor} Bs ({self.fecha.strftime('%d/%m/%Y %H:%M')})"

    @classmethod
    def obtener_ultima_tasa(cls, tipo):
        """Retorna la última tasa registrada para el tipo, o un valor por defecto si no hay."""
        ultima = cls.objects.filter(tipo=tipo).order_by('-fecha', '-id').first()
        if ultima:
            return ultima.valor
        # Valores de resguardo iniciales si la BD está vacía
        if tipo == 'USD_BCV':
            return Decimal("893.2000")
        elif tipo == 'USDT':
            return Decimal("1010.5000")
        return Decimal("1.0000")
