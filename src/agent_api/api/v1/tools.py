"""v1 tools endpoint: GET /v1/tools."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ...security import AuthDependency
from ...tools import TOOL_REGISTRY

router = APIRouter()


class ToolEntry(BaseModel):
    name: str
    description: str
    parameters: dict


class ToolsResponse(BaseModel):
    tools: list[ToolEntry]


@router.get("/tools", response_model=ToolsResponse, tags=["tools"])
async def list_tools(
    request: Request,
    _auth: AuthDependency,
) -> ToolsResponse:
    entries: list[ToolEntry] = []
    for name, (args_schema, _func) in TOOL_REGISTRY.items():
        schema = args_schema.model_json_schema()
        first_field = next(iter(args_schema.model_fields)) if args_schema.model_fields else None
        description = (
            args_schema.model_fields[first_field].description if first_field else ""
        )
        entries.append(ToolEntry(name=name, description=description, parameters=schema))
    return ToolsResponse(tools=entries)
