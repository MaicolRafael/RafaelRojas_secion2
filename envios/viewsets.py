from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django_filters.rest_framework import DjangoFilterBackend

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiExample,
)
from drf_spectacular.types import OpenApiTypes

from config.settings import CACHE_TTL
from api.permissions import EsEmpleadoActivo, EsPropietarioOAdmin
from api.pagination import EncomiendaPagination, HistorialPagination
from api.filters import EncomiendaFilter
from api.throttles import EmpleadoRateThrottle, CambioEstadoThrottle
from api.exceptions import EstadoInvalidoError, EncomiendaYaEntregadaError

from .models import Encomienda, Empleado
from .serializers import (
    EncomiendaSerializer,
    EncomiendaListSerializer,
    EncomiendaDetailSerializer,
    EncomiendaV2Serializer,
    HistorialEstadoSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary='Listar encomiendas',
        description='Devuelve la lista paginada de encomiendas. Soporta filtros por estado, búsqueda y ordenamiento.',
        tags=['Encomiendas'],
    ),
    create=extend_schema(
        summary='Crear encomienda',
        description='Registra una nueva encomienda en el sistema.',
        tags=['Encomiendas'],
    ),
    retrieve=extend_schema(
        summary='Detalle de encomienda',
        description='Devuelve los datos completos de una encomienda con remitente, destinatario, ruta e historial de estados.',
        tags=['Encomiendas'],
    ),
    update=extend_schema(
        summary='Actualizar encomienda',
        tags=['Encomiendas'],
    ),
    partial_update=extend_schema(
        summary='Actualizar parcial',
        tags=['Encomiendas'],
    ),
    destroy=extend_schema(
        summary='Eliminar encomienda',
        tags=['Encomiendas'],
    ),
)
class EncomiendaViewSet(viewsets.ModelViewSet):
    """
    ModelViewSet genera automáticamente:
    list()           → GET    /encomiendas/
    create()         → POST   /encomiendas/
    retrieve()       → GET    /encomiendas/{pk}/
    update()         → PUT    /encomiendas/{pk}/
    partial_update() → PATCH  /encomiendas/{pk}/
    destroy()        → DELETE /encomiendas/{pk}/
    """
    queryset = Encomienda.objects.con_relaciones()
    serializer_class = EncomiendaSerializer
    permission_classes = [EsEmpleadoActivo]
    pagination_class = EncomiendaPagination
    throttle_classes = [EmpleadoRateThrottle]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = EncomiendaFilter
    search_fields = [
        'codigo',
        'remitente__apellidos',
        'destinatario__apellidos',
        'descripcion',
    ]
    ordering_fields = ['fecha_registro', 'peso_kg', 'costo_envio']
    ordering = ['-fecha_registro']

    def get_permissions(self):
        """
        Permisos distintos según la acción.
        """
        if self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            return [EsEmpleadoActivo(), EsPropietarioOAdmin()]
        return [EsEmpleadoActivo()]

    def get_throttles(self):
        """
        Throttle diferente para la acción cambiar_estado.
        """
        if self.action == 'cambiar_estado':
            return [CambioEstadoThrottle()]
        return super().get_throttles()

    def get_serializer_class(self):
        """
        Elegir serializer según versión y acción.

        v1:
        - list -> serializer ligero
        - retrieve -> serializer detalle
        - write -> serializer estándar

        v2:
        - cualquier acción -> EncomiendaV2Serializer
        """
        version = getattr(self.request, 'version', 'v1')

        if version == 'v2':
            return EncomiendaV2Serializer

        if self.action == 'list':
            return EncomiendaListSerializer

        if self.action == 'retrieve':
            return EncomiendaDetailSerializer

        return EncomiendaSerializer

    def get_queryset(self):
        """
        Todas las acciones del ViewSet parten de un queryset optimizado
        con con_relaciones() para evitar N+1.
        Luego se aplican filtros adicionales encima.

        Para el listado se usa only() con los campos necesarios del
        serializer ligero, incluyendo las FK recorridas por select_related.
        """
        qs = Encomienda.objects.con_relaciones()

        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        q = self.request.query_params.get('search')
        if q:
            qs = qs.filter(
                Q(codigo__icontains=q) |
                Q(remitente__apellidos__icontains=q) |
                Q(destinatario__apellidos__icontains=q) |
                Q(descripcion__icontains=q)
            )

        if self.action == 'list':
            qs = qs.only(
                'id',
                'codigo',
                'estado',
                'peso_kg',
                'costo_envio',
                'fecha_registro',
                'fecha_entrega_est',
                'fecha_entrega_real',
                'remitente',
                'remitente__nombres',
                'remitente__apellidos',
                'destinatario',
                'destinatario__nombres',
                'destinatario__apellidos',
                'ruta',
                'ruta__destino',
                'empleado_registro',
            )

        return qs

    def list(self, request, *args, **kwargs):
        """
        Agrega la cabecera X-API-Version en listados.
        """
        response = super().list(request, *args, **kwargs)
        response['X-API-Version'] = getattr(request, 'version', 'v1')
        return response

    def retrieve(self, request, *args, **kwargs):
        """
        Agrega la cabecera X-API-Version en detalles.
        """
        response = super().retrieve(request, *args, **kwargs)
        response['X-API-Version'] = getattr(request, 'version', 'v1')
        return response

    def perform_create(self, serializer):
        try:
            empleado = Empleado.objects.get(email=self.request.user.email)
        except Empleado.DoesNotExist:
            raise serializers.ValidationError({
                'detail': 'El usuario autenticado no tiene un empleado asociado.'
            })

        serializer.save(empleado_registro=empleado)
        cache.delete(f'estadisticas_empleado_{self.request.user.id}')

    def perform_update(self, serializer):
        """
        Invalidar caché cuando se actualiza una encomienda.
        """
        super().perform_update(serializer)
        cache.delete_many([
            f'estadisticas_empleado_{self.request.user.id}',
            f'encomienda_detalle_{self.kwargs.get("pk")}',
        ])

    @extend_schema(
        summary='Cambiar estado de encomienda',
        description='''
Cambia el estado de una encomienda y registra el cambio automáticamente
en el historial de estados.

Estados disponibles:
- PE: Pendiente
- TR: En tránsito
- DE: En destino
- EN: Entregado
- DV: Devuelto
''',
        request=OpenApiTypes.OBJECT,
        responses={
            200: EncomiendaSerializer,
            400: OpenApiResponse(description='Estado faltante o datos inválidos.'),
            409: OpenApiResponse(description='La encomienda ya fue entregada y no puede modificarse.'),
            422: OpenApiResponse(description='La transición de estado no está permitida.'),
        },
        examples=[
            OpenApiExample(
                'Pasar a En tránsito',
                value={
                    'estado': 'TR',
                    'observacion': 'Recogido en agencia Lima'
                },
                request_only=True,
            ),
            OpenApiExample(
                'Marcar como Entregado',
                value={
                    'estado': 'EN',
                    'observacion': 'Entregado al destinatario'
                },
                request_only=True,
            ),
        ],
        tags=['Encomiendas'],
    )
    @action(detail=True, methods=['post'], url_path='cambiar_estado')
    def cambiar_estado(self, request, version=None, pk=None):
        enc = self.get_object()
        nuevo_estado = request.data.get('estado')
        observacion = request.data.get('observacion', '')

        if not nuevo_estado:
            return Response(
                {'error': 'El campo estado es requerido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if enc.esta_entregada:
            raise EncomiendaYaEntregadaError()

        try:
            empleado = Empleado.objects.get(email=request.user.email)
            enc.cambiar_estado(nuevo_estado, empleado, observacion)
            serializer = self.get_serializer(enc)

            cache.delete_many([
                f'estadisticas_empleado_{request.user.id}',
                f'encomienda_detalle_{pk}',
            ])

            response = Response(serializer.data)
            response['X-API-Version'] = getattr(request, 'version', 'v1')
            return response
        except Empleado.DoesNotExist:
            return Response(
                {'error': 'El usuario autenticado no tiene un empleado asociado.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            raise EstadoInvalidoError(detail=str(e))

    @extend_schema(
        summary='Encomiendas con retraso',
        description='Lista todas las encomiendas activas cuya fecha estimada de entrega ya pasó.',
        tags=['Encomiendas'],
        responses={200: EncomiendaSerializer(many=True)},
    )
    @action(detail=False, methods=['get'], url_path='con_retraso')
    def con_retraso(self, request, version=None):
        qs = Encomienda.objects.con_retraso().con_relaciones()
        response = Response(self.get_serializer(qs, many=True).data)
        response['X-API-Version'] = getattr(request, 'version', 'v1')
        return response

    @extend_schema(
        summary='Encomiendas pendientes',
        description='Lista todas las encomiendas en estado Pendiente.',
        tags=['Encomiendas'],
        responses={200: EncomiendaSerializer(many=True)},
    )
    @action(detail=False, methods=['get'])
    def pendientes(self, request, version=None):
        qs = Encomienda.objects.pendientes().con_relaciones()
        response = Response(self.get_serializer(qs, many=True).data)
        response['X-API-Version'] = getattr(request, 'version', 'v1')
        return response

    @extend_schema(
        summary='Historial de estados',
        description='Devuelve el historial de cambios de estado de una encomienda, paginado con limit/offset.',
        parameters=[
            OpenApiParameter(
                name='limit',
                type=int,
                description='Número de resultados a devolver.',
                required=False,
                default=10,
            ),
            OpenApiParameter(
                name='offset',
                type=int,
                description='Posición inicial de la paginación.',
                required=False,
                default=0,
            ),
        ],
        tags=['Encomiendas'],
    )
    @action(detail=True, methods=['get'], url_path='historial')
    def historial(self, request, version=None, pk=None):
        """
        GET /api/v1/encomiendas/{pk}/historial/
        GET /api/v2/encomiendas/{pk}/historial/
        """
        enc = self.get_object()
        qs = enc.historial.select_related('empleado').order_by('-fecha_cambio')

        paginator = HistorialPagination()
        page = paginator.paginate_queryset(qs, request)

        if page is not None:
            serializer = HistorialEstadoSerializer(page, many=True)
            response = paginator.get_paginated_response(serializer.data)
            response['X-API-Version'] = getattr(request, 'version', 'v1')
            return response

        serializer = HistorialEstadoSerializer(qs, many=True)
        response = Response(serializer.data)
        response['X-API-Version'] = getattr(request, 'version', 'v1')
        return response

    @extend_schema(
        summary='Estadísticas globales',
        description='Contadores del sistema: activas, en tránsito, con retraso y entregadas hoy.',
        tags=['Encomiendas'],
        responses={
            200: OpenApiResponse(description='Objeto JSON con contadores globales del sistema.')
        },
    )
    @action(detail=False, methods=['get'])
    def estadisticas(self, request, version=None):
        """
        GET /api/v1/encomiendas/estadisticas/
        GET /api/v2/encomiendas/estadisticas/
        """
        cache_key = f'estadisticas_empleado_{request.user.id}'
        data = cache.get(cache_key)

        if data is None:
            hoy = timezone.now().date()
            data = {
                'total_activas': Encomienda.objects.activas().count(),
                'en_transito': Encomienda.objects.en_transito().count(),
                'con_retraso': Encomienda.objects.con_retraso().count(),
                'entregadas_hoy': Encomienda.objects.filter(
                    estado='EN',
                    fecha_entrega_real=hoy
                ).count(),
            }
            cache.set(cache_key, data, CACHE_TTL)

        response = Response(data)
        response['X-API-Version'] = getattr(request, 'version', 'v1')
        return response

    @extend_schema(
        summary='Crear multiples encomiendas',
        description='Crea varias encomiendas en una sola peticion. Body: lista de objetos.',
        tags=['Encomiendas'],
    )
    @action(detail=False, methods=['post'], url_path='bulk_create')
    def bulk_create(self, request, version=None):
        """
        POST /api/v1/encomiendas/bulk_create/
        Body: [{enc1}, {enc2}, {enc3}]
        Crea todas las encomiendas con una sola peticion.
        """
        serializer = self.get_serializer(
            data=request.data,
            many=True,
            context={'request': request}
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            empleado = Empleado.objects.get(email=request.user.email)
        except Empleado.DoesNotExist:
            return Response(
                {'error': 'El usuario no tiene un empleado asociado.'},
                status=status.HTTP_403_FORBIDDEN
            )

        encomiendas = serializer.save(empleado_registro=empleado)

        cache.delete(f'estadisticas_empleado_{request.user.id}')

        response = Response(
            self.get_serializer(
                encomiendas,
                many=True,
                context={'request': request}
            ).data,
            status=status.HTTP_201_CREATED
        )
        response['X-API-Version'] = getattr(request, 'version', 'v1')
        return response

    @extend_schema(
        summary='Cambiar estado a multiples encomiendas',
        description='Cambia el estado de varias encomiendas. Reporta cuales tuvieron errores.',
        tags=['Encomiendas'],
    )
    @action(detail=False, methods=['patch'], url_path='bulk_estado')
    def bulk_estado(self, request, version=None):
        """
        PATCH /api/v1/encomiendas/bulk_estado/
        Body: {"ids": [1, 2, 3], "estado": "TR", "observacion": "..."}
        Procesa cada encomienda y reporta cuales tuvieron errores.
        """
        ids = request.data.get('ids', [])
        nuevo_estado = request.data.get('estado')
        observacion = request.data.get('observacion', '')

        if not ids:
            return Response(
                {'error': 'El campo ids es requerido y no puede estar vacio.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not nuevo_estado:
            return Response(
                {'error': 'El campo estado es requerido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            empleado = Empleado.objects.get(email=request.user.email)
        except Empleado.DoesNotExist:
            return Response(
                {'error': 'El usuario no tiene un empleado asociado.'},
                status=status.HTTP_403_FORBIDDEN
            )

        encomiendas = Encomienda.objects.filter(id__in=ids)
        actualizadas = []
        errores = []

        for enc in encomiendas:
            try:
                if enc.esta_entregada:
                    raise ValueError('La encomienda ya fue entregada y no puede modificarse.')

                enc.cambiar_estado(nuevo_estado, empleado, observacion)
                actualizadas.append(enc.id)
            except ValueError as e:
                errores.append({
                    'id': enc.id,
                    'error': str(e)
                })

        ids_procesados = list(encomiendas.values_list('id', flat=True))
        no_encontrados = [i for i in ids if i not in ids_procesados]

        cache.delete_many([
            f'estadisticas_empleado_{request.user.id}',
            *[f'encomienda_detalle_{enc_id}' for enc_id in actualizadas],
        ])

        response = Response({
            'actualizadas': actualizadas,
            'errores': errores,
            'no_encontrados': no_encontrados,
            'total': len(actualizadas),
        })
        response['X-API-Version'] = getattr(request, 'version', 'v1')
        return response