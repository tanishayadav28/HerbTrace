from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password

from apps.core.forms import BootstrapFormMixin

from .models import User


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    username = forms.CharField(
        label="Username or email",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser and user.approval_status == User.Approval.PENDING:
            raise forms.ValidationError(
                "Your registration is waiting for administrator approval. "
                "You will be able to sign in once it is approved.",
                code="pending",
            )
        if not user.is_superuser and user.approval_status == User.Approval.REJECTED:
            raise forms.ValidationError(
                "Your registration was not approved. Please contact the administrator.",
                code="rejected",
            )


class FarmerRegistrationForm(BootstrapFormMixin, UserCreationForm):
    """Public self-registration. Always creates a PENDING farmer account."""

    first_name = forms.CharField(max_length=60, label="First name")
    last_name = forms.CharField(max_length=60, label="Last name")
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone", "organization")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.FARMER
        user.approval_status = User.Approval.PENDING
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class StaffUserForm(BootstrapFormMixin, forms.ModelForm):
    """Admin-managed account creation / editing for every role."""

    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Required for new users. Leave blank when editing to keep the current password.",
    )

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "organization",
            "role",
            "approval_status",
            "is_active",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        qs = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if not self.instance.pk and not password:
            self.add_error("password", "A password is required for new users.")
        if password:
            try:
                validate_password(password, self.instance)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class StyledPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    pass
