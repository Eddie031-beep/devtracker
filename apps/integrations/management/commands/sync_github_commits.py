from urllib.error import HTTPError, URLError

from django.core.management.base import BaseCommand, CommandError

from apps.projects.models import Project

from ...tasks import sync_project_commits


class Command(BaseCommand):
    help = (
        "Trae el historial de commits desde GitHub sin pasar por Celery (útil en staging sin worker). "
        "Uso: sync_github_commits <id> [<id> ...] o sync_github_commits --all"
    )

    def add_arguments(self, parser):
        parser.add_argument("project_ids", nargs="*", type=int, help="ids de los proyectos a sincronizar")
        parser.add_argument("--all", action="store_true", help="todos los proyectos con repo de GitHub vinculado")

    def handle(self, *args, **options):
        if options["all"] == bool(options["project_ids"]):
            raise CommandError("Indica los ids de los proyectos o --all (no ambos).")

        projects = Project.objects.exclude(github_repo="")
        if options["project_ids"]:
            projects = projects.filter(pk__in=options["project_ids"])
            missing = set(options["project_ids"]) - set(projects.values_list("pk", flat=True))
            if missing:
                ids = ", ".join(str(pk) for pk in sorted(missing))
                raise CommandError(f"Proyecto(s) inexistente(s) o sin repo de GitHub vinculado: {ids}")

        if not projects.exists():
            self.stdout.write("No hay proyectos con repo de GitHub vinculado.")
            return

        failed = 0
        for project in projects.order_by("pk"):
            try:
                # Se llama a la tarea directamente: corre aquí mismo, sin Redis ni worker
                result = sync_project_commits(project.pk)
            except HTTPError as error:
                failed += 1
                self.stderr.write(f"✗ {project} ({project.github_repo}): GitHub respondió {error.code}")
                continue
            except URLError as error:
                failed += 1
                self.stderr.write(f"✗ {project} ({project.github_repo}): sin conexión con GitHub ({error.reason})")
                continue
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ {project} ({project.github_repo}): {result['created']} commits nuevos, "
                    f"{result['linked']} vinculados"
                )
            )

        if failed:
            raise CommandError(f"Falló la sincronización de {failed} proyecto(s).")
