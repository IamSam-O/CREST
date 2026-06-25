from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm


class BootstrapFormMixin:
    """Applies the app's existing form-control / form-check-input classes
    (themed via public/styles.css's CSS variables) to every field, so these
    server-rendered pages match the SPA's theme instead of bare Bootstrap."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = 'form-check-input' if isinstance(field.widget, forms.CheckboxInput) else 'form-control'
            field.widget.attrs['class'] = css_class


class ThemedAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    pass


class ThemedPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class InviteAcceptForm(BootstrapFormMixin, UserCreationForm):
    class Meta:
        model = get_user_model()
        fields = ('username',)
