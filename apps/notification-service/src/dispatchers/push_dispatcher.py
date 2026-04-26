import base64
import json
import time
import httpx
import google.auth
import google.auth.transport.requests
from google.oauth2 import service_account

from src.config import settings
from src.dispatchers.base import BaseDispatcher, DispatchResult
from src.core.middleware import provider_dispatch_errors_total


class FCMPushDispatcher(BaseDispatcher):
    """
    Firebase Cloud Messaging v1 HTTP API.
    """
    
    _credentials = None
    _token_expiry = 0

    def _get_access_token(self) -> str:
        now = time.time()
        if self._credentials is None or now > self._token_expiry - 60:
            if not settings.FCM_SERVICE_ACCOUNT_JSON:
                return "mock_token"
            sa_json = json.loads(base64.b64decode(settings.FCM_SERVICE_ACCOUNT_JSON))
            creds = service_account.Credentials.from_service_account_info(
                sa_json,
                scopes=["https://www.googleapis.com/auth/firebase.messaging"],
            )
            req = google.auth.transport.requests.Request()
            creds.refresh(req)
            self.__class__._credentials = creds
            self.__class__._token_expiry = now + 3600
        return self._credentials.token

    async def send(self, *, destination: str, content: str, subject=None, notification_id: int) -> DispatchResult:
        if not destination:
            return DispatchResult(success=False, failure_reason="NO_FCM_TOKEN", should_retry=False)

        api_url = settings.FCM_API_URL.format(project_id=settings.FCM_PROJECT_ID)
        
        message = {
            "message": {
                "token": destination,
                "notification": {
                    "title": subject or "SahulatKar",
                    "body": content,
                },
                "android": {
                    "priority": "high",
                    "notification": {"click_action": "FLUTTER_NOTIFICATION_CLICK"},
                },
                "apns": {
                    "payload": {"aps": {"alert": {"title": subject, "body": content}, "sound": "default"}},
                },
                "data": {
                    "notification_id": str(notification_id),
                    "click_action": "OPEN_APP",
                },
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    api_url,
                    json=message,
                    headers={
                        "Authorization": f"Bearer {self._get_access_token()}",
                        "Content-Type": "application/json",
                    },
                )
            except httpx.RequestError as exc:
                 provider_dispatch_errors_total.labels(
                    provider="fcm", 
                    error_code="REQUEST_ERROR"
                ).inc()
                 return DispatchResult(
                    success=False,
                    provider_name="fcm",
                    failure_reason=f"FCM_HTTP_ERROR: {str(exc)}",
                    should_retry=True,
                )

        if response.status_code == 200:
            body = response.json()
            return DispatchResult(
                success=True,
                provider_message_id=body.get("name", ""),
                provider_name="fcm",
            )

        body = response.json()
        error_code = body.get("error", {}).get("details", [{}])[0].get("errorCode", "UNKNOWN")
        
        provider_dispatch_errors_total.labels(
            provider="fcm", 
            error_code=error_code
        ).inc()
        
        is_permanent = error_code in (
            "REGISTRATION_TOKEN_NOT_REGISTERED",
            "INVALID_ARGUMENT",
            "UNREGISTERED",
        )
        
        return DispatchResult(
            success=False,
            provider_name="fcm",
            failure_reason=f"FCM_{error_code}",
            should_retry=not is_permanent,
        )

    async def health_check(self) -> bool:
        return bool(settings.FCM_SERVICE_ACCOUNT_JSON and settings.FCM_PROJECT_ID)
