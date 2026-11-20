from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import re
import ssl
import threading

def web_test_identity(folder, hostname):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.now(timezone.utc)
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Zentaji test CA")])
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    leaf_key = ec.generate_private_key(ec.SECP256R1())

    def certificate(subject, issuer, key):
        return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
                .serial_number(x509.random_serial_number()).public_key(key.public_key())
                .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=2)))

    root = (certificate(root_name, root_name, root_key)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,None,None), critical=True)
            .sign(root_key, hashes.SHA256()))
    leaf = (certificate(leaf_name, root_name, leaf_key)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(True,False,False,False,False,False,False,None,None), critical=True)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(root_key, hashes.SHA256()))
    folder.mkdir()
    (folder / "key.pem").write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
                                      serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (folder / "chain.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    return root.public_bytes(serialization.Encoding.PEM)


@contextmanager
def web_test_peer(body, cert_folder=None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def do_GET(self):
            self.server.requests.append((self.path, self.headers.get("Host"),
                                         self.connection.version() if cert_folder else "HTTP"))
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            self.close_connection = True

        def log_message(self, *args):
            pass

    class Server(ThreadingHTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(45)
            return connection, address

        def process_request_thread(self, connection, address):
            if self.tls_context:
                try:
                    connection = self.tls_context.wrap_socket(connection, server_side=True)
                except (OSError, ssl.SSLError):
                    connection.close()
                    return
            super().process_request_thread(connection, address)

        def shutdown_request(self, connection):
            if isinstance(connection, ssl.SSLSocket):
                # Send close_notify before TCP FIN and consume the guest's reply.
                # SocketServer's ordinary TCP shutdown skips the TLS shutdown.
                try:
                    connection = connection.unwrap()
                except OSError:
                    connection.close()
                    return
            super().shutdown_request(connection)

    with Server(("127.0.0.1", 0), Handler) as server:
        server.requests = []
        server.tls_context = None
        if cert_folder:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_3
            context.maximum_version = ssl.TLSVersion.TLSv1_3
            context.load_cert_chain(cert_folder / "chain.pem", cert_folder / "key.pem")
            server.tls_context = context
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


def check_web_peers(command, forwarded_port, keys, body):
    # The ordinary host clients and servers reach the guest through native NAT.
    import http.client
    token = body.decode("ascii")
    with web_test_peer(body) as peer:
        port = peer.server_port
        text = command(f"http get http://10.0.2.2:{port}/plain", token)
        assert "HTTP/1.1 200" in text and len(peer.requests) == 1
        assert peer.requests[0][0] == "/plain"
    command("http serve 8080", "HTTP server listens on port 8080")
    try:
        with closing(http.client.HTTPConnection("127.0.0.1", forwarded_port, timeout=20)) as host:
            host.request("GET", "/health", headers={"Connection":"close"})
            response = host.getresponse()
            health = response.read()
            assert response.status == 200 and health.strip() == b"Anvil HTTP service is ready."
    finally:
        command("http stop", "HTTP server is stopped")
    command("settings set tls.roots 1:/ROOTS.PEM", "pmf> ")
    command("tls reload", "1 roots registered")
    with web_test_peer(body, keys / "good") as peer:
        port = peer.server_port
        text = command(f"https get https://localhost:{port}/secure", token)
        assert f"https: body {len(body)} bytes" in text, text
        assert len(peer.requests) == 1 and peer.requests[0][0] == "/secure"
        assert peer.requests[0][2] == "TLSv1.3"
    with web_test_peer(body, keys / "untrusted") as peer:
        text = command(f"https get https://localhost:{peer.server_port}/untrusted", "FAILED")
        # The issuer has the trusted CA's name but a different signing key.
        assert re.search(r"tls13 refusal 64 +x509 verdict (52|62)\b", text), text
        assert token not in text and not peer.requests
    with web_test_peer(body, keys / "good") as peer:
        text = command(f"https get https://10.0.2.2:{peer.server_port}/mismatch", "FAILED")
        assert re.search(r"tls13 refusal 64 +x509 verdict 56\b", text), text
        assert token not in text and not peer.requests
    return dict(http_client=True,http_health_bytes=len(health),tls_version="TLSv1.3",
                trusted_reply_sha256=hashlib.sha256(body).hexdigest(),
                untrusted_issuer_refused=True,wrong_hostname_refused=True)


def check_payload_peers(command, keys):
    import secrets

    command("settings set tls.roots 1:/ROOTS.PEM", "pmf> ")
    command("tls reload", "1 roots registered")
    result = {}
    for mode, label, certificate in (("P", "tcp", None), ("T", "tls", keys / "good"),
                                     ("R", "untrusted", keys / "untrusted"), ("P", "tcp_again", None)):
        body = secrets.token_bytes(4)
        with web_test_peer(body, certificate) as server:
            command(f"settings set test.network {mode}{server.server_port}", "Set test.network")
            expected = "0000000052454655" if mode == "R" else "4E455400" + body.hex().upper()
            command("boot PAYNET.PMF", "The payload returned, r1 = $" + expected)
            if mode == "R":
                assert not server.requests
                result[label] = "refused before sending application data"
            else:
                protocol = "TLSv1.3" if certificate else "HTTP"
                assert server.requests == [("/payload", "localhost", protocol)], server.requests
                result[label] = {"peer_protocol": protocol, "body_hex": body.hex()}
    return result
