from django.shortcuts import render, redirect
from django.contrib.auth import logout as auth_logout, login as auth_login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from tasas.models import HistorialTasa

@login_required
def dashboard_view(request):
    tasa_usd = HistorialTasa.obtener_ultima_tasa('USD_BCV')
    tasa_usdt = HistorialTasa.obtener_ultima_tasa('USDT')
    return render(request, 'index.html', {
        'tasa_usd_bcv': tasa_usd,
        'tasa_usdt': tasa_usdt
    })

def custom_login_view(request):
    """
    Acceso ultra rápido por clave directa de tienda.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    error = False
    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        
        # 1. Comprobar primero al usuario de la tienda (acceso en milisegundos)
        store_user = User.objects.filter(is_superuser=False, is_active=True).first()
        if store_user and store_user.check_password(password):
            auth_login(request, store_user)
            return redirect(request.GET.get('next') or '/')

        # 2. Si no es la clave de tienda, comprobar superusuario admin
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
