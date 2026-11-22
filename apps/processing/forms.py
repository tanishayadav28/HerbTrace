from datetime import date

from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import Processing


class ProcessingForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Processing
        fields = ("stage", "processing_date", "location", "description", "status")
        widgets = {
            "processing_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_processing_date(self):
        value = self.cleaned_data["processing_date"]
        if value > date.today():
            raise forms.ValidationError("Processing date cannot be in the future.")
        return value
