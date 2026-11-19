from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.integrations.services import link_user_commits
from apps.projects.models import Project, ProjectMembership

User = get_user_model()
Role = ProjectMembership.ProjectRole

# usuario, nombre, apellido, usuario de GitHub, correo, rol en el proyecto, responsabilidades
TEAM = [
    ("harold", "Harold", "Morales", "AtunConMayonesa06", "hm707947@gmail.com", Role.MEMBER, "Permisos, auditoría"),
    ("brayan", "Brayan", "Quintero", "Brashan09", "quinbrayan9@gmail.com", Role.MEMBER, "CRUD, historial de versiones"),
    ("carlos", "Carlos", "Miranda", "Litdemonick", "badleon2744@gmail.com", Role.MEMBER, "Autenticación, webhook de GitHub"),
    ("eliecias", "Eliecias", "Cubilla", "ElieCubi", "eliecubi@gmail.com", Role.MEMBER, "Integrantes, sincronización de GitHub"),
]
EVALUATOR = ("profesor", "Profesor", "Evaluador", "", "profesor@devtracker.local", Role.EVALUATOR, "Revisa y evalúa entregables")


class Command(BaseCommand):
    help = (
        "Crea o actualiza los usuarios del equipo (y un evaluador) con la contraseña indicada y los agrega al "
        "proyecto con su rol y responsabilidades. Se puede correr más de una vez."
    )

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="contraseña inicial de todos los usuarios del equipo")
        parser.add_argument("--proyecto", type=int, default=1, help="id del proyecto (por defecto 1)")
        parser.add_argument("--sin-evaluador", action="store_true", help="no crea el usuario «profesor»")

    @transaction.atomic
    def handle(self, *args, **options):
        project = Project.objects.filter(pk=options["proyecto"]).first()
        if project is None:
            raise CommandError(f"No existe el proyecto {options['proyecto']}.")

        people = TEAM if options["sin_evaluador"] else [*TEAM, EVALUATOR]
        rows = []
        for username, first, last, github, email, role, duties in people:
            user = User.objects.filter(username=username).first() or User(username=username)
            user.first_name, user.last_name, user.is_active = first, last, True
            if github and not User.objects.filter(github_username__iexact=github).exclude(pk=user.pk).exists():
                user.github_username = github
            # Si el correo ya lo usa otra cuenta, se deja el que tenía (el correo es único)
            if not User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                user.email = email
            elif not user.email:
                user.email = f"{username}@devtracker.local"
            if role == Role.EVALUATOR:
                user.global_role = User.GlobalRole.EVALUATOR
            user.set_password(options["password"])
            user.save()
            membership, _ = ProjectMembership.objects.get_or_create(project=project, user=user, defaults={"role": role})
            membership.responsibilities = membership.responsibilities or duties
            membership.save(update_fields=["responsibilities"])
            if user.github_username:
                link_user_commits(user)  # sus commits ya sincronizados pasan a ser suyos
            rows.append(f"  {username:<10} {first} {last:<10} · {membership.get_role_display()}")

        self.stdout.write(self.style.SUCCESS(f"✓ Equipo listo en {project.name}:"))
        self.stdout.write("\n".join(rows))
        self.stdout.write("Todos entran con la contraseña indicada; cada uno puede cambiarla después.")
