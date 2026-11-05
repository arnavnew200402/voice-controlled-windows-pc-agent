"""Official SIWC public-client flow. Credentials never enter logs or arguments."""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import secrets
import time
import uuid
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt

from vox.agent.auth_storage import CredentialStore, Session
from vox.branding import APP_NAME

AUTH_HOST = "auth.openai.com"
AUTH_URL = f"https://{AUTH_HOST}/api/accounts/authorize"
TOKEN_PATH = "/api/accounts/oauth/token"
JWKS_PATH = "/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
MAX_RESPONSE = 1_048_576


class AuthError(RuntimeError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class Attempt:
    state: str = field(repr=False)
    nonce: str = field(repr=False)
    verifier: str = field(repr=False)
    redirect_uri: str
    host_id: str
    client_id: str | None

    @classmethod
    def create(cls, port: int, host_id: str, client_id: str | None) -> Attempt:
        return cls(
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(64),
            f"http://127.0.0.1:{port}/auth/callback",
            host_id,
            client_id,
        )

    def authorization_url(self) -> str:
        params = {
            "client_id": self.client_id or "dynamic_agent_client",
            "ext_agent_host_id": self.host_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": self.state,
            "nonce": self.nonce,
            "code_challenge_method": "S256",
            "code_challenge": _b64(hashlib.sha256(self.verifier.encode("ascii")).digest()),
        }
        if self.client_id is None:
            params["agent_name_hint"] = APP_NAME
        return AUTH_URL + "?" + urlencode(params)

    def callback(self, path: str) -> tuple[str, str]:
        parsed = urlsplit(path)
        if parsed.path != "/auth/callback" or len(path) > 8192:
            raise AuthError("Invalid callback.")
        try:
            values = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=32)
        except ValueError as exc:
            raise AuthError("Invalid callback.") from exc
        if any(len(v) != 1 for v in values.values()):
            raise AuthError("Invalid callback.")
        received = values.get("state", [""])[0]
        if not received or not hmac.compare_digest(
            received.encode("utf-8"), self.state.encode("ascii")
        ):
            raise AuthError("Invalid callback.")
        if values.get("error"):
            raise AuthError("ChatGPT sign-in was not completed.")
        code = values.get("code", [""])[0]
        issued = values.get("client_id", [""])[0]
        if not code or len(code) > 4096 or len(issued) > 512:
            raise AuthError("Sign-in callback was incomplete.")
        if self.client_id and issued and issued != self.client_id:
            raise AuthError("Sign-in returned a different client registration.")
        selected = self.client_id or issued
        if not selected or selected == "dynamic_agent_client":
            raise AuthError("Sign-in did not return an issued client registration.")
        return code, selected


def auth_request(path: str, form: dict[str, str] | None = None) -> dict[str, Any]:
    if path not in (TOKEN_PATH, JWKS_PATH):
        raise AuthError("Unsupported authentication endpoint.")
    connection = http.client.HTTPSConnection(AUTH_HOST, timeout=20)
    try:
        if form is None:
            connection.request("GET", path)
        else:
            connection.request(
                "POST",
                path,
                body=urlencode(form),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        response = connection.getresponse()
        if response.status != 200:
            raise AuthError("ChatGPT authentication request failed. Try signing in again.")
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise AuthError("Authentication response was too large.")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise AuthError("Authentication response was invalid.")
        return data
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise AuthError("Could not reach or read the ChatGPT authentication service.") from exc
    finally:
        connection.close()


def validate_tokens(
    tokens: dict[str, Any],
    jwks: dict[str, Any],
    attempt: Attempt,
    client_id: str,
    *,
    now: Callable[[], float] = time.time,
) -> Session:
    try:
        id_token = tokens["id_token"]
        access = tokens["access_token"]
        refresh = tokens["refresh_token"]
        scope = tokens["scope"]
        expires = tokens["expires_in"]
        if not all(
            isinstance(v, str) and v and len(v) <= 65536 for v in (id_token, access, refresh, scope)
        ):
            raise ValueError("invalid token response")
        token_type = tokens.get("token_type")
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise ValueError("invalid token type")
        if type(expires) not in (int, float) or not 0 < expires <= 86400:
            raise ValueError("invalid expiry")
        if not {"chatgpt.tokens.use.direct", "resource.invoke"}.issubset(set(scope.split())):
            raise AuthError("ChatGPT plan usage was not authorized.")
        header = jwt.get_unverified_header(id_token)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise ValueError("invalid signing header")
        keyset = jwt.PyJWKSet.from_dict(jwks)
        key = next(
            k.key for k in keyset.keys if k.key_id == header["kid"] and k.algorithm_name == "RS256"
        )
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            issuer="https://auth.openai.com",
            audience=client_id,
            options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]},
        )
        subject, nonce = claims.get("sub"), claims.get("nonce")
        if (
            not isinstance(subject, str)
            or not subject
            or not isinstance(nonce, str)
            or not hmac.compare_digest(nonce, attempt.nonce)
        ):
            raise ValueError("invalid identity")
        return Session(
            client_id=client_id,
            subject=subject,
            access_token=access,
            refresh_token=refresh,
            id_token=id_token,
            expires_at=now() + float(expires),
        )
    except AuthError:
        raise
    except (KeyError, TypeError, ValueError, StopIteration, jwt.PyJWTError) as exc:
        raise AuthError("ChatGPT identity or authorization could not be verified.") from exc


