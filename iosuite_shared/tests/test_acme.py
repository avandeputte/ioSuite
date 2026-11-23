"""The ACME client against a certificate authority of the tests' own (authority.py)."""
import pytest

from iosuite_shared import acme
from iosuite_shared.tests.authority import NAME, Authority


@pytest.fixture(autouse=True)
def fresh_db():
    """Nothing here touches the database."""
    yield


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(acme, "PAUSE", (0.01, 0.02))


class Proofs:
    """Where the client puts its proofs: what http://<name>/.well-known/acme-challenge/<token> and DNS answer."""

    def __init__(self):
        self.http, self.dns, self.log = {}, {}, []

    def publish(self, kind, name, token, value):
        self.log.append(("publish", kind, name))
        if kind == "http-01":
            self.http[(name, token)] = value
        else:
            self.dns.setdefault(f"_acme-challenge.{name[2:] if name.startswith('*.') else name}", []).append(value)

    def remove(self, kind, name, token):
        self.log.append(("remove", kind, name))
        self.http.pop((name, token), None)

    def fetch(self, name, path):
        return self.http.get((name, path.rsplit("/", 1)[-1]))

    def txt(self, record):
        return self.dns.get(record, [])


def test_the_pieces():
    key = acme._load(acme.new_key())
    j = acme.jwk(key)
    assert set(j) == {"crv", "kty", "x", "y"} and j["crv"] == "P-256" and len(acme.thumbprint(key)) == 43
    import base64
    import hashlib
    assert acme.txt_value("token.thumb") == base64.urlsafe_b64encode(hashlib.sha256(b"token.thumb").digest()).decode().rstrip("=")
    assert acme.covers(["home.example.com"], "HOME.example.com") and not acme.covers(["home.example.com"], "example.com")
    assert acme.covers(["*.example.com"], "calendar.example.com")
    assert not acme.covers(["*.example.com"], "example.com") and not acme.covers(["*.example.com"], "a.b.example.com")


def test_a_certificate_with_the_proof_over_http():
    p = Proofs()
    with Authority(fetch=p.fetch) as ca:
        account = acme.new_key()
        said = []
        client = acme.Client(ca.directory, account, contact="alex@example.com", log=said.append)
        key, chain = client.certificate(["Home.Example.com", "calendar.example.com", "home.example.com"], "http-01", p.publish, p.remove)
        have = acme.describe(chain)
        assert have["names"] == ["home.example.com", "calendar.example.com"] and have["issuer"] == NAME
        assert have["until"] - have["from"] == 90 * 86400 and len(have["fingerprint"]) == 64
        assert chain.count("BEGIN CERTIFICATE") == 2 and "BEGIN PRIVATE KEY" in key  # its chain comes with it
        assert not p.http and [x for x in p.log if x[0] == "remove"] == [("remove", "http-01", "home.example.com"), ("remove", "http-01", "calendar.example.com")]
        assert ca.looked == [("http-01", "home.example.com"), ("http-01", "calendar.example.com")]
        assert list(ca.accounts.values())[0]["contact"] == ["mailto:alex@example.com"]
        assert any("home.example.com" in line for line in said)
        # the key the certificate was asked with is its own
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        spki = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        assert x509.load_pem_x509_certificate(chain.encode()).public_key().public_bytes(*spki) == acme._load(key).public_key().public_bytes(*spki)
        # the same key is the same account, also for a client that starts anew
        again = acme.Client(ca.directory, account)
        key2, chain2 = again.certificate(["home.example.com"], "http-01", p.publish, p.remove)
        assert len(ca.accounts) == 1 and again.kid == client.kid and key2 != key
        assert acme.describe(chain2)["fingerprint"] != have["fingerprint"]


def test_a_star_is_proven_through_dns():
    p = Proofs()
    with Authority(txt=p.txt) as ca:
        client = acme.Client(ca.directory, acme.new_key())
        with pytest.raises(acme.Problem) as e:
            client.certificate(["*.example.com"], "http-01", p.publish, p.remove)
        assert e.value.kind == "names" and not ca.seen  # said before the authority is asked anything
        _key, chain = client.certificate(["example.com", "*.example.com"], "dns-01", p.publish, p.remove)
        assert acme.describe(chain)["names"] == ["example.com", "*.example.com"]
        assert len(p.dns["_acme-challenge.example.com"]) == 2  # one record's name, a value for each


