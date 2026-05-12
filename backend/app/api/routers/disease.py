from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.security import get_current_user
from app.services.disease_fallback_service import get_gemini_disease_advisory
from app.services.ml_client import get_supported_disease_crops, is_crop_supported_by_models, predict_crop_disease

router = APIRouter()


@router.post("/predict")
async def predict_disease(
    crop_name: str = Form(...),
    image: UploadFile | None = File(None),
    issue_text: str | None = Form(None),
    text_issue: str | None = Form(None),
    current_user: dict = Depends(get_current_user),
):
    issue_text = (issue_text or text_issue or "").strip() or None
    if image is None and not issue_text:
        return _prediction_error(
            status_code=400,
            message="Provide either a crop image or a text description of the issue.",
        )

    image_bytes = None
    content_type = None
    filename = "crop-image.jpg"
    if image is not None:
        content_type = (image.content_type or "").lower()
        if content_type not in settings.ml_proxy_allowed_content_types:
            return _prediction_error(
                status_code=415,
                message=f"Unsupported image content type '{content_type or 'unknown'}'.",
            )

        image_or_error = await _read_limited_upload(image)
        if isinstance(image_or_error, JSONResponse):
            return image_or_error
        image_bytes = image_or_error
        filename = image.filename or filename

    supported_crops = await get_supported_disease_crops()
    crop_supported = is_crop_supported_by_models(crop_name, supported_crops)

    if crop_supported is False or image_bytes is None:
        return await get_gemini_disease_advisory(
            crop_name=crop_name,
            issue_text=issue_text,
            image_bytes=image_bytes,
            content_type=content_type,
        )

    ml_result = await predict_crop_disease(
        crop_name=crop_name,
        image_bytes=image_bytes,
        filename=filename,
        content_type=content_type or "image/jpeg",
    )
    ml_result.setdefault("source", "ml")
    ml_result.setdefault("model_supported", crop_supported is not False)
    return ml_result


async def _read_limited_upload(image: UploadFile) -> bytes | JSONResponse:
    chunks = []
    total_size = 0

    while True:
        chunk = await image.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > settings.ML_PROXY_MAX_UPLOAD_BYTES:
            return _prediction_error(
                status_code=413,
                message=f"Image exceeds max upload size of {settings.ML_PROXY_MAX_UPLOAD_BYTES} bytes.",
            )
        chunks.append(chunk)

    if total_size == 0:
        return _prediction_error(status_code=400, message="Image file is empty.")

    return b"".join(chunks)


def _prediction_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "disease": None,
            "confidence": 0,
            "top3": [],
            "error": message,
        },
    )
