from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.models import Action
from apps.audit.services import log_action
from apps.projects.models import Deliverable
from apps.projects.services import change_status

from .models import Evaluation

Status = Deliverable.Status

# Estados en los que el evaluador puede calificar: lo entregado (a tiempo o tarde) o lo que ya está en revisión
EVALUABLE_STATES = {Status.SUBMITTED, Status.LATE, Status.IN_REVIEW}


@transaction.atomic
def evaluate_deliverable(deliverable, user, decision, score, feedback=""):
    """Califica un entregable: lo aprueba o lo rechaza con una nota de 0 a 100.

    Reutiliza el flujo de estados (#5): si el entregable recién se entregó, primero pasa a
    «En revisión» y luego a la decisión, así cada paso queda en la auditoría.
    `change_status` valida que el usuario sea evaluador o líder del proyecto.
    """
    if decision not in Evaluation.Decision.values:
        raise ValidationError(f"«{decision}» no es una decisión válida: usa approved o rejected.")
    if not 0 <= score <= 100:
        raise ValidationError("La nota debe estar entre 0 y 100.")

    deliverable = Deliverable.objects.select_for_update().get(pk=deliverable.pk)
    if deliverable.status not in EVALUABLE_STATES:
        raise ValidationError(
            f"No se puede evaluar un entregable en estado «{deliverable.get_status_display()}»."
        )

    if deliverable.status != Status.IN_REVIEW:
        deliverable = change_status(deliverable, user, Status.IN_REVIEW)
    deliverable = change_status(deliverable, user, decision)

    evaluation = Evaluation.objects.create(
        deliverable=deliverable, evaluator=user, decision=decision, score=score, feedback=feedback or ""
    )
    log_action(
        user,
        Action.DELIVERABLE_EVALUATED,
        deliverable,
        changes={"decision": {"before": None, "after": decision}, "score": {"before": None, "after": score}},
    )
    return evaluation
