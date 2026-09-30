"""Upload local storefront media to Cloudinary and switch product records.

Run from the backend directory:
    venv/bin/python scripts/migrate_media_to_cloudinary.py --apply

Uploads are idempotent because each asset uses a stable public ID. Product
database rows are only updated after every required image and the hero video
have uploaded successfully.
"""

from argparse import ArgumentParser
from pathlib import Path
import sys

import cloudinary
import cloudinary.api
import cloudinary.uploader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.cache import CacheInvalidator
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.product import Product


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
PRODUCT_MEDIA_DIR = FRONTEND_DIR / "public" / "products"
HERO_VIDEO_PATH = FRONTEND_DIR / "public" / "videos" / "njd-campaign-film.mp4"
ROOT_FOLDER = "not-just-dark"


def optimized_url(secure_url: str) -> str:
    return secure_url.replace("/upload/", "/upload/f_auto,q_auto/")


def configure_cloudinary() -> None:
    if not all((settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET)):
        raise RuntimeError("Cloudinary credentials are incomplete in backend/.env")
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    cloudinary.api.ping()


def collect_local_products(db: SessionLocal) -> list[tuple[Product, list[Path]]]:
    collected = []
    for product in db.query(Product).filter(Product.is_active.is_(True)).order_by(Product.slug):
        local_paths = []
        for image_url in product.images or []:
            if not image_url.startswith("/products/"):
                continue
            path = FRONTEND_DIR / "public" / image_url.lstrip("/")
            if not path.is_file():
                raise FileNotFoundError(f"Missing product image: {path}")
            local_paths.append(path)
        if local_paths:
            collected.append((product, local_paths))
    return collected


def upload_image(product: Product, path: Path) -> str:
    public_id = f"{ROOT_FOLDER}/products/{product.slug}/{path.stem}"
    result = cloudinary.uploader.upload(
        str(path),
        resource_type="image",
        public_id=public_id,
        overwrite=True,
        invalidate=True,
        unique_filename=False,
        use_filename=False,
        tags=["not-just-dark", "product", product.slug],
        context={"alt": product.name, "caption": product.name},
    )
    return optimized_url(result["secure_url"])


def upload_hero_video() -> str:
    if not HERO_VIDEO_PATH.is_file():
        raise FileNotFoundError(f"Missing hero video: {HERO_VIDEO_PATH}")
    result = cloudinary.uploader.upload_large(
        str(HERO_VIDEO_PATH),
        resource_type="video",
        public_id=f"{ROOT_FOLDER}/videos/njd-campaign-film",
        overwrite=True,
        invalidate=True,
        unique_filename=False,
        use_filename=False,
        chunk_size=6_000_000,
        tags=["not-just-dark", "hero-video"],
        context={"alt": "NOT JUST DARK campaign film", "caption": "NOT JUST DARK campaign film"},
    )
    return optimized_url(result["secure_url"])


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Upload and update the product database")
    args = parser.parse_args()

    configure_cloudinary()
    with SessionLocal() as db:
        products = collect_local_products(db)
        image_count = sum(len(paths) for _, paths in products)
        print(f"Validated Cloudinary and {image_count} local images across {len(products)} products.", flush=True)
        print(f"Hero video: {HERO_VIDEO_PATH.name} ({HERO_VIDEO_PATH.stat().st_size / 1024 / 1024:.1f} MB)", flush=True)
        if not args.apply:
            print("Dry run complete. Pass --apply to upload and update PostgreSQL.")
            return

        uploaded_products: dict[str, list[str]] = {}
        uploaded = 0
        for product, paths in products:
            urls = []
            for path in paths:
                urls.append(upload_image(product, path))
                uploaded += 1
                print(f"[{uploaded}/{image_count}] {product.slug}/{path.name}", flush=True)
            uploaded_products[str(product.id)] = urls

        print("Uploading hero video in chunks...", flush=True)
        hero_video_url = upload_hero_video()
        print("Hero video uploaded.", flush=True)

        for product, _ in products:
            product.images = uploaded_products[str(product.id)]
        db.commit()

    CacheInvalidator.invalidate_all_products()
    print(f"HERO_VIDEO_URL={hero_video_url}", flush=True)
    print("Cloudinary upload and product database update complete.", flush=True)


if __name__ == "__main__":
    main()
