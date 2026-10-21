"""Cart add/update/remove, guest-vs-account owner resolution, and
guest-cart merge-on-login."""
import uuid


def _register_and_login(client, email):
    client.post("/auth/register", json={"email": email, "password": "longenough8"})
    token = client.post(
        "/auth/login", json={"email": email, "password": "longenough8"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _first_product_id(client):
    return client.get("/shop/products").json()[0]["id"]


def test_cart_requires_exactly_one_owner_header(client):
    resp = client.get("/shop/cart")
    assert resp.status_code == 400

    headers = _register_and_login(client, "both@example.com")
    resp = client.get("/shop/cart", headers={**headers, "X-Cart-Token": str(uuid.uuid4())})
    assert resp.status_code == 400


def test_guest_add_and_view_cart(client):
    product_id = _first_product_id(client)
    guest_token = str(uuid.uuid4())
    headers = {"X-Cart-Token": guest_token}

    resp = client.post("/shop/cart/items", json={"product_id": product_id, "quantity": 2},
                        headers=headers)
    assert resp.status_code == 200
    cart = resp.json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 2

    resp = client.post("/shop/cart/items", json={"product_id": product_id, "quantity": 3},
                        headers=headers)
    assert resp.json()["items"][0]["quantity"] == 5  # summed, not replaced


def test_update_quantity_to_zero_removes_item(client):
    product_id = _first_product_id(client)
    headers = {"X-Cart-Token": str(uuid.uuid4())}
    client.post("/shop/cart/items", json={"product_id": product_id, "quantity": 1}, headers=headers)

    resp = client.put(f"/shop/cart/items/{product_id}", json={"quantity": 0}, headers=headers)
    assert resp.json()["items"] == []


def test_guest_cart_merges_into_account_on_login(client):
    product_id = _first_product_id(client)
    guest_token = str(uuid.uuid4())
    client.post("/shop/cart/items", json={"product_id": product_id, "quantity": 2},
                headers={"X-Cart-Token": guest_token})

    headers = _register_and_login(client, "merger@example.com")
    client.post("/shop/cart/items", json={"product_id": product_id, "quantity": 1}, headers=headers)

    resp = client.post("/shop/cart/merge", json={"guest_token": guest_token}, headers=headers)
    assert resp.status_code == 200
    merged = client.get("/shop/cart", headers=headers).json()
    assert merged["items"][0]["quantity"] == 3  # 1 (account) + 2 (guest), summed

    # Guest cart is gone — reusing the same token now gets a fresh empty cart.
    guest_cart = client.get("/shop/cart", headers={"X-Cart-Token": guest_token}).json()
    assert guest_cart["items"] == []
