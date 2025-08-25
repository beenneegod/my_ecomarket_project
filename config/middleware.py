from django.utils.deprecation import MiddlewareMixin


class AdditionalSecurityHeadersMiddleware(MiddlewareMixin):
    """Add a few extra security-related headers safely.

    - Permissions-Policy to disable powerful features we don't use.
    - X-Download-Options for legacy IE protection.
    - X-Permitted-Cross-Domain-Policies to prevent Adobe plugin cross-domain access.
    """

    def process_response(self, request, response):
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(self), camera=(self), microphone=(), payment=(self), usb=()",
        )
        response.headers.setdefault("X-Download-Options", "noopen")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        return response
