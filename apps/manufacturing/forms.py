from datetime import date

from django import forms

from apps.core.forms import BootstrapFormMixin
from apps.traceability.models import Batch

from .models import FinalFormulation, Manufacturing
from .services import eligible_batches


class ManufacturingForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Manufacturing
        fields = ("manufacturer_name", "manufacturing_date", "location", "details")
        widgets = {
            "manufacturing_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "details": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_manufacturing_date(self):
        value = self.cleaned_data["manufacturing_date"]
        if value > date.today():
            raise forms.ValidationError("Manufacturing date cannot be in the future.")
        return value


class FormulationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = FinalFormulation
        fields = ("product_name", "formulation_date", "packaging_info")
        widgets = {
            "formulation_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "packaging_info": forms.Textarea(attrs={"rows": 3}),
        }


class BatchSelectionForm(forms.Form):
    """Only laboratory-passed, fully processed, not-yet-manufactured batches are valid."""

    batches = forms.ModelMultipleChoiceField(
        queryset=Batch.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Select at least one eligible batch."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batches"].queryset = eligible_batches().select_related("collection__herb")
