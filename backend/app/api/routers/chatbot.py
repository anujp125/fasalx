from fastapi import APIRouter, Depends, File, UploadFile

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.chatbot import ChatbotRequest, ChatbotResponse, ChatbotVoiceResponse
from app.services.chatbot_service import generate_chatbot_reply_with_audio, generate_chatbot_voice_reply

router = APIRouter()


@router.post("/message", response_model=ChatbotResponse)
async def send_chatbot_message(
    request: ChatbotRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Sends a user message to the Gemini-powered FasalX chatbot.
    """
    reply, audio = await generate_chatbot_reply_with_audio(request.message)
    return ChatbotResponse(reply=reply, model=settings.GEMINI_MODEL, audio=audio)


@router.post("/voice", response_model=ChatbotVoiceResponse)
async def send_chatbot_voice_message(
    audio: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Sends an audio message to the Gemini-powered FasalX chatbot.
    The transcript is domain-checked before an answer is generated.
    """
    content_type = (audio.content_type or "").lower()
    if content_type not in settings.chatbot_audio_allowed_content_types:
        raise AppError(
            status_code=415,
            code="CHATBOT_AUDIO_TYPE_UNSUPPORTED",
            message=f"Unsupported audio content type '{content_type or 'unknown'}'.",
        )

    audio_bytes = await _read_limited_audio(audio)
    transcript, reply, response_audio = await generate_chatbot_voice_reply(audio_bytes, content_type)
    return ChatbotVoiceResponse(
        transcript=transcript,
        reply=reply,
        model=settings.GEMINI_MODEL,
        audio=response_audio,
    )


async def _read_limited_audio(audio: UploadFile) -> bytes:
    chunks = []
    total_size = 0

    while True:
        chunk = await audio.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > settings.CHATBOT_AUDIO_MAX_UPLOAD_BYTES:
            raise AppError(
                status_code=413,
                code="CHATBOT_AUDIO_TOO_LARGE",
                message=f"Audio exceeds max upload size of {settings.CHATBOT_AUDIO_MAX_UPLOAD_BYTES} bytes.",
            )
        chunks.append(chunk)

    if total_size == 0:
        raise AppError(
            status_code=400,
            code="CHATBOT_AUDIO_EMPTY",
            message="Audio file is empty.",
        )

    return b"".join(chunks)
