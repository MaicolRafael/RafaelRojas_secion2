import factory
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from clientes.models import Cliente
from rutas.models import Ruta
from envios.models import Empleado, Encomienda


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@encomiendas.pe')

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        raw_password = extracted or 'test1234'
        self.set_password(raw_password)
        if create:
            self.save()


class ClienteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cliente

    tipo_doc = 'DNI'
    nro_doc = factory.Sequence(lambda n: f'700000{n:02d}')
    nombres = factory.Sequence(lambda n: f'Cliente{n}')
    apellidos = factory.Sequence(lambda n: f'Apellido{n}')
    telefono = factory.Sequence(lambda n: f'999000{n:03d}')
    email = factory.Sequence(lambda n: f'cliente{n}@mail.com')
    direccion = factory.Sequence(lambda n: f'Direccion {n}')
    estado = 1
    fecha_registro = factory.LazyFunction(timezone.now)


class RutaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ruta

    codigo = factory.Sequence(lambda n: f'RUT-{n:03d}')
    origen = 'Chiclayo'
    destino = factory.Sequence(lambda n: f'Destino {n}')
    descripcion = factory.Sequence(lambda n: f'Ruta de prueba {n}')
    precio_base = Decimal('25.00')
    dias_entrega = 1
    estado = 1


class EmpleadoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Empleado

    codigo = factory.Sequence(lambda n: f'EMP-{n:03d}')
    nombres = factory.Sequence(lambda n: f'Empleado{n}')
    apellidos = factory.Sequence(lambda n: f'Apellido{n}')
    cargo = 'Tester'
    email = factory.Sequence(lambda n: f'empleado{n}@encomiendas.pe')
    telefono = factory.Sequence(lambda n: f'988000{n:03d}')
    estado = 1
    fecha_ingreso = factory.LazyFunction(lambda: timezone.now().date())


class EncomiendaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Encomienda

    codigo = factory.Sequence(lambda n: f'ENC-2026-{n:03d}')
    descripcion = factory.Sequence(lambda n: f'Encomienda de prueba {n}')
    peso_kg = Decimal('5.00')
    volumen_cm3 = Decimal('1000.00')
    remitente = factory.SubFactory(ClienteFactory)
    destinatario = factory.SubFactory(ClienteFactory)
    ruta = factory.SubFactory(RutaFactory)
    empleado_registro = factory.SubFactory(EmpleadoFactory)
    estado = 'PE'
    costo_envio = Decimal('25.00')
    fecha_registro = factory.LazyFunction(timezone.now)
    fecha_entrega_est = factory.LazyFunction(
        lambda: timezone.now().date() + timedelta(days=2)
    )
    fecha_entrega_real = None
    observaciones = 'Creada desde factory'