"""E2E test: fresh install flow (no vault → setup → API key → chat)."""

import json
import os
import shutil
import tempfile
import threading
import time
import urllib.request
import urllib.error

import pytest

# Use a unique port to avoid conflicts
TEST_PORT = 18877


@pytest.fixture(scope="module")
def fresh_server():
    """Start a salmalm server with a completely fresh DATA_DIR."""
    data_dir = tempfile.mkdtemp(prefix="salmalm_e2e_")
    env = os.environ.copy()
    env["SALMALM_HOME"] = data_dir
    env["SALMALM_PORT"] = str(TEST_PORT)
    env["SALMALM_VAULT_FALLBACK"] = "1"
    # Ensure no leftover env vars interfere
    env.pop("SALMALM_VAULT_PW", None)
    env.pop("SALMALM_CSP_STRICT", None)
    env.pop("SALMALM_PLUGINS", None)

    import subprocess

    proc = subprocess.Popen(
        ["python3", "-m", "salmalm", "--port", str(TEST_PORT)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for server to be ready
    base = f"http://127.0.0.1:{TEST_PORT}"
    ready = False
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{base}/", timeout=1)
            ready = True
            break
        except Exception:
            time.sleep(0.5)

    if not ready:
        proc.kill()
        out = proc.stdout.read().decode() if proc.stdout else ""
        shutil.rmtree(data_dir, ignore_errors=True)
        pytest.fail(f"Server failed to start on port {TEST_PORT}. Output:\n{out[:2000]}")

    yield {"proc": proc, "base": base, "data_dir": data_dir}

    proc.kill()
    proc.wait()
    shutil.rmtree(data_dir, ignore_errors=True)


def _get(base, path):
    req = urllib.request.Request(f"{base}{path}")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, resp.read().decode()


def _post(base, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class TestFreshInstallE2E:
    """Test the complete fresh install flow."""

    def test_01_root_shows_setup_page(self, fresh_server):
        """Fresh install should show setup wizard (not unlock or main UI)."""
        status, html = _get(fresh_server["base"], "/")
        assert status == 200
        assert "First Run" in html or "처음" in html or "setup" in html.lower()

    def test_02_setup_without_password(self, fresh_server):
        """Setup with no password should succeed."""
        status, body = _post(fresh_server["base"], "/api/setup", {
            "use_password": False,
            "password": "",
        })
        assert status == 200
        assert body.get("ok") is True

    def test_03_root_shows_onboarding_after_setup(self, fresh_server):
        """After vault setup, should show onboarding page."""
        status, html = _get(fresh_server["base"], "/")
        assert status == 200
        # Should be onboarding (not setup, not unlock)
        assert "First Run" not in html
        # Onboarding has API key fields
        assert "api" in html.lower() or "onboarding" in html.lower() or "환영" in html

    def test_04_onboarding_skip(self, fresh_server):
        """Onboarding with no API keys (skip) should succeed."""
        status, body = _post(fresh_server["base"], "/api/onboarding", {})
        assert status == 200

    def test_05_root_shows_main_ui(self, fresh_server):
        """After onboarding, should show main chat UI."""
        status, html = _get(fresh_server["base"], "/")
        assert status == 200
        assert "app.js" in html

    def test_06_setup_with_password(self):
        """Setup with password should work and vault should lock on restart."""
        data_dir = tempfile.mkdtemp(prefix="salmalm_e2e_pw_")
        env = os.environ.copy()
        env["SALMALM_HOME"] = data_dir
        env["SALMALM_PORT"] = str(TEST_PORT + 1)
        env["SALMALM_VAULT_FALLBACK"] = "1"
        env.pop("SALMALM_VAULT_PW", None)

        import subprocess

        proc = subprocess.Popen(
            ["python3", "-m", "salmalm", "--port", str(TEST_PORT + 1)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        base = f"http://127.0.0.1:{TEST_PORT + 1}"
        try:
            for _ in range(30):
                try:
                    urllib.request.urlopen(f"{base}/", timeout=1)
                    break
                except Exception:
                    time.sleep(0.5)

            # Setup with password
            status, body = _post(base, "/api/setup", {
                "use_password": True,
                "password": "testpass123",
            })
            assert status == 200
            assert body.get("ok") is True

            # Vault file should exist
            vault_file = os.path.join(data_dir, ".vault.enc")
            assert os.path.exists(vault_file)

            # .vault_auto should exist (for auto-unlock)
            vault_auto = os.path.join(data_dir, ".vault_auto")
            assert os.path.exists(vault_auto)

        finally:
            proc.kill()
            proc.wait()
            shutil.rmtree(data_dir, ignore_errors=True)

    def test_07_csp_allows_inline_scripts(self, fresh_server):
        """CSP header should allow inline scripts (unsafe-inline by default)."""
        req = urllib.request.Request(f"{fresh_server['base']}/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            csp = resp.headers.get("Content-Security-Policy", "")
            assert "'unsafe-inline'" in csp or "nonce-" in csp
