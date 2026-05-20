# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from envios import views_auth

urlpatterns = [
    path('admin/', admin.site.urls),

    # Vistas web del sistema
    path('', include('envios.urls')),

    # Autenticación web personalizada
    path('accounts/login/', views_auth.login_view, name='login'),
    path('accounts/logout/', views_auth.logout_view, name='logout'),
    path('accounts/perfil/', views_auth.perfil_view, name='perfil'),

    # Auth JWT sin versionado
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # API REST con versionado dinámico
    # Ejemplos:
    # /api/v1/encomiendas/
    # /api/v2/encomiendas/
    path('api/<str:version>/', include('api.urls')),

    # Schema OpenAPI 3.0
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),

    # Swagger UI
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger'),

    # ReDoc
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Configuración para desarrollo
if settings.DEBUG:
    urlpatterns += [
        path('silk/', include('silk.urls', namespace='silk')),
    ]
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)