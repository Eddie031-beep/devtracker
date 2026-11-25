from django import forms
from django.utils import timezone

from apps.web.forms import NoColonMixin

from . import matrix
from .models import Risk


def _people_field(field, people):
    field.queryset = people
    field.label_from_instance = lambda u: u.get_full_name() or u.username


class RiskForm(NoColonMixin, forms.ModelForm):
    probability = forms.TypedChoiceField(label="Probabilidad", choices=matrix.SCALE, coerce=int)
    impact = forms.TypedChoiceField(label="Impacto", choices=matrix.IMPACT_SCALE, coerce=int)

    class Meta:
        model = Risk
        fields = ["title", "description", "probability", "impact", "owner"]
        labels = {"title": "Riesgo", "description": "Descripción", "owner": "Responsable"}
        widgets = {
            "title": forms.TextInput(attrs={"minlength": 5, "placeholder": "Ej.: Un integrante abandona el curso"}),
            "description": forms.Textarea(attrs={"rows": 3, "minlength": 10, "placeholder": "Qué podría pasar y qué afectaría"}),
        }

    def __init__(self, *args, people, **kwargs):
        super().__init__(*args, **kwargs)
        _people_field(self.fields["owner"], people)
        self.fields["owner"].empty_label = "Elige al responsable"
        # El navegador calcula el nivel mientras se elige (ver risks/_level_preview.html)
        for name in ("probability", "impact"):
            self.fields[name].widget.attrs["data-risk-input"] = name

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if len(title) < 5:
            raise forms.ValidationError("El riesgo debe tener al menos 5 caracteres.")
        return title

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 10:
            raise forms.ValidationError("Describe el riesgo con al menos 10 caracteres.")
        return text


class StatusForm(NoColonMixin, forms.Form):
    status = forms.ChoiceField(label="Nuevo estado", choices=Risk.Status.choices)
    comment = forms.CharField(
        label="Comentario", required=False, max_length=2000,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Obligatorio si se materializa o se cierra"}),
    )

    def __init__(self, *args, choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if choices is not None:
            self.fields["status"].choices = choices


class MitigationForm(NoColonMixin, forms.Form):
    description = forms.CharField(
        label="Medida", min_length=5, max_length=2000,
        widget=forms.Textarea(attrs={"rows": 2, "minlength": 5, "placeholder": "Qué se hará para reducir el riesgo"}),
    )
    responsible = forms.ModelChoiceField(label="Responsable", queryset=None, required=False, empty_label="Sin responsable")
    due_date = forms.DateField(label="Fecha límite", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, people, **kwargs):
        super().__init__(*args, **kwargs)
        _people_field(self.fields["responsible"], people)
        self.fields["due_date"].widget.attrs["min"] = timezone.localdate().isoformat()

    def clean_due_date(self):
        due = self.cleaned_data["due_date"]
        if due and due < timezone.localdate():
            raise forms.ValidationError("La fecha no puede estar en el pasado.")
        return due


class RiskFilterForm(NoColonMixin, forms.Form):
    status = forms.ChoiceField(label="Estado", required=False, choices=[("", "Todos"), *Risk.Status.choices])
    level = forms.ChoiceField(label="Nivel", required=False, choices=[("", "Todos"), *matrix.LEVEL_LABELS.items()])
    owner = forms.ModelChoiceField(label="Responsable", queryset=None, required=False, empty_label="Todos")
    p = forms.TypedChoiceField(required=False, choices=[("", "")] + [(str(v), v) for v, _ in matrix.SCALE], coerce=int, empty_value=None, widget=forms.HiddenInput)
    i = forms.TypedChoiceField(required=False, choices=[("", "")] + [(str(v), v) for v, _ in matrix.SCALE], coerce=int, empty_value=None, widget=forms.HiddenInput)

    def __init__(self, *args, people, **kwargs):
        super().__init__(*args, **kwargs)
        _people_field(self.fields["owner"], people)
