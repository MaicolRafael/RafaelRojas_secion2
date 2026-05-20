from decimal import Decimal
import uuid

from django.utils import timezone
from rest_framework import serializers

from .models import Encomienda, HistorialEstado
from clientes.models import Cliente
from rutas.models import Ruta


class ClienteSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.ReadOnlyField()
    esta_activo = serializers.ReadOnlyField()

    class Meta:
        model = Cliente
        fields = [
            'id',
            'tipo_doc',
            'nro_doc',
            'nombres',
            'apellidos',
            'nombre_completo',
            'telefono',
            'email',
            'esta_activo',
        ]


class RutaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ruta
        fields = [
            'id',
            'codigo',
            'origen',
            'destino',
            'precio_base',
            'dias_entrega',
            'estado',
        ]


class HistorialEstadoSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.ReadOnlyField(source='empleado.__str__')
    estado_anterior_display = serializers.CharField(
        source='get_estado_anterior_display',
        read_only=True
    )
    estado_nuevo_display = serializers.CharField(
        source='get_estado_nuevo_display',
        read_only=True
    )

    class Meta:
        model = HistorialEstado
        fields = [
            'id',
            'estado_anterior',
            'estado_anterior_display',
            'estado_nuevo',
            'estado_nuevo_display',
            'empleado_nombre',
            'observacion',
            'fecha_cambio',
        ]


class EncomiendaBulkSerializer(serializers.ListSerializer):
    """
    Serializer para operaciones masivas.
    Se activa automaticamente cuando se usa EncomiendaSerializer(many=True).
    Reemplaza los metodos create() y update() por versiones optimizadas.
    """

    def create(self, validated_data):
        """
        Crear multiples encomiendas con una sola query SQL.
        """
        encomiendas = [
            Encomienda(**item) for item in validated_data
        ]
        return Encomienda.objects.bulk_create(encomiendas)

    def update(self, instances, validated_data):
        """
        Actualizar multiples encomiendas.
        Nota: bulk_update no dispara signals ni save() del modelo.
        """
        instance_map = {enc.id: enc for enc in instances}
        updated = []

        for item in validated_data:
            enc_id = item.pop('id', None)
            enc = instance_map.get(enc_id)

            if enc:
                for campo, valor in item.items():
                    setattr(enc, campo, valor)
                updated.append(enc)

        if updated:
            Encomienda.objects.bulk_update(
                updated,
                ['estado', 'observaciones', 'costo_envio'],
            )

        return updated


class EncomiendaListSerializer(serializers.ModelSerializer):
    """
    Serializer optimizado para el listado.
    Solo los campos necesarios para mostrar la tabla.
    No incluye descripcion larga, observaciones ni historial.
    """
    remitente_nombre = serializers.ReadOnlyField(source='remitente.nombre_completo')
    destinatario_nombre = serializers.ReadOnlyField(source='destinatario.nombre_completo')
    ruta_destino = serializers.ReadOnlyField(source='ruta.destino')
    estado_display = serializers.SerializerMethodField()
    tiene_retraso = serializers.ReadOnlyField()

    class Meta:
        model = Encomienda
        fields = [
            'id',
            'codigo',
            'estado',
            'estado_display',
            'remitente_nombre',
            'destinatario_nombre',
            'ruta_destino',
            'peso_kg',
            'costo_envio',
            'fecha_registro',
            'fecha_entrega_est',
            'tiene_retraso',
        ]

    def get_estado_display(self, obj):
        return obj.get_estado_display()


