"""Transaction-outbox SMTP sender; run via a cron/job after configuring SMTP."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from sqlalchemy import select
from .core import Outbox, SessionLocal, utcnow


def send_pending(limit=25, send=None):
    host = os.environ.get("SMTP_HOST", "")
    sender = os.environ.get("SMTP_SENDER", "")
    if send is None and (not host or not sender):
        raise RuntimeError("Configure SMTP_HOST and SMTP_SENDER before sending")
    sent = 0
    with SessionLocal() as session:
        pending = session.scalars(select(Outbox).where(Outbox.status.in_(["pending", "failed"]), Outbox.attempts < 5).order_by(Outbox.id).limit(limit).with_for_update(skip_locked=True)).all()
        for row in pending:
            msg = EmailMessage()
            msg["From"] = sender or "test@example.invalid"
            msg["To"] = row.recipient
            msg["Subject"] = row.subject
            msg.set_content(row.body)
            try:
                if send:
                    send(msg)
                else:
                    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as client:
                        client.starttls(context=ssl.create_default_context())
                        client.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
                        client.send_message(msg)
                row.status = "sent"
                row.error = None
                row.sent_at = utcnow()
                sent += 1
            except Exception as exc:
                row.status = "failed"
                # Avoid putting exception details/credentials into user-visible logs.
                row.error = type(exc).__name__[:350]
            row.attempts += 1
            session.commit()
    return sent


if __name__ == "__main__":
    print("Sent", send_pending(), "emails")
