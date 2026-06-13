"""HyperScale Platform — GraphQL Gateway URLs."""

from django.urls import path
from strawberry.django.views import AsyncGraphQLView
from services.graphql_gateway.api.schema import schema

urlpatterns = [
    path("graphql", AsyncGraphQLView.as_view(schema=schema)),
]
