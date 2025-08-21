from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from django.db.models import Model


class ReaderRouter:
    """Route all models with app_label="reader" to the 'reader' database."""

    route_app_labels: ClassVar[set[str]] = {"reader"}

    def db_for_read(self, model: type[Model], **hints: dict[str, Any]) -> str | None:  # noqa: ARG002
        if model._meta.app_label in self.route_app_labels:  # noqa: SLF001
            return "reader"
        return None

    def db_for_write(self, model: type[Model], **hints: dict[str, Any]) -> str | None:  # noqa: ARG002
        if model._meta.app_label in self.route_app_labels:  # noqa: SLF001
            return "reader"
        return None

    def allow_migrate(
        self,
        db: str,  # noqa: ARG002
        app_label: str,
        model_name: str | None = None,  # noqa: ARG002
        **hints: dict[str, Any],  # noqa: ARG002
    ) -> bool | None:
        if app_label in self.route_app_labels:
            return False
        return None