class EncomiendaSerializer(serializers.ModelSerializer):
    esta_entregada = serializers.ReadOnlyField()
    tiene_retraso = serializers.ReadOnlyField()
    dias_en_transito = serializers.ReadOnlyField()
    descripcion_corta = serializers.ReadOnlyField()
    estado_display = serializers.SerializerMethodField()

    class Meta:
        model = Encomienda
        fields = [
            'id',
            'codigo',
            'descripcion',
            'descripcion_corta',
            'peso_kg',
            'volumen_cm3',
            'costo_envio',
            'remitente',
            'destinatario',
            'ruta',
            'empleado_registro',
            'estado',
            'estado_display',
            'fecha_registro',
            'fecha_entrega_est',
            'fecha_entrega_real',
            'esta_entregada',
            'tiene_retraso',
            'dias_en_transito',
            'observaciones',
        ]
        read_only_fields = [
            'fecha_registro',
            'fecha_entrega_real',
            'empleado_registro',
        ]
        list_serializer_class = EncomiendaBulkSerializer

    def get_estado_display(self, obj):
        return obj.get_estado_display()

    def to_representation(self, instance):
        """
        Se ejecuta al serializar (convertir objeto -> JSON).
        Permite modificar la respuesta despues de que DRF la genera.
        """
        data = super().to_representation(instance)

        if instance.ruta_id:
            data['ruta_codigo'] = instance.ruta.codigo
            data['ruta_destino'] = instance.ruta.destino
            data['ruta_origen'] = instance.ruta.origen

        data['costo_display'] = f'S/ {instance.costo_envio:.2f}'

        request = self.context.get('request')
        if request and not request.user.is_staff:
            data.pop('observaciones', None)
            data.pop('empleado_registro', None)

        colores = {
            'PE': 'gray',
            'TR': 'blue',
            'DE': 'orange',
            'EN': 'green',
            'DV': 'red',
        }
        data['estado_color'] = colores.get(instance.estado, 'gray')

        return data

    def to_internal_value(self, data):
        """
        Se ejecuta al deserializar (convertir JSON -> objeto Python).
        Se usa para limpiar y normalizar ANTES de la validacion.
        """
        if hasattr(data, '_mutable'):
            data._mutable = True

        data = data.copy() if hasattr(data, 'copy') else dict(data)

        if 'codigo' in data and data['codigo']:
            data['codigo'] = str(data['codigo']).upper().strip()

        if 'descripcion' in data and data['descripcion']:
            data['descripcion'] = str(data['descripcion']).strip()

        if 'costo_envio' in data and data['costo_envio']:
            try:
                from decimal import Decimal, ROUND_HALF_UP
                costo = Decimal(str(data['costo_envio']))
                data['costo_envio'] = str(
                    costo.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                )
            except Exception:
                pass

        return super().to_internal_value(data)

    def validate_peso_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError('El peso debe ser mayor a 0 kg.')
        if value > 500:
            raise serializers.ValidationError('El peso máximo permitido es 500 kg.')
        return value

    def validate_codigo(self, value):
        if value and not value.startswith('ENC-'):
            raise serializers.ValidationError('El código debe comenzar con ENC-.')
        return value.upper() if value else value

    def validate_costo_envio(self, value):
        if value < 0:
            raise serializers.ValidationError('El costo no puede ser negativo.')
        return value

    def validate(self, data):
        errors = {}

        remitente = data.get('remitente') or getattr(self.instance, 'remitente', None)
        destinatario = data.get('destinatario') or getattr(self.instance, 'destinatario', None)
        fecha_est = data.get('fecha_entrega_est') or getattr(self.instance, 'fecha_entrega_est', None)
        ruta = data.get('ruta') or getattr(self.instance, 'ruta', None)
        costo = data.get('costo_envio')
        if costo is None and self.instance is not None:
            costo = self.instance.costo_envio

        if remitente and destinatario and remitente == destinatario:
            errors['destinatario'] = 'El destinatario no puede ser el mismo que el remitente.'

        if fecha_est and fecha_est < timezone.now().date():
            errors['fecha_entrega_est'] = 'La fecha estimada no puede ser en el pasado.'

        if ruta and costo is not None and costo < ruta.precio_base:
            errors['costo_envio'] = f'El costo mínimo para esta ruta es S/ {ruta.precio_base}.'

        if errors:
            raise serializers.ValidationError(errors)

        return data

    def create(self, validated_data):
        ruta = validated_data['ruta']
        peso_kg = validated_data['peso_kg']

        if not validated_data.get('codigo'):
            validated_data['codigo'] = (
                f'ENC-{timezone.now().strftime("%Y%m%d")}-'
                f'{str(uuid.uuid4())[:6].upper()}'
            )

        if not validated_data.get('fecha_entrega_est'):
            validated_data['fecha_entrega_est'] = (
                timezone.now().date() + timezone.timedelta(days=ruta.dias_entrega)
            )

        if not validated_data.get('costo_envio'):
            precio_base = Decimal(str(ruta.precio_base))
            peso_base = Decimal('5.0')
            precio_extra = Decimal('2.50')
            peso_actual = Decimal(str(peso_kg))

            costo = precio_base
            if peso_actual > peso_base:
                costo += (peso_actual - peso_base) * precio_extra

            validated_data['costo_envio'] = costo.quantize(Decimal('0.01'))

        return Encomienda.objects.create(**validated_data)


