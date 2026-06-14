"""HyperScale Platform

Architectural Note (Senior Dev):
    This package acts as a boundary context for the microservice. Exposing internal
    modules explicitly via __all__ (where applicable) prevents namespace pollution
    and enforces strict dependency boundaries. In distributed systems, keeping
    domain boundaries airtight prevents unintended coupling that can lead to cascading
    failures across independent deployments.
"""
