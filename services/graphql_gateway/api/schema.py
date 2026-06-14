"""HyperScale Platform — GraphQL Gateway Schema.

Defines the federated GraphQL schema.
"""

import strawberry
from typing import Optional


import asyncio
import aiohttp
import strawberry
from typing import Optional, List, Any
from strawberry.dataloader import DataLoader
from shared.config import get_settings

# Architectural Note (Senior Dev):
# GraphQL endpoints are prone to the N+1 query problem. To mitigate this across
# distributed microservices, we use Strawberry DataLoaders. These batch multiple
# ID lookups into a single network request to the downstream service (e.g., User
# Service or Product Service) via REST or gRPC.

async def load_users(keys: List[strawberry.ID]) -> List[Any]:
    """Batch load users from the User Service via internal REST API."""
    settings = get_settings()
    url = f"http://localhost:{settings.USER_SERVICE_PORT}/api/v1/users/batch"
    
    try:
        async with aiohttp.ClientSession() as session:
            # We send a batch POST request with all IDs
            async with session.post(url, json={"ids": [str(k) for k in keys]}) as response:
                if response.status == 200:
                    data = await response.json()
                    # Map response back to User objects in order of keys
                    user_map = {u["id"]: User(**u) for u in data.get("users", [])}
                    return [user_map.get(str(k)) for k in keys]
    except Exception:
        pass
        
    # Fallback/Graceful degradation if service is down
    return [None for _ in keys]

async def load_products(keys: List[strawberry.ID]) -> List[Any]:
    """Batch load products from the Product Service via internal REST API."""
    settings = get_settings()
    url = f"http://localhost:{settings.PRODUCT_SERVICE_PORT}/api/v1/products/batch"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"ids": [str(k) for k in keys]}) as response:
                if response.status == 200:
                    data = await response.json()
                    prod_map = {p["id"]: Product(**p) for p in data.get("products", [])}
                    return [prod_map.get(str(k)) for k in keys]
    except Exception:
        pass
        
    return [None for _ in keys]

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