class EncomiendaDetailSerializer(serializers.ModelSerializer):
    remitente = ClienteSerializer(read_only=True)
    destinatario = ClienteSerializer(read_only=True)
    ruta = RutaSerializer(read_only=True)

    remitente_id = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.activos(),
        write_only=True,
        source='remitente'
    )
    destinatario_id = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.activos(),
        write_only=True,
        source='destinatario'
    )
    ruta_id = serializers.PrimaryKeyRelatedField(
        queryset=Ruta.objects.activas(),
        write_only=True,
        source='ruta'
    )

    historial = serializers.SerializerMethodField()
    esta_entregada = serializers.ReadOnlyField()
    tiene_retraso = serializers.ReadOnlyField()
    dias_en_transito = serializers.ReadOnlyField()

    class Meta:
        model = Encomienda
        fields = [
            'id',
            'codigo',
            'descripcion',
            'peso_kg',
            'remitente',
            'remitente_id',
            'destinatario',
            'destinatario_id',
            'ruta',
            'ruta_id',
            'estado',
            'costo_envio',
            'fecha_registro',
            'fecha_entrega_est',
            'fecha_entrega_real',
            'esta_entregada',
            'tiene_retraso',
            'dias_en_transito',
            'historial',
            'observaciones',
        ]
        read_only_fields = ['fecha_registro', 'fecha_entrega_real']

    def get_historial(self, obj):
        return HistorialEstadoSerializer(
            obj.historial.all()[:5],
            many=True
        ).data

    def validate_peso_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError('El peso debe ser mayor a 0 kg.')
        if value > 500:
            raise serializers.ValidationError('El peso máximo permitido es 500 kg.')
        return value

    def validate_codigo(self, value):
        if value and not value.startswith('ENC-'):
            raise serializers.ValidationError('El código debe comenzar con ENC-.')
        return value.upper() if value else value

    def validate_costo_envio(self, value):
        if value < 0:
            raise serializers.ValidationError('El costo no puede ser negativo.')
        return value

    def validate(self, data):
        errors = {}

        remitente = data.get('remitente') or getattr(self.instance, 'remitente', None)
        destinatario = data.get('destinatario') or getattr(self.instance, 'destinatario', None)
        fecha_est = data.get('fecha_entrega_est') or getattr(self.instance, 'fecha_entrega_est', None)
        ruta = data.get('ruta') or getattr(self.instance, 'ruta', None)
        costo = data.get('costo_envio')
        if costo is None and self.instance is not None:
            costo = self.instance.costo_envio

        if remitente and destinatario and remitente == destinatario:
            errors['destinatario'] = 'El destinatario no puede ser el mismo que el remitente.'

        if fecha_est and fecha_est < timezone.now().date():
            errors['fecha_entrega_est'] = 'La fecha estimada no puede ser en el pasado.'

        if ruta and costo is not None and costo < ruta.precio_base:
            errors['costo_envio'] = f'El costo mínimo para esta ruta es S/ {ruta.precio_base}.'

        if errors:
            raise serializers.ValidationError(errors)

        return data


