from decimal import Decimal
from django.db import migrations

def corregir_precios_usd(apps, schema_editor):
    EntradaMercancia = apps.get_model('inventario', 'EntradaMercancia')
    TasaModel = apps.get_model('tasas', 'HistorialTasa')

    # Obtener última tasa registrada en BD o usar 897.54
    ultima_tasa = TasaModel.objects.filter(tipo='USD_BCV').order_by('-fecha', '-id').first()
    tasa_ref = ultima_tasa.valor if (ultima_tasa and ultima_tasa.valor > Decimal('10.00')) else Decimal('897.54')

    for e in EntradaMercancia.objects.all():
        t_actual = e.tasa_al_momento or Decimal('0.00')
        es_anomalo = False

        if t_actual <= Decimal('10.00'):
            es_anomalo = True
        elif e.precio_venta and e.precio_venta_usd and abs(e.precio_venta_usd - e.precio_venta) < Decimal('0.05'):
            es_anomalo = True
        elif e.precio_venta_usd and e.precio_venta_usd > Decimal('200.00') and e.precio_venta and e.precio_venta < Decimal('10000000.00'):
            es_anomalo = True

        if es_anomalo:
            e.tasa_al_momento = tasa_ref
            t = tasa_ref

            if e.precio_venta and e.precio_venta > Decimal('0.00'):
                e.precio_venta_usd = (e.precio_venta / t).quantize(Decimal('0.01'))
            if e.costo_unitario and e.costo_unitario > Decimal('0.00'):
                e.costo_unitario_usd = (e.costo_unitario / t).quantize(Decimal('0.01'))
            if e.precio_mayor and e.precio_mayor > Decimal('0.00'):
                e.precio_mayor_usd = (e.precio_mayor / t).quantize(Decimal('0.01'))
            if e.precio_promo_mayor and e.precio_promo_mayor > Decimal('0.00'):
                e.precio_promo_mayor_usd = (e.precio_promo_mayor / t).quantize(Decimal('0.01'))
            if e.precio_gran_mayor and e.precio_gran_mayor > Decimal('0.00'):
                e.precio_gran_mayor_usd = (e.precio_gran_mayor / t).quantize(Decimal('0.01'))
            if e.precio_promo_gran_mayor and e.precio_promo_gran_mayor > Decimal('0.00'):
                e.precio_promo_gran_mayor_usd = (e.precio_promo_gran_mayor / t).quantize(Decimal('0.01'))
            if e.precio_promo_divisa and e.precio_promo_divisa > Decimal('0.00'):
                e.precio_promo_divisa_usd = (e.precio_promo_divisa / t).quantize(Decimal('0.01'))

            e.save()


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0005_populate_usd_prices'),
        ('tasas', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(corregir_precios_usd, migrations.RunPython.noop),
    ]
