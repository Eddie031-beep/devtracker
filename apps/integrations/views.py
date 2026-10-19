import json

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project

from .services import save_push_commits, verify_signature


class GitHubWebhookView(APIView):
    """Recibe los webhooks de GitHub. Es público: la autenticación es la firma HMAC."""

    authentication_classes = []  # sin sesión ni JWT (y sin CSRF)
    permission_classes = [AllowAny]

    def post(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        # La firma se calcula sobre los bytes exactos que mandó GitHub, no sobre el JSON ya parseado
        body = request.body
        if not verify_signature(
            project.github_webhook_secret, body, request.headers.get("X-Hub-Signature-256", "")
        ):
            return Response({"detail": "Firma inválida."}, status=status.HTTP_403_FORBIDDEN)

        event = request.headers.get("X-GitHub-Event", "")
        if event == "ping":
            return Response({"detail": "pong"})
        if event != "push":
            return Response({"detail": f"Evento «{event}» ignorado."})

        try:
            payload = json.loads(body)
        except ValueError:
            return Response({"detail": "JSON inválido."}, status=status.HTTP_400_BAD_REQUEST)

        repo = (payload.get("repository") or {}).get("full_name", "")
        if project.github_repo and repo.lower() != project.github_repo.lower():
            return Response(
                {"detail": f"El push es de «{repo}», pero el proyecto está vinculado a «{project.github_repo}»."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = save_push_commits(project, payload)
        return Response({"detail": "ok", "created": created})
