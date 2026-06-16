from django.utils import timezone
from django.conf import settings

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        try:
            path = request.path
            if path.startswith('/static/') or path.startswith('/media/') or path == '/favicon.ico':
                return response

            from .models import RequestLog
            is_login_attempt = request.method == 'POST' and path in ['/login/', '/admin-panel/']
            status_code = getattr(response, 'status_code', None)
            login_success = None
            if is_login_attempt:
                login_success = status_code in (301, 302, 303, 307, 308)

            RequestLog.objects.create(
                path=path,
                method=request.method,
                user=request.user if request.user.is_authenticated else None,
                ip_address=self._get_ip(request),
                status_code=status_code,
                server_port=request.META.get('SERVER_PORT', ''),
                is_authenticated=request.user.is_authenticated,
                is_login_attempt=is_login_attempt,
                login_success=login_success
            )
        except Exception:
            pass

        return response

    def _get_ip(self, request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '127.0.0.1')
