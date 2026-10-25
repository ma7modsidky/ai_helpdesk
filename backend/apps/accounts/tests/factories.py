"""Factory Boy factories for account tests.

Factories write through the same manager method production uses
(``User.objects.create_user``) rather than ``Model.objects.create``. That keeps
the invariants the manager owns — lowercased email, a hashed password, an
explicit ``is_staff`` — in force inside tests, so a factory can never build a
row that the real code path would have rejected.
"""

from __future__ import annotations

from typing import Any

import factory
from factory.declarations import Sequence

from apps.accounts.models import User

# Shared with the fixtures below so tests compare against one known credential.
DEFAULT_PASSWORD = "s3cret-password"


class UserFactory(factory.django.DjangoModelFactory[User]):
    """Create a user with a usable password and a unique email.

    Use ``UserFactory.create(...)`` rather than calling the class: factory_boy's
    metaclass ``__call__`` is untyped, while ``create`` returns the model instance.
    """

    class Meta:
        model = User

    # factory_boy declares attributes through untyped descriptors.
    email = Sequence(lambda index: f"user{index}@example.com")  # type: ignore[no-untyped-call]
    password = DEFAULT_PASSWORD
    is_active = True
    is_staff = False
    is_superuser = False

    @classmethod
    def _create(cls, model_class: type[User], *args: Any, **kwargs: Any) -> User:
        password = kwargs.pop("password", DEFAULT_PASSWORD)
        email = kwargs.pop("email")
        return model_class.objects.create_user(email=email, password=password, **kwargs)
