from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .permissions import IsAdmin
from .serializers import (
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    RoleUpdateSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


class LogoutView(APIView):
    """Invalida el refresh token (queda en la lista negra de SimpleJWT)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            return Response({"detail": "Token inválido o expirado."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserListView(generics.ListAPIView):
    queryset = User.objects.order_by("username")
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]


class UserRoleUpdateView(generics.UpdateAPIView):
    """Solo un administrador puede cambiar el rol global de un usuario."""

    queryset = User.objects.all()
    serializer_class = RoleUpdateSerializer
    permission_classes = [IsAdmin]
    http_method_names = ["patch"]

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(UserSerializer(self.get_object()).data)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"], is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            send_mail(
                subject="DevTracker: recuperación de contraseña",
                message=(
                    f"Hola {user},\n\n"
                    "Usa estos datos para restablecer tu contraseña en POST /api/auth/password-reset/confirm/:\n\n"
                    f"uid: {uid}\ntoken: {token}\n\n"
                    "Si no solicitaste el cambio, ignora este correo."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )
        # Misma respuesta exista o no el correo, para no revelar qué cuentas existen
        return Response({"detail": "Si el correo está registrado, recibirás instrucciones para restablecer la contraseña."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Contraseña actualizada correctamente."})
