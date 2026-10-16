from fastapi import APIRouter
from app.api.v1 import auth, users, products, categories, cart, wishlist, reviews, orders, payments, compare, addresses, early_access, logistics, meta
from app.api.v1.admin import dashboard, inventory, meta_ads, setup

api_router = APIRouter()

# Public/Customer routes
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(categories.router, prefix="/categories", tags=["Categories"])
api_router.include_router(cart.router, prefix="/cart", tags=["Cart"])
api_router.include_router(wishlist.router, prefix="/wishlist", tags=["Wishlist"])
api_router.include_router(compare.router, prefix="/compare", tags=["Compare"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
api_router.include_router(orders.router, prefix="/orders", tags=["Orders"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])
api_router.include_router(addresses.router, prefix="/addresses", tags=["Addresses"])
api_router.include_router(early_access.router, prefix="/early-access", tags=["Early Access"])
api_router.include_router(logistics.router, prefix="/logistics", tags=["Logistics"])
api_router.include_router(meta.router, prefix="/meta", tags=["Meta Ads"])

# Admin routes
api_router.include_router(setup.router, prefix="/admin", tags=["Admin - Setup & Auth"])
api_router.include_router(dashboard.router, prefix="/admin/dashboard", tags=["Admin - Dashboard"])
api_router.include_router(inventory.router, prefix="/admin/inventory", tags=["Admin - Inventory"])
api_router.include_router(meta_ads.router, prefix="/admin/meta", tags=["Admin - Meta Ads"])
