from typing import Optional
from PIL import Image

from services.gis_service.exif import extract_exif_gps


class GISService:

    def extract_gps(self, image: Image.Image) -> Optional[tuple]:
        """Return (lat, lon) from image EXIF, or None."""
        return extract_exif_gps(image)

    def to_geojson(self, observations: list) -> dict:
        """Convert a list of observation dicts to a GeoJSON FeatureCollection."""
        features = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [obs["longitude"], obs["latitude"]],
                },
                "properties": {
                    k: v for k, v in obs.items() if k not in ("latitude", "longitude")
                },
            }
            for obs in observations
            if obs.get("latitude") is not None and obs.get("longitude") is not None
        ]
        return {"type": "FeatureCollection", "features": features}
