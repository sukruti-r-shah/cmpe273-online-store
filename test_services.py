"""Integration test using actual independent HTTP service processes."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent


class ServiceIntegrationTest(unittest.TestCase):
    def start_service(self, filename, port):
        # Do not accidentally test an unrelated service already using the port.
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
        process = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / filename)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.stop_service, process)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail(f"{filename} exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    return process
            except OSError:
                time.sleep(0.05)
        self.fail(f"{filename} did not start within five seconds")

    @staticmethod
    def stop_service(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    @staticmethod
    def submit(payload):
        request = Request(
            "http://127.0.0.1:8000/orders",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_order_flow_dependency_failure_and_recovery(self):
        inventory = self.start_service("inventory_service.py", 8001)
        order = self.start_service("order_service.py", 8000)
        status, body = self.submit({"item_id": "coffee", "quantity": 2})
        self.assertEqual(status, 201)
        self.assertEqual(body["status"], "created")
        self.assertTrue(body["order_id"])
        for item, quantity in [("pen", 1), ("missing", 1), ("coffee", 11)]:
            with self.subTest(item=item, quantity=quantity):
                status, body = self.submit({"item_id": item, "quantity": quantity})
                self.assertEqual(status, 409)
                self.assertEqual(body["status"], "rejected")
        for quantity in [0, -1, True, 1.5, "2"]:
            with self.subTest(invalid_quantity=quantity):
                status, _ = self.submit({"item_id": "coffee", "quantity": quantity})
                self.assertEqual(status, 400)

        self.stop_service(inventory)
        for _ in range(2):
            status, body = self.submit({"item_id": "coffee", "quantity": 2})
            self.assertEqual(status, 503)
            self.assertEqual(body, {"error": "inventory service unavailable"})
            self.assertIsNone(order.poll(), "Order Service crashed")
        print("Inventory stopped: two HTTP 503 responses; Order Service still running.")

        self.start_service("inventory_service.py", 8001)
        status, _ = self.submit({"item_id": "coffee", "quantity": 2})
        self.assertEqual(status, 201)
        self.assertIsNone(order.poll())
        print("Inventory restarted: HTTP 201 without restarting Order Service.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
