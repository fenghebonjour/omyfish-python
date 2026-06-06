from sqlalchemy import text

from apps.omyfish_api.db.engine import IS_POSTGIS, new_id, get_db
from shared.events import ObservationCreated, emit
from shared.schemas.observation import ObservationCreate


class ObservationRepository:

    def create(self, obs: ObservationCreate) -> str:
        with get_db() as db:
            if IS_POSTGIS:
                row = db.execute(
                    text("""
                        INSERT INTO observations
                          (species_name, scientific_name, confidence,
                           latitude, longitude, geom, user_id, source, image_url)
                        VALUES
                          (:species, :sci, :conf, :lat, :lon,
                           ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                           :uid, :source, :img)
                        RETURNING id
                    """),
                    dict(
                        species=obs.species_name, sci=obs.scientific_name,
                        conf=obs.confidence, lat=obs.latitude, lon=obs.longitude,
                        uid=obs.user_id, source=obs.source, img=obs.image_url,
                    ),
                ).fetchone()
                obs_id = str(row[0])
            else:
                obs_id = new_id()
                db.execute(
                    text("""
                        INSERT INTO observations
                          (id, species_name, scientific_name, confidence,
                           latitude, longitude, user_id, source, image_url)
                        VALUES
                          (:id, :species, :sci, :conf, :lat, :lon, :uid, :source, :img)
                    """),
                    dict(
                        id=obs_id, species=obs.species_name, sci=obs.scientific_name,
                        conf=obs.confidence, lat=obs.latitude, lon=obs.longitude,
                        uid=obs.user_id, source=obs.source, img=obs.image_url,
                    ),
                )

        emit(ObservationCreated(
            observation_id=obs_id,
            species_name=obs.species_name,
            latitude=obs.latitude,
            longitude=obs.longitude,
            source=obs.source,
        ))
        return obs_id

    def list(self, limit: int = 100) -> list:
        with get_db() as db:
            rows = db.execute(
                text("""
                    SELECT id, species_name, scientific_name, confidence,
                           timestamp, latitude, longitude, image_url, user_id, source
                    FROM observations ORDER BY timestamp DESC LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row) -> dict:
    d = dict(row._mapping)
    ts = d.get("timestamp")
    if ts and hasattr(ts, "isoformat"):
        d["timestamp"] = ts.isoformat()
    if d.get("id"):
        d["id"] = str(d["id"])
    return d