def test_a_nonce_no_longer_taken_is_tried_again():
    p = Proofs()
    with Authority(fetch=p.fetch) as ca:
        ca.bad_nonces = 2
        _key, chain = acme.Client(ca.directory, acme.new_key()).certificate(["home.example.com"], "http-01", p.publish, p.remove)
        assert acme.describe(chain)["names"] == ["home.example.com"] and ca.bad_nonces == 0
        ca.bad_nonces = 50
        with pytest.raises(acme.Problem) as e:
            acme.Client(ca.directory, acme.new_key()).certificate(["home.example.com"], "http-01", p.publish, p.remove)
        assert e.value.kind == "badNonce"


def test_an_authority_that_takes_its_time():
    p = Proofs()
    with Authority(fetch=p.fetch) as ca:
        ca.slow = 3
        _key, chain = acme.Client(ca.directory, acme.new_key()).certificate(["home.example.com"], "http-01", p.publish, p.remove)
        assert acme.describe(chain)["names"] == ["home.example.com"]
        ca.slow = 10 ** 6
        with pytest.raises(acme.Problem) as e:
            acme.Client(ca.directory, acme.new_key()).certificate(["home.example.com"], "http-01", p.publish, p.remove, wait=0.2)
        assert e.value.kind == "timeout" and "home.example.com" in e.value.detail and not p.http  # the proof is taken away all the same


def test_what_the_authority_says_no_with():
    p = Proofs()
    with Authority(fetch=lambda name, path: None) as ca:  # nothing answers at the name
        with pytest.raises(acme.Problem) as e:
            acme.Client(ca.directory, acme.new_key()).certificate(["home.example.com"], "http-01", p.publish, p.remove)
        assert e.value.kind == "unauthorized" and e.value.detail.startswith("home.example.com: The key authorization file")
        assert not p.http
        ca.fetch = p.fetch
        ca.fail["calendar.example.com"] = "DNS problem: NXDOMAIN looking up A for calendar.example.com"
        with pytest.raises(acme.Problem) as e:
            acme.Client(ca.directory, acme.new_key()).certificate(["home.example.com", "calendar.example.com"], "http-01", p.publish, p.remove)
        assert "NXDOMAIN" in e.value.detail and e.value.detail.startswith("calendar.example.com: ")
        ca.offer = ("dns-01",)
        with pytest.raises(acme.Problem) as e:
            acme.Client(ca.directory, acme.new_key()).certificate(["home.example.com"], "http-01", p.publish, p.remove)
        assert e.value.kind == "challenge" and "dns-01" in e.value.detail
        with pytest.raises(acme.Problem) as e:
            acme.Client(ca.url + "/nothing", acme.new_key()).certificate(["home.example.com"], "http-01", p.publish)
        assert e.value.kind == "directory"
        with pytest.raises(acme.Problem) as e:
            acme.Client(ca.directory, acme.new_key()).certificate([" "], "http-01", p.publish)
        assert e.value.kind == "names"
    with pytest.raises(acme.Problem) as e:  # the authority is away
        acme.Client(ca.directory, acme.new_key(), timeout=2).certificate(["home.example.com"], "http-01", p.publish)
    assert e.value.kind == "connection"


def test_the_authority_checks_what_a_real_one_checks():
    """The stand-in is worth something only if it refuses what a real authority refuses."""
    import json
    import urllib.error
    import urllib.request
    p = Proofs()
    with Authority(fetch=p.fetch) as ca:
        client = acme.Client(ca.directory, acme.new_key())
        client.account()

        def post(data: bytes):
            req = urllib.request.Request(ca.url + "/order", data=data, method="POST", headers={"Content-Type": "application/jose+json"})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as x:
                return x.code, json.loads(x.read())
        order = {"identifiers": [{"type": "dns", "value": "home.example.com"}]}
        good = client._sign(ca.url + "/order", order, client._fresh_nonce())
        assert post(good)[0] == 201
        assert post(good)[1]["type"].endswith("badNonce")  # a nonce is taken once
        assert post(client._sign(ca.url + "/acct", order, client._fresh_nonce()))[1]["type"].endswith("malformed")  # signed for another address
        other = acme.Client(ca.directory, acme.new_key())
        other.kid = client.kid  # someone else's key under this account
        assert "signature" in post(other._sign(ca.url + "/order", order, client._fresh_nonce()))[1]["detail"]
        # a certificate is not made before every name is proven, nor for other names than were ordered
        _s, headers, made = client._post(ca.url + "/order", order)
        with pytest.raises(acme.Problem) as e:
            client._post(made["finalize"], {"csr": acme.b64(acme.request(["home.example.com"], acme.new_key()))})
        assert e.value.kind == "orderNotReady"
        key, chain = client.certificate(["home.example.com"], "http-01", p.publish, p.remove)
        with pytest.raises(acme.Problem):  # the wrong proof at the right place
            client.certificate(["home.example.com"], "http-01", lambda kind, name, token, value: p.publish(kind, name, token, value + "x"), p.remove)
