"""PackAuth API client for Python.

Every method is DERIVED from spec/registries/api.json when the client is
constructed — the same registry the Worker routes from and the TypeScript SDK
builds its methods from.

That is the whole design. A client whose method list is written by hand is a
second declaration of the API, and the second declaration is the one that falls
behind: a method that no longer matches its endpoint fails in your build, not in
ours. Here there is nothing to fall behind — add an operation and the method
exists; remove one and calling it raises AttributeError at the call site rather
than returning a 404 six weeks later.

    from packauth import PackAuth

    pa = PackAuth(token=os.environ["PACKAUTH_TOKEN"])
    pa.health()                                  # public, no token needed
    pa.list_packs()
    pa.get_pack(pack_id="gcc_pack")
    pa.create_run(body={"manifest_id": "man_01HX7Q2T"})
    pa.manifest_matrix(manifest_id="man_01HX7Q2T")

Path parameters are keyword-only, never positional. `get_pack(pack_id=...)`
reads at the call site; a positional version invites the day someone swaps two
arguments and ships it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from ._registry import load_registry

__all__ = ["PackAuth", "PackAuthError", "DEFAULT_BASE_URL"]

DEFAULT_BASE_URL = "https://api.packauth.com"
_REGISTRY = load_registry()


class PackAuthError(Exception):
    """Every failure, carrying what you need to act on it.

    `code` is stable and safe to branch on. `message` is not. `request_id` is
    what makes a support conversation about one specific call possible.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str = "packauth_error",
        request_id: str | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id
        self.body = body


def _build_path(op: dict, params: dict) -> str:
    """Substitute :name segments. A missing one is an error, never an empty path."""

    path = op["path"]
    for name in op.get("path_params") or []:
        value = params.get(name)
        if value in (None, ""):
            raise PackAuthError(
                f"{op['operation_id']}() needs '{name}' — it is part of the path {op['path']}",
                code="missing_path_param",
            )
        path = path.replace(f":{name}", urllib.parse.quote(str(value), safe=""))
    return path


class PackAuth:
    """The PackAuth API client.

    :param token: Bearer token. Required for every operation except the three
        declared public.
    :param base_url: Defaults to production.
    :param timeout: Seconds.
    :param opener: Injected for tests; defaults to urllib.
    """

    def __init__(
        self,
        token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        opener: Callable[[urllib.request.Request, float], Any] | None = None,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener
        self.operations = {op["operation_id"]: op for op in _REGISTRY["operations"]}

    # -- introspection -------------------------------------------------------

    def describe(self) -> list[dict]:
        """Which operations exist and what each needs. Useful in a REPL."""

        return [
            {
                "operation_id": op["operation_id"],
                "http": f"{op['method']} {op['path']}",
                "scope": op.get("scope"),
                "public": bool(op.get("public")),
                "path_params": op.get("path_params") or [],
                "summary": op["summary"],
            }
            for op in _REGISTRY["operations"]
        ]

    # -- the generated surface -----------------------------------------------

    def __getattr__(self, name: str) -> Callable[..., Any]:
        # Only reached when normal attribute lookup fails, so real attributes
        # always win and an unknown operation still raises AttributeError —
        # which is the point: a removed operation fails at the call site.
        op = self.operations.get(name) if hasattr(self, "operations") else None
        if op is None:
            raise AttributeError(
                f"PackAuth has no operation {name!r}. "
                f"spec/registries/api.json declares {len(getattr(self, 'operations', {}))} operations; "
                f"call describe() to list them."
            )

        def invoke(**kwargs: Any) -> Any:
            return self.call(name, **kwargs)

        invoke.__name__ = name
        invoke.__doc__ = f"{op['summary']}\n\n{op['method']} {op['path']}" + (
            f"\nRequires scope: {op['scope']}" if op.get("scope") else "\nPublic."
        )
        return invoke

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(self.operations))

    # -- the one place a request is made -------------------------------------

    def call(
        self,
        operation_id: str,
        *,
        query: dict | None = None,
        body: Any = None,
        **params: Any,
    ) -> Any:
        op = self.operations.get(operation_id)
        if op is None:
            raise PackAuthError(f"no operation {operation_id!r}", code="unknown_operation")

        if not op.get("public") and not self.token:
            raise PackAuthError(
                f"{operation_id}() requires a token — it is scoped {op['scope']!r}",
                code="no_token",
            )

        url = self.base_url + _build_path(op, params)
        if query:
            pairs = {k: str(v) for k, v in query.items() if v is not None}
            if pairs:
                url += "?" + urllib.parse.urlencode(pairs)

        data = None
        headers = {"accept": "application/json"}
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["content-type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=op["method"])

        try:
            if self._opener is not None:
                status, payload_text = self._opener(request, self.timeout)
            else:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    status = response.status
                    payload_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = exc.code
            payload_text = exc.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise PackAuthError(
                f"{operation_id}() could not reach {self.base_url}: {exc.reason}",
                code="unreachable",
            ) from exc

        try:
            payload = json.loads(payload_text) if payload_text else None
        except json.JSONDecodeError:
            payload = {"raw": payload_text}

        if status >= 400:
            error = (payload or {}).get("error") or {}
            raise PackAuthError(
                error.get("message") or f"HTTP {status}",
                status=status,
                code=error.get("code") or f"http_{status}",
                request_id=(payload or {}).get("request_id"),
                body=payload,
            )
        return payload
