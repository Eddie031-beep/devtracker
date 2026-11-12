from django import forms
from django.core.validators import URLValidator

from apps.evaluations.models import Evaluation


class SubmitForm(forms.Form):
    url = forms.URLField(
        label="Enlace de la entrega",
        max_length=2000,
        validators=[URLValidator(schemes=["http", "https"])],
        widget=forms.URLInput(attrs={"placeholder": "https://github.com/..."}),
    )
    comment = forms.CharField(label="Comentario (opcional)", required=False, widget=forms.Textarea(attrs={"rows": 2}))


class EvaluateForm(forms.Form):
    decision = forms.ChoiceField(label="Decisión", choices=Evaluation.Decision.choices)
    score = forms.IntegerField(label="Nota (0 a 100)", min_value=0, max_value=100)
    feedback = forms.CharField(label="Retroalimentación", required=False, widget=forms.Textarea(attrs={"rows": 3}))
