"""The Python client is generated from the registry, so these tests check the
generation, not a hand-written list of methods. A test that restates the method
list would be a third declaration of the API.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packauth import DEFAULT_BASE_URL, PackAuth, PackAuthError  # noqa: E402
from packauth._registry import load_registry  # noqa: E402

REGISTRY = load_registry()
OPERATIONS = REGISTRY["operations"]


def fake(status=200, payload=None, capture=None):
    def opener(request, timeout):
        if capture is not None:
            capture["url"] = request.full_url
            capture["method"] = request.method
            capture["headers"] = dict(request.headers)
            capture["body"] = request.data
        return status, json.dumps(payload if payload is not None else {"ok": True})
    return opener


def test_every_declared_operation_is_callable():
    pa = PackAuth(token="t")
    for op in OPERATIONS:
        assert callable(getattr(pa, op["operation_id"])), op["operation_id"]


def test_no_operation_is_invented():
    pa = PackAuth(token="t")
    with pytest.raises(AttributeError):
        pa.definitely_not_an_operation()


def test_describe_matches_the_registry():
    described = PackAuth(token="t").describe()
    assert len(described) == len(OPERATIONS)
    assert {d["operation_id"] for d in described} == {o["operation_id"] for o in OPERATIONS}


def test_public_operations_need_no_token():
    public = [o for o in OPERATIONS if o.get("public")]
    assert public, "the registry declares no public operations"
    capture = {}
    pa = PackAuth(opener=fake(capture=capture))
    pa.call(public[0]["operation_id"])
    assert "authorization" not in {k.lower() for k in capture["headers"]}


def test_scoped_operation_without_a_token_fails_before_any_request():
    scoped = next(o for o in OPERATIONS if not o.get("public"))
    called = {"n": 0}

    def opener(request, timeout):
        called["n"] += 1
        return 200, "{}"

    with pytest.raises(PackAuthError) as exc:
        PackAuth(opener=opener).call(scoped["operation_id"])
    assert exc.value.code == "no_token"
    assert called["n"] == 0, "a request was sent despite there being no token"


def test_missing_path_parameter_fails_before_any_request():
    with_param = next(o for o in OPERATIONS if o.get("path_params"))
    with pytest.raises(PackAuthError) as exc:
        PackAuth(token="t").call(with_param["operation_id"])
    assert exc.value.code == "missing_path_param"
    assert with_param["path_params"][0] in str(exc.value)


def test_path_parameters_are_substituted_and_encoded():
    op = next(o for o in OPERATIONS if len(o.get("path_params") or []) == 1)
    name = op["path_params"][0]
    capture = {}
    PackAuth(token="t", opener=fake(capture=capture)).call(op["operation_id"], **{name: "a/b c"})
    assert "a%2Fb%20c" in capture["url"]
    assert ":" + name not in capture["url"]


def test_error_responses_carry_code_and_request_id():
    op = next(o for o in OPERATIONS if o.get("public"))
    opener = fake(
        status=409,
        payload={"error": {"code": "manifest_state_invalid", "message": "nope"}, "request_id": "req_1"},
    )
    with pytest.raises(PackAuthError) as exc:
        PackAuth(opener=opener).call(op["operation_id"])
    assert exc.value.status == 409
    assert exc.value.code == "manifest_state_invalid"
    assert exc.value.request_id == "req_1"


def test_default_base_url_is_the_production_api():
    assert DEFAULT_BASE_URL == "https://api.packauth.com"


def test_client_contains_no_literal_api_paths():
    """The surface is read from the registry. A path here is a second declaration."""
    source = (Path(__file__).resolve().parents[1] / "packauth" / "__init__.py").read_text()
    code = "\n".join(l for l in source.splitlines() if not l.strip().startswith("#"))
    assert "/v1/" not in code
