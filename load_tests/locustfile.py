"""HyperScale Platform — Locust Load Testing Suite."""

from locust import HttpUser, task, between


class HyperScaleLoadTest(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Set up authentication."""
        response = self.client.post("/api/v1/auth/login", json={
            "email": "loadtest@example.com",
            "password": "Password123!"
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            self.client.headers.update({"Authorization": f"Bearer {token}"})

    @task(3)
    def view_products(self):
        """Simulate viewing product catalog."""
        self.client.get("/api/v1/products")

    @task(1)
    def view_profile(self):
        """Simulate viewing user profile."""
        self.client.get("/api/v1/users/me")

    @task(2)
    def add_to_cart_and_checkout(self):
        """Simulate adding an item to cart and checking out."""
        # Add to cart
        self.client.post("/api/v1/cart/items", json={
            "product_id": "prod_123",
            "quantity": 1
        })
        
        # View cart
        self.client.get("/api/v1/cart")
        
        # Place order
        self.client.post("/api/v1/orders", json={
            "shipping_address": {
                "line1": "123 Test St",
                "city": "Testville",
                "state": "TS",
                "postal_code": "12345",
                "country": "US"
            },
            "payment_method_id": "pm_card_visa"
        })
