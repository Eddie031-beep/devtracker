from collections import Counter
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.evaluations.models import Evaluation
from apps.integrations.models import Commit
from apps.projects.models import Deliverable, DeliverableVersion, ProjectMembership

User = get_user_model()
Status = Deliverable.Status

WEEKS = 8  # semanas que muestra la gráfica de commits


def _percent(part, total):
    return round(100 * part / total) if total else None


def _average(values):
    values = list(values)
    return round(sum(values) / len(values), 1) if values else None


def _latest_scores(deliverable_ids):
    """Nota vigente de cada entregable: la de su evaluación más reciente."""
    scores = {}
    for deliverable_id, score in (
        Evaluation.objects.filter(deliverable_id__in=deliverable_ids)
        .order_by("created_at")
        .values_list("deliverable_id", "score")
    ):
        scores[deliverable_id] = score  # en orden: la última pisa a las anteriores
    return scores


def _week_start(moment):
    day = timezone.localtime(moment).date()
    return day - timedelta(days=day.weekday())


def project_metrics(project):
    """Métricas de un proyecto y de cada integrante (base del dashboard de la Etapa 3).

    Solo cuenta entregables vivos (sin borrado lógico, ni el suyo ni el de su hito).
    """
    deliverables = list(
        Deliverable.objects.filter(milestone__project=project, milestone__deleted_at__isnull=True)
        .prefetch_related("assignees")
    )
    ids = [d.pk for d in deliverables]
    scores = _latest_scores(ids)

    delivered = [d for d in deliverables if d.submitted_at]
    late = [d for d in delivered if d.is_late]
    by_status = Counter(d.status for d in deliverables)

    commits = Commit.objects.filter(project=project)
    now = timezone.now()
    first_week = _week_start(now) - timedelta(weeks=WEEKS - 1)
    weekly = Counter(
        _week_start(moment)
        for moment in commits.filter(committed_at__date__gte=first_week).values_list("committed_at", flat=True)
    )
    commits_by_author = Counter(commits.exclude(author=None).values_list("author_id", flat=True))
    versions_by_author = Counter(
        DeliverableVersion.objects.filter(deliverable_id__in=ids).values_list("author_id", flat=True)
    )

    members = []
    # Primero el líder, luego los integrantes y al final los evaluadores
    order = {ProjectMembership.ProjectRole.LEADER: 0, ProjectMembership.ProjectRole.MEMBER: 1}
    memberships = sorted(
        ProjectMembership.objects.filter(project=project).select_related("user"),
        key=lambda m: (order.get(m.role, 2), m.user.username.lower()),
    )
    for membership in memberships:
        user = membership.user
        own = [d for d in deliverables if user in d.assignees.all()]
        own_delivered = [d for d in own if d.submitted_at]
        own_late = [d for d in own_delivered if d.is_late]
        members.append(
            {
                "user_id": user.pk,
                "username": user.username,
                "name": user.get_full_name() or user.username,
                "role": membership.role,
                "role_display": membership.get_role_display(),
                "assigned": len(own),
                "delivered": len(own_delivered),
                "late": len(own_late),
                "approved": sum(1 for d in own if d.status == Status.APPROVED),
                "on_time_rate": _percent(len(own_delivered) - len(own_late), len(own_delivered)),
                "average_score": _average(scores[d.pk] for d in own if d.pk in scores),
                "commits": commits_by_author.get(user.pk, 0),
                "versions": versions_by_author.get(user.pk, 0),
            }
        )

    return {
        "project": {"id": project.pk, "name": project.name},
        "deliverables": {
            "total": len(deliverables),
            "by_status": {value: by_status.get(value, 0) for value in Status.values},
            "delivered": len(delivered),
            "late": len(late),
            "on_time_rate": _percent(len(delivered) - len(late), len(delivered)),
            "approved": by_status.get(Status.APPROVED, 0),
            "average_score": _average(scores.values()),
            "overdue": sum(
                1 for d in deliverables if d.status in (Status.PENDING, Status.REJECTED) and d.is_past_due(now)
            ),
        },
        "commits": {
            "total": commits.count(),
            "linked_to_deliverables": commits.exclude(deliverable=None).count(),
            "unlinked_author": commits.filter(author=None).count(),
            "last_30_days": commits.filter(committed_at__gte=now - timedelta(days=30)).count(),
            "by_week": [
                {"week": str(first_week + timedelta(weeks=i)), "count": weekly.get(first_week + timedelta(weeks=i), 0)}
                for i in range(WEEKS)
            ],
        },
        "members": members,
    }
