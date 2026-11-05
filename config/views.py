from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth import logout as auth_logout, login as auth_login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from tasas.models import HistorialTasa

@login_required
def dashboard_view(request):
    tasa_usd = HistorialTasa.obtener_ultima_tasa('USD_BCV')
    tasa_usdt = HistorialTasa.obtener_ultima_tasa('USDT')
    if not tasa_usd or tasa_usd <= 0:
        tasa_usd = Decimal('893.20')
        HistorialTasa.objects.get_or_create(tipo='USD_BCV', defaults={'valor': tasa_usd, 'fuente': 'Resguardo'})
    if not tasa_usdt or tasa_usdt <= 0:
        tasa_usdt = Decimal('1010.50')
        HistorialTasa.objects.get_or_create(tipo='USDT', defaults={'valor': tasa_usdt, 'fuente': 'Resguardo'})
    return render(request, 'index.html', {
        'tasa_usd_bcv': tasa_usd,
        'tasa_usdt': tasa_usdt
    })

def custom_login_view(request):
    """
    Acceso ultra rápido por clave directa de tienda con auto-inicialización en la nube.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    error = False
    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        
        # Buscar usuario de tienda o crearlo si la base de datos es nueva
        store_user = User.objects.filter(username='tienda').first()
        if not store_user:
            store_user = User.objects.filter(is_superuser=False, is_active=True).first()
        if not store_user:
            store_user = User.objects.create_user(username='tienda', password='1234')

        # Si ingresa una de las claves de acceso de la tienda (1234 u osma1234), acceso garantizado
        if password in ('1234', 'osma1234'):
            store_user.set_password(password)
            store_user.is_active = True
            store_user.save()
            auth_login(request, store_user)
            return redirect(request.GET.get('next') or '/')

        # Comprobar si coincide con otra clave personalizada guardada
        if store_user and store_user.check_password(password):
            auth_login(request, store_user)
            return redirect(request.GET.get('next') or '/')

        # Comprobar superusuario admin
        admin_user = User.objects.filter(is_superuser=True, is_active=True).first()
        if admin_user and admin_user.check_password(password):
            auth_login(request, admin_user)
            return redirect(request.GET.get('next') or '/')

        error = True

    return render(request, 'login.html', {'error': error})

def logout_view(request):
    """Cierra la sesión de la tienda y redirige al login sin errores de CSRF."""
    auth_logout(request)
    return redirect('login')
