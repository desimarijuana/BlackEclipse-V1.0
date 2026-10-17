"""Email provider — IMAP inbound + SMTP outbound.

Email needs no public endpoint either: the runtime polls the mailbox over IMAP.
A user links by sending an email whose body begins with `/link <code>`; replies
are sent over SMTP to the sender's address.

The mailbox is a spoofable channel, so linking (a code only an authenticated
Eclipse session can mint) is what establishes trust — a forged `From:` cannot
create a binding. Auto-submitted / bulk mail is ignored so a vacation responder or
a mailing list cannot drive the app.
"""

from __future__ import annotations

import asyncio
import email
import email.utils
import imaplib
import logging
import re
import smtplib
from email.message import EmailMessage
from email.policy import default as email_policy
from typing import Any, Optional

from ..model import InboundMessage
from ..transport import MessageHandler, OutboundMessage

log = logging.getLogger("harness.channels.email")

_QUOTE_MARKER = re.compile(r"^>")
_DEFAULT_POLL_S = 60


class EmailProvider:
    kind = "email"

    def __init__(
        self,
        *,
        imap_host: str,
        imap_user: str,
        imap_pass: str,
        imap_port: int = 993,
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_pass: str = "",
        from_address: str = "",
        poll_seconds: int = _DEFAULT_POLL_S,
        mailbox: str = "INBOX",
    ) -> None:
        self._imap_host = str(imap_host or "").strip()
        self._imap_user = str(imap_user or "").strip()
        self._imap_pass = str(imap_pass or "")
        self._imap_port = int(imap_port or 993)
        self._smtp_host = str(smtp_host or "").strip()
        self._smtp_port = int(smtp_port or 587)
        self._smtp_user = str(smtp_user or "").strip()
        self._smtp_pass = str(smtp_pass or "")
        self._from = str(from_address or imap_user or "").strip()
        self._poll = max(15, int(poll_seconds or _DEFAULT_POLL_S))
        self._mailbox = mailbox or "INBOX"
        self._stopped = asyncio.Event()

    # ── outbound ─────────────────────────────────────────────────────────────
    async def send(self, message: OutboundMessage) -> bool:
        if not self._smtp_host or not self._from:
            return False
        try:
            await asyncio.to_thread(self._send_sync, message.external_chat, message.text)
            return True
        except Exception:  # noqa: BLE001 - a delivery failure is reported, not raised
            log.warning("email send error", exc_info=True)
            return False

    def _send_sync(self, to_addr: str, text: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._from
        msg["To"] = to_addr
        msg["Subject"] = "Eclipse"
        msg.set_content(text[:20000])
        if self._smtp_port == 465:
            with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, timeout=20) as smtp:
                if self._smtp_user:
                    smtp.login(self._smtp_user, self._smtp_pass)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=20) as smtp:
                smtp.starttls()
                if self._smtp_user:
                    smtp.login(self._smtp_user, self._smtp_pass)
                smtp.send_message(msg)

    # ── inbound ──────────────────────────────────────────────────────────────
    async def stop(self) -> None:
        self._stopped.set()

    async def run(self, on_message: MessageHandler) -> None:
        if not self._imap_host:
            log.warning("email provider has no IMAP host; poller not started")
            return
        log.info("email channel poller started")
        while not self._stopped.is_set():
            try:
                messages = await asyncio.to_thread(self._poll_sync)
            except Exception:  # noqa: BLE001 - a transient IMAP error retries
                log.debug("email poll error", exc_info=True)
                messages = []
            for message in messages:
                try:
                    await on_message(message)
                except Exception:  # noqa: BLE001 - one bad message never kills the poller
                    log.warning("email message handling failed", exc_info=True)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._poll)
            except asyncio.TimeoutError:
                pass

    def _poll_sync(self) -> list[InboundMessage]:
        out: list[InboundMessage] = []
        conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
        try:
            conn.login(self._imap_user, self._imap_pass)
            conn.select(self._mailbox)
            status, data = conn.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return out
            for num in data[0].split():
                try:
                    status, fetched = conn.fetch(num, "(RFC822)")
                    if status != "OK" or not fetched:
                        continue
                    raw = _first_bytes(fetched)
                    if raw is None:
                        continue
                    message = self._to_inbound(raw)
                    conn.store(num, "+FLAGS", "(\\Seen)")
                    if message is not None:
                        out.append(message)
                except Exception:  # noqa: BLE001 - one unparsable mail never blocks the mailbox
                    log.debug("email parse error", exc_info=True)
                    continue
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass
        return out

    def _to_inbound(self, raw: bytes) -> Optional[InboundMessage]:
        msg = email.message_from_bytes(raw, policy=email_policy)
        # Loop / auto-reply guards: never process our own outbound or a robot email.
        if msg.get("Auto-Submitted") and msg.get("Auto-Submitted") != "no":
            return None
        if msg.get("Precedence", "").lower() in ("bulk", "junk", "list"):
            return None
        _, from_addr = email.utils.parseaddr(msg.get("From", ""))
        if not from_addr or from_addr.lower() == self._from.lower():
            return None
        body = _extract_text(msg)
        if not body.strip():
            return None
        return InboundMessage(
            kind=self.kind,
            external_id=from_addr.lower(),
            external_chat=from_addr,
            text=body[:4000],
            platform_message_id=str(msg.get("Message-ID") or ""),
            display_name=str(msg.get("From") or ""),
            raw={"subject": str(msg.get("Subject") or "")},
        )


def _first_bytes(fetched: Any) -> Optional[bytes]:
    for item in fetched:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
            return bytes(item[1])
    return None


def _extract_text(msg: Any) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment":
                try:
                    text = part.get_content()
                except Exception:  # noqa: BLE001
                    continue
                return _strip_quotes(str(text))
        return ""
    try:
        return _strip_quotes(str(msg.get_content()))
    except Exception:  # noqa: BLE001
        return ""


def _strip_quotes(text: str) -> str:
    """Drop a trailing quoted reply so `/link CODE` on line 1 survives intact."""
    lines: list[str] = []
    for line in text.splitlines():
        if _QUOTE_MARKER.match(line.strip()) or line.strip().startswith("On ") and line.strip().endswith("wrote:"):
            break
        lines.append(line)
    return "\n".join(lines).strip()


__all__ = ["EmailProvider"]
