"""Session-bound CSRF checks for forms and same-origin fetch requests."""
import hmac
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse


class CSRFProtection(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = request.session.setdefault('csrf_token', secrets.token_urlsafe(32))
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            supplied = request.headers.get('X-CSRF-Token', '')
            if not supplied:
                await request.body()  # Preserve the body for the downstream form parser.
                if request.headers.get('content-type', '').split(';')[0] in {'application/x-www-form-urlencoded', 'multipart/form-data'}:
                    supplied = str((await request.form()).get('csrf_token', ''))
            if not supplied or not hmac.compare_digest(token, supplied):
                return PlainTextResponse('Your form expired. Reload the page and try again.', status_code=403)
        response = await call_next(request)
        # Login/logout can change session contents; keep the readable token aligned.
        token = request.session.setdefault('csrf_token', secrets.token_urlsafe(32))
        response.set_cookie('csrf_token', token, samesite='lax', secure=request.url.scheme == 'https')
        return response
