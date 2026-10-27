from urllib.parse import unquote
from config import UPLOAD_DIR, SearchRequest, AskRequest, AgentRequest, OUTPUT_DIR, chat_client
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from tools import available_functions
from rag import extract_text, index_text, search_similar
from tools_json import tools
import os
import shutil
import json
import re


app = FastAPI()


#确保文件目录存在
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

#健康检测
@app.get("/health")
def health():
    return {"status": "OK"}

def generate_answer(query: str, context_chunks: list[dict]) -> str:
    context_text = "\n\n---\n\n".join([item["text"] for item in context_chunks])
    prompt = f"""
    你是一个严谨的知识库助手，请根据以下参考信息回答用户的问题。
    如果参考信息中没有相关内容，请如实回答“根据提供的文档，我无法回答这个问题”，不要编造。

    【参考信息】
    {context_text}

    【用户问题】
    {query}

    【回答】
    """

    response = chat_client.chat.completions.create(
        model="deepseek-ai/DeepSeek-V4.1-Flash",
        messages=[
            {"role": "system", "content": "你是一个基于文档回答问题的AI助手。"},
            {"role": "user", "content": prompt}
        ],
        temperature= 0.3,
        max_tokens=1024
    )

    return response.choices[0].message.content

#文本上传
@app.post("/upload")
def upload_file(file: UploadFile = File(...)):
    #检查文件类型
    allowed_type = [
        "text/plain",
        "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]

    if file.content_type not in allowed_type:
        print(file.content_type, file.filename)
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型:{file.content_type}"
        )

    #保存原始文件
    filename = os.path.basename(file.filename or "upload")
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    #提取文本
    try:
        text = extract_text(file_path, file.content_type)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"文本提取失败：{str(e)}"
        )

    #保存提取的文本：放进独立子目录并保留原扩展名，避免同 basename 互相覆盖
    text_dir = os.path.join(UPLOAD_DIR, "_extracted")
    os.makedirs(text_dir, exist_ok=True)
    txt_path = os.path.join(text_dir, filename + ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    #建立索引
    chunk_count = index_text(text, source=filename)

    return{
        "filename": file.filename,
        "saved_to": file_path,
        "text_save_to": txt_path,
        "size": os.path.getsize(file_path),
        "text_length": len(text),
        "chunks_indexed": chunk_count,
        "preview": text[:200]
    }


#本地检索
@app.post("/search")
def search(request: SearchRequest):
    results = search_similar(request.query, request.top_k)
    return {"query":request.query, "results":results}

@app.post("/ask")
def ask(request: AskRequest):
    chunks = search_similar(request.query, request.top_k)

    if not chunks:
        raise HTTPException(status_code=404, detail=f"知识库为空，请先上传并索引文档")

    try:
        answer = generate_answer(request.query, chunks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成回答失败：{str(e)}")

    return {
        "query": request.query,
        "answer": answer,
        "sources": [
            {
                "source": c["source"], "text_preview": c["text"][:100]
            }
            for c in chunks
        ]
    }

#agent流
@app.post("/agent")
async def agent_chat_stream(request: AgentRequest):
    messages = [{
            "role": "system",
                "content": """
                # 角色设定
                你是一个高效、专业的全能 AI 自动化助手。你不仅能回答问题，还能通过调用工具来联网搜索、检索本地知识库以及生成 Word 文档。

                # 核心工具与使用场景
                你有以下四个工具可以使用：
                1. `local_knowledge_search`：当用户询问内部资料、上传的文档内容、或特定业务知识时使用。
                2. `web_search`：当用户需要查询最新资讯、实时信息，或本地知识库没有的内容时使用。
                3. `generate_word`：当用户明确要求“生成文档”、“写报告”、“整理成 Word”时使用。
                4. `generate_excel`：生成 Excel 数据表格。


                # 工作流规范（极其重要）
                1. **先检索，后生成**：如果用户要求生成一份基于某主题的文档，你必须**先调用搜索工具**（本地或联网）获取内容。拿到搜索结果后，再进行下一步。
                2. **多步执行**：你可以多次调用工具。例如：先调用 `web_search` 搜资料，拿到结果后，再调用 `generate_word` 写文档。
                3. **参数提取**：调用 `generate_word` 时，`topic` 请提取简短的文件名（不要带标点符号和空格），`content` 必须是你整理好的、结构清晰的段落文本。
                4. **结合上下文**：请仔细阅读对话历史。如果用户说“把刚才搜到的内容写下来”，请直接从历史记录中提取信息，不要再重复搜索。

                # 行为约束
                - **拒绝幻觉**：如果搜索结果不足以回答问题，请直接告知用户，绝对不要凭空捏造。
                - **精简回答**：工具执行完毕后，直接用自然语言总结结果。不要输出任何类似 `<|DSML|>` 的特殊标记。
                - **结束标志**：当你认为任务已经完全结束（不需要再调用工具时），请直接用自然语言输出最终结果。
            """
        }
    ]

    for msg in request.history[-10:]: 
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": request.query})
    
    async def event_generator():
        max_iterations = 5
        iteration = 0
        generated_files = []
        leak_count = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # 1. 先进行一次非流式调用，判断是否需要调用工具
            try:
                response = chat_client.chat.completions.create(
                    model="deepseek-ai/DeepSeek-V4.1-Flash",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )
            except Exception as e:
                yield f"data: {json.dumps({'type': 'text', 'content': f'API请求失败: {e}'})}\n\n"
                break

            response_message = response.choices[0].message

            # 防御：模型把工具调用的模板 token 当正文吐出来（服务端序列化问题）
            # 做「识别 + 要求重试」
            leaked = (
                not response_message.tool_calls
                and response_message.content
                and "DSML" in response_message.content
            )

            if leaked:
                leak_count += 1
                print(f"[工具标记泄漏] 第 {leak_count} 次，原始内容片段: {response_message.content[:200]!r}")

                if leak_count >= 2:
                    yield f"data: {json.dumps({'type': 'text', 'content': '模型输出格式异常（工具调用标记泄漏），请重试或换一种问法。'})}\n\n"
                    if generated_files:
                        yield f"data: {json.dumps({'type': 'files', 'content': generated_files})}\n\n"
                    break

                # 丢弃这一轮的异常文本，要求模型改用标准 tool_calls 重新发起
                messages.append({"role": "assistant", "content": "（上一条输出格式异常，已忽略）"})
                messages.append({
                    "role": "user",
                    "content": "请通过标准的工具调用接口（tool_calls）发起调用，不要在正文中输出任何工具标记文本。"
                })
                continue

            # 2. 如果不需要调工具，输出最终文本了。重新开启流式请求
            if not response_message.tool_calls:
                messages.append({"role": "assistant", "content": "好的，我整理一下最终的回答。"})
                
                try:
                    stream_response = chat_client.chat.completions.create(
                        model="deepseek-ai/DeepSeek-V4.1-Flash",
                        messages=messages,
                        stream=True
                    )
                    
                    for chunk in stream_response:
                        if chunk.choices and chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'text', 'content': f'\n\n**流式生成失败:** {str(e)}'})}\n\n"
                
                # 推送生成的文件信息
                if generated_files:
                    yield f"data: {json.dumps({'type': 'files', 'content': generated_files})}\n\n"
                break
                
            # 3. 如果需要调工具，执行工具，并推送状态给前端
            messages.append(response_message)
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                
                # 向前端推送：“正在调用某工具”
                status_msg = f"正在执行: {function_name} ..."
                yield f"data: {json.dumps({'type': 'status', 'content': status_msg})}\n\n"
                
                # 执行函数
                func = available_functions.get(function_name)
                tool_result = func(**arguments) if func else "工具未找到"
                
                # 收集生成的文件
                if "已保存为：" in tool_result:
                    raw_path = tool_result.split("已保存为：")[-1].strip()
                    file_name = os.path.basename(raw_path)
                    generated_files.append(file_name)
                

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": str(tool_result)
                })

    # 返回流式响应
    return StreamingResponse(event_generator(), media_type="text/event-stream")

#下载
@app.get("/download/{filename}")
async def download_file(filename: str):
    # 1. 对前端传过来的 URL 编码进行解码
    filename = unquote(filename)
    
    # 2. 防止路径穿越，只取最后的文件名（去掉可能带上的 outputs\）
    filename = os.path.basename(filename)
    
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename)
    print(f"[下载报错] 找不到文件: {file_path}")
    raise HTTPException(status_code=404, detail="文件不存在")