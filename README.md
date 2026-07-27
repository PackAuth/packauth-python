> **This repository is generated.**
> The source of truth is the PackAuth API registry. This client is assembled
> from it and pushed here, so it cannot fall behind the API it covers. Open
> issues here; send changes to the source repository, because an edit made in
> this one is overwritten by the next publish.

# packauth (Python)

The PackAuth API client for Python. No dependencies — standard library only.

## The one design decision

Every method is **derived from `spec/registries/api.json`** at construction
time: the same registry the Worker binds its route table to, the TypeScript SDK
builds its methods from, and the OpenAPI document is generated from.

A client written by hand is a second declaration of the API, and the second
declaration is the one that falls behind. Here there is nothing to fall behind —
add an operation and the method exists; remove one and calling it raises
`AttributeError` at the call site rather than returning a 404 six weeks later.

```python
import os
from packauth import PackAuth

pa = PackAuth(token=os.environ["PACKAUTH_TOKEN"])

pa.health()                                        # public, no token needed
pa.list_packs()
pa.get_pack(pack_id="gcc_pack")
pa.create_run(body={"manifest_id": "man_01HX7Q2T"})
pa.manifest_matrix(manifest_id="man_01HX7Q2T")
```

Path parameters are keyword-only, never positional. `get_pack(pack_id=...)`
reads at the call site; a positional version invites the day someone swaps two
arguments and ships it.

`pa.describe()` lists every operation with its route, scope and summary.

## Errors

Everything raises `PackAuthError`:

```python
try:
    pa.create_print_release(body=body)
except PackAuthError as e:
    e.status       # 409
    e.code         # "manifest_state_invalid" — the API's own code, not a guess
    e.request_id   # "req_01HX…" — what makes a support conversation possible
    e.body         # the full response
```

Branch on `code`. It is stable; `message` is free to change.

A scoped call with no token, or a missing path parameter, raises **before any
request is sent** — a clear local error rather than a 401 or 404 to interpret.

## What this does not do yet

No retry, no pagination helper, no async client. Each is a real feature with
real semantics to get right, and a retry that silently repeats a non-idempotent
`POST` would be worse than having none. They land when they are built, not as a
stub.
