#工具json格式简介
tools = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "当用户需要查询最新资讯、实时信息、或者本地知识库中没有的内容时，使用此工具进行联网搜索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_word",
            "description": "当用户要求生成报告、编写文档或大纲时，使用此工具将其保存为 Word 文档。",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "文档的标题"},
                    "content": {"type": "string", "description": "文档的详细正文内容，支持多段文本"}
                },
                "required": ["topic", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "local_knowledge_search",
            "description": "当用户询问公司内部文档、个人上传的资料、或特定知识库内容时，使用此工具检索本地文档。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词"}
                },
                "required": ["query"]
            }
        }
    },
        {
        "type": "function",
        "function": {
            "name": "generate_excel",
            "description": "当用户要求生成表格、Excel、提取数据对比时使用。你必须先把数据整理成标准的 CSV 格式字符串再传入。",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "表格的名称，例如：AI模型对比表"},
                    "table_data": {
                        "type": "string", 
                        "description": "严格使用 CSV 格式的数据。第一行是表头，列之间用英文逗号分隔，行之间用换行符 \\n 分隔。千万不要输出 Markdown 格式的表格！"
                    }
                },
                "required": ["topic", "table_data"]
            }
        }
    }
]