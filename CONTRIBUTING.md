# Contributing to HyperScale Platform

First off, **thank you** for considering contributing to HyperScale Platform! 🎉

Whether you're fixing a typo, adding a test, or building an entirely new service — every contribution matters.

---

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Pull Request Process](#pull-request-process)
- [Issue Guidelines](#issue-guidelines)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior via [GitHub Issues](https://github.com/vishalranaut/hyperscale-platform/issues).

---

## How Can I Contribute?

### 🐛 Report Bugs

Found a bug? Open an issue with:
- A clear, descriptive title
- Steps to reproduce
- Expected vs. actual behavior
- Your environment (OS, Python version, Docker version)

### 💡 Suggest Features

Have an idea? Open an issue with the `enhancement` label and describe:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

### 🔧 Submit Code

1. Check the [open issues](https://github.com/vishalranaut/hyperscale-platform/issues) for something to work on.
2. Issues tagged **`good first issue`** are perfect for newcomers.
3. Issues tagged **`help wanted`** are ready for community contribution.

### 📝 Improve Documentation

Documentation improvements are always welcome — from fixing typos to adding architecture diagrams.

---

## Development Setup

### Prerequisites

- Python 3.12+
- Docker or Podman (for infrastructure services)
- Git

### Setup Steps

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/hyperscale-platform.git
cd hyperscale-platform

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate    # Linux/macOS
venv\Scripts\activate       # Windows

# 3. Install all dependencies
pip install -e ".[all]"

# 4. Copy environment config
cp .env.example .env

# 5. Start infrastructure
docker-compose up -d

# 6. Verify tests pass
pytest services/user_service/tests -v
```

### Branch Naming

| Type        | Pattern                          | Example                              |
|-------------|----------------------------------|--------------------------------------|
| Feature     | `feature/<description>`          | `feature/email-notifications`        |
| Bug fix     | `fix/<description>`              | `fix/jwt-refresh-race-condition`     |
| Docs        | `docs/<description>`             | `docs/api-endpoint-examples`         |
| Refactor    | `refactor/<description>`         | `refactor/saga-error-handling`       |
| Test        | `test/<description>`             | `test/order-service-integration`     |

---

## Coding Standards

### Python Style

- **Linter:** We use [Ruff](https://github.com/astral-sh/ruff). Run `ruff check .` before committing.
- **Type checker:** We use [mypy](https://mypy.readthedocs.io/). Run `mypy shared/ services/` to check types.
- **Line length:** 100 characters max.
- **Imports:** Sorted by `isort` (configured in `pyproject.toml`).

### Async-First

All I/O-bound operations **must** be async:

```python
# ✅ Correct
async def get_user(self, user_id: str) -> User:
    return await self._repo.get_by_id(user_id)

# ❌ Wrong — blocks the event loop
def get_user(self, user_id: str) -> User:
    return self._repo.get_by_id(user_id)
```

### Type Hints

Every function must have complete type annotations:

```python
# ✅ Correct
async def create_order(self, user_id: str, items: list[CartItem]) -> Order:
    ...

# ❌ Wrong — missing types
async def create_order(self, user_id, items):
    ...
```

### Docstrings

Use Google-style docstrings on all public methods:

```python
async def reserve_inventory(self, product_id: str, quantity: int) -> bool:
    """Reserve inventory for a product using atomic MongoDB operations.

    Architectural Note (Senior Dev):
        We use MongoDB's $inc with a negative value combined with a
        {stock: {$gte: quantity}} filter to achieve an atomic
        compare-and-swap without distributed locks.

    Args:
        product_id: The product identifier.
        quantity: Number of units to reserve.

    Returns:
        True if reservation succeeded, False if insufficient stock.

    Raises:
        NotFoundError: If the product does not exist.
    """
```

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`

**Scopes:** `user-service`, `product-service`, `order-service`, `chat-service`, `notification-service`, `analytics-service`, `ai-service`, `gateway`, `shared`, `infra`, `docs`

**Examples:**
```
feat(order-service): implement payment intent creation via Stripe
fix(shared): resolve Redis connection pool exhaustion under load
docs(readme): add Kubernetes deployment instructions
test(user-service): add login rate-limiting edge case tests
refactor(chat-service): extract presence tracking to dedicated module
```

---

## Pull Request Process

### Before Submitting

- [ ] Your code follows the [Coding Standards](#coding-standards)
- [ ] You've added tests for new functionality
- [ ] All existing tests pass (`pytest services/ -v`)
- [ ] Linting passes (`ruff check .`)
- [ ] You've updated documentation if needed
- [ ] Your commits follow conventional commit format

### PR Template

When opening a PR, please include:

```markdown
## What does this PR do?
Brief description of the changes.

## Why is this change needed?
Context and motivation.

## How was this tested?
- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual testing

## Screenshots (if applicable)

## Related Issues
Closes #<issue_number>
```

### Review Process

1. A maintainer will review your PR within **48 hours**.
2. Address any feedback in new commits (don't force-push during review).
3. Once approved, a maintainer will merge using **squash merge**.

---

## Issue Guidelines

### Bug Reports

Use this template:

```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
1. Start service '...'
2. Send request to '...'
3. See error

**Expected behavior**
What you expected to happen.

**Environment**
- OS: [e.g., Ubuntu 22.04]
- Python: [e.g., 3.12.3]
- Docker: [e.g., 24.0.7]

**Logs**
Paste relevant log output.
```

### Feature Requests

Use this template:

```markdown
**Is your feature request related to a problem?**
A clear description of the problem.

**Describe the solution you'd like**
What you want to happen.

**Describe alternatives you've considered**
Other approaches you've thought about.

**Additional context**
Any mockups, diagrams, or references.
```

---

## 🏆 Recognition

Contributors are recognized in the following ways:

- Listed in the project's contributor graph on GitHub
- Mentioned in release notes for significant contributions
- Top contributors may be invited as maintainers

---

## 📬 Questions?

- Open a [GitHub Discussion](https://github.com/vishalranaut/hyperscale-platform/discussions)
- Tag your issue with `question`

Thank you for helping make HyperScale Platform better! 🚀
