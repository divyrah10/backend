"""
Seed demo catalog data through the live HTTP API.

This intentionally hits the real FastAPI endpoints (admin auth, categories,
products) rather than writing to the DB directly, so the write paths get
exercised end-to-end while the demo data is created.

Usage:
    # backend server must be running (e.g. uvicorn app.main:app --port 8000)
    venv/bin/python scripts/seed_demo_data.py

Env overrides:
    API_BASE          default http://localhost:8000/api/v1
    ADMIN_SETUP_KEY   default notjustdark-setup-2024  (must match backend .env)
    ADMIN_EMAIL       default admin@notjustdark.com
    ADMIN_PASSWORD    default Admin@12345
"""
import os
import sys
import requests

API_BASE = os.environ.get("API_BASE", "http://localhost:8000/api/v1")
SETUP_KEY = os.environ.get("ADMIN_SETUP_KEY", "notjustdark-setup-2024")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@notjustdark.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
ADMIN_NAME = "Store Admin"

IMG = "https://images.unsplash.com/photo-{}?w=800&q=80&auto=format&fit=crop"


def img(photo_id: str) -> str:
    return IMG.format(photo_id)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_admin_token() -> str:
    """Create the first super-admin, or log in if one already exists."""
    r = requests.post(
        f"{API_BASE}/admin/initialize",
        json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "full_name": ADMIN_NAME,
            "setup_key": SETUP_KEY,
        },
    )
    if r.status_code == 200:
        print(f"  ✓ created super admin {ADMIN_EMAIL}")
        return r.json()["access_token"]

    # Already set up (or this email exists) -> log in via the admin endpoint
    if r.status_code == 400:
        r2 = requests.post(
            f"{API_BASE}/admin/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if r2.status_code == 200:
            print(f"  ✓ logged in as existing admin {ADMIN_EMAIL}")
            return r2.json()["access_token"]
        sys.exit(f"  ✗ admin exists but login failed: {r2.status_code} {r2.text}")

    sys.exit(f"  ✗ admin initialize failed: {r.status_code} {r.text}")


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CATEGORIES = [
    {
        "name": "Women",
        "slug": "women",
        "description": "Elegant pieces crafted for the modern woman.",
        "image_url": img("1485968579580-b6d095142e6e"),
        "sort_order": 1,
    },
    {
        "name": "Men",
        "slug": "men",
        "description": "Bold statements for the distinguished gentleman.",
        "image_url": img("1516257984-b1b4d707412e"),
        "sort_order": 2,
    },
    {
        "name": "Accessories",
        "slug": "accessories",
        "description": "The finishing touches that complete the look.",
        "image_url": img("1523275335684-37898b6baf30"),
        "sort_order": 3,
    },
]


def seed_categories(headers) -> dict:
    """Create categories; return {slug: id}. Reuses any that already exist."""
    slug_to_id = {}
    for cat in CATEGORIES:
        r = requests.post(f"{API_BASE}/categories/", json=cat, headers=headers)
        if r.status_code == 201:
            slug_to_id[cat["slug"]] = r.json()["id"]
            print(f"  ✓ category {cat['name']}")
        elif r.status_code == 400:  # slug already exists
            existing = requests.get(f"{API_BASE}/categories/slug/{cat['slug']}").json()
            slug_to_id[cat["slug"]] = existing["id"]
            print(f"  · category {cat['name']} already exists, reusing")
        else:
            sys.exit(f"  ✗ category {cat['name']} failed: {r.status_code} {r.text}")
    return slug_to_id


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def p(name, cat, price, photos, *, compare=None, stock=40, featured=False,
      sizes=None, colors=None, material="Cotton blend", desc=None):
    return {
        "name": name,
        "category": cat,
        "price": price,
        "compare_at_price": compare,
        "stock_quantity": stock,
        "is_featured": featured,
        "short_description": desc or name,
        "description": (
            desc or name
        ) + " Designed in Italy, crafted in India. Part of the NOT JUST DARK collection.",
        "images": [img(x) for x in photos],
        "attributes": {
            "size": sizes or ["XS", "S", "M", "L", "XL"],
            "color": colors or ["Black", "Charcoal"],
            "material": material,
        },
    }


PRODUCTS = [
    # ---- Women ----
    p("Noir Silk Slip Dress", "women", 8990, ["1515372039744-b8f02a3ae446", "1539008835657-9e8e9680c956"],
      compare=11990, featured=True, colors=["Black", "Wine"], material="Mulberry silk",
      desc="A bias-cut silk slip dress that drapes effortlessly."),
    p("Onyx Tailored Blazer", "women", 12500, ["1490481651871-ab68de25d43d", "1485968579580-b6d095142e6e"],
      featured=True, material="Wool blend", desc="A sharp single-breasted blazer with structured shoulders."),
    p("Midnight Pleated Trousers", "women", 6490, ["1525507119028-ed4c629a60a3"],
      colors=["Black", "Slate"], material="Crepe", desc="High-waisted pleated trousers with a fluid fall."),
    p("Shadow Knit Turtleneck", "women", 4290, ["1483985988355-763728e1935b"],
      compare=5490, colors=["Charcoal", "Black", "Cream"], material="Merino wool",
      desc="A fine-gauge merino turtleneck for layered elegance."),
    p("Eclipse Wrap Blouse", "women", 5290, ["1496747611176-843222e1e57c"],
      featured=True, colors=["Black", "Ivory"], material="Viscose", desc="A softly draped wrap blouse with tie waist."),
    p("Raven Wide-Leg Jumpsuit", "women", 9990, ["1572804013309-59a88b7e92f1"],
      colors=["Black"], material="Tencel", desc="A monochrome wide-leg jumpsuit with a cinched waist."),
    p("Velvet Evening Gown", "women", 15990, ["1539008835657-9e8e9680c956", "1515372039744-b8f02a3ae446"],
      compare=19990, featured=True, sizes=["S", "M", "L"], colors=["Black", "Emerald"],
      material="Velvet", desc="A floor-length velvet gown for occasions that matter."),
    p("Smoke Cashmere Cardigan", "women", 8490, ["1485968579580-b6d095142e6e"],
      colors=["Smoke", "Black"], material="Cashmere", desc="An oversized cashmere cardigan, impossibly soft."),

    # ---- Men ----
    p("Obsidian Oxford Shirt", "men", 4990, ["1516257984-b1b4d707412e", "1488161628813-04466f872be2"],
      featured=True, colors=["White", "Black", "Sky"], material="Egyptian cotton",
      desc="A crisp tailored oxford shirt with mother-of-pearl buttons."),
    p("Carbon Wool Overcoat", "men", 18990, ["1488161628813-04466f872be2"],
      compare=23990, featured=True, sizes=["S", "M", "L", "XL"], colors=["Charcoal", "Camel"],
      material="Italian wool", desc="A long double-faced wool overcoat with clean lines."),
    p("Graphite Slim Chinos", "men", 5490, ["1507003211169-0a1dd7228f2d"],
      colors=["Stone", "Navy", "Black"], material="Stretch cotton", desc="Slim-fit chinos with a touch of stretch."),
    p("Midnight Merino Polo", "men", 4290, ["1521572163474-6864f9cf17ab"],
      compare=5290, colors=["Black", "Forest", "Grey"], material="Merino wool",
      desc="A refined knitted polo that bridges smart and casual."),
    p("Slate Crewneck Tee", "men", 2490, ["1521572163474-6864f9cf17ab", "1507003211169-0a1dd7228f2d"],
      featured=True, colors=["White", "Black", "Olive"], material="Pima cotton",
      desc="The perfect heavyweight everyday crewneck tee."),
    p("Noir Leather Jacket", "men", 21990, ["1490578474895-699cd4e2cf59"],
      sizes=["M", "L", "XL"], colors=["Black"], material="Lambskin leather",
      desc="A minimalist lambskin biker jacket that ages beautifully."),
    p("Ash Linen Blazer", "men", 11490, ["1503341504253-dff4815485f1", "1516257984-b1b4d707412e"],
      featured=True, colors=["Ash", "Sand"], material="Linen", desc="An unstructured linen blazer for warmer days."),
    p("Charcoal Tailored Suit", "men", 24990, ["1602810318383-e386cc2a3ccf"],
      compare=29990, sizes=["38", "40", "42", "44"], colors=["Charcoal", "Navy"],
      material="Super 120s wool", desc="A two-piece tailored suit cut for a modern silhouette."),

    # ---- Accessories ----
    p("Onyx Automatic Watch", "accessories", 16990, ["1523275335684-37898b6baf30"],
      compare=21990, featured=True, sizes=["One Size"], colors=["Black", "Steel"],
      material="Stainless steel", desc="An automatic timepiece with a sapphire crystal face."),
    p("Eclipse Leather Belt", "accessories", 2990, ["1553062407-98eeb64c6a62"],
      sizes=["S", "M", "L"], colors=["Black", "Brown"], material="Full-grain leather",
      desc="A full-grain leather belt with a brushed buckle."),
    p("Noir Cardholder Wallet", "accessories", 3490, ["1584917865442-de89df76afd3"],
      sizes=["One Size"], colors=["Black", "Tan"], material="Saffiano leather",
      desc="A slim saffiano leather cardholder."),
    p("Shadow Aviator Sunglasses", "accessories", 5990, ["1611652022419-a9419f74343d"],
      compare=7490, featured=True, sizes=["One Size"], colors=["Black", "Gunmetal"],
      material="Acetate", desc="Polarised aviators with a matte finish."),
    p("Carbon Leather Holdall", "accessories", 13990, ["1547949003-9792a18a2601"],
      sizes=["One Size"], colors=["Black"], material="Pebbled leather",
      desc="A weekend holdall in structured pebbled leather."),
    p("Midnight Wool Scarf", "accessories", 3290, ["1620625515032-6ed0c1790c75"],
      sizes=["One Size"], colors=["Charcoal", "Black", "Grey"], material="Lambswool",
      desc="A generously sized lambswool scarf."),
]


def seed_products(headers, slug_to_id) -> int:
    # Skip products that already exist (by name) so the script is re-runnable.
    existing = requests.get(f"{API_BASE}/products/?page_size=100").json()
    existing_names = {item["name"] for item in existing.get("items", [])}

    created = 0
    for prod in PRODUCTS:
        if prod["name"] in existing_names:
            print(f"  · {prod['name']} already exists, skipping")
            continue
        body = {k: v for k, v in prod.items() if k != "category"}
        body["category_id"] = slug_to_id[prod["category"]]
        r = requests.post(f"{API_BASE}/products/", json=body, headers=headers)
        if r.status_code == 201:
            created += 1
            tag = " ★featured" if prod["is_featured"] else ""
            sale = " (sale)" if prod["compare_at_price"] else ""
            print(f"  ✓ {prod['name']}{tag}{sale}")
        else:
            print(f"  ✗ {prod['name']} failed: {r.status_code} {r.text}")
    return created


# ---------------------------------------------------------------------------
# Verification (read paths)
# ---------------------------------------------------------------------------

def verify():
    print("\nVerifying via public GET endpoints:")
    cats = requests.get(f"{API_BASE}/categories/").json()
    print(f"  categories: {len(cats)} -> {[c['name'] for c in cats]}")

    featured = requests.get(f"{API_BASE}/products/featured?limit=8").json()
    print(f"  featured products: {len(featured)}")

    allp = requests.get(f"{API_BASE}/products/?page_size=100").json()
    print(f"  total active products: {allp['total']}")

    for slug in ("women", "men", "accessories"):
        r = requests.get(f"{API_BASE}/products/?category_slug={slug}&page_size=100").json()
        print(f"  category '{slug}': {r['total']} products")

    # Spot-check a single product detail by slug
    if allp["items"]:
        sample = allp["items"][0]["slug"]
        d = requests.get(f"{API_BASE}/products/slug/{sample}")
        print(f"  detail /products/slug/{sample}: HTTP {d.status_code}")


def main():
    print(f"Seeding demo data against {API_BASE}\n")
    print("Auth:")
    token = get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    print("\nCategories:")
    slug_to_id = seed_categories(headers)

    print("\nProducts:")
    n = seed_products(headers, slug_to_id)
    print(f"\n  created {n} new products")

    verify()
    print("\nDone. Admin login:", ADMIN_EMAIL, "/", ADMIN_PASSWORD)


if __name__ == "__main__":
    main()
