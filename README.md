# HyperScale Platform

A real-time, microservices-based platform built with Django, MongoDB, Redis, Kafka, gRPC, WebSockets, and Firebase.

## Technology Stack

- **Language:** Python 3.12+
- **Framework:** Django 5.x + Django REST Framework
- **Database:** MongoDB (via Motor async driver + Beanie ODM)
- **Cache/PubSub:** Redis 7+ (via aioredis)
- **Message Broker:** Apache Kafka (via aiokafka)
- **RPC:** gRPC + Protocol Buffers (protobuf3)
- **Real-Time:** Django Channels + WebSockets (ASGI)
- **Containerization:** Podman

## Services

- **User Service:** Authentication, profile management, JWT handling.
- **Product Service:** Product catalog, inventory, gRPC integration.
- **Order Service:** Shopping cart, order placement saga, payment intent generation.
- **Chat Service:** Real-time messaging, WebSocket channels.
- **Notification Service:** Push notifications, Kafka consumer for system events.
