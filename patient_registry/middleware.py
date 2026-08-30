import secrets

from django.utils.cache import patch_vary_headers


class BrowserSecurityMiddleware:
    """Apply a per-response CSP nonce and privacy headers to application responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(18)
        response = self.get_response(request)

        nonce = request.csp_nonce
        directives = [
            "default-src 'self'",
            "base-uri 'self'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "form-action 'self'",
            f"script-src 'self' blob: 'nonce-{nonce}'",
            "script-src-attr 'none'",
            "style-src 'self' 'unsafe-inline'",
            (
                f"style-src-elem 'self' 'nonce-{nonce}' "
                "'sha256-e6ycxNK0KQEbRUnIqoIkSpN1WX7AWfaqrCdtdORNPjo='"
            ),
            "style-src-attr 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "manifest-src 'self'",
            "media-src 'self'",
            "worker-src 'self' blob:",
        ]
        if request.is_secure():
            directives.append("upgrade-insecure-requests")
        response.headers["Content-Security-Policy"] = "; ".join(directives)
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
            "publickey-credentials-get=(self), publickey-credentials-create=(self)"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            response.headers["Cache-Control"] = "private, no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            patch_vary_headers(response, ("Cookie", "Authorization"))

        return response