class EncomiendaV2Serializer(serializers.ModelSerializer):
    remitente = ClienteSerializer(read_only=True)
    destinatario = ClienteSerializer(read_only=True)
    ruta = RutaSerializer(read_only=True)

    remitente_id = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.activos(),
        write_only=True,
        source='remitente'
    )
    destinatario_id = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.activos(),
        write_only=True,
        source='destinatario'
    )
    ruta_id = serializers.PrimaryKeyRelatedField(
        queryset=Ruta.objects.activas(),
        write_only=True,
        source='ruta'
    )

    dias_en_transito = serializers.ReadOnlyField()
    tiene_retraso = serializers.ReadOnlyField()
    esta_entregada = serializers.ReadOnlyField()
    descripcion_corta = serializers.ReadOnlyField()
    meta = serializers.SerializerMethodField()

    class Meta:
        model = Encomienda
        fields = [
            'id',
            'codigo',
            'descripcion',
            'descripcion_corta',
            'peso_kg',
            'volumen_cm3',
            'costo_envio',
            'remitente',
            'remitente_id',
            'destinatario',
            'destinatario_id',
            'ruta',
            'ruta_id',
            'estado',
            'fecha_registro',
            'fecha_entrega_est',
            'fecha_entrega_real',
            'dias_en_transito',
            'tiene_retraso',
            'esta_entregada',
            'observaciones',
            'meta',
        ]
        read_only_fields = [
            'fecha_registro',
            'fecha_entrega_real',
        ]

    def get_meta(self, obj):
        return {
            'version': 'v2',
            'generado': timezone.now().date().isoformat(),
        }

    def validate_peso_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError('El peso debe ser mayor a 0 kg.')
        if value > 500:
            raise serializers.ValidationError('El peso máximo permitido es 500 kg.')
        return value

    def validate_codigo(self, value):
        if value and not value.startswith('ENC-'):
            raise serializers.ValidationError('El código debe comenzar con ENC-.')
        return value.upper() if value else value

    def validate_costo_envio(self, value):
        if value < 0:
            raise serializers.ValidationError('El costo no puede ser negativo.')
        return value

    def validate(self, data):
        errors = {}

        remitente = data.get('remitente') or getattr(self.instance, 'remitente', None)
        destinatario = data.get('destinatario') or getattr(self.instance, 'destinatario', None)
        fecha_est = data.get('fecha_entrega_est') or getattr(self.instance, 'fecha_entrega_est', None)
        ruta = data.get('ruta') or getattr(self.instance, 'ruta', None)
        costo = data.get('costo_envio')
        if costo is None and self.instance is not None:
            costo = self.instance.costo_envio

        if remitente and destinatario and remitente == destinatario:
            errors['destinatario'] = 'El destinatario no puede ser el mismo que el remitente.'

        if fecha_est and fecha_est < timezone.now().date():
            errors['fecha_entrega_est'] = 'La fecha estimada no puede ser en el pasado.'

        if ruta and costo is not None and costo < ruta.precio_base:
            errors['costo_envio'] = f'El costo mínimo para esta ruta es S/ {ruta.precio_base}.'

        if errors:
            raise serializers.ValidationError(errors)

        return data

    def create(self, validated_data):
        ruta = validated_data['ruta']
        peso_kg = validated_data['peso_kg']

        if not validated_data.get('codigo'):
            validated_data['codigo'] = (
                f'ENC-{timezone.now().strftime("%Y%m%d")}-'
                f'{str(uuid.uuid4())[:6].upper()}'
            )

        if not validated_data.get('fecha_entrega_est'):
            validated_data['fecha_entrega_est'] = (
                timezone.now().date() + timezone.timedelta(days=ruta.dias_entrega)
            )

        if not validated_data.get('costo_envio'):
            precio_base = Decimal(str(ruta.precio_base))
            peso_base = Decimal('5.0')
            precio_extra = Decimal('2.50')
            peso_actual = Decimal(str(peso_kg))

            costo = precio_base
            if peso_actual > peso_base:
                costo += (peso_actual - peso_base) * precio_extra

            validated_data['costo_envio'] = costo.quantize(Decimal('0.01'))

        return Encomienda.objects.create(**validated_data)