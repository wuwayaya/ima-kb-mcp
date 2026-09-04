# ima-kb-mcp

腾讯 ima 知识库的 MCP 服务器。基于官方 [IMA OpenAPI](https://ima.qq.com/agent-interface)，提供知识库搜索、浏览、读取原文能力，可用于 Cherry Studio、Claude Desktop、Cursor 等支持 MCP 的客户端。

## 功能

| 工具 | 作用 |
| --- | --- |
| `search_knowledge_bases` | 搜索 / 列出知识库 |
| `get_knowledge_base_detail` | 知识库详细信息 |
| `list_knowledge` | 浏览知识库内容（含文件夹） |
| `search_knowledge` | 在知识库内全文搜索（如"断路器 低电压脱扣"） |
| `get_media_info` | 获取文件原文访问地址（PDF 等） |
| `search_notes` | 搜索笔记 |
| `get_note_content` | 读取笔记正文 |
| `raw_call` | 直接调用任意 IMA OpenAPI 接口 |

## 认证

凭证按优先级读取：环境变量 → 本地配置文件。

- 环境变量：`IMA_OPENAPI_CLIENTID` / `IMA_OPENAPI_APIKEY`
- 配置文件：`~/.config/ima/client_id` / `~/.config/ima/api_key`

凭证获取：https://ima.qq.com/agent-interface

## 本地运行（stdio）

```bash
# 方式一：直接运行
uv run --with mcp --with httpx python ima_kb_mcp.py

# 方式二：作为包安装
uvx ima-kb-mcp
```

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "ima-kb": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp",
        "--with",
        "httpx",
        "/path/to/ima_kb_mcp.py"
      ],
      "env": {
        "IMA_OPENAPI_CLIENTID": "your_client_id",
        "IMA_OPENAPI_APIKEY": "your_api_key"
      }
    }
  }
}
```

## 部署到 ModelScope 魔搭 MCP 广场（托管）

1. 将本仓库推送到 GitHub。
2. 打开 [魔搭 MCP 广场](https://modelscope.cn/mcp) → **创建 MCP** → 选择 **从 GitHub 仓库快速创建**。
3. 托管类型选择 **可托管部署**。
4. 配置环境变量：
   - `IMA_OPENAPI_CLIENTID`：你的 Client ID
   - `IMA_OPENAPI_APIKEY`：你的 API Key
5. 部署完成后，复制生成的 **SSE 地址**。
6. 在 Cherry Studio 中：**设置 → MCP 服务器 → 添加**，类型选择 `SSE`，填入地址即可。

## 技术栈

- Python ≥ 3.10
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server 框架
- [httpx](https://www.python-httpx.org/) - HTTP 客户端