from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import HealthResponse

app = FastAPI(title="Shadow Street API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_cache_age_minutes: int | None = None


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", cache_age_minutes=_cache_age_minutes)
