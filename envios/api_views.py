# envios/api_views.py

from rest_framework import mixins, generics
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema

from .models import Encomienda
from clientes.models import Cliente
from rutas.models import Ruta

from .serializers import (
    EncomiendaSerializer,
    EncomiendaDetailSerializer,
    ClienteSerializer,
    RutaSerializer,
)

# Importar los paginadores del proyecto
from api.pagination import ClientePagination


# ── Mixins + GenericAPIView ───────────────────────────────────────

class EncomiendaListCreateView(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    generics.GenericAPIView
):
    queryset = Encomienda.objects.con_relaciones()
    serializer_class = EncomiendaSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Hook: se llama antes de save() en create()"""
        serializer.save(
            empleado_registro=self.request.user.empleado
        )


class EncomiendaDetailView(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    generics.GenericAPIView
):
    queryset = Encomienda.objects.con_relaciones()
    serializer_class = EncomiendaSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)


# ── Generic Views ─────────────────────────────────────────────────

class EncomiendaListCreateGenericView(generics.ListCreateAPIView):
    queryset = Encomienda.objects.con_relaciones()
    serializer_class = EncomiendaSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(
            empleado_registro=self.request.user.empleado
        )


class EncomiendaDetailGenericView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Encomienda.objects.con_relaciones()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        """Usar serializer diferente según el método"""
        if self.request.method == 'GET':
            return EncomiendaDetailSerializer
        return EncomiendaSerializer


@extend_schema(
    summary='Listar clientes activos',
    description='Devuelve todos los clientes con estado Activo, paginados de 20 en 20.',
    tags=['Clientes'],
)
class ClienteListView(generics.ListAPIView):
    serializer_class = ClienteSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ClientePagination  # 20 por página

    def get_queryset(self):
        return Cliente.objects.activos()


@extend_schema(
    summary='Listar rutas activas',
    description='Devuelve todas las rutas con estado Activo. Sin paginación.',
    tags=['Rutas'],
)
class RutaListView(generics.ListAPIView):
    serializer_class = RutaSerializer
    permission_classes = [IsAuthenticated]

    # Las rutas son pocas: no paginamos (None deshabilita la paginación)
    pagination_class = None

    def get_queryset(self):
        return Ruta.objects.activas()