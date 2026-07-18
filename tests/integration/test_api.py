import io

from PIL import Image


def _png_upload(name="fish.png"):
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color=(0, 100, 200)).save(buf, "png")
    buf.seek(0)
    return {"file": (name, buf, "image/png")}


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": True}


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_register_login_me_flow(client):
    r = client.post("/auth/register", json={"email": "a@b.c", "password": "hunter2222"})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "a@b.c" and body["role"] == "user" and body["is_active"]

    assert client.post(
        "/auth/register", json={"email": "a@b.c", "password": "otherpassword"}
    ).status_code == 409

    r = client.post("/auth/login", json={"email": "a@b.c", "password": "hunter2222"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["email"] == "a@b.c"


def test_register_rejects_short_password(client):
    r = client.post("/auth/register", json={"email": "a@b.c", "password": "short7c"})
    assert r.status_code == 422


def test_register_rejects_invalid_email(client):
    r = client.post("/auth/register", json={"email": "not-an-email", "password": "longenough8"})
    assert r.status_code == 422


def test_login_wrong_password_rejected(client):
    client.post("/auth/register", json={"email": "a@b.c", "password": "hunter2222"})
    assert client.post(
        "/auth/login", json={"email": "a@b.c", "password": "nope"}
    ).status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_users_endpoint_is_admin_only(client, auth_headers):
    headers, _ = auth_headers
    assert client.get("/users").status_code == 401
    assert client.get("/users", headers=headers).status_code == 403


# ── Observations ──────────────────────────────────────────────────────────────

OBS = {
    "species_name": "walleye",
    "scientific_name": "Sander vitreus",
    "confidence": 0.91,
    "latitude": 45.5,
    "longitude": -73.5,
}


def test_create_and_list_observation(client):
    r = client.post("/observations", json=OBS)
    assert r.status_code == 200
    obs_id = r.json()["id"]
    assert r.json()["status"] == "created"

    rows = client.get("/observations").json()
    assert [row["id"] for row in rows] == [obs_id]
    row = rows[0]
    assert row["species_name"] == "walleye"
    assert row["latitude"] == 45.5 and row["longitude"] == -73.5
    assert row["source"] == "manual"


def test_authenticated_observation_gets_user_id(client, auth_headers):
    headers, user_id = auth_headers
    client.post("/observations", json=OBS, headers=headers)
    client.post("/observations", json=OBS)  # anonymous

    mine = client.get("/observations", headers=headers).json()
    assert len(mine) == 1 and mine[0]["user_id"] == user_id

    everything = client.get("/observations").json()
    assert len(everything) == 2


def test_observations_geojson(client):
    client.post("/observations", json=OBS)
    fc = client.get("/observations/geojson").json()
    assert fc["type"] == "FeatureCollection"
    assert fc["features"][0]["geometry"]["coordinates"] == [-73.5, 45.5]


# ── Prediction endpoints (stubbed AI service) ─────────────────────────────────

def test_predict_rejects_non_image(client):
    r = client.post("/predict", files={"file": ("data.txt", io.BytesIO(b"hi"), "text/plain")})
    assert r.status_code == 400


def test_predict_returns_stub_predictions(client):
    r = client.post("/predict", files=_png_upload())
    assert r.status_code == 200
    body = r.json()
    assert body["is_fish"] is True
    assert body["predictions"][0]["species"] == "walleye"


def test_identify_fish_saves_observation_with_manual_coords(client):
    r = client.post(
        "/identify-fish",
        files=_png_upload(),
        data={"latitude": "46.8", "longitude": "-71.2", "save": "true"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["location_source"] == "manual"
    assert body["latitude"] == 46.8 and body["longitude"] == -71.2
    assert "observation_id" in body

    rows = client.get("/observations").json()
    assert rows[0]["id"] == body["observation_id"]
    assert rows[0]["species_name"] == "walleye"
    assert rows[0]["source"] == "upload"


def test_identify_fish_without_coords_does_not_save(client):
    r = client.post("/identify-fish", files=_png_upload(), data={"save": "true"})
    assert r.status_code == 200
    assert "observation_id" not in r.json()
    assert client.get("/observations").json() == []


def test_predict_rejects_corrupt_image_bytes(client):
    r = client.post("/predict", files={"file": ("x.png", io.BytesIO(b"not an image"), "image/png")})
    assert r.status_code == 400


def test_predict_rejects_oversized_upload(client):
    big = io.BytesIO(b"\x00" * (10 * 1024 * 1024 + 1))
    r = client.post("/predict", files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413


# ── Not-a-fish edge case (e.g. a cat photo) ───────────────────────────────────

def test_predict_not_a_fish(not_a_fish_client):
    r = not_a_fish_client.post("/predict", files=_png_upload(name="cat.png"))
    assert r.status_code == 200
    body = r.json()
    assert body["is_fish"] is False
    assert body["predictions"] == []
    assert body["uncertain"] is True
    assert "fish" in body["message"]


def test_identify_fish_not_a_fish_never_saves(not_a_fish_client):
    r = not_a_fish_client.post(
        "/identify-fish",
        files=_png_upload(name="cat.png"),
        data={"latitude": "46.8", "longitude": "-71.2", "save": "true"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_fish"] is False
    assert "observation_id" not in body
    assert not_a_fish_client.get("/observations").json() == []
