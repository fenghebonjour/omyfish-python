from sqlalchemy import text

from apps.omyfish_api.db.engine import IS_POSTGIS, new_id, get_db


class UserRepository:

    def create(self, email: str, hashed_password: str, role: str = "user") -> dict:
        uid = new_id()
        with get_db() as db:
            db.execute(
                text(
                    "INSERT INTO users (id, email, hashed_password, role) "
                    "VALUES (:id, :email, :pw, :role)"
                ),
                {"id": uid, "email": email, "pw": hashed_password, "role": role},
            )
        return self.get_by_id(uid)

    def get_by_email(self, email: str) -> dict | None:
        with get_db() as db:
            row = db.execute(
                text(
                    "SELECT id, email, hashed_password, role, is_active "
                    "FROM users WHERE email = :e"
                ),
                {"e": email},
            ).fetchone()
        return dict(row._mapping) if row else None

    def get_by_id(self, uid: str) -> dict | None:
        with get_db() as db:
            row = db.execute(
                text("SELECT id, email, role, is_active FROM users WHERE id = :id"),
                {"id": uid},
            ).fetchone()
        return dict(row._mapping) if row else None

    def list(self, limit: int = 100) -> list:
        with get_db() as db:
            rows = db.execute(
                text(
                    "SELECT id, email, role, is_active FROM users "
                    "ORDER BY created_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]

    def delete(self, uid: str) -> bool:
        with get_db() as db:
            result = db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
        return result.rowcount > 0
