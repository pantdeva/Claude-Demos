"""Google APIs used for phone notifications, authenticated with the Firebase
service-account key (path in the SFA_FCM_SERVICE_ACCOUNT setting) through google-auth:

  Firebase Cloud Messaging HTTP v1   send data-only, high-priority messages to a device
                                     token or a topic
  Cloud Firestore REST               read the device registry users/{uid}/devices/{id}
                                     that the signed-in app writes
  Identity Toolkit (Firebase Auth)   look up each user's verified email, so only the
                                     accounts you allow receive messages

Data-only messages always reach the app's FirebaseMessagingService, which builds the
notification itself (own channels, tap action, alert history).
"""

from __future__ import annotations

import json
import os
import time

import requests

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]   # covers FCM, Firestore and Identity Toolkit
FCM_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
FS_URL = "https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents"
IDT_URL = "https://identitytoolkit.googleapis.com/v1/projects/{project}/accounts:lookup"


class FCMError(RuntimeError):
    def __init__(self, msg: str, status: int = 0, unregistered: bool = False):
        super().__init__(msg)
        self.status = status
        self.unregistered = unregistered


class FCMSender:
    def __init__(self, key_path: str | None = None, session: requests.Session | None = None):
        self.key_path = key_path or os.environ.get("SFA_FCM_SERVICE_ACCOUNT")
        if not self.key_path or not os.path.exists(self.key_path):
            raise FCMError("SFA_FCM_SERVICE_ACCOUNT is not set to a Firebase service-account key file")
        with open(self.key_path, encoding="utf-8") as f:
            self.project = json.load(f)["project_id"]
        self.session = session or requests.Session()
        self._creds = None

    # ------------------------------------------------------------ auth
    def _token(self) -> str:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account
        except ImportError as e:
            raise FCMError("the google-auth package is missing: pip install google-auth") from e
        if self._creds is None:
            self._creds = service_account.Credentials.from_service_account_file(self.key_path, scopes=SCOPES)
        if not self._creds.valid:
            self._creds.refresh(Request())
        return self._creds.token

    def _req(self, method: str, url: str, **kw):
        kw.setdefault("timeout", 20)
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._token()}"
        return self.session.request(method, url, headers=headers, **kw)

    # ------------------------------------------------------------ messaging
    def send(self, data: dict[str, str], token: str | None = None, topic: str | None = None, ttl_s: int = 86400) -> str:
        target = {"token": token} if token else {"topic": topic}
        body = {"message": {**target, "data": {k: str(v) for k, v in data.items() if v is not None},
                            "android": {"priority": "HIGH", "ttl": f"{ttl_s}s"}}}
        for attempt in range(3):
            r = self._req("POST", FCM_URL.format(project=self.project), json=body)
            if r.status_code == 200:
                return r.json().get("name", "")
            if r.status_code in (429, 500, 503) and attempt < 2:
                time.sleep(2 ** attempt * 2)
                continue
            text = r.text[:300]
            gone = r.status_code == 404 or "UNREGISTERED" in text or "registration-token-not-registered" in text
            raise FCMError(f"FCM HTTP {r.status_code}: {text}", r.status_code, unregistered=gone)
        raise FCMError("FCM: retries exhausted")

    # ------------------------------------------------------------ device registry (Firestore)
    def _list(self, path: str) -> list[dict]:
        out, page = [], None
        while True:
            params = {"pageSize": 300, **({"pageToken": page} if page else {})}
            r = self._req("GET", f"{FS_URL.format(project=self.project)}/{path}", params=params)
            if r.status_code == 404:
                return out
            if r.status_code != 200:
                raise FCMError(f"Firestore HTTP {r.status_code}: {r.text[:300]}", r.status_code)
            d = r.json()
            out += d.get("documents", [])
            page = d.get("nextPageToken")
            if not page:
                return out

    @staticmethod
    def _field(doc: dict, name: str) -> str | None:
        v = (doc.get("fields") or {}).get(name) or {}
        return v.get("stringValue") or v.get("timestampValue")

    def users_emails(self, uids: list[str]) -> dict[str, dict]:
        """{uid: {"email", "verified", "disabled"}} from Firebase Authentication (not from the app)."""
        out = {}
        for i in range(0, len(uids), 100):
            r = self._req("POST", IDT_URL.format(project=self.project), json={"localId": uids[i:i + 100]})
            if r.status_code != 200:
                raise FCMError(f"Identity Toolkit HTTP {r.status_code}: {r.text[:300]}", r.status_code)
            for u in r.json().get("users", []):
                out[u["localId"]] = {"email": (u.get("email") or "").lower(), "verified": bool(u.get("emailVerified")),
                                     "disabled": bool(u.get("disabled"))}
        return out

    def devices(self, allowed_emails: set[str]) -> list[dict]:
        """Registered devices of signed-in users whose verified email is allowed."""
        users = [d["name"].rsplit("/", 1)[1] for d in self._list("users")]
        if not users:
            return []
        info = self.users_emails(users)
        out = []
        for uid in users:
            u = info.get(uid)
            if not u or u["disabled"] or not u["verified"] or u["email"] not in allowed_emails:
                continue
            for d in self._list(f"users/{uid}/devices"):
                tok = self._field(d, "token")
                if tok:
                    out.append({"uid": uid, "email": u["email"], "device": d["name"].rsplit("/", 1)[1], "token": tok,
                                "model": self._field(d, "model") or "", "updated": self._field(d, "updatedAt") or "",
                                "doc": d["name"]})
        return out

    def delete_device(self, doc_name: str) -> None:
        self._req("DELETE", f"https://firestore.googleapis.com/v1/{doc_name}")
