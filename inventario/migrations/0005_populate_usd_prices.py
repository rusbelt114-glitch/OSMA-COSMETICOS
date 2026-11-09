from decimal import Decimal
from django.db import migrations

def popular_precios_usd(apps, schema_editor):
    EntradaMercancia = apps.get_model('inventario', 'EntradaMercancia')
    for e in EntradaMercancia.objects.all():
        t = e.tasa_al_momento if (e.tasa_al_momento and e.tasa_al_momento > Decimal('0.00')) else Decimal('896.12')
        if not e.tasa_al_momento or e.tasa_al_momento <= Decimal('0.00'):
            e.tasa_al_momento = t

        if e.costo_unitario and (not e.costo_unitario_usd or e.costo_unitario_usd <= Decimal('0.00')):
            e.costo_unitario_usd = (e.costo_unitario / t).quantize(Decimal('0.01'))
        if e.precio_venta and (not e.precio_venta_usd or e.precio_venta_usd <= Decimal('0.00')):
            e.precio_venta_usd = (e.precio_venta / t).quantize(Decimal('0.01'))
        if e.precio_mayor and (not e.precio_mayor_usd or e.precio_mayor_usd <= Decimal('0.00')):
            e.precio_mayor_usd = (e.precio_mayor / t).quantize(Decimal('0.01'))
        if e.precio_promo_mayor and (not e.precio_promo_mayor_usd or e.precio_promo_mayor_usd <= Decimal('0.00')):
            e.precio_promo_mayor_usd = (e.precio_promo_mayor / t).quantize(Decimal('0.01'))
        if e.precio_gran_mayor and (not e.precio_gran_mayor_usd or e.precio_gran_mayor_usd <= Decimal('0.00')):
            e.precio_gran_mayor_usd = (e.precio_gran_mayor / t).quantize(Decimal('0.01'))
        if e.precio_promo_gran_mayor and (not e.precio_promo_gran_mayor_usd or e.precio_promo_gran_mayor_usd <= Decimal('0.00')):
            e.precio_promo_gran_mayor_usd = (e.precio_promo_gran_mayor / t).quantize(Decimal('0.01'))
        if e.precio_promo_divisa and (not e.precio_promo_divisa_usd or e.precio_promo_divisa_usd <= Decimal('0.00')):
            e.precio_promo_divisa_usd = (e.precio_promo_divisa / t).quantize(Decimal('0.01'))
        e.save()

class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0004_entradamercancia_costo_unitario_usd_and_more'),
    ]

    operations = [
        migrations.RunPython(popular_precios_usd, migrations.RunPython.noop),
    ]
