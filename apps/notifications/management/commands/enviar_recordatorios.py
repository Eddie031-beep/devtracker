from django.core.management.base import BaseCommand

from ...services import send_due_reminders


class Command(BaseCommand):
    help = "Avisa a los asignados de los entregables que vencen pronto y siguen sin entregarse."

    def add_arguments(self, parser):
        parser.add_argument("--horas", type=int, default=48, help="ventana de vencimiento en horas (por defecto 48)")

    def handle(self, *args, **options):
        created = send_due_reminders(hours=options["horas"])
        self.stdout.write(self.style.SUCCESS(f"✓ {created} recordatorios enviados."))
