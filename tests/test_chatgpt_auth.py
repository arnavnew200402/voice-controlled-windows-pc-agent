"""SIWC contracts use generated keys and fake tokens; no account or network access."""

import json
import os
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from vox.agent.auth_storage import CredentialStore, Session, StorageError
from vox.agent.chatgpt_auth import (
    JWKS_PATH,
    TOKEN_PATH,
    Attempt,
    AuthError,
    sign_in,
    validate_tokens,
)

HOST = "urn:uuid:12345678-1234-4234-8234-123456789abc"


@pytest.fixture(scope="module")
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    return private, {"keys": [jwk]}


def token_response(private, attempt, **overrides):
    now = int(time.time())
    claims = {
        "iss": "https://auth.openai.com",
        "sub": "test-subject",
        "aud": "issued-client",
        "iat": now,
        "exp": now + 600,
        "nonce": attempt.nonce,
    }
    claims.update(overrides)
    return {
        "id_token": jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test-key"}),
        "access_token": "fake-access",
        "refresh_token": "fake-refresh",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct",
    }


def test_authorization_pkce_and_callback_binding():
    attempt = Attempt.create(45678, HOST, None)
    params = parse_qs(urlsplit(attempt.authorization_url()).query)
    assert params["client_id"] == ["dynamic_agent_client"]
    assert params["agent_name_hint"] == ["vox"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://127.0.0.1:45678/auth/callback"]
    assert attempt.verifier not in attempt.authorization_url()
    assert attempt.state not in repr(attempt)
    assert attempt.callback(
        "/auth/callback?"
        + urlencode({"state": attempt.state, "code": "test", "client_id": "issued-client"})
    ) == ("test", "issued-client")
    for query in (
        {"state": "wrong", "code": "test", "client_id": "issued-client"},
        {"state": attempt.state, "code": "test"},
        {"state": attempt.state, "code": "test", "client_id": "dynamic_agent_client"},
    ):
        with pytest.raises(AuthError):
            attempt.callback("/auth/callback?" + urlencode(query))
    with pytest.raises(AuthError):
        attempt.callback(
            "/auth/callback?state=" + attempt.state + "&state=other&code=x&client_id=y"
        )
    returning = Attempt.create(45679, HOST, "issued-client")
    assert "agent_name_hint" not in parse_qs(urlsplit(returning.authorization_url()).query)
    with pytest.raises(AuthError):
        returning.callback(
            "/auth/callback?"
            + urlencode({"state": returning.state, "code": "x", "client_id": "other"})
        )


def test_jwt_signature_nonce_audience_and_permissions(keys):
    private, jwks = keys
    attempt = Attempt.create(45678, HOST, None)
    tokens = token_response(private, attempt)
    session = validate_tokens(tokens, jwks, attempt, "issued-client")
    assert session.subject == "test-subject"
    assert "fake-access" not in repr(session)
    for changes in ({"nonce": "wrong"}, {"aud": "other"}, {"iss": "https://evil.test"}, {"exp": 1}):
        with pytest.raises(AuthError):
            validate_tokens(
                token_response(private, attempt, **changes), jwks, attempt, "issued-client"
            )
    bad_scope = dict(tokens, scope="openid email")
    with pytest.raises(AuthError, match="not authorized"):
        validate_tokens(bad_scope, jwks, attempt, "issued-client")
    with pytest.raises(AuthError):
        validate_tokens(tokens, {"keys": []}, attempt, "issued-client")


def test_protected_store_atomic_round_trip_with_fake_cipher(tmp_path):
    # The test cipher is deliberately fake; Windows DPAPI is separately tested on Windows.
    encrypt = lambda b: b"protected:" + b[::-1]
    decrypt = lambda b: b.removeprefix(b"protected:")[::-1]
    store = CredentialStore(tmp_path / "private" / "state.bin", encrypt=encrypt, decrypt=decrypt)
    session = Session(
        "client", "subject", "fake-access", "fake-refresh", "fake-id", time.time() + 100
    )
    store.save(HOST, session)
    assert b"fake-access" not in store.path.read_bytes()
    assert store.load() == (HOST, session)
    store.path.write_bytes(b"bad")
    with pytest.raises(StorageError):
        store.load()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI round trip")
def test_windows_dpapi_round_trip(tmp_path):
    store = CredentialStore(tmp_path / "private" / "state.bin")
    session = Session(
        "client", "subject", "fake-access", "fake-refresh", "fake-id", time.time() + 100
    )
    store.save(HOST, session)
    assert b"fake-access" not in store.path.read_bytes()
    assert store.load() == (HOST, session)


def test_sign_in_uses_issued_client_and_saves_only_after_validation(monkeypatch, tmp_path, keys):
    import vox.agent.chatgpt_auth as auth

    private, jwks = keys
    store = CredentialStore(tmp_path / "state", encrypt=lambda b: b, decrypt=lambda b: b)
    store.save(HOST, None)
    attempt = Attempt.create(45555, HOST, None)
    exchange = []
    monkeypatch.setattr(
        auth, "_browser_callback", lambda factory, **kwargs: (attempt, "fake-code", "issued-client")
    )

    def request(path, form=None):
        exchange.append((path, form))
        return token_response(private, attempt) if path == TOKEN_PATH else jwks

    monkeypatch.setattr(auth, "auth_request", request)
    sign_in(store)
    assert exchange[0][0] == TOKEN_PATH and exchange[0][1]["client_id"] == "issued-client"
    assert exchange[1][0] == JWKS_PATH
    assert store.load()[1].subject == "test-subject"
    assert "fake-code" not in json.dumps({"host": store.load()[0]})


def test_loopback_callback_rejects_wrong_state_and_never_logs_code(monkeypatch, capsys):
    import threading
    import urllib.request

    import vox.agent.chatgpt_auth as auth

    responses = []
    threads = []

    def browser(url):
        params = parse_qs(urlsplit(url).query)
        redirect = params["redirect_uri"][0]
        state = params["state"][0]

        def visit():
            wrong = (
                redirect
                + "?"
                + urlencode({"state": "wrong", "code": "test-code", "client_id": "test-client"})
            )
            try:
                urllib.request.urlopen(wrong, timeout=3)
            except urllib.error.HTTPError as exc:
                responses.append(exc.code)
            good = (
                redirect
                + "?"
                + urlencode({"state": state, "code": "test-code", "client_id": "test-client"})
            )
            with urllib.request.urlopen(good, timeout=3) as res:
                responses.append(res.status)
                assert b"test-code" not in res.read()

        t = threading.Thread(target=visit)
        threads.append(t)
        t.start()
        return True

    monkeypatch.setattr(auth.webbrowser, "open", browser)
    _, code, client = auth._browser_callback(
        lambda port: Attempt.create(port, HOST, None), timeout=5
    )
    threads[0].join(timeout=3)
    assert (code, client) == ("test-code", "test-client")
    assert responses == [400, 200]
    captured = capsys.readouterr()
    assert "test-code" not in captured.out + captured.err


def test_forged_signature_is_rejected(keys):
    _, trusted_jwks = keys
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attempt = Attempt.create(45678, HOST, None)
    with pytest.raises(AuthError):
        validate_tokens(
            token_response(attacker_key, attempt), trusted_jwks, attempt, "issued-client"
        )


def test_reauth_different_subject_does_not_replace_saved_session(monkeypatch, tmp_path, keys):
    import vox.agent.chatgpt_auth as auth

    private, jwks = keys
    store = CredentialStore(tmp_path / "state", encrypt=lambda b: b, decrypt=lambda b: b)
    existing = Session(
        "issued-client",
        "original-subject",
        "fake-access",
        "fake-refresh",
        "fake-id",
        time.time() + 100,
    )
    store.save(HOST, existing)
    attempt = Attempt.create(45555, HOST, "issued-client")
    monkeypatch.setattr(
        auth, "_browser_callback", lambda factory, **kwargs: (attempt, "fake-code", "issued-client")
    )
    monkeypatch.setattr(
        auth,
        "auth_request",
        lambda path, form=None: (
            token_response(private, attempt, sub="different-subject")
            if path == TOKEN_PATH
            else jwks
        ),
    )
    with pytest.raises(AuthError, match="different account"):
        sign_in(store)
    assert store.load() == (HOST, existing)
