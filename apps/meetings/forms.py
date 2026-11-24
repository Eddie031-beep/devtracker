from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.web.forms import NoColonMixin

from .models import Agreement, Meeting


def _people(field, people):
    field.queryset = people
    field.label_from_instance = lambda u: u.get_full_name() or u.username


class MeetingForm(NoColonMixin, forms.ModelForm):
    held_at = forms.DateTimeField(
        label="Fecha y hora", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
    )
    participants = forms.ModelMultipleChoiceField(label="Participantes", queryset=None, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Meeting
        fields = ["title", "held_at", "location", "participants", "summary"]
        labels = {"title": "Reunión", "location": "Lugar o enlace", "summary": "Temas tratados"}
        widgets = {
            "title": forms.TextInput(attrs={"minlength": 3, "placeholder": "Ej.: Revisión de la etapa 5"}),
            "location": forms.TextInput(attrs={"placeholder": "Aula 3-205 o enlace de Meet"}),
            "summary": forms.Textarea(attrs={"rows": 5, "minlength": 10, "placeholder": "Qué se habló y qué se decidió"}),
        }

    def __init__(self, *args, people, **kwargs):
        super().__init__(*args, **kwargs)
        _people(self.fields["participants"], people)
        # No se puede elegir una fecha futura: el acta es de una reunión que ya pasó
        self.fields["held_at"].widget.attrs["max"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
        if self.instance.pk:
            self.initial["held_at"] = timezone.localtime(self.instance.held_at)

    def clean_held_at(self):
        held_at = self.cleaned_data["held_at"]
        if held_at > timezone.now() + timedelta(hours=1):
            raise forms.ValidationError("La fecha no puede ser futura.")
        return held_at

    def clean_summary(self):
        text = self.cleaned_data["summary"].strip()
        if len(text) < 10:
            raise forms.ValidationError("Resume los temas tratados (al menos 10 caracteres).")
        return text


class AgreementForm(NoColonMixin, forms.ModelForm):
    class Meta:
        model = Agreement
        fields = ["description", "responsible", "due_date"]
        labels = {"description": "Acuerdo", "responsible": "Responsable", "due_date": "Fecha de cumplimiento"}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2, "minlength": 5, "placeholder": "Qué se hará"}),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, people, meeting, **kwargs):
        super().__init__(*args, **kwargs)
        _people(self.fields["responsible"], people)
        self.fields["responsible"].empty_label = "Elige al responsable"
        self.fields["due_date"].widget.attrs["min"] = timezone.localdate(meeting.held_at).isoformat()


class AgreementStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Agreement.Status.choices)


class AgreementFilterForm(NoColonMixin, forms.Form):
    status = forms.ChoiceField(
        label="Estado", required=False,
        choices=[("", "Todos"), ("pending", "Pendientes"), ("overdue", "Vencidos"), ("done", "Cumplidos")],
    )
    responsible = forms.ModelChoiceField(label="Responsable", queryset=None, required=False, empty_label="Todos")

    def __init__(self, *args, people, **kwargs):
        super().__init__(*args, **kwargs)
        _people(self.fields["responsible"], people)
