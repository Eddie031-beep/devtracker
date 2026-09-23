from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "global_role")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "password")

    def validate(self, attrs):
        # Valida la contraseña con los validadores de settings (longitud, similitud, etc.)
        candidate = User(username=attrs.get("username"), email=attrs.get("email"))
        password_validation.validate_password(attrs["password"], candidate)
        return attrs

    def create(self, validated_data):
        # El rol no se elige al registrarse: todo usuario nuevo es estudiante
        return User.objects.create_user(**validated_data)


class RoleUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("global_role",)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    default_error_messages = {"invalid_link": "El enlace de recuperación no es válido o ya expiró."}

    def validate(self, attrs):
        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            self.fail("invalid_link")

        if not default_token_generator.check_token(user, attrs["token"]):
            self.fail("invalid_link")

        password_validation.validate_password(attrs["new_password"], user)
        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
