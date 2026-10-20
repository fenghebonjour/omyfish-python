import json

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from apps.omyfish_api.db.engine import get_db


class IdempotencyConflict(Exception):
    """Key already used by another user, or a request with it is still in flight."""


class IdempotencyRepository:

    def reserve(self, key: str, endpoint: str, user_id: str) -> dict | None:
        """Reserve (key, endpoint) for user_id. Returns the stored result if this
        is a replay of an already-completed request, or None for a fresh
        reservation. Raises IdempotencyConflict if the key is in flight or
        belongs to a different user."""
        try:
            with get_db() as db:
                db.execute(
                    text(
                        "INSERT INTO idempotency_keys (idempotency_key, endpoint, user_id, status) "
                        "VALUES (:key, :endpoint, :uid, 'pending')"
                    ),
                    {"key": key, "endpoint": endpoint, "uid": user_id},
                )
            return None
        except IntegrityError:
            existing = self._get(key, endpoint)
            if existing["user_id"] != user_id:
                raise IdempotencyConflict("Idempotency key already used by another request")
            if existing["status"] == "pending":
                raise IdempotencyConflict("A request with this idempotency key is already in progress")
            return json.loads(existing["result_json"])

    def complete(self, key: str, endpoint: str, result: dict) -> None:
        with get_db() as db:
            db.execute(
                text(
                    "UPDATE idempotency_keys SET status = 'completed', result_json = :r "
                    "WHERE idempotency_key = :key AND endpoint = :endpoint"
                ),
                {"r": json.dumps(result), "key": key, "endpoint": endpoint},
            )

    def release(self, key: str, endpoint: str) -> None:
        """Drop a pending reservation after a failed call so the key can be retried."""
        with get_db() as db:
            db.execute(
                text(
                    "DELETE FROM idempotency_keys "
                    "WHERE idempotency_key = :key AND endpoint = :endpoint AND status = 'pending'"
                ),
                {"key": key, "endpoint": endpoint},
            )

    def _get(self, key: str, endpoint: str) -> dict | None:
        with get_db() as db:
            row = db.execute(
                text(
                    "SELECT * FROM idempotency_keys WHERE idempotency_key = :key AND endpoint = :endpoint"
                ),
                {"key": key, "endpoint": endpoint},
            ).fetchone()
        return dict(row._mapping) if row else None
