"""Small HTTP inventory service with in-memory sample data."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import parse_qs, urlparse


INVENTORY = {
    "coffee": 10,
    "notebook": 3,
    "pen": 0,
}


class InventoryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/availability":
            self._send_json(404, {"error": "not found"})
            return

        params = parse_qs(parsed.query)
        item_id = params.get("item_id", [""])[0]
        try:
            quantity = int(params.get("quantity", ["1"])[0])
        except ValueError:
            self._send_json(400, {"error": "quantity must be an integer"})
            return

        if not item_id or quantity < 1:
            self._send_json(400, {"error": "item_id and positive quantity are required"})
            return

        available_quantity = INVENTORY.get(item_id, 0)
        self._send_json(
            200,
            {
                "item_id": item_id,
                "requested_quantity": quantity,
                "available_quantity": available_quantity,
                "available": available_quantity >= quantity,
            },
        )

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        print("[inventory] " + format_string % args)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8001), InventoryHandler)
    print("Inventory Service listening on http://127.0.0.1:8001", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
