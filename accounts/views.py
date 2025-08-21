from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView

from accounts.forms import CustomUserCreationForm
from accounts.models import User

if TYPE_CHECKING:
    from django.forms import BaseModelForm
    from django.http import HttpRequest, HttpResponse


class CustomLoginView(LoginView):
    """Custom login view with better styling."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self) -> str:
        """Redirect to the dashboard after successful login.

        Returns:
            str: URL to redirect to after successful login.
        """
        return reverse_lazy("core:feeds")


class CustomLogoutView(LogoutView):
    """Custom logout view."""

    next_page = reverse_lazy("feeds")
    http_method_names: ClassVar[list[str]] = ["get", "post", "options"]

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:  # noqa: ANN002, ANN003
        """Allow GET requests for logout.

        Args:
            request: The HTTP request object.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            HttpResponse: Response after logout.
        """
        return self.post(request, *args, **kwargs)


class SignUpView(CreateView):
    """User registration view."""

    model = User
    form_class = CustomUserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("feeds")

    def form_valid(self, form: BaseModelForm) -> HttpResponse:
        """Login the user after successful registration.

        Args:
            form: The validated user creation form.

        Returns:
            HttpResponse: Response after successful form processing.
        """
        response = super().form_valid(form)
        login(self.request, self.object)  # type: ignore[attr-defined]
        return response


@login_required
def profile_view(request: HttpRequest) -> HttpResponse:
    """User profile view.

    Args:
        request: The HTTP request object.

    Returns:
        HttpResponse: Rendered profile template.
    """
    return render(
        request,
        "accounts/profile.html",
        {"user": request.user},
    )
