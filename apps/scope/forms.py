from django import forms

from apps.web.forms import NoColonMixin

from .models import ChangeRequest


class ChangeRequestForm(NoColonMixin, forms.ModelForm):
    affected_deliverables = forms.ModelMultipleChoiceField(
        label="Entregables que tocaría (solo referencia)", queryset=None, required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Aprobar la solicitud no los modifica: el líder los ajusta después si hace falta.",
    )

    class Meta:
        model = ChangeRequest
        fields = ["title", "description", "justification", "expected_impact", "impact_level", "affected_deliverables"]
        labels = {
            "title": "Cambio propuesto", "description": "Descripción del cambio", "justification": "Justificación",
            "expected_impact": "Impacto esperado", "impact_level": "Nivel de impacto",
        }
        help_texts = {"description": "", "expected_impact": "En tiempo, entregables, calidad o equipo."}
        widgets = {
            "title": forms.TextInput(attrs={"minlength": 5, "placeholder": "Ej.: Quitar el login con Google"}),
            "description": forms.Textarea(attrs={"rows": 3, "minlength": 10}),
            "justification": forms.Textarea(attrs={"rows": 3, "minlength": 10, "placeholder": "Por qué hace falta"}),
            "expected_impact": forms.Textarea(attrs={"rows": 3, "minlength": 10}),
        }

    def __init__(self, *args, deliverables, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["affected_deliverables"]
        field.queryset = deliverables
        field.label_from_instance = lambda d: f"#D{d.pk} {d.title}"

    def clean(self):
        data = super().clean()
        for name, minimum in (("title", 5), ("description", 10), ("justification", 10), ("expected_impact", 10)):
            value = (data.get(name) or "").strip()
            if name in data and len(value) < minimum:
                self.add_error(name, f"Escribe al menos {minimum} caracteres.")
        return data


class DecisionForm(NoColonMixin, forms.Form):
    decision = forms.ChoiceField(choices=[("approved", "Aprobar"), ("rejected", "Rechazar")], widget=forms.HiddenInput)
    comment = forms.CharField(
        label="Comentario de la decisión", min_length=5, max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3, "minlength": 5, "placeholder": "Por qué se aprueba o se rechaza"}),
    )


class ChangeFilterForm(NoColonMixin, forms.Form):
    status = forms.ChoiceField(label="Estado", required=False, choices=[("", "Todas"), *ChangeRequest.Status.choices])
