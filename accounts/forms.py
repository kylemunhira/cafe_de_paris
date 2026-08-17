from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm


class StaffAuthenticationForm(AuthenticationForm):
    """Allow username/password or a 4-digit staff access code."""

    access_code = forms.CharField(
        label="Access code",
        required=False,
        max_length=4,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "pattern": "[0-9]{4}",
                "autocomplete": "one-time-code",
                "maxlength": "4",
                "placeholder": "••••",
            }
        ),
    )

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        self.fields["username"].required = False
        self.fields["password"].required = False

    def clean(self):
        access_code = (self.cleaned_data.get("access_code") or "").strip()
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if access_code:
            if not access_code.isdigit() or len(access_code) != 4:
                raise forms.ValidationError("Access code must be exactly 4 digits.")
            self.user_cache = authenticate(self.request, access_code=access_code)
            if self.user_cache is None:
                raise forms.ValidationError("Invalid access code.")
            self.confirm_login_allowed(self.user_cache)
            return self.cleaned_data

        if not username or not password:
            raise forms.ValidationError(
                "Enter username and password, or a 4-digit access code."
            )
        return super().clean()
