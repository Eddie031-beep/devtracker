from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import URLValidator

from apps.evaluations.models import Evaluation


class NoColonMixin:
    """Etiquetas sin «:» al final, como en el diseño."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)


class SubmitForm(NoColonMixin, forms.Form):
    url = forms.URLField(
        label="Enlace de la entrega",
        max_length=2000,
        validators=[URLValidator(schemes=["http", "https"])],
        widget=forms.URLInput(attrs={"placeholder": "https://github.com/..."}),
    )
    comment = forms.CharField(label="Comentario (opcional)", required=False, widget=forms.Textarea(attrs={"rows": 2}))


class EvaluateForm(NoColonMixin, forms.Form):
    decision = forms.ChoiceField(label="Decisión", choices=Evaluation.Decision.choices)
    score = forms.IntegerField(label="Nota (0 a 100)", min_value=0, max_value=100)
    feedback = forms.CharField(label="Retroalimentación", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class ProfileForm(NoColonMixin, forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name", "github_username")
        labels = {"first_name": "Nombre", "last_name": "Apellido", "github_username": "Usuario de GitHub"}
        help_texts = {
            "github_username": "Sirve para vincular tus commits y para entrar con GitHub. Ej.: Eddie031-beep",
        }


class MilestoneForm(NoColonMixin, forms.Form):
    title = forms.CharField(label="Título del hito", max_length=200)
    description = forms.CharField(label="Descripción", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    due_date = forms.DateField(label="Fecha de cierre", widget=forms.DateInput(attrs={"type": "date"}))


class DeliverableForm(NoColonMixin, forms.Form):
    milestone = forms.ModelChoiceField(label="Hito", queryset=None, empty_label="Elige un hito")
    title = forms.CharField(label="Título del entregable", max_length=200)
    description = forms.CharField(label="Qué hay que entregar", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    due_at = forms.DateTimeField(label="Fecha y hora de entrega", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    assignees = forms.ModelMultipleChoiceField(
        label="Asignar a", queryset=None, required=False, widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["milestone"].queryset = project.milestones.order_by("due_date")
        self.fields["assignees"].queryset = (
            get_user_model().objects.filter(memberships__project=project).order_by("first_name", "username")
        )
        self.fields["assignees"].label_from_instance = lambda u: u.get_full_name() or u.username


class AuditFilterForm(NoColonMixin, forms.Form):
    action = forms.ChoiceField(label="Acción", required=False)
    actor = forms.ModelChoiceField(label="Integrante", queryset=None, required=False, empty_label="Todos")
    date_from = forms.DateField(label="Desde", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label="Hasta", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, actors, **kwargs):
        from apps.audit.models import Action

        super().__init__(*args, **kwargs)
        self.fields["action"].choices = [("", "Todas las acciones"), *Action.choices]
        self.fields["actor"].queryset = actors
        self.fields["actor"].label_from_instance = lambda u: u.get_full_name() or u.username
