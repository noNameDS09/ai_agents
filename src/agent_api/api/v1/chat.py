"""v1 chat endpoints: POST /v1/chat, GET /v1/threads/{thread_id}."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel

from ...security import AuthDependency, validate_message
from ...service.agent import AgentService, get_service

router = APIRouter()


class ChatRequest(BaseModel):
    thread_id: str | None = None
    message: str
    model: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    response: str
    tool_calls: list[dict[str, Any]]
    steps: int


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    tags=["chat"],
)
async def chat(
    request: Request,
    body: ChatRequest,
    _auth: AuthDependency,
    service: AgentService = Depends(get_service),
) -> ChatResponse:
    message = validate_message(body.message)

    if body.thread_id is not None:
        try:
            uuid.UUID(body.thread_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid thread_id")

    if body.model is not None and not body.model.endswith(":free"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only free OpenRouter models may be requested",
        )

    result = await service.chat(message, body.thread_id, body.model)
    return ChatResponse(**result)


@router.get("/threads/{thread_id}", tags=["chat"])
async def get_thread(
    request: Request,
    thread_id: str,
    _auth: AuthDependency,
    service: AgentService = Depends(get_service),
) -> dict[str, Any]:
    try:
        uuid.UUID(thread_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid thread_id")

    history = await service.get_history(thread_id)
    if not history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
    return {"thread_id": thread_id, "messages": history}


from fastapi import HTTPException  # noqa: E402
