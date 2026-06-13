"""HyperScale Platform — User Service Test Factories.

Factory Boy factories for generating test data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import factory
from faker import Faker

fake = Faker()


class UserFactory(factory.Factory):
    """Factory for creating User test data dictionaries.

    Example:
        >>> user_data = UserFactory()
        >>> user_data = UserFactory(email="specific@example.com", roles=["admin"])
    """

    class Meta:
        """Factory configuration."""
        model = dict

    email = factory.LazyFunction(lambda: fake.email())
    phone = factory.LazyFunction(lambda: fake.phone_number())
    password_hash = factory.LazyFunction(
        lambda: "$2b$12$LJ3m4y1aITDrK.g3j1Cq8OFcHW0p55/bsQmqZCXs9.KJ8rKHKXxG"
    )
    full_name = factory.LazyFunction(lambda: fake.name())
    avatar_url = factory.LazyFunction(lambda: fake.image_url())
    roles = factory.LazyFunction(lambda: ["customer"])
    is_verified = False
    is_active = True
    last_login = None
    firebase_uid = None
    oauth_providers = factory.LazyFunction(list)
    metadata = factory.LazyFunction(dict)
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))
    is_deleted = False


class RoleFactory(factory.Factory):
    """Factory for creating Role test data dictionaries."""

    class Meta:
        """Factory configuration."""
        model = dict

    name = factory.Sequence(lambda n: f"role_{n}")
    display_name = factory.LazyAttribute(lambda o: o.name.replace("_", " ").title())
    description = factory.LazyFunction(lambda: fake.sentence())
    permissions = factory.LazyFunction(lambda: ["users:read"])
    is_system = False
    priority = factory.Sequence(lambda n: n * 10)


class UserProfileFactory(factory.Factory):
    """Factory for creating UserProfile test data dictionaries."""

    class Meta:
        """Factory configuration."""
        model = dict

    user_id = factory.LazyFunction(lambda: str(fake.uuid4()))
    bio = factory.LazyFunction(lambda: fake.text(max_nb_chars=200))
    social_links = factory.LazyFunction(lambda: {"github": fake.url()})
    preferences = factory.LazyFunction(lambda: {"theme": "dark"})
    location = factory.LazyFunction(lambda: fake.city())
    timezone = "UTC"
    language = "en"


class RegisterRequestFactory(factory.Factory):
    """Factory for creating RegisterRequest test data."""

    class Meta:
        """Factory configuration."""
        model = dict

    email = factory.LazyFunction(lambda: fake.email())
    password = "SecurePass123!"
    full_name = factory.LazyFunction(lambda: fake.name())
    phone = factory.LazyFunction(lambda: fake.phone_number())


class LoginRequestFactory(factory.Factory):
    """Factory for creating LoginRequest test data."""

    class Meta:
        """Factory configuration."""
        model = dict

    email = factory.LazyFunction(lambda: fake.email())
    password = "SecurePass123!"
