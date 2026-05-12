from pydantic import BaseModel, Field
from typing import Optional


class ChatbotRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User message to send to the FasalX chatbot",
    )


class ChatbotAudioResponse(BaseModel):
    data: str = Field(..., description="Base64-encoded audio bytes")
    mime_type: str = Field(..., description="Audio MIME type returned by Gemini")
    encoding: str = Field(default="base64")


class ChatbotResponse(BaseModel):
    reply: str
    model: str
    audio: Optional[ChatbotAudioResponse] = None


class ChatbotVoiceResponse(ChatbotResponse):
    transcript: str
