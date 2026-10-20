from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from apps.omyfish_api.db.engine import get_db


class WebhookEventRepository:

    def already_processed(self, event_id: str) -> bool:
        with get_db() as db:
            row = db.execute(
                text("SELECT 1 FROM processed_webhook_events WHERE event_id = :id"),
                {"id": event_id},
            ).fetchone()
        return row is not None

    def mark_processed(self, event_id: str) -> None:
        try:
            with get_db() as db:
                db.execute(
                    text(
                        "INSERT INTO processed_webhook_events (event_id, processed_at) "
                        "VALUES (:id, :now)"
                    ),
                    {"id": event_id, "now": datetime.now(timezone.utc).isoformat()},
                )
        except IntegrityError:
            pass  # already recorded by a concurrent redelivery
