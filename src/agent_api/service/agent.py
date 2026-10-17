"""Agent service: persists conversation/audit rows and runs the LangGraph loop."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import async_session, Conversation, Message, AuditEvent
from ..graph import run_graph

logger = logging.getLogger("agent-api.service")


class AgentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _ensure_conversation(self, thread_id: str | None) -> uuid.UUID:
        if thread_id:
            conv_id = uuid.UUID(thread_id)
            result = await self.session.execute(
                select(Conversation).where(Conversation.id == conv_id)
            )
            conv = result.scalar_one_or_none()
            if conv is None:
                raise ValueError(f"conversation {thread_id} not found")
            return conv_id
        conv = Conversation()
        self.session.add(conv)
        await self.session.flush()
        return conv.id

    async def _append_message(
        self, conversation_id: uuid.UUID, role: str, content: str, tool_calls: list | None = None
    ) -> None:
        self.session.add(
            Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                tool_calls=tool_calls,
            )
        )

    async def _audit(self, event: str, actor: str | None, details: dict | None = None) -> None:
        self.session.add(AuditEvent(event=event, actor=actor, details=details))

    async def chat(
        self,
        message: str,
        thread_id: str | None,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        """Process one user turn: persist, run graph, persist, return."""
        actor = "user"
        conversation_id = await self._ensure_conversation(thread_id)

        # Persist user turn.
        await self._append_message(conversation_id, "user", message)
        await self._audit("chat.request", actor, {"conversation_id": str(conversation_id)})
        await self.session.commit()

        # Build message history for the graph (prior assistant turns).
        prior = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        history = [
            {"role": m.role, "content": m.content} for m in prior.scalars().all()
        ]

        try:
            result = await run_graph(history, str(conversation_id), model_override)
        except Exception as exc:
            await self._audit("chat.error", actor, {"error": str(exc)})
            await self.session.commit()
            raise

        # Persist assistant turn.
        await self._append_message(
            conversation_id,
            "assistant",
            result["response"],
            tool_calls=result["tool_calls"] or None,
        )
        await self._audit(
            "chat.response",
            actor,
            {
                "conversation_id": str(conversation_id),
                "tool_calls": result["tool_calls"],
                "steps": result["steps"],
            },
        )
        await self.session.commit()

        return {
            "thread_id": str(conversation_id),
            "response": result["response"],
            "tool_calls": result["tool_calls"],
            "steps": result["steps"],
        }

    async def get_history(self, thread_id: str) -> list[dict[str, Any]]:
        conv_id = uuid.UUID(thread_id)
        result = await self.session.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )
        if result.scalar_one_or_none() is None:
            return []
        messages = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.asc())
        )
        return [
            {
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages.scalars().all()
        ]

    async def health(self) -> dict[str, Any]:
        db_ok = False
        try:
            await self.session.execute(select(Conversation).limit(1))
            db_ok = True
        except Exception:  # noqa: BLE001
            logger.exception("database health check failed")
        return {
            "database": "ok" if db_ok else "fail",
            "inference_configured": bool(settings.openrouter_api_key),
        }


async def get_service() -> AgentService:
    async with async_session() as session:
        yield AgentService(session)
