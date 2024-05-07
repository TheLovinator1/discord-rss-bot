from __future__ import annotations

import typing

from crispy_bootstrap5.bootstrap5 import FloatingField
from crispy_forms.helper import FormHelper
from crispy_forms.layout import ButtonHolder, Layout, Submit
from django import forms

from feeds.models.webhooks import Webhook


class WebhookForm(forms.ModelForm):
    class Meta:
        model = Webhook
        fields: typing.ClassVar[list[str]] = ["name", "url"]

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        """Initialize the form. We use crispy forms to make the form look nice."""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            FloatingField("name"),
            FloatingField("url"),
            ButtonHolder(Submit("submit", "Submit")),
        )
