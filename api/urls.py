# api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenRefreshView,
    TokenBlacklistView,
)
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

from envios import api_views
from envios.viewsets import EncomiendaViewSet
from api.auth_views import EncomiendaTokenView

router = DefaultRouter()
router.register('encomiendas', EncomiendaViewSet, basename='encomienda')

urlpatterns = [
    # Endpoints auxiliares con vistas genéricas
    path('clientes/', api_views.ClienteListView.as_view(), name='cliente-list'),
    path('rutas/', api_views.RutaListView.as_view(), name='ruta-list'),

    # Endpoints de autenticación JWT
    path('auth/token/', EncomiendaTokenView.as_view(), name='token_obtain'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),

    # Documentación interactiva dentro de /api/v1/
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger'),

    # Endpoints del ViewSet
    path('', include(router.urls)),
]