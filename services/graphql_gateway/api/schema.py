"""HyperScale Platform — GraphQL Gateway Schema.

Defines the federated GraphQL schema.
"""

import strawberry
from typing import Optional


import asyncio
import strawberry
from typing import Optional, List
from strawberry.dataloader import DataLoader

# Architectural Note (Senior Dev):
# GraphQL endpoints are prone to the N+1 query problem. To mitigate this across
# distributed microservices, we use Strawberry DataLoaders. These batch multiple
# ID lookups into a single network request to the downstream service (e.g., User
# Service or Product Service) via gRPC or REST.

async def load_users(keys: List[strawberry.ID]) -> List[Any]:
    """Batch load users from the User Service."""
    # In production: make a single gRPC call: stub.GetUsersByIds(keys)
    # Mocking the network call for demonstration:
    await asyncio.sleep(0.01)
    return [
        User(id=key, email=f"user_{key}@example.com", first_name="Test", last_name="User")
        for key in keys
    ]

async def load_products(keys: List[strawberry.ID]) -> List[Any]:
    """Batch load products from the Product Service."""
    await asyncio.sleep(0.01)
    return [
        Product(id=key, title=f"Product {key}", description="Great product", price=2999)
        for key in keys
    ]

user_loader = DataLoader(load_fn=load_users)
product_loader = DataLoader(load_fn=load_products)


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
    async def me(self, info: strawberry.Info) -> Optional[User]:
        # Typically extract user ID from JWT in info.context
        return await user_loader.load(strawberry.ID("123"))

    @strawberry.field
    async def product(self, id: strawberry.ID) -> Optional[Product]:
        return await product_loader.load(id)

    @strawberry.field
    async def products(self, ids: List[strawberry.ID]) -> List[Product]:
        """Fetch multiple products efficiently using DataLoader batching."""
        return await product_loader.load_many(ids)

schema = strawberry.federation.Schema(query=Query)
