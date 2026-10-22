"""Fixed seed catalog for the Omyshop product table. Shared by both backends
so the SQLite dev/test catalog and the Postgres prod catalog never drift:
engine.py's init_db() (SQLite) and migration 006 (Postgres) both insert this
same list. Fixed ids (not new_id()) so the insert is idempotent across
repeated calls/migrations, same pattern as omyfish-java's Flyway seed.

Placeholder images are inline SVG data URIs — no external image hosting
needed, same approach omyfish-java's own seed migration uses."""

import base64


def _placeholder_svg(label: str, color: str) -> str:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300">'
        f'<rect width="300" height="300" fill="{color}"/>'
        f'<text x="150" y="150" font-size="20" text-anchor="middle" '
        f'dominant-baseline="middle" fill="white" font-family="sans-serif">{label}</text>'
        f'</svg>'
    )
    # Raw (non-base64) data URIs break here: the hex colors' "#" is parsed as
    # the URL fragment delimiter, truncating the SVG markup mid-attribute.
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


SHOP_SEED_PRODUCTS = [
    {
        "id": "shop-seed-0001", "name": "Spinnerbait Lure",
        "description": "Flash-and-vibration lure for bass and walleye in stained water.",
        "price_cents": 899, "image_url": _placeholder_svg("Spinnerbait", "#2b6cb0"),
        "stock_quantity": 50, "active": True,
    },
    {
        "id": "shop-seed-0002", "name": "Soft Plastic Worm Pack (10)",
        "description": "Weedless-rigged finesse worms, 4-inch, natural colors.",
        "price_cents": 599, "image_url": _placeholder_svg("Worms", "#2f855a"),
        "stock_quantity": 100, "active": True,
    },
    {
        "id": "shop-seed-0003", "name": "Topwater Popper",
        "description": "Surface popper for early-morning bass and pike strikes.",
        "price_cents": 1099, "image_url": _placeholder_svg("Popper", "#c05621"),
        "stock_quantity": 40, "active": True,
    },
    {
        "id": "shop-seed-0004", "name": "Braided Fishing Line (150yd)",
        "description": "20lb test braided line, low stretch, high sensitivity.",
        "price_cents": 1499, "image_url": _placeholder_svg("Line", "#4a5568"),
        "stock_quantity": 60, "active": True,
    },
    {
        "id": "shop-seed-0005", "name": "Polarized Fishing Sunglasses",
        "description": "Cuts surface glare to spot structure and fish in the water column.",
        "price_cents": 2499, "image_url": _placeholder_svg("Glasses", "#1a202c"),
        "stock_quantity": 25, "active": True,
    },
    {
        "id": "shop-seed-0006", "name": "Tackle Box — 4 Tray",
        "description": "Stackable tray tackle box with adjustable dividers.",
        "price_cents": 1999, "image_url": _placeholder_svg("Tackle Box", "#744210"),
        "stock_quantity": 30, "active": True,
    },
    {
        "id": "shop-seed-0007", "name": "Fish Fillet Knife",
        "description": "Flexible 6-inch stainless blade for cleaning your catch.",
        "price_cents": 1799, "image_url": _placeholder_svg("Fillet Knife", "#822727"),
        "stock_quantity": 35, "active": True,
    },
    {
        "id": "shop-seed-0008", "name": "OMyFish Insulated Mug",
        "description": "12oz stainless mug — keep coffee hot on an early launch.",
        "price_cents": 1299, "image_url": _placeholder_svg("Mug", "#2c5282"),
        "stock_quantity": 75, "active": True,
    },
]
