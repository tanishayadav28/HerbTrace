from django import forms


class BootstrapFormMixin:
    """Adds Bootstrap 5 classes to every widget so templates stay clean."""

    def _style_fields(self):
        for field in self.fields.values():
            widget = field.widget
            css = widget.attrs.get("class", "")
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = f"{css} form-check-input".strip()
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = f"{css} form-select".strip()
            elif isinstance(widget, forms.FileInput):
                widget.attrs["class"] = f"{css} form-control".strip()
            else:
                widget.attrs["class"] = f"{css} form-control".strip()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()
