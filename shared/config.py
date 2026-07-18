import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")


class Settings:
    checkpoint_path: str = os.getenv(
        "CHECKPOINT_PATH", str(_REPO_ROOT / "checkpoints" / "best.pt")
    )
    metadata_path: str = os.getenv(
        "METADATA_PATH", str(_REPO_ROOT / "data" / "metadata" / "fish_info.json")
    )
    database_url: str = os.getenv("DATABASE_URL", "")
    env: str = os.getenv("ENV", "development")

    # Shared omyfish-ai service (bite-score forecasts live only there)
    bite_service_url: str = os.getenv("BITE_SERVICE_URL", "http://localhost:8000")

    # JWT — set JWT_SECRET in production; random default is safe for dev only
    jwt_secret: str = os.getenv("JWT_SECRET", secrets.token_hex(32))
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24h

    # Emails (comma-separated) that get the admin role on registration
    admin_emails: list = [
        e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
    ]

    # Stripe (test keys) — billing endpoints return 503 until these are set
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_price_monthly: str = os.getenv("STRIPE_PRICE_MONTHLY", "")  # 5 CAD/month
    stripe_price_yearly: str = os.getenv("STRIPE_PRICE_YEARLY", "")    # 29 CAD/year
    app_base_url: str = os.getenv("APP_BASE_URL", "http://localhost:8501")
    trial_days: int = int(os.getenv("TRIAL_DAYS", "7"))


settings = Settings()
