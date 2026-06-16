from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from slugify import slugify
import cloudinary
import cloudinary.uploader
from app.db.session import get_db
from app.api.deps import get_current_active_user, require_permission
from app.core.config import settings
from app.core.permissions import Permission
from app.core.cache import cache, CacheKeys, CacheInvalidator, hash_params
from app.models.product import Product
from app.models.category import Category
from app.models.review import Review
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse, ProductListResponse

router = APIRouter()

# Configure Cloudinary
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)


def get_product_with_stats(product: Product, db: Session) -> dict:
    """Add review stats to product"""
    stats = db.query(
        func.avg(Review.rating).label("avg_rating"),
        func.count(Review.id).label("count")
    ).filter(
        Review.product_id == product.id,
        Review.is_approved == True
    ).first()

    return {
        **product.__dict__,
        "category": product.category,  # Explicitly include the relationship
        "average_rating": float(stats.avg_rating) if stats.avg_rating else None,
        "review_count": stats.count or 0,
        "is_on_sale": product.is_on_sale,
        "discount_percentage": product.discount_percentage,
        "in_stock": product.in_stock
    }


@router.get("/", response_model=ProductListResponse)
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: Optional[UUID] = None,
    category_slug: Optional[str] = None,
    search: Optional[str] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    is_featured: Optional[bool] = None,
    sort_by: str = Query("created_at", pattern="^(created_at|price|name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    # Generate cache key from params
    cache_key = CacheKeys.products_list(hash_params(
        page=page,
        page_size=page_size,
        category_id=str(category_id) if category_id else None,
        category_slug=category_slug,
        search=search,
        min_price=str(min_price) if min_price else None,
        max_price=str(max_price) if max_price else None,
        is_featured=is_featured,
        sort_by=sort_by,
        sort_order=sort_order
    ))

    # Try cache first (skip for search queries - they're too varied)
    if not search:
        cached = cache.get(cache_key)
        if cached:
            return ProductListResponse(**cached)

    query = db.query(Product).filter(Product.is_active == True)

    # Category filter
    if category_id:
        query = query.filter(Product.category_id == category_id)
    elif category_slug:
        category = db.query(Category).filter(Category.slug == category_slug).first()
        if category:
            query = query.filter(Product.category_id == category.id)

    # Search
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Product.name.ilike(search_term),
                Product.description.ilike(search_term),
                Product.sku.ilike(search_term)
            )
        )

    # Price filter
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    # Featured filter
    if is_featured is not None:
        query = query.filter(Product.is_featured == is_featured)

    # Count total
    total = query.count()

    # Sort
    sort_column = getattr(Product, sort_by)
    if sort_order == "desc":
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    # Paginate
    offset = (page - 1) * page_size
    products = query.options(joinedload(Product.category)).offset(offset).limit(page_size).all()

    # Add stats
    items = [get_product_with_stats(p, db) for p in products]

    result = ProductListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )

    # Cache the result (skip for search queries)
    if not search:
        cache.set(cache_key, result.model_dump(), ttl=settings.CACHE_PRODUCT_TTL)

    return result


@router.get("/featured", response_model=List[ProductResponse])
def get_featured_products(limit: int = 8, db: Session = Depends(get_db)):
    # Try cache first
    cache_key = CacheKeys.products_featured(limit)
    cached = cache.get(cache_key)
    if cached:
        return cached

    products = db.query(Product).filter(
        Product.is_active == True,
        Product.is_featured == True
    ).options(joinedload(Product.category)).limit(limit).all()

    result = [get_product_with_stats(p, db) for p in products]

    # Cache for longer since featured products don't change often
    cache.set(cache_key, result, ttl=settings.CACHE_PRODUCT_TTL)

    return result


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: UUID, db: Session = Depends(get_db)):
    # Try cache first
    cache_key = CacheKeys.product_id(str(product_id))
    cached = cache.get(cache_key)
    if cached:
        return cached

    product = db.query(Product).options(
        joinedload(Product.category)
    ).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    result = get_product_with_stats(product, db)
    cache.set(cache_key, result, ttl=settings.CACHE_PRODUCT_TTL)

    return result


@router.get("/slug/{slug}", response_model=ProductResponse)
def get_product_by_slug(slug: str, db: Session = Depends(get_db)):
    # Try cache first
    cache_key = CacheKeys.product_slug(slug)
    cached = cache.get(cache_key)
    if cached:
        return cached

    product = db.query(Product).options(
        joinedload(Product.category)
    ).filter(Product.slug == slug).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    result = get_product_with_stats(product, db)
    cache.set(cache_key, result, ttl=settings.CACHE_PRODUCT_TTL)

    return result


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(require_permission(Permission.MANAGE_PRODUCTS)),
    db: Session = Depends(get_db)
):
    # Generate slug
    slug = product_data.slug or slugify(product_data.name)

    # Ensure unique slug
    base_slug = slug
    counter = 1
    while db.query(Product).filter(Product.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    product = Product(
        name=product_data.name,
        slug=slug,
        description=product_data.description,
        short_description=product_data.short_description,
        price=product_data.price,
        compare_at_price=product_data.compare_at_price,
        sku=product_data.sku,
        stock_quantity=product_data.stock_quantity,
        low_stock_threshold=product_data.low_stock_threshold,
        category_id=product_data.category_id,
        vendor_id=product_data.vendor_id,
        images=product_data.images,
        attributes=product_data.attributes,
        is_active=product_data.is_active,
        is_featured=product_data.is_featured,
        meta_title=product_data.meta_title,
        meta_description=product_data.meta_description
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    # Invalidate product list caches
    CacheInvalidator.invalidate_all_products()

    return get_product_with_stats(product, db)


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: UUID,
    product_data: ProductUpdate,
    current_user: User = Depends(require_permission(Permission.MANAGE_PRODUCTS)),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    old_slug = product.slug
    update_data = product_data.model_dump(exclude_unset=True)

    # Update slug if name changes
    if "name" in update_data and "slug" not in update_data:
        slug = slugify(update_data["name"])
        base_slug = slug
        counter = 1
        while db.query(Product).filter(Product.slug == slug, Product.id != product_id).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
        update_data["slug"] = slug

    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    # Invalidate caches for this product
    CacheInvalidator.invalidate_product(str(product_id), old_slug)
    if product.slug != old_slug:
        CacheInvalidator.invalidate_product(str(product_id), product.slug)

    return get_product_with_stats(product, db)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: UUID,
    current_user: User = Depends(require_permission(Permission.MANAGE_PRODUCTS)),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    slug = product.slug

    # Soft delete
    product.is_active = False
    db.commit()

    # Invalidate caches
    CacheInvalidator.invalidate_product(str(product_id), slug)


@router.post("/{product_id}/images", response_model=ProductResponse)
async def upload_product_image(
    product_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission(Permission.MANAGE_PRODUCTS)),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Upload to Cloudinary
    try:
        result = cloudinary.uploader.upload(
            file.file,
            folder="products",
            resource_type="image",
            transformation=[
                {"width": 1200, "height": 1200, "crop": "limit"},
                {"quality": "auto:best"},
                {"fetch_format": "auto"}
            ]
        )
        image_url = result["secure_url"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    # Add to product images
    images = product.images or []
    images.append(image_url)
    product.images = images

    db.commit()
    db.refresh(product)

    # Invalidate cache
    CacheInvalidator.invalidate_product(str(product_id), product.slug)

    return get_product_with_stats(product, db)
