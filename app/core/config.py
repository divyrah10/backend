from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "NOT JUST DARK"
    DEBUG: bool = True
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    API_V1_PREFIX: str = "/api/v1"

    # JWT / Auth
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1 hour
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30 days

    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/lorem_ipsum_store"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_RECYCLE: int = 3600

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_DEFAULT_TTL: int = 300  # 5 minutes
    CACHE_PRODUCT_TTL: int = 600  # 10 minutes
    CACHE_CATEGORY_TTL: int = 3600  # 1 hour (categories change rarely)

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "hello@notjustdark.com"
    SMTP_USE_TLS: bool = True

    # Admin Setup
    ADMIN_SETUP_KEY: str = "notjustdark-setup-2024"  # Change this in production!

    # Firebase
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CREDENTIALS_PATH: str = ""  # Path to service account JSON

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Shiprocket (use a dedicated API user from Settings > API in the Shiprocket panel)
    SHIPROCKET_BASE_URL: str = "https://apiv2.shiprocket.in/v1/external"
    SHIPROCKET_EMAIL: str = ""
    SHIPROCKET_PASSWORD: str = ""
    SHIPROCKET_PICKUP_LOCATION: str = "Primary"  # Pickup address nickname in Shiprocket
    SHIPROCKET_WEBHOOK_TOKEN: str = ""  # Sent by Shiprocket as the x-api-key header
    # Assigning an AWB and booking a pickup charge the Shiprocket wallet, so both are opt-in.
    SHIPROCKET_AUTO_ASSIGN_AWB: bool = False
    SHIPROCKET_AUTO_PICKUP: bool = False
    # Products have no weight or size yet, so every parcel uses these.
    SHIPROCKET_ITEM_WEIGHT_KG: float = 0.3
    SHIPROCKET_PACKAGE_LENGTH_CM: float = 30
    SHIPROCKET_PACKAGE_BREADTH_CM: float = 25
    SHIPROCKET_PACKAGE_HEIGHT_CM: float = 4

    @property
    def shiprocket_enabled(self) -> bool:
        return bool(self.SHIPROCKET_EMAIL and self.SHIPROCKET_PASSWORD)

    # Public storefront origin, used for product links in the Meta catalog feed.
    STOREFRONT_URL: str = "http://localhost:3000"

    # Meta (Facebook/Instagram) ads
    META_GRAPH_URL: str = "https://graph.facebook.com"
    META_GRAPH_VERSION: str = "v26.0"
    META_PIXEL_ID: str = ""  # Events Manager > Data sources > your dataset (pixel) id
    META_CAPI_ACCESS_TOKEN: str = ""  # Conversions API token generated in that dataset's settings
    META_TEST_EVENT_CODE: str = ""  # Set while testing so events land in Events Manager > Test events
    META_AD_ACCOUNT_ID: str = ""  # With or without the "act_" prefix
    META_ADS_ACCESS_TOKEN: str = ""  # System-user token with ads_read, for the admin performance report
    META_CATALOG_FEED_TOKEN: str = ""  # When set, the catalog feed requires ?token=<this>
    META_CATALOG_CURRENCY: str = "INR"

    @property
    def meta_capi_enabled(self) -> bool:
        return bool(self.META_PIXEL_ID and self.META_CAPI_ACCESS_TOKEN)

    @property
    def meta_insights_enabled(self) -> bool:
        return bool(self.META_AD_ACCOUNT_ID and self.META_ADS_ACCESS_TOKEN)

    # CORS
    CORS_ORIGINS: str = '["http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
