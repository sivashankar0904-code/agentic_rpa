from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", operation_id="getHealth", summary="Health check")
def health() -> dict:
    return {"status": "ok"}
