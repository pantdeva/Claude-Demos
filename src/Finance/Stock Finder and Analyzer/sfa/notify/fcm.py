"""Firebase Cloud Messaging (HTTP v1) sender.

Authenticates with a Firebase service-account key (JSON file path in the
SFA_FCM_SERVICE_ACCOUNT setting) through the google-auth package, and sends
*data-only* messages with high priority to an FCM topic. Data-only messages always
reach the app's FirebaseMessagingService, so the app builds the notification itself
(its own channels, tap action and alert history).
"""

from __future__ import annotations

import json
import os
import time

import requests

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"


class FCMError(RuntimeError):
    pass


class FCMSender:
    def __init__(self, key_path: str | None = None, session: requests.Session | None = None):
        self.key_path = key_path or os.environ.get("SFA_FCM_SERVICE_ACCOUNT")
        if not self.key_path or not os.path.exists(self.key_path):
            raise FCMError("SFA_FCM_SERVICE_ACCOUNT is not set to a Firebase service-account key file")
        with open(self.key_path, encoding="utf-8") as f:
            self.project = json.load(f)["project_id"]
        self.session = session or requests.Session()
        self._creds = None

    def _token(self) -> str:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account
        except ImportError as e:
            raise FCMError("the google-auth package is missing: pip install google-auth") from e
        if self._creds is None:
            self._creds = service_account.Credentials.from_service_account_file(self.key_path, scopes=[SCOPE])
        if not self._creds.valid:
            self._creds.refresh(Request())
        return self._creds.token

    def send(self, topic: str, data: dict[str, str], ttl_s: int = 86400) -> str:
        body = {"message": {"topic": topic, "data": {k: str(v) for k, v in data.items() if v is not None},
                            "android": {"priority": "HIGH", "ttl": f"{ttl_s}s"}}}
        for attempt in range(3):
            r = self.session.post(URL.format(project=self.project), json=body, timeout=20,
                                  headers={"Authorization": f"Bearer {self._token()}"})
            if r.status_code == 200:
                return r.json().get("name", "")
            if r.status_code in (429, 500, 503) and attempt < 2:
                time.sleep(2 ** attempt * 2)
                continue
            raise FCMError(f"FCM HTTP {r.status_code}: {r.text[:300]}")
        raise FCMError("FCM: retries exhausted")
