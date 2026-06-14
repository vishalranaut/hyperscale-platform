<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Django-5.x-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django">
  <img src="https://img.shields.io/badge/MongoDB-7.0-47A248?style=for-the-badge&logo=mongodb&logoColor=white" alt="MongoDB">
  <img src="https://img.shields.io/badge/Redis-7.2-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis">
  <img src="https://img.shields.io/badge/Kafka-3.x-231F20?style=for-the-badge&logo=apachekafka&logoColor=white" alt="Kafka">
  <img src="https://img.shields.io/badge/gRPC-1.67-244c5a?style=for-the-badge&logo=google&logoColor=white" alt="gRPC">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License">
</p>

<h1 align="center">⚡ HyperScale Platform</h1>

<p align="center">
  <strong>A production-grade, real-time microservices platform built for scale.</strong><br>
  Event-driven architecture • Async-first • Cloud-native • Fully containerized
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-services">Services</a> •
  <a href="#-contributing">Contributing</a> •
  <a href="#-roadmap">Roadmap</a>
</p>

---

## 🎯 What is HyperScale?

HyperScale Platform is a **production-ready microservices ecosystem** demonstrating best practices in distributed systems design. It showcases real-world patterns including the **Saga Pattern** for distributed transactions, **CQRS**, **Event Sourcing** via Kafka, **WebSocket** real-time communication, and **gRPC** inter-service communication — all built with Python 3.12+ and Django 5.x.

Whether you're learning microservices, building your portfolio, or looking for a battle-tested reference architecture — HyperScale is for you.

---

## 🏗️ Architecture

```
                            ┌───────────────────────┐
                            │    GraphQL Gateway     │
                            │   (Strawberry + DL)    │
                            └──────────┬────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                   │
          ┌────────▼────────┐ ┌───────▼────────┐ ┌───────▼────────┐
          │  User Service   │ │ Product Service│ │  Order Service  │
          │  (REST + gRPC)  │ │  (REST + gRPC) │ │  (Saga Pattern) │
          └────────┬────────┘ └───────┬────────┘ └───────┬────────┘
                   │                  │                   │
          ┌────────▼──────────────────▼───────────────────▼────────┐
          │                    Apache Kafka                         │
          │               (Event Bus / Pub-Sub)                    │
          └────────┬──────────────────┬───────────────────┬────────┘
                   │                  │                   │
          ┌────────▼────────┐ ┌───────▼────────┐ ┌───────▼────────┐
          │  Chat Service   │ │  Notification  │ │   Analytics    │
          │  (WebSockets)   │ │  Service (FCM) │ │    Service     │
          └─────────────────┘ └────────────────┘ └────────────────┘
                                                          │
                                                  ┌───────▼────────┐
                                                  │   AI Service   │
                                                  │ (Recommender)  │
                                                  └────────────────┘

          ┌────────────────────────────────────────────────────────┐
          │         MongoDB          Redis           Prometheus    │
          │        (Primary)       (Cache/PubSub)   (Monitoring)   │
          └────────────────────────────────────────────────────────┘
```

---

## 🧰 Technology Stack

| Layer             | Technology                                      |
|-------------------|--------------------------------------------------|
| **Language**      | Python 3.12+                                     |
| **Framework**     | Django 5.x + Django REST Framework               |
| **Database**      | MongoDB 7.0 (Motor async driver + Beanie ODM)    |
| **Cache / PubSub**| Redis 7.2 (hiredis)                              |
| **Message Broker**| Apache Kafka (aiokafka)                          |
| **RPC**           | gRPC + Protocol Buffers 3                        |
| **Real-Time**     | Django Channels + WebSockets (ASGI)              |
| **Push Notifs**   | Firebase Admin SDK (FCM)                         |
| **GraphQL**       | Strawberry GraphQL (Federation + DataLoaders)    |
| **Auth**          | JWT (PyJWT) + Firebase Auth + API Keys           |
| **Containers**    | Podman / Docker Compose                          |
| **Orchestration** | Kubernetes (manifests included)                  |
| **Monitoring**    | Prometheus + Grafana + OpenTelemetry             |
| **CI/CD**         | GitHub Actions                                   |
| **Load Testing**  | Locust                                           |

---

## 📂 Project Structure

```
hyperscale-platform/
├── .github/workflows/       # CI/CD pipeline (GitHub Actions)
├── docker-compose.yml       # Local infrastructure (MongoDB, Redis, Kafka, etc.)
├── pyproject.toml           # Python project config & dependencies
├── .env.example             # Environment variable template
│
├── proto/                   # Protocol Buffer definitions
│   ├── common.proto
│   ├── user.proto
│   ├── product.proto
│   └── order.proto
│
├── shared/                  # Shared libraries (used by all services)
│   ├── auth/                #   JWT handler, Firebase token verification
│   ├── cache/               #   Redis client wrapper
│   ├── config.py            #   Centralized Pydantic settings (12-Factor)
│   ├── db/                  #   MongoDB/Beanie initialization
│   ├── exceptions.py        #   Global exception hierarchy
│   ├── kafka/               #   Kafka producer, consumer, schemas
│   ├── logging.py           #   Structured logging (structlog)
│   └── middleware/           #   Auth, rate limiting, tracing middleware
│
├── services/                # Microservices
│   ├── user_service/        #   User registration, login, roles, profiles
│   ├── product_service/     #   Product catalog, inventory management
│   ├── order_service/       #   Cart, orders, Saga orchestration
│   ├── chat_service/        #   Real-time messaging (WebSockets)
│   ├── notification_service/#   Push notifications (Firebase FCM)
│   ├── analytics_service/   #   Event aggregation, daily metrics
│   ├── ai_service/          #   Recommendation engine
│   └── graphql_gateway/     #   Federated GraphQL entry point
│
├── k8s/                     # Kubernetes deployment manifests
├── infra/                   # Infrastructure configs (Prometheus, etc.)
└── load_tests/              # Locust load testing suite
```

