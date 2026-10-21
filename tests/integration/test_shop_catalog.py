"""Shop product catalog — public, read-only."""


def test_list_products_returns_seeded_catalog(client):
    resp = client.get("/shop/products")
    assert resp.status_code == 200
    products = resp.json()
    assert len(products) == 8
    assert all(p["active"] for p in products)


def test_get_product_by_id(client):
    products = client.get("/shop/products").json()
    product_id = products[0]["id"]
    resp = client.get(f"/shop/products/{product_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == product_id


def test_get_unknown_product_404s(client):
    resp = client.get("/shop/products/does-not-exist")
    assert resp.status_code == 404
