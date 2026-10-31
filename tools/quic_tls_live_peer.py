"""Independent aioquic 1.7.0 peer for the physical TLS/QUIC handshake proof.

No certificate bypass, session key logging, fixed traffic keys or TLS mocking.
The disposable CA is trusted only by this test, never by the operating system.
Private keys stay in the caller's work directory, outside published evidence.
"""
from pathlib import Path
import datetime, hashlib, json, socket, threading, time
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from aioquic.buffer import Buffer
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.events import HandshakeCompleted, ConnectionTerminated, ProtocolNegotiated
from aioquic.quic.logger import QuicLogger
from aioquic.quic.packet import pull_quic_header, QuicPacketType
from aioquic.tls import CipherSuite

def prepare(directory):
    directory.mkdir(parents=True, exist_ok=False)
    now = datetime.datetime.now(datetime.timezone.utc)
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Anvil QUIC test root')])
    root = (x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name)
            .public_key(root_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-datetime.timedelta(days=1)).not_valid_after(now+datetime.timedelta(days=7))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,None,None), True)
            .sign(root_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'quic-test.local')]))
            .issuer_name(root_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-datetime.timedelta(days=1)).not_valid_after(now+datetime.timedelta(days=7))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('quic-test.local')]), False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .add_extension(x509.KeyUsage(True,False,False,False,False,False,False,None,None), True)
            .sign(root_key, hashes.SHA256()))
    pem = serialization.Encoding.PEM
    (directory/'root.pem').write_bytes(root.public_bytes(pem))
    (directory/'chain.pem').write_bytes(leaf.public_bytes(pem)+root.public_bytes(pem))
    (directory/'key.pem').write_bytes(key.private_bytes(pem,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    public = dict(unix_time=int(now.timestamp()), hostname='quic-test.local',
                  root_dn=root_name.public_bytes().hex(),
                  root_key=root_key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint).hex(),
                  root_sha256=root.fingerprint(hashes.SHA256()).hex(),
                  leaf_sha256=leaf.fingerprint(hashes.SHA256()).hex())
    (directory/'public.json').write_text(json.dumps(public,indent=2),encoding='utf8')
    return public

def prepare_bad_signature(source, destination):
    """Keep the key/name/issuer, flip one leaf signature bit, verify corruption."""
    from cryptography.exceptions import InvalidSignature
    destination.mkdir(parents=True,exist_ok=False)
    root=x509.load_pem_x509_certificate((source/'root.pem').read_bytes())
    leaf=x509.load_pem_x509_certificate((source/'chain.pem').read_bytes())
    root.public_key().verify(leaf.signature,leaf.tbs_certificate_bytes,ec.ECDSA(hashes.SHA256()))
    der=bytearray(leaf.public_bytes(serialization.Encoding.DER));der[-1]^=1
    broken=x509.load_der_x509_certificate(bytes(der))
    try:root.public_key().verify(broken.signature,broken.tbs_certificate_bytes,ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:pass
    else:raise AssertionError('Signature mutation did not invalidate the leaf')
    for name in ['key.pem','root.pem','public.json']:
        (destination/name).write_bytes((source/name).read_bytes())
    (destination/'chain.pem').write_bytes(broken.public_bytes(serialization.Encoding.PEM)+root.public_bytes(serialization.Encoding.PEM))
    (destination/'mutation.json').write_text(json.dumps(dict(valid_leaf_sha256=leaf.fingerprint(hashes.SHA256()).hex(),
        invalid_leaf_sha256=broken.fingerprint(hashes.SHA256()).hex(),signature_independently_rejected=True),indent=2),encoding='utf8')

class FixtureConnection(QuicConnection):
    def _replenish_connection_ids(self):
        # aioquic 1.7.0 otherwise emits invalid empty NEW_CONNECTION_ID frames.
        # Zero-ID fixtures keep their single ID; all TLS/crypto is unchanged.
        if self._configuration.connection_id_length:
            super()._replenish_connection_ids()

class Peer:
    def __init__(self, directory, report, host='192.168.1.104', port=55442, allowed='192.168.1.114', connection_id_length=8):
        assert 0 <= connection_id_length <= 20
        self.directory, self.report, self.allowed = directory, report, allowed
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.bind((host,port)); self.sock.settimeout(.02)
        self.logger=QuicLogger()
        self.config=QuicConfiguration(is_client=False,alpn_protocols=['h3'],connection_id_length=connection_id_length,
                  cipher_suites=[CipherSuite.AES_128_GCM_SHA256],quic_logger=self.logger,idle_timeout=30)
        self.config.load_cert_chain(str(directory/'chain.pem'),str(directory/'key.pem'))
        self.connection=None;self.stop=threading.Event();self.thread=None
        self.result=dict(implementation='aioquic 1.7.0',connection_id_length=connection_id_length,received=[],sent=[],events=[],complete=False,error=None)

    def __enter__(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start();return self

    def run(self):
        try:
            while not self.stop.is_set():
                try: data,addr=self.sock.recvfrom(65535)
                except socket.timeout: data=None
                now=time.monotonic()
                if data is not None:
                    if addr[0]!=self.allowed: continue
                    self.result['received'].append(dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
                    if self.connection is None:
                        header=pull_quic_header(Buffer(data=data),host_cid_length=8)
                        assert header.packet_type==QuicPacketType.INITIAL and header.version==1 and len(data)>=1200
                        self.connection=FixtureConnection(configuration=self.config,original_destination_connection_id=header.destination_cid)
                    self.connection.receive_datagram(data,addr,now)
                if self.connection:
                    deadline=self.connection.get_timer()
                    if deadline is not None and deadline<=now: self.connection.handle_timer(now)
                    for packet,addr in self.connection.datagrams_to_send(now):
                        self.sock.sendto(packet,addr)
                        self.result['sent'].append(dict(bytes=len(packet),sha256=hashlib.sha256(packet).hexdigest()))
                    while (event:=self.connection.next_event()) is not None:
                        self.result['events'].append(repr(event))
                        if isinstance(event,HandshakeCompleted):
                            assert event.alpn_protocol=='h3' and not event.early_data_accepted and not event.session_resumed
                            self.result['complete']=True
                        if isinstance(event,ConnectionTerminated) and event.error_code:
                            raise AssertionError(repr(event))
        except Exception as exc:
            self.result['error']=repr(exc)

    def __exit__(self,*args):
        self.stop.set();self.thread.join(3);assert not self.thread.is_alive()
        self.sock.close()
        self.result['qlog']=self.logger.to_dict()
        self.report.write_text(json.dumps(self.result,indent=2),encoding='utf8')

    def check(self):
        assert self.result['error'] is None,self.result['error']
        assert self.result['complete'],self.result['events']

def selftest(directory, report, connection_id_length=8):
    """Verify this exact test CA/chain with a normal independent local client."""
    with Peer(directory,report,host='127.0.0.1',port=0,allowed='127.0.0.1',connection_id_length=connection_id_length) as peer:
        config=QuicConfiguration(is_client=True,alpn_protocols=['h3'],server_name='quic-test.local')
        config.load_verify_locations(cafile=str(directory/'root.pem'))
        client=QuicConnection(configuration=config)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.bind(('127.0.0.1',0));sock.settimeout(.02)
            client.connect(peer.sock.getsockname(),time.monotonic())
            end=time.monotonic()+5;complete=False;completed_at=None
            while time.monotonic()<end:
                now=time.monotonic()
                for data,addr in client.datagrams_to_send(now):sock.sendto(data,addr)
                try:data,addr=sock.recvfrom(65535)
                except socket.timeout:data=None
                now=time.monotonic()
                if data:client.receive_datagram(data,addr,now)
                assert client._close_event is None,client._close_event
                deadline=client.get_timer()
                if deadline is not None and deadline<=now:client.handle_timer(now)
                while (event:=client.next_event()) is not None:
                    if isinstance(event,HandshakeCompleted):complete=True
                    if isinstance(event,ConnectionTerminated):raise AssertionError(repr(event))
                if complete and peer.result['complete']:
                    if completed_at is None:completed_at=now
                    if now-completed_at>=.25:break
            assert complete
            assert completed_at is not None and time.monotonic()-completed_at>=.25
            peer.check()
