import hashlib
import io
import time
import zipfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.api import server
from backend.core.report_save import describe_report_save
from scripts import fetch_report_saves as helper


def make_save(
    path, *, meta=b'name="Test empire"\ndate="2300.01.01"\nversion="4.5.2"', gamestate=True
):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("meta", meta)
        if gamestate:
            archive.writestr("gamestate", "synthetic=yes")


def test_describes_only_bounded_stellaris_archives(tmp_path):
    path = tmp_path / "autosave.sav"
    make_save(path)
    info = describe_report_save(path)
    assert info["empireName"] == "Test empire"
    assert info["gameVersion"] == "4.5.2"
    assert info["sizeBytes"] == path.stat().st_size
    make_save(path, gamestate=False)
    with pytest.raises(ValueError):
        describe_report_save(path)
    make_save(path, meta=b"x" * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="too large"):
        describe_report_save(path)


def test_endpoint_requires_auth_and_uses_active_save_not_client_paths(monkeypatch, tmp_path):
    monkeypatch.setenv(server.ENV_API_TOKEN, "report-test")
    path = tmp_path / "active.sav"
    make_save(path)
    app = server.create_app()
    app.state.companion = SimpleNamespace(is_loaded=True, save_path=path)
    with TestClient(app) as client:
        assert client.get("/api/report-save").status_code == 401
        response = client.get(
            "/api/report-save?path=/etc/passwd", headers={"Authorization": "Bearer report-test"}
        )
        assert response.status_code == 200
        assert response.json()["filename"] == "active.sav"
        path.write_bytes(b"not a save")
        assert (
            client.get(
                "/api/report-save", headers={"Authorization": "Bearer report-test"}
            ).status_code
            == 409
        )


def metadata(data=b"PK\x03\x04test"):
    return {
        "id": "00000000-0000-4000-8000-000000000000",
        "sha256": hashlib.sha256(data).hexdigest(),
        "sizeBytes": len(data),
        "expiresAt": (time.time() + 3600) * 1000,
    }


class FakeResponse(io.BytesIO):
    headers = SimpleNamespace(get_content_type=lambda: "application/octet-stream")


def test_agent_helper_verifies_checksum_and_never_keeps_partial_downloads(tmp_path):
    save = metadata()
    opener = SimpleNamespace(open=lambda *args, **kwargs: FakeResponse(b"PK\x03\x04evil"))
    with pytest.raises(ValueError, match="checksum"):
        helper.download(save, tmp_path, {}, opener)
    assert not list(tmp_path.iterdir())
    opener.open = lambda *args, **kwargs: FakeResponse(b"PK\x03\x04test")
    target = helper.download(save, tmp_path, {}, opener)
    assert target.read_bytes() == b"PK\x03\x04test"
    assert target.name == f"{save['id']}.sav"


def test_agent_helper_rejects_paths_expiry_and_redirects(tmp_path):
    with pytest.raises(ValueError):
        helper.validate_save({**metadata(), "id": "../../secrets"})
    with pytest.raises(ValueError):
        helper.validate_save({**metadata(), "expiresAt": 1})
    with pytest.raises(ValueError, match="redirected"):
        helper.NoRedirect().redirect_request(None, None, 302, None, None, "https://other.test")
    save = metadata()
    (tmp_path / f"{save['id']}.sav").symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="symlink"):
        helper.download(save, tmp_path, {}, None)


def test_agent_helper_purges_expired_and_withdrawn_copies_without_touching_other_files(tmp_path):
    folder = tmp_path / "issue-79"
    folder.mkdir()
    save = metadata()
    target = folder / f"{save['id']}.sav"
    personal = folder / "notes.txt"
    personal.write_text("Keep these notes")
    target.write_bytes(b"PK\x03\x04test")
    helper.write_manifest(folder, {"saves": [save]})
    helper.write_manifest(folder, {"saves": []})
    assert not target.exists()
    target.write_bytes(b"PK\x03\x04test")
    helper.write_manifest(folder, {"saves": [{**save, "expiresAt": 1}]})
    assert helper.cleanup(tmp_path) == 1
    assert personal.read_text() == "Keep these notes"
