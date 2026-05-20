# api/auth_views.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


class EncomiendaTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Agregar datos básicos del usuario al payload del JWT
        token['username'] = user.username
        token['email'] = user.email

        # Agregar datos del empleado, si existen
        try:
            emp = user.empleado
            token['empleado_id'] = emp.id
            token['empleado_cod'] = emp.codigo
            token['cargo'] = emp.cargo
        except Exception:
            pass

        return token


class EncomiendaTokenView(TokenObtainPairView):
    serializer_class = EncomiendaTokenSerializer