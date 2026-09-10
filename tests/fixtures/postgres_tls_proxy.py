"""Private Docker-network TLS fixture forwarding PostgreSQL to the test database host."""

import socket
import socketserver
import ssl
import threading

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("/certs/server.crt", "/certs/server.key")


def relay(source, target):
    try:
        while chunk := source.recv(65536):
            target.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class Connection(socketserver.BaseRequestHandler):
    def handle(self):
        request = b""
        while len(request) < 8:
            chunk = self.request.recv(8 - len(request))
            if not chunk:
                return
            request += chunk
        if request != bytes.fromhex("0000000804d2162f"):
            return
        self.request.sendall(b"S")
        try:
            with context.wrap_socket(self.request, server_side=True) as client:
                with socket.create_connection(("postgres", 5432), timeout=5) as database:
                    database.settimeout(None)
                    outgoing = threading.Thread(target=relay, args=(client, database), daemon=True)
                    outgoing.start()
                    relay(database, client)
                    outgoing.join(timeout=2)
        except OSError:
            pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


with Server(("0.0.0.0", 5432), Connection) as server:
    server.serve_forever()
