"""Email notifier (ARCHITECTURE 6.8; E8.1). Email only, to Nick's address from
.env (ALERT_EMAIL_TO); no other recipients are configurable in v1.

``SmtpNotifier`` is the real implementation. ``RecordingNotifier`` is the fake
used by tests and the simulator; it never sends anything.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol


class NotifyError(RuntimeError):
    pass


class Notifier(Protocol):
    def send(self, subject: str, body: str) -> None:
        """Send one message; raise NotifyError on failure."""


class SmtpNotifier:
    def __init__(self, host: str, port: int, user: str, password: str, sender: str, to: str,
                 timeout_s: float = 20.0) -> None:
        if not (host and sender and to):
            raise NotifyError("SMTP not configured (SMTP_HOST, SMTP_FROM, ALERT_EMAIL_TO)")
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.to, self.timeout_s = sender, to, timeout_s

    @classmethod
    def from_secrets(cls, s) -> "SmtpNotifier":
        return cls(s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password, s.smtp_from, s.alert_email_to)

    def send(self, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = self.to
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout_s) as s:
                s.starttls()
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(msg)
        except (OSError, smtplib.SMTPException) as e:
            raise NotifyError(f"SMTP send failed: {e}") from e


@dataclass
class RecordingNotifier:
    """Fake notifier: records messages; can be told to fail N times."""

    sent: list[tuple[str, str]] = field(default_factory=list)
    fail_next: int = 0
    attempts: int = 0

    def send(self, subject: str, body: str) -> None:
        self.attempts += 1
        if self.fail_next > 0:
            self.fail_next -= 1
            raise NotifyError("simulated SMTP failure")
        self.sent.append((subject, body))
