"""Desktop ChatGPT bridge contract; no OpenAI credentials enter Python."""

import json
import ssl
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pydantic import BaseModel

from backend.core.advisor_providers import (
    AdvisorProviderConfig,
    AdvisorProviderError,
    ChatGPTAdvisorGenerator,
    create_advisor_generator,
)


class ChapterProbe(BaseModel):
    title: str
    text: str


def config():
    return AdvisorProviderConfig(
        provider="chatgpt",
        model="account-model",
        base_url="http://127.0.0.1:54321",
        api_key="local-capability",
    )


@contextmanager
def loopback_bridge(tls_context=None):
    """Use real sockets so tests exercise HTTPX's own transport initialization."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers.get("Authorization"), body))
            payload = json.dumps({"text": "Victory", "model": "account-model"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        if tls_context is not None:
            server.socket = tls_context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        scheme = "https" if tls_context is not None else "http"
        try:
            yield f"{scheme}://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()


@pytest.mark.parametrize("ca_state", ["missing", "corrupt", "directory"])
def test_local_bridge_generation_does_not_depend_on_ca_files(monkeypatch, tmp_path, ca_state):
    ca_path = tmp_path / "cacert.pem"
    if ca_state == "corrupt":
        ca_path.write_text("not a certificate")
    elif ca_state == "directory":
        ca_path.mkdir()
    monkeypatch.setattr("certifi.where", lambda: str(ca_path))

    with loopback_bridge() as (url, requests):
        generator = ChatGPTAdvisorGenerator(config=replace(config(), base_url=url))
        result = generator.generate(system_prompt="Advisor", user_prompt="Campaign briefing")

    assert result.text == "Victory"
    assert requests == [
        (
            "/generate",
            "Bearer local-capability",
            {"instructions": "Advisor", "input": "Campaign briefing", "purpose": "advisor"},
        )
    ]
    # The exception is scoped to the HTTP bridge; normal clients still load CAs.
    with pytest.raises(OSError), httpx.Client(trust_env=False):
        pass


@pytest.mark.parametrize("error_type", [OSError, ValueError])
def test_bridge_client_initialization_failure_is_a_typed_provider_error(monkeypatch, error_type):
    cause = error_type("internal initialization detail")

    def fail_client(**kwargs):
        raise cause

    monkeypatch.setattr(httpx, "Client", fail_client)
    generator = ChatGPTAdvisorGenerator(config=config())
    with pytest.raises(AdvisorProviderError) as failure:
        generator.generate(system_prompt="Advisor", user_prompt="Campaign briefing")

    assert failure.value.code == "CHATGPT_UNAVAILABLE"
    assert failure.value.status_code == 503
    assert failure.value.__cause__ is cause
    assert "internal initialization detail" not in str(failure.value)


def test_unexpected_https_bridge_still_rejects_untrusted_certificates(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "bridge test")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), False
        )
        .sign(key, hashes.SHA256())
    )
    certificate_path = tmp_path / "server.pem"
    key_path = tmp_path / "server-key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls_context.load_cert_chain(certificate_path, key_path)

    with loopback_bridge(tls_context) as (url, requests):
        # Bypass the environment URL gate to check the transport's fallback safety.
        generator = ChatGPTAdvisorGenerator(config=replace(config(), base_url=url))
        with pytest.raises(AdvisorProviderError) as failure:
            generator.generate(system_prompt="Advisor", user_prompt="Campaign briefing")

    assert isinstance(failure.value.__cause__, httpx.ConnectError)
    assert "CERTIFICATE_VERIFY_FAILED" in str(failure.value.__cause__)
    assert requests == []


def test_chatgpt_uses_desktop_bridge_environment(monkeypatch):
    monkeypatch.setenv("STELLARIS_ADVISOR_PROVIDER", "chatgpt")
    monkeypatch.setenv("STELLARIS_ADVISOR_MODEL", "account-model")
    monkeypatch.setenv("STELLARIS_CHATGPT_BRIDGE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("STELLARIS_CHATGPT_BRIDGE_TOKEN", "local-capability")
    monkeypatch.setenv("STELLARIS_ADVISOR_API_KEY", "unrelated-key")
    resolved = AdvisorProviderConfig.from_environment()
    assert resolved.is_configured
    assert resolved.api_key == "local-capability"
    assert resolved.display_name == "ChatGPT"
    assert isinstance(create_advisor_generator(config=resolved), ChatGPTAdvisorGenerator)
    for url in [
        "https://provider.example",
        "http://localhost:54321",
        "http://127.0.0.1:54321/other",
        "http://127.0.0.1:54321?secret=1",
    ]:
        monkeypatch.setenv("STELLARIS_CHATGPT_BRIDGE_URL", url)
        assert not AdvisorProviderConfig.from_environment().is_configured


def test_chronicle_schema_travels_through_bridge_and_output_remains_validatable():
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer local-capability"
        assert str(request.url) == "http://127.0.0.1:54321/generate"
        return httpx.Response(
            200,
            json={
                "text": '{"title":"First Contact","text":"A new era."}',
                "model": "account-model",
                "schemaFallbackUsed": True,
            },
        )

    generator = ChatGPTAdvisorGenerator(
        config=config(), client=httpx.Client(transport=httpx.MockTransport(handle))
    )
    result = generator.generate(
        system_prompt="Narrate the empire",
        user_prompt="Campaign briefing",
        response_schema=ChapterProbe,
        purpose="chronicle",
    )
    assert ChapterProbe.model_validate_json(result.text).title == "First Contact"
    assert result.provider == "chatgpt"
    assert result.schema_fallback_used
    assert seen[0]["instructions"] == "Narrate the empire"
    assert seen[0]["purpose"] == "chronicle"
    assert "model" not in seen[0]
    assert "Campaign briefing" in seen[0]["input"]
    assert "JSON" in seen[0]["input"]
    assert seen[0]["schema"]["additionalProperties"] is False
    assert set(seen[0]["schema"]["required"]) == {"title", "text"}
    assert "temperature" not in seen[0]
    assert "max_output_tokens" not in seen[0]


def test_explicit_model_override_is_forwarded_and_actual_selection_is_reported():
    def handle(request):
        assert json.loads(request.content)["model"] == "explicit-model"
        assert json.loads(request.content)["purpose"] == "advisor"
        return httpx.Response(200, json={"text": "Advice", "model": "explicit-model"})

    generator = ChatGPTAdvisorGenerator(
        config=config(), client=httpx.Client(transport=httpx.MockTransport(handle))
    )
    result = generator.generate(
        system_prompt="Advisor", user_prompt="Briefing", model="explicit-model"
    )
    assert result.requested_model == "explicit-model"


@pytest.mark.parametrize(
    "code,status",
    [
        ("CHATGPT_LIMIT", 429),
        ("CHATGPT_RECONNECT", 401),
        ("CHATGPT_UNAVAILABLE", 503),
        ("CHATGPT_INVALID_RESPONSE", 502),
    ],
)
def test_bridge_failures_are_actionable_and_do_not_expose_credentials(code, status):
    generator = ChatGPTAdvisorGenerator(
        config=config(),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    status,
                    json={"code": code, "error": "local-capability access-token secret details"},
                )
            )
        ),
    )
    with pytest.raises(AdvisorProviderError) as failure:
        generator.generate(system_prompt="Advisor", user_prompt="Briefing")
    assert failure.value.code == code
    assert failure.value.status_code == status
    assert "local-capability" not in str(failure.value)
    assert "access-token" not in str(failure.value)


def test_empty_bridge_output_is_never_a_success():
    generator = ChatGPTAdvisorGenerator(
        config=config(),
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"text": ""}))
        ),
    )
    with pytest.raises(AdvisorProviderError, match="did not finish"):
        generator.generate(system_prompt="Advisor", user_prompt="Briefing")
