from fastapi import FastAPI
from dotenv import load_dotenv

# Load env early
load_dotenv()
from .config import settings, load_overrides
from .logging_config import configure_logging
from .routes.twilio_webhook import router as twilio_router
from .routes.health import router as health_router
from .routes.admin import router as admin_router


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="WotBot", version="0.1.0")
    # Load persisted config overrides
    load_overrides()

    # Routers
    app.include_router(health_router, prefix="/health", tags=["health"]) 
    app.include_router(twilio_router, prefix="/webhook/twilio", tags=["twilio"]) 
    app.include_router(admin_router, prefix="/admin", tags=["admin"]) 

    return app
