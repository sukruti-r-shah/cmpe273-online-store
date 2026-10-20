"""Small HTTP order service that synchronously checks inventory."""

from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import uuid
from urllib.parse import urlencode


INVENTORY_HOST = "127.0.0.1"
INVENTORY_PORT = 8001
INVENTORY_TIMEOUT_SECONDS = 2
ORDERS = []


class OrderHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/orders":
            self._send_json(404, {"error": "not found"})
            return

        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 65536:
                raise ValueError
            request = json.loads(self.rfile.read(size))
            item_id = request["item_id"]
            quantity = request["quantity"]
            if (
                not isinstance(item_id, str)
                or not item_id.strip()
                or type(quantity) is not int
                or quantity < 1
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": "item_id and positive integer quantity are required"})
            return

        try:
            availability = self._check_inventory(item_id, quantity)
        except (OSError, HTTPException, ValueError) as error:
            print(f"[order] inventory dependency failed: {error}")
            self._send_json(503, {"error": "inventory service unavailable"})
            return

        if not availability.get("available", False):
            self._send_json(
                409,
                {
                    "status": "rejected",
                    "reason": "item unavailable",
                    "item_id": item_id,
                    "requested_quantity": quantity,
                    "available_quantity": availability.get("available_quantity", 0),
                },
            )
            return

        order = {
            "order_id": str(uuid.uuid4()),
            "status": "created",
            "item_id": item_id,
            "quantity": quantity,
        }
        ORDERS.append(order)
        # In a fuller system this is where an OrderCreated event would be published.
        self._send_json(201, order)

    def _check_inventory(self, item_id, quantity):
        query = urlencode({"item_id": item_id, "quantity": quantity})
        connection = HTTPConnection(
            INVENTORY_HOST, INVENTORY_PORT, timeout=INVENTORY_TIMEOUT_SECONDS
        )
        try:
            connection.request("GET", f"/availability?{query}")
            response = connection.getresponse()
            body = response.read()
            if response.status != 200:
                raise ConnectionError(f"inventory returned HTTP {response.status}")
            availability = json.loads(body)
            if (
                not isinstance(availability, dict)
                or type(availability.get("available")) is not bool
                or type(availability.get("available_quantity")) is not int
            ):
                raise ValueError("invalid inventory response")
            return availability
        finally:
            connection.close()

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        print("[order] " + format_string % args)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), OrderHandler)
    print("Order Service listening on http://127.0.0.1:8000", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
