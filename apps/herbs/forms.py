from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import ApprovedRegion, Herb


class HerbForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Herb
        fields = ("name", "botanical_name", "part_used", "description", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class ApprovedRegionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ApprovedRegion
        fields = (
            "name", "state", "center_latitude", "center_longitude", "radius_km",
            "herbs", "notes", "is_active",
        )
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "herbs": forms.SelectMultiple(attrs={"size": 6}),
            "center_latitude": forms.NumberInput(attrs={"step": "0.000001"}),
            "center_longitude": forms.NumberInput(attrs={"step": "0.000001"}),
            "radius_km": forms.NumberInput(attrs={"step": "0.01", "min": "0.1"}),
        }
