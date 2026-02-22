from pydantic import BaseModel


class ChatStartRequest(BaseModel):
    tenant_id: str


class ChatStartResponse(BaseModel):
    conversation_id: str
    first_message: str


class ChatRequest(BaseModel):
    tenant_id: str
    conversation_id: str
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    status: str
