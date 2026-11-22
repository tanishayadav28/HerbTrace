from datetime import date

from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import LaboratoryTest


class LabTestForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LaboratoryTest
        fields = (
            "test_date", "purity_percentage", "moisture_percentage",
            "contamination_details", "observations", "remarks", "result",
        )
        widgets = {
            "test_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "purity_percentage": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
            "moisture_percentage": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
            "contamination_details": forms.Textarea(attrs={"rows": 3}),
            "observations": forms.Textarea(attrs={"rows": 3}),
            "remarks": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["result"].choices = [("", "Select result…")] + list(LaboratoryTest.Result.choices)

    def clean_test_date(self):
        value = self.cleaned_data["test_date"]
        if value > date.today():
            raise forms.ValidationError("Test date cannot be in the future.")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("result") == LaboratoryTest.Result.FAIL and not (
            (cleaned.get("remarks") or "").strip() or (cleaned.get("contamination_details") or "").strip()
        ):
            self.add_error("remarks", "Explain the reason for a FAIL result in remarks or contamination details.")
        return cleaned
