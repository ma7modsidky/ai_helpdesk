"""User identity.

A custom user model exists from the first migration: the specification requires
one before any tenant or ticket tables reference it, and swapping it later is
painful. Email is the login identifier; there is no username field.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Create users with a normalized email address.

    All writes must pass through this manager or the model constructor plus
    ``set_password``; emails are stored lowercased so the unique constraint
    behaves consistently.
    """

    use_in_migrations = True

    def _create_user(self, email: str | None, password: str | None, **extra_fields: Any) -> User:
        if not email or not email.strip():
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).strip().lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self, email: str | None, password: str | None = None, **extra_fields: Any
    ) -> User:
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str | None, password: str | None = None, **extra_fields: Any
    ) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Platform identity, independent of workspace membership."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ("email",)

    def __str__(self) -> str:
        return self.email

    @property
    def display_name(self) -> str:
        return self.email
