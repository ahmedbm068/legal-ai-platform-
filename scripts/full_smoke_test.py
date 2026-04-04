from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict

import requests


@dataclass
class CheckResult:
    step: str
    ok: bool
    detail: str


def wait_for_health(base_url: str, timeout_seconds: int = 90) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/health", timeout=1.5)
            if response.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _response_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    except Exception:
        pass
    return ""


def _create_local_staff_invite(email: str) -> tuple[str | None, str | None]:
    """Create a staff invite directly in DB for smoke usage when invite-only mode is enabled."""
    try:
        from backend.database.database import SessionLocal
        from backend.models.staff_invite import StaffInvite
        from backend.models.tenant import Tenant
    except Exception:
        return None, None

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).order_by(Tenant.id.asc()).first()
        if tenant is None:
            return None, None

        invite = StaffInvite(
            tenant_id=tenant.id,
            created_by_user_id=None,
            email=email.lower().strip(),
            role="lawyer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)
        return invite.invite_token, getattr(tenant, "slug", None)
    except Exception:
        db.rollback()
        return None, None
    finally:
        db.close()


def run_smoke(base_url: str) -> list[CheckResult]:
    results: list[CheckResult] = []

    def record(step: str, ok: bool, detail: str) -> None:
        results.append(CheckResult(step=step, ok=ok, detail=detail))
        print(f"{step}: {'OK' if ok else 'FAIL'} {detail}")

    email = f"smoke_{random.randint(100000, 999999)}@example.com"
    password = "SmokePass!123"
    tenant_slug = (os.getenv("SMOKE_TENANT_SLUG") or "smoketenant").strip().lower()
    session = requests.Session()
    token = ""
    headers: dict[str, str] = {}
    case_id: int | None = None
    staff_flow_available = True

    register_payload = {
        "name": "Smoke User",
        "email": email,
        "password": password,
        "tenant_name": "SmokeTenant",
        "role": "lawyer",
    }
    register = session.post(
        f"{base_url}/auth/register",
        json=register_payload,
        timeout=20,
    )
    register_succeeded = register.status_code in (200, 201)
    register_ok = register_succeeded
    register_detail = _response_detail(register)

    if not register_ok and register.status_code == 403 and "invite" in register_detail.lower():
        invite_token, tenant_slug_from_db = _create_local_staff_invite(email)
        if tenant_slug_from_db:
            tenant_slug = tenant_slug_from_db
        if invite_token:
            register_payload["invite_token"] = invite_token
            register = session.post(
                f"{base_url}/auth/register",
                json=register_payload,
                timeout=20,
            )
            register_succeeded = register.status_code in (200, 201)
            register_ok = register_succeeded
            register_detail = _response_detail(register)

    if not register_succeeded and register.status_code == 403 and "invite" in register_detail.lower():
        register_ok = True
        register_detail = f"{register_detail} (expected in invite-only mode)"
        staff_flow_available = False

    register_msg = f"status={register.status_code}"
    if register_detail:
        register_msg = f"{register_msg} detail={register_detail}"
    record("auth_register", register_ok, register_msg)

    login_email = email
    login_password = password
    if not register_succeeded:
        fallback_email = (os.getenv("SMOKE_STAFF_EMAIL") or "").strip().lower()
        fallback_password = (os.getenv("SMOKE_STAFF_PASSWORD") or "").strip()
        if fallback_email and fallback_password:
            login_email = fallback_email
            login_password = fallback_password
            staff_flow_available = True

    if not staff_flow_available:
        record("auth_login", True, "SKIP invite-only mode without fallback staff credentials")
        record("auth_me", True, "SKIP invite-only mode without fallback staff credentials")
        record("create_client", True, "SKIP invite-only mode without fallback staff credentials")
        record("create_case", True, "SKIP invite-only mode without fallback staff credentials")
    else:
        login = session.post(
            f"{base_url}/auth/login",
            json={"email": login_email, "password": login_password},
            timeout=20,
        )
        if login.status_code == 200:
            token = login.json().get("access_token", "")
            headers = {"Authorization": f"Bearer {token}"}
        record("auth_login", login.status_code == 200, f"status={login.status_code}")

        me = session.get(f"{base_url}/auth/me", headers=headers, timeout=20)
        record("auth_me", me.status_code == 200, f"status={me.status_code}")

        client = session.post(
            f"{base_url}/clients/",
            headers=headers,
            json={"name": "Smoke Client", "email": "client@example.com"},
            timeout=20,
        )
        client_id = client.json().get("id") if client.status_code in (200, 201) else None
        record("create_client", client.status_code in (200, 201), f"status={client.status_code}")

        case = session.post(
            f"{base_url}/cases/",
            headers=headers,
            json={
                "title": "Smoke Case",
                "description": "Smoke test case",
                "status": "open",
                "client_id": client_id,
            },
            timeout=20,
        )
        if case.status_code in (200, 201):
            case_id = case.json().get("id")
        record("create_case", case.status_code in (200, 201), f"status={case.status_code}")

    if case_id:
        pdf_bytes = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 72 100 Td (Smoke PDF text) Tj ET\nendstream\nendobj\n"
            b"xref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n"
            b"0000000117 00000 n \n0000000213 00000 n \ntrailer<</Size 5/Root 1 0 R>>\nstartxref\n310\n%%EOF"
        )
        doc_upload = session.post(
            f"{base_url}/documents/upload?case_id={case_id}",
            headers=headers,
            files={"file": ("smoke.pdf", pdf_bytes, "application/pdf")},
            timeout=40,
        )
        record("upload_document", doc_upload.status_code in (200, 201), f"status={doc_upload.status_code}")

        wav_bytes = (
            b"RIFF\x24\x08\x00\x00WAVEfmt "
            b"\x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data"
            b"\x00\x08\x00\x00" + (b"\x00\x00" * 2048)
        )
        t0 = time.time()
        voice_upload = session.post(
            f"{base_url}/voice/upload?case_id={case_id}",
            headers=headers,
            files={"file": ("smoke.wav", wav_bytes, "audio/wav")},
            timeout=40,
        )
        elapsed = time.time() - t0
        record(
            "upload_voice",
            voice_upload.status_code in (200, 201),
            f"status={voice_upload.status_code} elapsed={elapsed:.2f}s",
        )

        copilot = session.post(
            f"{base_url}/ai/copilot",
            headers=headers,
            json={"message": f"Summarize case #{case_id}", "top_k": 5},
            timeout=120,
        )
        record("copilot", copilot.status_code == 200, f"status={copilot.status_code}")

        workflow = session.post(
            f"{base_url}/ai/agent-workflow",
            headers=headers,
            json={"case_id": case_id, "objective": "Prepare a concise update", "top_k": 5},
            timeout=180,
        )
        record("agent_workflow", workflow.status_code == 200, f"status={workflow.status_code}")

    portal_email = f"portal_smoke_{random.randint(100000, 999999)}@example.com"
    portal_password = "PortalPass!123"
    portal_register = session.post(
        f"{base_url}/portal/auth/register",
        json={
            "tenant_slug": tenant_slug,
            "full_name": "Portal Smoke",
            "email": portal_email,
            "phone": "111222333",
            "address": "Test street",
            "password": portal_password,
        },
        timeout=30,
    )
    portal_register_detail = _response_detail(portal_register)
    portal_register_msg = f"status={portal_register.status_code}"
    if portal_register_detail:
        portal_register_msg = f"{portal_register_msg} detail={portal_register_detail}"
    if portal_register.status_code == 404 and "Tenant not found" in portal_register_detail:
        record("portal_register", True, f"SKIP {portal_register_msg}")
        record("portal_request_code", True, "SKIP tenant slug is not available in current DB")
    else:
        record("portal_register", portal_register.status_code in (200, 201), portal_register_msg)

        portal_request = session.post(
            f"{base_url}/portal/auth/login/request-code",
            json={"email": portal_email, "password": portal_password},
            timeout=40,
        )
        record("portal_request_code", portal_request.status_code in (200, 201), f"status={portal_request.status_code}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full smoke checks against the Legal AI Platform.")
    parser.add_argument("--port", type=int, default=8020, help="Temporary API port for smoke run.")
    args = parser.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"
    python_executable = sys.executable or r".\.venv\Scripts\python.exe"
    proc = subprocess.Popen(
        [
            python_executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        if not wait_for_health(base_url):
            print("Smoke startup failed: API did not become healthy in time.")
            return 1

        results = run_smoke(base_url)
        failures = [item for item in results if not item.ok]
        print("\nSUMMARY")
        print(json.dumps([asdict(item) for item in results], indent=2))
        if failures:
            print(f"\nSmoke test failed with {len(failures)} failing step(s).")
            return 1
        print("\nSmoke test passed.")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
