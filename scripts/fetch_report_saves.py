#!/usr/bin/env python3
"""Fetch consented reproduction saves using a Cloudflare Access service credential."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVICE = "https://feedback.galacticfilingcabinet.com"
MAX_BYTES = 50 * 1024 * 1024
UUID = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Download redirected. Check the Cloudflare Access service policy.")


def credentials() -> dict[str, str]:
    client_id = os.environ.get("CF_ACCESS_CLIENT_ID")
    secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")
    if not client_id or not secret:
        raise ValueError(
            "Set CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET in the trusted agent environment."
        )
    return {"CF-Access-Client-Id": client_id, "CF-Access-Client-Secret": secret}


def validate_save(save: dict) -> None:
    if not isinstance(save, dict) or not UUID.fullmatch(str(save.get("id", ""))):
        raise ValueError("Invalid save reference in manifest.")
    if not re.fullmatch(r"[a-f0-9]{64}", str(save.get("sha256", ""))):
        raise ValueError("Invalid checksum in manifest.")
    size = save.get("sizeBytes")
    expiry = save.get("expiresAt")
    if type(size) is not int or not 4 <= size <= MAX_BYTES:
        raise ValueError("Invalid save size in manifest.")
    if (
        type(expiry) not in (int, float)
        or not time.time() * 1000 < expiry <= (time.time() + 91 * 86400) * 1000
    ):
        raise ValueError("Save has expired or has an invalid retention deadline.")


def cleanup(root: Path) -> int:
    """Remove only UUID-named saves listed in this helper's own manifests."""
    count = 0
    if root.is_symlink():
        raise ValueError("The output directory must not be a symlink.")
    for manifest in root.glob("*/manifest.json"):
        if manifest.is_symlink() or manifest.parent.is_symlink():
            continue
        data = json.loads(manifest.read_text())
        if data.get("source") != SERVICE:
            continue
        for save in data.get("saves", []):
            if (
                UUID.fullmatch(str(save.get("id", "")))
                and save.get("expiresAt", float("inf")) <= time.time() * 1000
            ):
                target = manifest.parent / f"{save['id']}.sav"
                if target.is_file() and not target.is_symlink():
                    target.unlink()
                    count += 1
    return count


def download(save: dict, folder: Path, headers: dict[str, str], opener) -> Path:
    validate_save(save)
    target = folder / f"{save['id']}.sav"
    if target.is_symlink():
        raise ValueError("Refusing a symlink download target.")
    if target.exists():
        if target.stat().st_size == save["sizeBytes"]:
            digest = hashlib.sha256()
            with target.open("rb") as existing:
                while chunk := existing.read(256 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() == save["sha256"]:
                return target
        raise ValueError(
            "An existing save differs from the expected checksum; move it before retrying."
        )
    fd, temporary = tempfile.mkstemp(prefix=".download-", dir=folder)
    try:
        request = urllib.request.Request(
            f"{SERVICE}/maintainer/saves/{save['id']}/download", headers=headers
        )
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(fd, "wb") as output, opener.open(request, timeout=120) as response:
            if response.headers.get_content_type() != "application/octet-stream":
                raise ValueError("Expected a save download. Check Access authentication.")
            while chunk := response.read(256 * 1024):
                size += len(chunk)
                if size > save["sizeBytes"]:
                    raise ValueError("Download exceeds declared size.")
                digest.update(chunk)
                output.write(chunk)
        if size != save["sizeBytes"] or digest.hexdigest() != save["sha256"]:
            raise ValueError("Save checksum verification failed.")
        # Hard-link publication fails instead of overwriting an existing file.
        os.link(temporary, target)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_manifest(folder: Path, manifest: dict) -> None:
    """Retire withdrawn copies and preserve expiry evidence even if a download fails."""
    receipt = folder / "manifest.json"
    if receipt.is_symlink():
        raise ValueError("Refusing a symlink manifest.")
    if receipt.exists():
        previous = json.loads(receipt.read_text())
        current = {save["id"] for save in manifest["saves"]}
        if previous.get("source") == SERVICE:
            for save in previous.get("saves", []):
                save_id = str(save.get("id", ""))
                if UUID.fullmatch(save_id) and save_id not in current:
                    target = folder / f"{save_id}.sav"
                    if target.is_file() and not target.is_symlink():
                        target.unlink()
    fd, temporary = tempfile.mkstemp(prefix=".manifest-", dir=folder)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump({**manifest, "source": SERVICE}, output, indent=2)
            output.write("\n")
        os.replace(temporary, receipt)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    reference = parser.add_mutually_exclusive_group(required=True)
    reference.add_argument("--issue", type=int)
    reference.add_argument("--pr", type=int)
    reference.add_argument("--cleanup", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("artifacts/report-saves"))
    args = parser.parse_args()
    try:
        root = args.output.absolute()
        cleanup(root)
        if args.cleanup:
            print("Expired local reproduction saves removed.")
            return 0
        kind, number = ("issue", args.issue) if args.issue else ("pr", args.pr)
        if number is None or not 0 < number < 1000000000:
            raise ValueError("Supply a positive issue or PR number.")
        headers = {
            **credentials(),
            "Accept": "application/json",
            "User-Agent": "stellaris-report-saves-helper",
        }
        opener = urllib.request.build_opener(NoRedirect)
        request = urllib.request.Request(
            f"{SERVICE}/maintainer/saves?{kind}={number}", headers=headers
        )
        with opener.open(request, timeout=30) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("Save manifest is too large.")
            manifest = json.loads(raw)
        if manifest.get("repository") != "gitmaan/stellaris-companion" or not isinstance(
            manifest.get("saves"), list
        ):
            raise ValueError("Unexpected save manifest.")
        for save in manifest["saves"]:
            validate_save(save)
        folder = root / f"{kind}-{number}"
        if folder.is_symlink():
            raise ValueError("The output folder must not be a symlink.")
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        # No credentials, local source paths or save contents are recorded here.
        write_manifest(folder, manifest)
        for save in manifest["saves"]:
            print(download(save, folder, headers, opener))
        print(
            f"{len(manifest['saves'])} verified save(s); remove local copies after investigation and by their expiry dates."
        )
        return 0
    except (OSError, ValueError, urllib.error.URLError) as error:
        # HTTP errors expose only their status, never request headers or credentials.
        print(f"Save retrieval failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
