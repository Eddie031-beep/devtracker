from django.db import transaction

from .models import Action
from .services import diff, log_action, snapshot


class AuditedMixin:
    """Registra en la auditoría el crear/editar/borrar de una vista genérica de DRF.

    Uso:
        class MilestoneDetailView(AuditedMixin, generics.RetrieveUpdateDestroyAPIView):
            audit_entity = "milestone"
            audit_fields = ("title", "description", "due_date")

    En las vistas que ya sobrescriben `perform_create`, llama `self.audit_created(instance)`
    justo después de `serializer.save()` (dentro de su misma transacción).
    """

    audit_entity = None  # "project" | "milestone" | "deliverable"
    audit_fields = ()

    def _audit_action(self, verb):
        return Action(f"{self.audit_entity}.{verb}")

    def audit_created(self, instance):
        after = snapshot(instance, self.audit_fields)
        log_action(self.request.user, self._audit_action("created"), instance, changes=diff({}, after) or {})

    @transaction.atomic
    def perform_update(self, serializer):
        before = snapshot(serializer.instance, self.audit_fields)
        instance = serializer.save()
        changes = diff(before, snapshot(instance, self.audit_fields))
        if changes:
            log_action(self.request.user, self._audit_action("updated"), instance, changes=changes)

    @transaction.atomic
    def perform_destroy(self, instance):
        before = snapshot(instance, self.audit_fields)
        instance.delete()  # borrado lógico (SoftDeleteModel)
        log_action(
            self.request.user,
            self._audit_action("deleted"),
            instance,
            changes={field: {"before": value, "after": None} for field, value in before.items()},
        )
