# api/pagination.py
from rest_framework.pagination import (
    PageNumberPagination,
    LimitOffsetPagination,
    CursorPagination,
)


class EncomiendaPagination(PageNumberPagination):
    """
    Paginación por número de página.

    Uso:
    GET /api/v1/encomiendas/?page=2
    GET /api/v1/encomiendas/?page=2&page_size=30

    Usada en: EncomiendaViewSet (listado principal)
    """
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'

    def get_paginated_response_schema(self, schema):
        """Schema para drf-spectacular (documentación Swagger)"""
        return {
            'type': 'object',
            'properties': {
                'count': {'type': 'integer', 'example': 120},
                'next': {'type': 'string', 'nullable': True},
                'previous': {'type': 'string', 'nullable': True},
                'results': schema,
            }
        }


class ClientePagination(PageNumberPagination):
    """
    Paginación para el listado de clientes.

    Uso:
    GET /api/v1/clientes/?page=2

    Usada en: ClienteListView
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50


class HistorialPagination(LimitOffsetPagination):
    """
    Paginación por limit/offset para el historial de una encomienda.

    Uso:
    GET /api/v1/encomiendas/1/historial/?limit=5&offset=10

    Usada en: acción historial del EncomiendaViewSet
    """
    default_limit = 10
    max_limit = 50


class EncomiendaCursorPagination(CursorPagination):
    """
    Paginación por cursor. Eficiente para grandes volúmenes de datos.

    Uso:
    GET /api/v1/encomiendas/feed/?cursor=cD0yMDI2LTA0...

    Usada en: acción feed del EncomiendaViewSet (tiempo real)
    """
    page_size = 15
    ordering = '-fecha_registro'