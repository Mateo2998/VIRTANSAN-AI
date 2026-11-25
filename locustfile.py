
from locust import HttpUser, task, between

class VIRTANSANUser(HttpUser):
    wait_time = between(2, 5)

    def on_start(self):
        self.employee_email = "matthew@work.com"
        self.employee_password = "Matthew123"

        response = self.client.post(
            "/employee-login",
            json={
                "email": self.employee_email,
                "password": self.employee_password
            }
        )

        if response.status_code != 200:
            raise ValueError("Employee login failed.")

        check = self.client.get("/employee/me")

        if check.status_code != 200:
            raise ValueError("Employee session verification failed.")

    @task(1)
    def check_health(self):
        with self.client.get(
            "/health",
            name="Health Check",
            catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure("Health check failed")

    @task(3)
    def chat_request(self):
        with self.client.post(
            "/chat",
            json={
                "message": "How do I troubleshoot a VPN connection?",
                "history": []
            },
            name="Employee IT Chat",
            timeout=180,
            catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Chat failed: HTTP {response.status_code}"
                )
            else:
                try:
                    data = response.json()
                    if not data:
                        response.failure("Empty response")
                except ValueError:
                    response.failure("Invalid JSON response")
