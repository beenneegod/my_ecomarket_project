from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging

logger = logging.getLogger(__name__)


@csrf_exempt
def csp_report(request):
    """Accept CSP violation reports and log them.

    Spec per https://w3c.github.io/webappsec-csp/#violation-reports
    Some browsers send report-to format. We store minimally to logs.
    """
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        data = {}

    # Normalize common fields
    report = data.get('csp-report') or data
    logger.warning("CSP violation: %s", report)

    return JsonResponse({"status": "ok"})
