"""HyperScale Platform — GraphQL Gateway Schema.

Defines the federated GraphQL schema.
"""

import strawberry
from typing import Optional


@strawberry.type
class User:
    id: strawberry.ID
    email: str
    first_name: str
    last_name: str


@strawberry.type
class Product:
    id: strawberry.ID
    title: str
    description: str
    price: int


@strawberry.type
class Query:
    @strawberry.field
    def me(self) -> Optional[User]:
        # Placeholder
        return User(
            id=strawberry.ID("123"),
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )

    @strawberry.field
    def product(self, id: strawberry.ID) -> Optional[Product]:
        # Placeholder
        return Product(
            id=id,
            title="Sample Product",
            description="A great product.",
            price=2999,
        )


schema = strawberry.federation.Schema(query=Query)
