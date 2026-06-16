from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from slugify import slugify
from app.db.session import get_db
from app.api.deps import get_current_active_user, require_permission
from app.core.config import settings
from app.core.permissions import Permission
from app.core.cache import cache, CacheKeys, CacheInvalidator
from app.models.category import Category
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse, CategoryWithChildren

router = APIRouter()


def category_to_dict(category: Category) -> dict:
    """Convert category model to dict for caching"""
    return {
        "id": str(category.id),
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
        "image_url": category.image_url,
        "parent_id": str(category.parent_id) if category.parent_id else None,
        "sort_order": category.sort_order,
        "is_active": category.is_active
    }


@router.get("/", response_model=List[CategoryResponse])
def list_categories(
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    # Only cache active categories list (most common request)
    if not include_inactive:
        cached = cache.get(CacheKeys.CATEGORIES_LIST)
        if cached:
            return cached

    query = db.query(Category)
    if not include_inactive:
        query = query.filter(Category.is_active == True)
    categories = query.order_by(Category.sort_order).all()

    result = [category_to_dict(cat) for cat in categories]

    # Cache active categories (they change rarely)
    if not include_inactive:
        cache.set(CacheKeys.CATEGORIES_LIST, result, ttl=settings.CACHE_CATEGORY_TTL)

    return result


@router.get("/tree", response_model=List[CategoryWithChildren])
def get_category_tree(db: Session = Depends(get_db)):
    """Get categories as a nested tree structure"""
    # Try cache first - tree is expensive to build
    cached = cache.get(CacheKeys.CATEGORIES_TREE)
    if cached:
        return cached

    # Get root categories (no parent)
    root_categories = db.query(Category).filter(
        Category.parent_id == None,
        Category.is_active == True
    ).order_by(Category.sort_order).all()

    def build_tree(category):
        return {
            "id": str(category.id),
            "name": category.name,
            "slug": category.slug,
            "description": category.description,
            "image_url": category.image_url,
            "parent_id": str(category.parent_id) if category.parent_id else None,
            "sort_order": category.sort_order,
            "is_active": category.is_active,
            "subcategories": [build_tree(sub) for sub in category.subcategories if sub.is_active]
        }

    result = [build_tree(cat) for cat in root_categories]

    # Cache tree for longer (categories rarely change)
    cache.set(CacheKeys.CATEGORIES_TREE, result, ttl=settings.CACHE_CATEGORY_TTL)

    return result


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: UUID, db: Session = Depends(get_db)):
    # Try cache first
    cache_key = CacheKeys.category_id(str(category_id))
    cached = cache.get(cache_key)
    if cached:
        return cached

    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    result = category_to_dict(category)
    cache.set(cache_key, result, ttl=settings.CACHE_CATEGORY_TTL)

    return result


@router.get("/slug/{slug}", response_model=CategoryResponse)
def get_category_by_slug(slug: str, db: Session = Depends(get_db)):
    # Try cache first
    cache_key = CacheKeys.category_slug(slug)
    cached = cache.get(cache_key)
    if cached:
        return cached

    category = db.query(Category).filter(Category.slug == slug).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    result = category_to_dict(category)
    cache.set(cache_key, result, ttl=settings.CACHE_CATEGORY_TTL)

    return result


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    category_data: CategoryCreate,
    current_user: User = Depends(require_permission(Permission.MANAGE_CATEGORIES)),
    db: Session = Depends(get_db)
):
    # Generate slug if not provided
    slug = category_data.slug or slugify(category_data.name)

    # Check slug uniqueness
    existing = db.query(Category).filter(Category.slug == slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category slug already exists")

    category = Category(
        name=category_data.name,
        slug=slug,
        description=category_data.description,
        image_url=category_data.image_url,
        parent_id=category_data.parent_id,
        sort_order=category_data.sort_order,
        is_active=category_data.is_active
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    # Invalidate category caches
    CacheInvalidator.invalidate_all_categories()

    return category_to_dict(category)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: UUID,
    category_data: CategoryUpdate,
    current_user: User = Depends(require_permission(Permission.MANAGE_CATEGORIES)),
    db: Session = Depends(get_db)
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    old_slug = category.slug
    update_data = category_data.model_dump(exclude_unset=True)

    # Generate new slug if name changes
    if "name" in update_data and "slug" not in update_data:
        update_data["slug"] = slugify(update_data["name"])

    # Check slug uniqueness
    if "slug" in update_data:
        existing = db.query(Category).filter(
            Category.slug == update_data["slug"],
            Category.id != category_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Category slug already exists")

    for field, value in update_data.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)

    # Invalidate category caches
    CacheInvalidator.invalidate_category(str(category_id), old_slug)
    if category.slug != old_slug:
        CacheInvalidator.invalidate_category(str(category_id), category.slug)

    return category_to_dict(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: UUID,
    current_user: User = Depends(require_permission(Permission.MANAGE_CATEGORIES)),
    db: Session = Depends(get_db)
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check for subcategories
    if category.subcategories:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete category with subcategories"
        )

    # Check for products
    if category.products:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete category with products"
        )

    slug = category.slug
    db.delete(category)
    db.commit()

    # Invalidate category caches
    CacheInvalidator.invalidate_category(str(category_id), slug)
