from django import forms

from apps.web.forms import NoColonMixin

from .models import Issue


class IssueForm(NoColonMixin, forms.ModelForm):
    """Registrar o editar una incidencia. El responsable solo lo elige el líder (ver la vista)."""

    assignee = forms.ModelChoiceField(label="Responsable", queryset=None, required=False, empty_label="Sin asignar")

    class Meta:
        model = Issue
        fields = ["title", "priority", "description", "steps_to_reproduce"]
        labels = {
            "title": "Título",
            "priority": "Prioridad",
            "description": "Descripción del error",
            "steps_to_reproduce": "Pasos para reproducirlo",
        }
        widgets = {
            "title": forms.TextInput(attrs={"minlength": 5, "placeholder": "Ej.: El login devuelve error 500"}),
            "description": forms.Textarea(attrs={"rows": 3, "minlength": 10}),
            "steps_to_reproduce": forms.Textarea(
                attrs={"rows": 4, "placeholder": "1. Entrar a…\n2. Hacer clic en…\n3. Aparece…"}
            ),
        }

    def __init__(self, *args, assignees=None, **kwargs):
        super().__init__(*args, **kwargs)
        if assignees is None:
            del self.fields["assignee"]
        else:
            self.fields["assignee"].queryset = assignees
            self.fields["assignee"].label_from_instance = lambda u: u.get_full_name() or u.username

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if len(title) < 5:
            raise forms.ValidationError("El título debe tener al menos 5 caracteres.")
        return title

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 10:
            raise forms.ValidationError("Describe el error con al menos 10 caracteres.")
        return text


class AssignForm(NoColonMixin, forms.Form):
    assignee = forms.ModelChoiceField(label="Responsable", queryset=None, required=False, empty_label="Sin asignar")

    def __init__(self, *args, assignees, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = assignees
        self.fields["assignee"].label_from_instance = lambda u: u.get_full_name() or u.username


class TransitionForm(NoColonMixin, forms.Form):
    action = forms.ChoiceField(choices=[(a, a) for a in ("start", "resolve", "verify", "reopen")], widget=forms.HiddenInput)
    comment = forms.CharField(label="Comentario", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 2}))


class CommentForm(NoColonMixin, forms.Form):
    comment = forms.CharField(
        label="Comentario", max_length=2000, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Escribe un comentario…"})
    )


class IssueFilterForm(NoColonMixin, forms.Form):
    status = forms.ChoiceField(label="Estado", required=False, choices=[("", "Todos"), *Issue.Status.choices])
    priority = forms.ChoiceField(label="Prioridad", required=False, choices=[("", "Todas"), *Issue.Priority.choices])
    assignee = forms.ModelChoiceField(label="Responsable", queryset=None, required=False, empty_label="Todos")

    def __init__(self, *args, assignees, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = assignees
        self.fields["assignee"].label_from_instance = lambda u: u.get_full_name() or u.username
