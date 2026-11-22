from datetime import date

from django import forms

from apps.core.forms import BootstrapFormMixin
from apps.herbs.geo import valid_coordinates
from apps.herbs.models import Herb

from .models import Collection


class CollectionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Collection
        fields = (
            "herb", "collection_date", "collection_time", "quantity", "unit",
            "collection_method", "source_type", "sustainability_details",
            "permit_available", "permit_number", "location_name",
            "latitude", "longitude", "coordinate_source", "gps_accuracy_m",
        )
        widgets = {
            "collection_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "collection_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "quantity": forms.NumberInput(attrs={"step": "0.001", "min": "0.001"}),
            "sustainability_details": forms.Textarea(attrs={"rows": 3}),
            "latitude": forms.NumberInput(attrs={"step": "0.000001", "id": "id_latitude"}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001", "id": "id_longitude"}),
            "coordinate_source": forms.HiddenInput(),
            "gps_accuracy_m": forms.HiddenInput(),
        }
        labels = {"location_name": "Collection location (village / forest range / farm)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["herb"].queryset = Herb.objects.filter(is_active=True)
        self.fields["herb"].empty_label = "Select herb…"
        self.fields["coordinate_source"].required = False
        self.fields["gps_accuracy_m"].required = False
        self.fields["collection_method"].choices = [("", "Select method…")] + list(
            Collection.Method.choices
        )
        self.fields["source_type"].choices = [("", "Select source…")] + list(
            Collection.SourceType.choices
        )

    def clean_collection_date(self):
        value = self.cleaned_data["collection_date"]
        if value > date.today():
            raise forms.ValidationError("Collection date cannot be in the future.")
        return value

    def clean(self):
        cleaned = super().clean()
        lat, lng = cleaned.get("latitude"), cleaned.get("longitude")
        if (lat is None) != (lng is None):
            raise forms.ValidationError("Provide both latitude and longitude, or leave both empty.")
        if lat is not None and not valid_coordinates(lat, lng):
            raise forms.ValidationError("Coordinates are outside the valid range.")
        if lat is None:
            cleaned["coordinate_source"] = Collection.CoordinateSource.NONE
            cleaned["gps_accuracy_m"] = None
        else:
            source = cleaned.get("coordinate_source")
            if source not in (Collection.CoordinateSource.GPS, Collection.CoordinateSource.MANUAL):
                cleaned["coordinate_source"] = Collection.CoordinateSource.MANUAL
        if cleaned.get("source_type") == Collection.SourceType.WILD and not (
            cleaned.get("sustainability_details") or ""
        ).strip():
            self.add_error(
                "sustainability_details",
                "Sustainability information is required for wild collection.",
            )
        if cleaned.get("permit_available") and not (cleaned.get("permit_number") or "").strip():
            self.add_error("permit_number", "Enter the permit number when a permit is available.")
        return cleaned


class RegionReviewForm(BootstrapFormMixin, forms.Form):
    note = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional note"})
    )
