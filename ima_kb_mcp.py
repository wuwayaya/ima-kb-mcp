"""MCP server for Tencent IMA Knowledge Base (腾讯 ima 知识库).

通过官方 IMA OpenAPI 提供知识库的搜索、浏览、读取、写入能力。
认证方式：环境变量 IMA_OPENAPI_CLIENTID / IMA_OPENAPI_APIKEY，
或写入 ~/.config/ima/client_id 与 ~/.config/ima/api_key。

可部署到 ModelScope MCP 广场（托管）或本地 stdio 运行。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_BASE_URL = "https://ima.qq.com"
SERVER_VERSION = "1.1.0"


class ImaClientError(Exception):
    """IMA API 调用错误，携带 code 与详细信息。"""

    def __init__(self, message: str, code: int = -100, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


def _read_config_file(name: str) -> str:
    """读取 ~/.config/ima/ 下的凭证文件。"""
    path = Path.home() / ".config" / "ima" / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _load_credentials() -> tuple[str, str]:
    """按优先级获取凭证：环境变量 -> 本地配置文件。"""
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
    """调用 IMA OpenAPI。api_path 必须是相对路径，如 openapi/wiki/v1/search_knowledge。"""
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
    """搜索或列出 IMA 知识库。query 为空时返回默认列表。
    - query: 搜索关键词，留空返回全部知识库
    - cursor: 分页游标，首页传空字符串
    - limit: 每页数量，1-20
    """
    return await _call_ima(
        "openapi/wiki/v1/search_knowledge_base",
        {"query": query, "cursor": cursor, "limit": limit},
    )


@mcp.tool()
async def get_knowledge_base_detail(ids: list[str]) -> dict[str, Any]:
    """按知识库 ID 获取知识库详细信息。
    - ids: 知识库 ID 列表（1-20 个）
    """
    return await _call_ima("openapi/wiki/v1/get_knowledge_base", {"ids": ids})


@mcp.tool()
async def list_knowledge(
    knowledge_base_id: str,
    folder_id: str = "",
    cursor: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """浏览 IMA 知识库内容，可传 folder_id 进入子文件夹。
    - knowledge_base_id: 知识库 ID（必需）
    - folder_id: 文件夹 ID，留空表示根目录
    - cursor: 分页游标，首页传空字符串
    - limit: 每页数量，1-50
    """
    body: dict[str, Any] = {
        "knowledge_base_id": knowledge_base_id,
        "cursor": cursor,
        "limit": limit,
    }
    folder_id = _opt_str({"folder_id": folder_id}, "folder_id")
    if folder_id:
        body["folder_id"] = folder_id
    return await _call_ima("openapi/wiki/v1/get_knowledge_list", body)


@mcp.tool()
async def search_knowledge(
    knowledge_base_id: str,
    query: str,
    cursor: str = "",
) -> dict[str, Any]:
    """在指定 IMA 知识库中全文搜索文件与文件夹。
    - knowledge_base_id: 知识库 ID（必需）
    - query: 搜索关键词（必需），如 "断路器 低电压脱扣"
    - cursor: 分页游标，首页传空字符串
    """
    if not query.strip():
        raise ImaClientError("query 不能为空。")
    return await _call_ima(
        "openapi/wiki/v1/search_knowledge",
        {"knowledge_base_id": knowledge_base_id, "query": query, "cursor": cursor},
    )


@mcp.tool()
async def get_media_info(media_id: str) -> dict[str, Any]:
    """获取知识库中某个媒体条目的原文访问地址或笔记扩展信息。
    - media_id: 媒体 ID（来自 list_knowledge / search_knowledge 返回的 media_id 字段）
    返回 url_info.url 可用于查看/下载原文（PDF、文档等）。
    """
    if not media_id.strip():
        raise ImaClientError("media_id 不能为空。")
    return await _call_ima("openapi/wiki/v1/get_media_info", {"media_id": media_id})


# ---------- 可写知识库 / 写入工具 ----------

@mcp.tool()
async def get_addable_knowledge_base_list(
    cursor: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """获取当前用户有权限添加内容的知识库列表。
    当用户要添加内容但未指定目标知识库时使用。
    - cursor: 分页游标，首页传空字符串
    - limit: 每页数量，1-50
    """
    return await _call_ima(
        "openapi/wiki/v1/get_addable_knowledge_base_list",
        {"cursor": cursor, "limit": limit},
    )


@mcp.tool()
async def check_repeated_names(
    knowledge_base_id: str,
    params: list[dict[str, Any]],
    folder_id: str = "",
) -> dict[str, Any]:
    """上传文件到知识库前，检查目标位置是否已有同名文件。
    仅用于文件类型（media_type 1/3/4/5/7/9/13/14/20/21），不用于网页、笔记。
    - knowledge_base_id: 知识库 ID（必需）
    - params: 待检查列表，每项 {"name": 文件名, "media_type": 类型}，如 [{"name":"a.pdf","media_type":1}]
    - folder_id: 文件夹 ID，省略则检查根目录
    """
    if not knowledge_base_id.strip():
        raise ImaClientError("knowledge_base_id 不能为空。")
    if not params:
        raise ImaClientError("params 不能为空，至少提供一项待检查文件。")
    body: dict[str, Any] = {
        "knowledge_base_id": knowledge_base_id,
        "params": params,
    }
    folder_id = _opt_str({"folder_id": folder_id}, "folder_id")
    if folder_id:
        body["folder_id"] = folder_id
    return await _call_ima("openapi/wiki/v1/check_repeated_names", body)


@mcp.tool()
async def create_media(
    knowledge_base_id: str,
    file_name: str,
    file_size: int,
    content_type: str,
    file_ext: str,
) -> dict[str, Any]:
    """上传文件到知识库的第一步：创建媒体并获取 COS 上传凭证。
    一般流程：create_media → 用 cos_credential 将文件上传到 COS → add_knowledge 入库。
    - knowledge_base_id: 知识库 ID（必需）
    - file_name: 文件名称（需含扩展名，最长 1024 字符）
    - file_size: 文件大小（字节）
    - content_type: MIME 类型，如 application/pdf
    - file_ext: 文件后缀（无点号），如 pdf、docx
    返回 media_id 与 cos_credential（含 secret_id/secret_key/token/bucket_name/region/cos_key）。
    """
    if not knowledge_base_id.strip():
        raise ImaClientError("knowledge_base_id 不能为空。")
    if not file_name.strip():
        raise ImaClientError("file_name 不能为空。")
    if file_size <= 0:
        raise ImaClientError("file_size 必须大于 0。")
    return await _call_ima(
        "openapi/wiki/v1/create_media",
        {
            "knowledge_base_id": knowledge_base_id,
            "file_name": file_name,
            "file_size": file_size,
            "content_type": content_type,
            "file_ext": file_ext,
        },
    )


@mcp.tool()
async def add_knowledge(
    knowledge_base_id: str,
    media_type: int,
    title: str,
    media_id: str = "",
    folder_id: str = "",
    note_info: dict[str, Any] | None = None,
    web_info: dict[str, Any] | None = None,
    file_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """添加知识到知识库。三种典型用法：
    1) 文件入库（文件上传后）：media_type=1/3/4...，media_id=create_media 的返回值，file_info 含 cos_key/file_size/file_name
    2) 笔记入库：media_type=11，note_info={"content_id": 笔记ID}
    3) 网页入库：media_type=2（普通网页）或 6（微信公众号），web_info={"content_id": URL}
    一般建议：网页/公众号用 import_urls（自动识别、可批量）更省事。
    - knowledge_base_id: 知识库 ID（必需）
    - media_type: 媒体类型，见 MediaType 枚举（1 PDF, 3 Word, 4 PPT, 5 Excel, 9 图片, 11 笔记, 13 TXT...）
    - title: 标题（文件入库时必须等于文件名）
    - media_id: create_media 返回的媒体 ID（文件入库时必填）
    - folder_id: 文件夹 ID，省略则添加到根目录
    - note_info: 笔记信息 {"content_id": note_id}，media_type=11 时传
    - web_info: 网页信息 {"content_id": url}，media_type=2/6 时传
    - file_info: 文件信息 {"cos_key":..., "file_size":..., "file_name":...}，文件入库时传
    """
    if not knowledge_base_id.strip():
        raise ImaClientError("knowledge_base_id 不能为空。")
    if not title.strip():
        raise ImaClientError("title 不能为空。")
    body: dict[str, Any] = {
        "knowledge_base_id": knowledge_base_id,
        "media_type": media_type,
        "title": title,
    }
    if media_id.strip():
        body["media_id"] = media_id
    folder_id = _opt_str({"folder_id": folder_id}, "folder_id")
    if folder_id:
        body["folder_id"] = folder_id
    if note_info:
        body["note_info"] = note_info
    if web_info:
        body["web_info"] = web_info
    if file_info:
        body["file_info"] = file_info
    return await _call_ima("openapi/wiki/v1/add_knowledge", body)


@mcp.tool()
async def import_urls(
    knowledge_base_id: str,
    urls: list[str],
    folder_id: str = "",
) -> dict[str, Any]:
    """批量导入网页 / 微信公众号文章到知识库。服务端自动识别 URL 类型。
    支持普通网页、微信公众号文章（mp.weixin.qq.com/s）；不支持视频类（B站/YouTube）。
    - knowledge_base_id: 知识库 ID（必需）
    - urls: URL 列表（1-10 个）
    - folder_id: 文件夹 ID，省略则添加到根目录
    返回 results 映射：{"<url>": {url, ret_code, media_id}}。
    """
    if not knowledge_base_id.strip():
        raise ImaClientError("knowledge_base_id 不能为空。")
    if not urls:
        raise ImaClientError("urls 不能为空，至少提供一个 URL。")
    body: dict[str, Any] = {
        "knowledge_base_id": knowledge_base_id,
        "urls": urls,
    }
    folder_id = _opt_str({"folder_id": folder_id}, "folder_id")
    if folder_id:
        body["folder_id"] = folder_id
    return await _call_ima("openapi/wiki/v1/import_urls", body)


# ---------- 笔记 ----------

@mcp.tool()
async def search_notes(
    query: str,
    search_type: str = "title",
    start: int = 0,
    end: int = 20,
) -> dict[str, Any]:
    """搜索 IMA 笔记，可按标题或正文搜索。
    - query: 搜索关键词（必需）
    - search_type: "title" 按标题搜索，"content" 按正文搜索
    - start: 起始偏移
    - end: 结束偏移（start 到 end 之间）
    """
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
    """获取 IMA 笔记正文内容。
    - note_id: 笔记 ID（必需）
    - target_content_format: 0 返回纯文本，推荐默认
    """
    if not note_id.strip():
        raise ImaClientError("note_id 不能为空。")
    return await _call_ima(
        "openapi/note/v1/get_doc_content",
        {"note_id": note_id, "target_content_format": target_content_format},
    )


# ---------- 兜底 ----------

@mcp.tool()
async def raw_call(api_path: str, body: dict[str, Any] = {}) -> dict[str, Any]:
    """直接调用 IMA OpenAPI 相对路径，用于未封装的新接口。
    - api_path: 接口相对路径，如 openapi/wiki/v1/get_user_space
    - body: JSON 请求体
    """
    return await _call_ima(api_path, body)


def main() -> None:
    """入口：stdio 模式运行（本地 Cherry / MCP Inspector）。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
