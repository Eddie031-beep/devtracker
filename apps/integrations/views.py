import json

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project

from .services import save_pull_request, save_push_commits, submit_from_pull_request, verify_signature


class GitHubWebhookView(APIView):
    """Recibe los webhooks de GitHub. Es público: la autenticación es la firma HMAC."""

    authentication_classes = []  # sin sesión ni JWT (y sin CSRF)
    permission_classes = [AllowAny]

    @extend_schema(
        request={"application/json": dict},
        responses={200: OpenApiResponse(description="Commits guardados"), 403: OpenApiResponse(description="Firma inválida")},
        description="Endpoint para GitHub: exige la cabecera X-Hub-Signature-256.",
    )
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
        if event not in ("push", "pull_request"):
            return Response({"detail": f"Evento «{event}» ignorado."})

        try:
            payload = json.loads(body)
        except ValueError:
            return Response({"detail": "JSON inválido."}, status=status.HTTP_400_BAD_REQUEST)

        repo = (payload.get("repository") or {}).get("full_name", "")
        if project.github_repo and repo.lower() != project.github_repo.lower():
            return Response(
                {"detail": f"El evento es de «{repo}», pero el proyecto está vinculado a «{project.github_repo}»."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if event == "pull_request":
            pull, created = save_pull_request(project, payload.get("pull_request") or {})
            if pull is None:
                return Response({"detail": "El evento no trae el pull request."}, status=status.HTTP_400_BAD_REQUEST)
            submitted = submit_from_pull_request(pull, payload.get("action", ""))
            return Response({"detail": "ok", "pull_request": pull.number, "created": created, "submission": submitted})

        created = save_push_commits(project, payload)
        return Response({"detail": "ok", "created": created})
