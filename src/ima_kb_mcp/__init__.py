"""MCP server for Tencent IMA Knowledge Base (腾讯 ima 知识库)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_BASE_URL = "https://ima.qq.com"
SERVER_VERSION = "1.0.0"


class ImaClientError(Exception):
    def __init__(self, message: str, code: int = -100, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


def _read_config_file(name: str) -> str:
    path = Path.home() / ".config" / "ima" / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _load_credentials() -> tuple[str, str]:
    client_id = (
        os.environ.get("IMA_CLIENT_ID")
        or os.environ.get("IMA_OPENAPI_CLIENTID")
        or _read_config_file("client_id")
    )
    api_key = (
        os.environ.get("IMA_API_KEY")
        or os.environ.get("IMA_OPENAPI_APIKEY")
        or _read_config_file("api_key")
    )
    if not client_id or not api_key:
        raise ImaClientError(
            "未找到 IMA 凭证。请设置 IMA_OPENAPI_CLIENTID / IMA_OPENAPI_APIKEY "
            "环境变量，或写入 ~/.config/ima/client_id 和 ~/.config/ima/api_key。"
        )
    return client_id, api_key


async def _call_ima(api_path: str, body: dict[str, Any]) -> dict[str, Any]:
    if not api_path or api_path.startswith("/") or "://" in api_path:
        raise ImaClientError("api_path 必须是相对路径，例如 openapi/wiki/v1/search_knowledge。")
    client_id, api_key = _load_credentials()
    base_url = os.environ.get("IMA_BASE_URL", DEFAULT_BASE_URL)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{base_url}/{api_path}",
            headers={
                "ima-openapi-clientid": client_id,
                "ima-openapi-apikey": api_key,
                "ima-openapi-ctx": f"mcp_version={SERVER_VERSION}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    try:
        parsed = resp.json()
    except json.JSONDecodeError:
        raise ImaClientError(f"IMA 返回了非 JSON 响应：HTTP {resp.status_code}", details=resp.text)
    if resp.status_code >= 400:
        raise ImaClientError(f"IMA 请求失败：HTTP {resp.status_code}", -100, parsed)
    if isinstance(parsed, dict) and isinstance(parsed.get("code"), int) and parsed["code"] != 0:
        raise ImaClientError(
            parsed.get("msg") or f"IMA API 返回错误码 {parsed['code']}",
            parsed["code"],
            parsed,
        )
    return parsed


def _opt_str(args: dict[str, Any], key: str) -> str | None:
    v = args.get(key)
    return v if isinstance(v, str) and v.strip() else None


def _opt_num(args: dict[str, Any], key: str, default: int) -> int:
    v = args.get(key)
    return v if isinstance(v, (int, float)) else default


mcp = FastMCP("ima-kb-mcp")


# ---------- 知识库 ----------

@mcp.tool()
async def search_knowledge_bases(
    query: str = "",
    cursor: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """搜索或列出 IMA 知识库。query 为空时返回默认列表。"""
    return await _call_ima(
        "openapi/wiki/v1/search_knowledge_base",
        {"query": query, "cursor": cursor, "limit": limit},
    )


@mcp.tool()
async def get_knowledge_base_detail(ids: list[str]) -> dict[str, Any]:
    """按知识库 ID 获取知识库详细信息。"""
    return await _call_ima("openapi/wiki/v1/get_knowledge_base", {"ids": ids})


@mcp.tool()
async def list_knowledge(
    knowledge_base_id: str,
    folder_id: str = "",
    cursor: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """浏览 IMA 知识库内容，可传 folder_id 进入子文件夹。"""
    body: dict[str, Any] = {
        "knowledge_base_id": knowledge_base_id,
        "cursor": cursor,
        "limit": limit,
    }
    f = _opt_str({"folder_id": folder_id}, "folder_id")
    if f:
        body["folder_id"] = f
    return await _call_ima("openapi/wiki/v1/get_knowledge_list", body)


@mcp.tool()
async def search_knowledge(
    knowledge_base_id: str,
    query: str,
    cursor: str = "",
) -> dict[str, Any]:
    """在指定 IMA 知识库中全文搜索文件与文件夹。"""
    if not query.strip():
        raise ImaClientError("query 不能为空。")
    return await _call_ima(
        "openapi/wiki/v1/search_knowledge",
        {"knowledge_base_id": knowledge_base_id, "query": query, "cursor": cursor},
    )


@mcp.tool()
async def get_media_info(media_id: str) -> dict[str, Any]:
    """获取知识库中某个媒体条目的原文访问地址或笔记扩展信息。"""
    if not media_id.strip():
        raise ImaClientError("media_id 不能为空。")
    return await _call_ima("openapi/wiki/v1/get_media_info", {"media_id": media_id})


# ---------- 笔记 ----------

@mcp.tool()
async def search_notes(
    query: str,
    search_type: str = "title",
    start: int = 0,
    end: int = 20,
) -> dict[str, Any]:
    """搜索 IMA 笔记，可按标题或正文搜索。"""
    if not query.strip():
        raise ImaClientError("query 不能为空。")
    st = 1 if search_type == "content" else 0
    return await _call_ima(
        "openapi/note/v1/search_note",
        {
            "search_type": st,
            "query_info": {"content": query} if st == 1 else {"title": query},
            "start": start,
            "end": end,
        },
    )


@mcp.tool()
async def get_note_content(note_id: str, target_content_format: int = 0) -> dict[str, Any]:
    """获取 IMA 笔记正文内容。"""
    if not note_id.strip():
        raise ImaClientError("note_id 不能为空。")
    return await _call_ima(
        "openapi/note/v1/get_doc_content",
        {"note_id": note_id, "target_content_format": target_content_format},
    )


# ---------- 兜底 ----------

@mcp.tool()
async def raw_call(api_path: str, body: dict[str, Any] = {}) -> dict[str, Any]:
    """直接调用 IMA OpenAPI 相对路径，用于未封装的新接口。"""
    return await _call_ima(api_path, body)


def main() -> None:
    """入口：stdio 模式运行。"""
    mcp.run(transport="stdio")