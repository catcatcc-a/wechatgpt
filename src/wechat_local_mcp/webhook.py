"""A loopback-only, authenticated OneBot receiver; run independently of stdio."""

import hashlib
import hmac
import json

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .config import Config
from .store import Store

MAX_BODY_BYTES = 2 * 1024 * 1024


def create_app(config: Config, store: Store) -> Starlette:
    def bearer_ok(request: Request) -> bool:
        headers = request.headers.getlist("Authorization")
        expected = ("Bearer " + config.onebot_token).encode()
        return bool(config.onebot_token) and len(headers) == 1 and hmac.compare_digest(headers[0].encode(), expected)

    async def receive(request: Request):
        if not config.onebot_token:
            return JSONResponse({"error": "receiver token is not configured"}, status_code=503)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                return JSONResponse({"error": "event too large"}, status_code=413)
        expected = "sha1=" + hmac.new(config.onebot_token.encode(), body, hashlib.sha1).hexdigest()
        signatures = request.headers.getlist("X-Signature")
        if len(signatures) != 1 or not hmac.compare_digest(signatures[0].encode(), expected.encode()):
            return JSONResponse({"error": "invalid signature"}, status_code=401)
        try:
            event = json.loads(body)
            if not isinstance(event, dict):
                raise ValueError("event must be an object")
            result = store.ingest(event)
        except (ValueError, TypeError, AttributeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"status": "ok", **result})

    async def health(request: Request):
        if not config.onebot_token:
            return JSONResponse({"error": "receiver token is not configured"}, status_code=503)
        if not bearer_ok(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return JSONResponse({"status": "ok", "token_configured": True, **store.stats()})

    return Starlette(routes=[Route("/onebot", receive, methods=["POST"]), Route("/health", health, methods=["GET"])])
