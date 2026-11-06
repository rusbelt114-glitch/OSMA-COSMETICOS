import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env if present and dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass

from django.core.management.utils import get_random_secret_key
from django.core.exceptions import ImproperlyConfigured

from urllib.parse import urlparse, unquote, parse_qs

# SECURITY WARNING: don't run with debug turned on in production!
# Por defecto False para máxima seguridad (salvo que DEBUG=True esté explícito en .env local)
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', '*').split(',') if host.strip()]

# Configuración de proxy y orígenes confiables para CSRF en Render / Producción
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = [
    'https://*.onrender.com',
    'https://osma-cosmeticos.onrender.com',
    'http://127.0.0.1',
    'http://localhost',
]
extra_csrf = os.getenv('CSRF_TRUSTED_ORIGINS', '')
if extra_csrf:
    CSRF_TRUSTED_ORIGINS.extend([o.strip() for o in extra_csrf.split(',') if o.strip()])

# Blindaje de seguridad en producción
if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# SECURITY WARNING: keep the secret key used in production secret!
def get_secret_key():
    secret_key = os.getenv('SECRET_KEY')
    if secret_key:
        return secret_key
    
    secret_file = BASE_DIR / '.secret_key'
    if secret_file.exists():
        try:
            stored_key = secret_file.read_text(encoding='utf-8').strip()
            if stored_key:
                return stored_key
        except Exception:
            pass
    
    new_key = get_random_secret_key()
    try:
        secret_file.write_text(new_key, encoding='utf-8')
    except Exception:
        pass
    return new_key

SECRET_KEY = get_secret_key()


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Aplicaciones del sistema Osma Cosmetics
    'productos.apps.ProductosConfig',
    'inventario.apps.InventarioConfig',
    'ventas.apps.VentasConfig',
    'pagos.apps.PagosConfig',
    'reportes.apps.ReportesConfig',
    'tasas.apps.TasasConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
]

try:
    import whitenoise
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')
except ImportError:
    pass

MIDDLEWARE.extend([
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
])

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'tasas.context_processors.tasas_globales',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

def _configurar_base_datos():
    database_url = os.getenv('DATABASE_URL', '').strip()
    if database_url:
        parsed = urlparse(database_url)
        if parsed.scheme in ('postgres', 'postgresql', 'pgsql'):
            db_config = {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': unquote(parsed.path.lstrip('/')),
                'USER': unquote(parsed.username or 'postgres'),
                'PASSWORD': unquote(parsed.password or ''),
                'HOST': parsed.hostname or 'localhost',
                'PORT': str(parsed.port or '5432'),
            }
            if parsed.query:
                query_params = parse_qs(parsed.query)
                options = {k: v[0] for k, v in query_params.items()}
                if options:
                    db_config['OPTIONS'] = options
            return {'default': db_config}

    if os.getenv('DB_NAME'):
        db_engine = os.getenv('DB_ENGINE', '')
        if db_engine == 'django.db.backends.postgresql' or os.getenv('RENDER'):
            return {
                'default': {
                    'ENGINE': 'django.db.backends.postgresql',
                    'NAME': os.getenv('DB_NAME'),
                    'USER': os.getenv('DB_USER', 'postgres'),
                    'PASSWORD': os.getenv('DB_PASSWORD', ''),
                    'HOST': os.getenv('DB_HOST', 'localhost'),
                    'PORT': os.getenv('DB_PORT', '5432'),
                }
            }

    return {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

DATABASES = _configurar_base_datos()


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 4,
        }
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'es-ve'
TIME_ZONE = 'America/Caracas'
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True
THOUSAND_SEPARATOR = '.'
DECIMAL_SEPARATOR = ','
NUMBER_GROUPING = 3


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
