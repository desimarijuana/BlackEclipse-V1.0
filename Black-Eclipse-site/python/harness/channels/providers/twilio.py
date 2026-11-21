"""Twilio SMS provider — signed webhook inbound + REST outbound.

Twilio is the first **SMS** surface here and the first push provider that does not
speak JSON: it posts `application/x-www-form-urlencoded`, and signs the request
with **HMAC-SHA1 over the public URL plus the sorted form parameters**, base64
encoded (`X-Twilio-Signature`). Two consequences, both explicit:

  * **The signature covers the PUBLIC url**, because that is what Twilio fetched.
    Behind the Next.js front door the harness sees an internal URL, so the operator
    supplies `publicUrl` (e.g. `https://app.example.com/api/channels/webhook/twilio`)
    and the verifier reconstructs exactly that string. Missing `publicUrl` is a
    refusal — guessing it would make every signature fail silently.
  * **From/To are E.164 numbers.** A message whose `From` is the bot's own number
    is dropped, because Twilio echoes the outbound leg back to the same webhook.

Config:
  accountSid   AC… (required for outbound)
  authToken    the webhook signing secret and the REST password (required, secret)
  fromNumber   the Twilio number that sends (required for outbound)
  publicUrl    the exact public webhook URL Twilio signs (required for inbound)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any, Optional

import httpx

from ..model import InboundMessage
from ..transport import OutboundMessage

log = logging.getLogger("harness.channels.twilio")

_API = "https://api.twilio.com/2010-04-01"
_MAX_TEXT = 1_600   # one SMS segment set; Twilio splits silently beyond this


def signature_for(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Twilio's `X-Twilio-Signature`: base64(HMAC-SHA1(token, url + k+v…sorted))."""
    payload = str(url or "")
    for key in sorted(params):
        payload += f"{key}{params[key]}"
    digest = hmac.new(str(auth_token).encode("utf-8"), payload.encode("utf-8"),
                      hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def verify(auth_token: str, *, url: str, params: dict[str, str],
           signature: Optional[str]) -> bool:
    """Constant-time comparison; a missing token/url is a refusal, not a pass."""
    if not auth_token or not url or not signature:
        return False
    return hmac.compare_digest(signature_for(auth_token, url, params), signature)


def parse_inbound(params: dict[str, str], *, bot_number: str = "") -> Optional[InboundMessage]:
    """One Twilio form post -> one inbound message (None when it is not user text)."""
    sender = str(params.get("From") or "").strip()
    text = str(params.get("Body") or "").strip()
    if not sender or not text:
        return None
    if bot_number and sender == bot_number:
        return None
    return InboundMessage(
        kind="twilio",
        external_id=sender,
        external_chat=sender,
        text=text[:_MAX_TEXT],
        platform_message_id=str(params.get("MessageSid") or params.get("SmsSid") or ""),
        display_name=sender,
        raw={
            "to": params.get("To"),
            "numMedia": params.get("NumMedia"),
            "sid": params.get("MessageSid") or params.get("SmsSid"),
        },
    )


class TwilioProvider:
    kind = "twilio"

    def __init__(self, *, account_sid: str, auth_token: str, from_number: str,
                 public_url: str = "") -> None:
        self._sid = str(account_sid or "").strip()
        self._token = str(auth_token or "")
        self._from = str(from_number or "").strip()
        self._public_url = str(public_url or "").strip()

    async def send(self, message: OutboundMessage) -> bool:
        to = str(message.external_chat or "").strip()
        text = str(message.text or "").strip()
        if not self._sid or not self._token or not self._from or not to or not text:
            return False
        url = f"{_API}/Accounts/{self._sid}/Messages.json"
        data = {"From": self._from, "To": to, "Body": text[:_MAX_TEXT]}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(
                    connect=10.0, read=20.0, write=20.0, pool=10.0)) as client:
                res = await client.post(url, data=data, auth=(self._sid, self._token))
        except Exception:  # noqa: BLE001 - a delivery failure is False, never a crash
            log.warning("twilio send failed", exc_info=True)
            return False
        if res.status_code >= 400:
            log.warning("twilio rejected the message: HTTP %s", res.status_code)
            return False
        return True

    async def run(self, on_message: Any) -> None:
        """Inbound arrives by webhook; there is no transport to await here."""
        return None

    async def stop(self) -> None:
        return None


__all__ = ["TwilioProvider", "parse_inbound", "signature_for", "verify"]