def _browser_callback(
    attempt_factory: Callable[[int], Attempt],
    timeout: float = 180,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[Attempt, str, str]:
    result: list[tuple[str, str]] = []
    failure: list[AuthError] = []
    attempt: Attempt

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            try:
                callback_result = attempt.callback(self.path)
                result.append(callback_result)
                self.send_response(200)
                body = b"Sign-in response received. Return to the application to finish."
            except AuthError as exc:
                # Only a correctly bound denial is allowed to end the attempt.
                if str(exc) == "ChatGPT sign-in was not completed.":
                    failure.append(exc)
                self.send_response(400)
                body = b"Sign-in was not completed. You may return to the application."
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

    class CallbackServer(HTTPServer):
        def handle_error(self, request: object, client_address: object) -> None:
            # Callback query strings may contain authorization codes; never log them.
            pass

    try:
        server = CallbackServer(("127.0.0.1", 0), Handler)
    except OSError as exc:
        raise AuthError("Could not start the sign-in callback listener.") from exc
    try:
        attempt = attempt_factory(server.server_port)
        server.timeout = 0.5
        try:
            opened = webbrowser.open(attempt.authorization_url())
        except (OSError, webbrowser.Error) as exc:
            raise AuthError("Could not open the system browser for ChatGPT sign-in.") from exc
        if not opened:
            raise AuthError("Could not open the system browser for ChatGPT sign-in.")
        deadline = time.monotonic() + timeout
        while not result and not failure and not cancelled() and time.monotonic() < deadline:
            server.handle_request()
        if cancelled():
            raise AuthError("ChatGPT sign-in was cancelled.")
        if failure:
            raise failure[0]
        if not result:
            raise AuthError("ChatGPT sign-in timed out.")
        return attempt, result[0][0], result[0][1]
    finally:
        server.server_close()


def sign_in(store: CredentialStore, *, cancelled: Callable[[], bool] = lambda: False) -> None:
    host_id, previous = store.load()
    if host_id is None:
        host_id = "urn:uuid:" + str(uuid.uuid4())
        store.save(host_id, None)
    attempt, code, client_id = _browser_callback(
        lambda port: Attempt.create(port, host_id, previous.client_id if previous else None),
        cancelled=cancelled,
    )
    if cancelled():
        raise AuthError("ChatGPT sign-in was cancelled.")
    tokens = auth_request(
        TOKEN_PATH,
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": attempt.verifier,
            "redirect_uri": attempt.redirect_uri,
            "resource": RESOURCE,
        },
    )
    session = validate_tokens(tokens, auth_request(JWKS_PATH), attempt, client_id)
    if previous is not None and previous.subject != session.subject:
        raise AuthError("Sign-in returned a different account; the saved session was not replaced.")
    if cancelled():
        raise AuthError("ChatGPT sign-in was cancelled.")
    store.save(host_id, session)
