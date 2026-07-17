from services.gis_service.service import GISService


def test_to_geojson_coordinate_order_and_properties():
    obs = {
        "id": "abc", "species_name": "walleye",
        "latitude": 45.5, "longitude": -73.5,
    }
    fc = GISService().to_geojson([obs])
    assert fc["type"] == "FeatureCollection"
    feature = fc["features"][0]
    # GeoJSON mandates [longitude, latitude]
    assert feature["geometry"]["coordinates"] == [-73.5, 45.5]
    assert feature["properties"] == {"id": "abc", "species_name": "walleye"}


def test_to_geojson_skips_observations_without_coordinates():
    obs = [
        {"id": "1", "latitude": 45.0, "longitude": -73.0},
        {"id": "2", "latitude": None, "longitude": -73.0},
        {"id": "3"},
    ]
    fc = GISService().to_geojson(obs)
    assert [f["properties"]["id"] for f in fc["features"]] == ["1"]


def test_to_geojson_empty_list():
    assert GISService().to_geojson([]) == {"type": "FeatureCollection", "features": []}
