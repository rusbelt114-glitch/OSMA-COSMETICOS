"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Auto-asegurar usuarios para despliegues en la nube (Render)
try:
    from django.contrib.auth.models import User
    admin_user, _ = User.objects.get_or_create(username='admin')
    admin_user.set_password('admin1234')
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.is_active = True
    admin_user.save()

    tienda_user, _ = User.objects.get_or_create(username='tienda')
    tienda_user.set_password('1234')
    tienda_user.is_active = True
    tienda_user.save()
except Exception:
    pass