---

## 🚀 Quick Start

### Prerequisites

| Tool       | Version   | Installation                                  |
|------------|-----------|-----------------------------------------------|
| Python     | ≥ 3.12    | [python.org](https://python.org)              |
| Docker     | ≥ 24.0    | [docker.com](https://docker.com) or Podman    |
| Git        | ≥ 2.40    | [git-scm.com](https://git-scm.com)           |

### 1. Clone the Repository

```bash
git clone https://github.com/vishalranaut/hyperscale-platform.git
cd hyperscale-platform
```

### 2. Set Up Environment Variables

```bash
cp .env.example .env
# Edit .env with your local settings (defaults work for Docker setup)
```

### 3. Start Infrastructure

```bash
# Start MongoDB, Redis, Kafka, Prometheus, and Grafana
docker-compose up -d

# Verify all containers are running
docker-compose ps
```

### 4. Install Python Dependencies

```bash
# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate    # Linux/macOS
venv\Scripts\activate       # Windows

# Install all dependencies (core + dev + test)
pip install -e ".[all]"
```

### 5. Run a Service

```bash
# Example: Start the User Service
cd services/user_service
uvicorn services.user_service.asgi:application --host 0.0.0.0 --port 8001 --reload
```

### 6. Run Tests

```bash
pytest services/user_service/tests -v
```

---

## 🔌 Services Overview

### 👤 User Service (`port 8001`)
Authentication, user profiles, role-based access control (RBAC), JWT token management, and Firebase federated identity.

| Endpoint                    | Method | Description            |
|-----------------------------|--------|------------------------|
| `/api/v1/auth/register`     | POST   | Register a new user    |
| `/api/v1/auth/login`        | POST   | Login & receive tokens |
| `/api/v1/auth/refresh`      | POST   | Refresh access token   |
| `/api/v1/users/me`          | GET    | Get current user       |
| `/api/v1/users/<id>`        | GET    | Get user by ID         |

### 📦 Product Service (`port 8002`)
Product catalog management, inventory tracking with atomic operations via MongoDB, and gRPC endpoints for inter-service calls.

| Endpoint                    | Method | Description             |
|-----------------------------|--------|-------------------------|
| `/api/v1/products`          | GET    | List products           |
| `/api/v1/products`          | POST   | Create product (admin)  |
| `/api/v1/products/<id>`     | GET    | Get product details     |
| `/api/v1/inventory/<id>`    | PATCH  | Update stock (atomic)   |

### 🛒 Order Service (`port 8003`)
Shopping cart (Redis-backed), order placement using the **Saga Pattern** with compensating transactions, and payment intent lifecycle.

| Endpoint                    | Method | Description             |
|-----------------------------|--------|-------------------------|
| `/api/v1/cart`              | GET    | View cart               |
| `/api/v1/cart/items`        | POST   | Add item to cart        |
| `/api/v1/orders`            | POST   | Place order (saga)      |
| `/api/v1/orders/<id>`       | GET    | Get order details       |

### 💬 Chat Service (`port 8005`)
Real-time messaging over WebSockets with Redis-backed channel layers, typing indicators, read receipts, and online presence tracking.

```
ws://localhost:8005/ws/chat/?token=<JWT>
```

### 🔔 Notification Service (`port 8004`)
Firebase Cloud Messaging (FCM) push notifications, triggered automatically by Kafka events (e.g., `order.confirmed`, `message.received`).

### 📊 Analytics Service (`port 8006`)
Consumes platform events from Kafka and aggregates them into MongoDB time-series daily metrics.

### 🤖 AI Service (`port 8007`)
Content-based recommendation engine using MongoDB aggregation pipelines and a pre-computed cache layer.

### 🌐 GraphQL Gateway (`port 8000`)
Federated Strawberry GraphQL gateway with DataLoaders to prevent N+1 queries across microservices.

```
http://localhost:8000/graphql
```

---

## 🤝 Contributing

We love contributions! HyperScale is designed as a learning platform and a real-world reference — every improvement helps the entire community.

### How to Contribute

1. **Fork the repository** — Click the "Fork" button at the top right of this page.

2. **Clone your fork**
   ```bash
   git clone https://github.com/<your-username>/hyperscale-platform.git
   cd hyperscale-platform
   ```

3. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Make your changes** — Follow the coding standards below.

5. **Run the tests**
   ```bash
   pip install -e ".[dev,test]"
   pytest services/ -v
   ```

6. **Commit with conventional commits**
   ```bash
   git commit -m "feat(user-service): add email verification flow"
   ```

7. **Push and open a Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then open a PR against the `main` branch.

### 💡 Good First Issues

Looking for where to start? Here are beginner-friendly areas:

| Area                        | Description                                            | Difficulty  |
|-----------------------------|--------------------------------------------------------|-------------|
| 📝 Documentation            | Improve docstrings, add API examples                   | 🟢 Easy     |
| 🧪 Testing                  | Add unit tests for Product/Order services              | 🟢 Easy     |
| 🐛 Bug Fixes                | Check open issues tagged `bug`                         | 🟡 Medium   |
| 📧 Email Notifications      | Implement SMTP email sending in NotificationService    | 🟡 Medium   |
| 📱 SMS Notifications        | Integrate Twilio SMS in NotificationService            | 🟡 Medium   |
| 🔍 Search                   | Add Elasticsearch/Meilisearch for product search       | 🔴 Hard     |
| 🧠 ML Recommendations       | Integrate real embeddings (OpenAI/Vertex AI)           | 🔴 Hard     |
| ☸️ Kubernetes                | Add Helm charts for production deployment              | 🔴 Hard     |

### 📐 Coding Standards

- **Async-first**: All I/O operations must be `async`.
- **Type hints**: Every function signature must be fully typed.
- **Docstrings**: Google-style docstrings on all public classes and methods.
- **Comments**: Include `Architectural Note (Senior Dev):` blocks explaining *why* patterns are used, not just *what* the code does.
- **Linting**: We use `ruff` — run `ruff check .` before committing.
- **Conventional Commits**: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

### 🏛️ Architecture Principles

When contributing, please follow these principles:

1. **12-Factor App** — All configuration via environment variables.
2. **Single Responsibility** — One service = one bounded context.
3. **Event-Driven** — Services communicate via Kafka events, not direct HTTP calls (except for queries).
4. **CQRS** — Separate read and write models where applicable.
5. **Saga Pattern** — Distributed transactions use orchestrated sagas with compensation.
6. **Idempotency** — All event handlers must be idempotent (at-least-once delivery).

### Commit Message Format

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`

**Scopes:** `user-service`, `product-service`, `order-service`, `chat-service`, `notification-service`, `analytics-service`, `ai-service`, `gateway`, `shared`, `infra`, `docs`

---

## 🧪 Testing

```bash
# Run all tests
pytest services/ -v

# Run tests for a specific service
pytest services/user_service/tests -v

# Run with coverage
pytest services/ --cov=services --cov-report=html

# Run load tests (requires running infrastructure)
locust -f load_tests/locustfile.py --host=http://localhost:8001
```

---

## 🐳 Docker & Infrastructure

### Local Development (Docker Compose)

```bash
# Start all infrastructure
docker-compose up -d

# View logs
docker-compose logs -f kafka

# Stop everything
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

### Infrastructure Services

| Service      | Port  | Dashboard URL                   |
|-------------|-------|----------------------------------|
| MongoDB     | 27017 | —                                |
| Redis       | 6379  | —                                |
| Kafka       | 9092  | —                                |
| Zookeeper   | 2181  | —                                |
| Prometheus  | 9090  | http://localhost:9090            |
| Grafana     | 3000  | http://localhost:3000            |

### Kubernetes (Production)

```bash
# Apply all manifests
kubectl apply -f k8s/

# Check deployment status
kubectl get pods -n hyperscale
```

---

## 🗺️ Roadmap

- [x] Core shared libraries (config, auth, logging, middleware)
- [x] User Service (REST + gRPC + JWT + Firebase)
- [x] Product Service (CRUD + Inventory + gRPC)
- [x] Order Service (Cart + Saga Pattern)
- [x] Chat Service (WebSockets + Presence)
- [x] Notification Service (FCM + Kafka consumers)
- [x] Analytics Service (Event aggregation)
- [x] AI Service (Recommendation engine)
- [x] GraphQL Gateway (Federation + DataLoaders)
- [x] CI/CD Pipeline (GitHub Actions)
- [x] Docker Compose for local development
- [ ] Elasticsearch integration for full-text search
- [ ] Helm charts for Kubernetes
- [ ] OpenTelemetry distributed tracing
- [ ] Rate limiting with Redis sliding window
- [ ] Email & SMS notification channels
- [ ] Admin dashboard (React/Next.js)
- [ ] API versioning strategy (v2)
- [ ] Database migration tooling

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🌟 Star History

If you find this project useful, please consider giving it a ⭐ — it helps others discover it!

---

## 📬 Contact

- **Author:** [Vishal Ranaut](https://github.com/vishalranaut)
- **Issues:** [GitHub Issues](https://github.com/vishalranaut/hyperscale-platform/issues)
- **Discussions:** [GitHub Discussions](https://github.com/vishalranaut/hyperscale-platform/discussions)

---

<p align="center">
  Built with ❤️ by the open-source community
</p>
