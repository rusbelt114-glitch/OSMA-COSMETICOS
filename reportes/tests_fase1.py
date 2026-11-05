import json
from decimal import Decimal
from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from config.views import custom_login_view

class Fase1SeguridadAccesosTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        # Crear usuario tienda con clave personalizada
        self.tienda_user = User.objects.create_user(username='tienda', password='MiClavePersonalizada2026')
        self.admin_user = User.objects.create_superuser(username='admin', password='AdminClaveSegura2026')

    def _setup_request(self, request, user=None):
        request.user = user or AnonymousUser()
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()
        msg_middleware = MessageMiddleware(lambda r: None)
        msg_middleware.process_request(request)
        return request

    def test_01_no_sustitucion_de_claves_en_login(self):
        """Verifica que 1234 no sobreescriba ni permita acceso si se cambió la clave en Django."""
        # 1. Intentar entrar con la clave vieja 1234
        req_bad = self.factory.post(reverse('login'), {'password': '1234'})
        self._setup_request(req_bad)
        resp_bad = custom_login_view(req_bad)
        self.assertEqual(resp_bad.status_code, 200)
        
        # 2. Verificar que la clave en base de datos NO se sobreescribió
        self.tienda_user.refresh_from_db()
        self.assertTrue(self.tienda_user.check_password('MiClavePersonalizada2026'))
        self.assertFalse(self.tienda_user.check_password('1234'))

        # 3. Iniciar sesión con la clave correcta
        req_ok = self.factory.post(reverse('login'), {'password': 'MiClavePersonalizada2026'})
        self._setup_request(req_ok)
        resp_ok = custom_login_view(req_ok)
        self.assertEqual(resp_ok.status_code, 302) # Redirige al dashboard
        self.assertEqual(resp_ok.url, '/')

    def test_02_inicializar_sistema_conserva_claves(self):
        """Verifica que ejecutar inicializar_sistema no borre las claves cambiadas por el dueño."""
        call_command('inicializar_sistema')
        self.tienda_user.refresh_from_db()
        self.admin_user.refresh_from_db()
        self.assertTrue(self.tienda_user.check_password('MiClavePersonalizada2026'))
        self.assertTrue(self.admin_user.check_password('AdminClaveSegura2026'))

    def test_03_restaurar_bloquea_usuario_tienda(self):
        """Verifica que el usuario normal de tienda no pueda restaurar copias de seguridad."""
        self.client.login(username='tienda', password='MiClavePersonalizada2026')
        archivo_dummy = SimpleUploadedFile("backup.json", b"[]", content_type="application/json")
        resp = self.client.post(reverse('api_restaurar_copia'), {'archivo': archivo_dummy})
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Solo el administrador', resp.json().get('error', ''))

    def test_04_restaurar_rechaza_inyeccion_usuarios_auth(self):
        """Verifica que una copia que intente inyectar auth.User sea rechazada de inmediato."""
        self.client.login(username='admin', password='AdminClaveSegura2026')
        malicious_json = json.dumps([
            {
                "model": "auth.user",
                "pk": 99,
                "fields": {
                    "username": "hacker",
                    "password": "hash"
                }
            }
        ]).encode('utf-8')
        archivo = SimpleUploadedFile("malicioso.json", malicious_json, content_type="application/json")
        resp = self.client.post(reverse('api_restaurar_copia'), {'archivo': archivo})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('datos restringidos de seguridad', resp.json().get('error', ''))

    def test_05_crear_respaldo_funciona(self):
        """Verifica que el comando crear_respaldo genere copias exitosamente."""
        call_command('crear_respaldo')
        # Verificar que se ejecute sin excepciones
