import streamlit as st
import requests
import json
import urllib.parse

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="全能 AI Agent", page_icon="🤖", layout="wide")
st.title("🤖 搜索小助手")
st.markdown('可以管理、搜索、写文档')

# ================= 侧边栏 =================
with st.sidebar:
    st.header("📁 本地知识库管理")
    uploaded_file = st.file_uploader("上传文档 (TXT/PDF/DOCX/MD)", type=["txt", "pdf", "docx", "md"])
    if uploaded_file and st.button("上传并建立索引"):
        with st.spinner("正在处理文档并建立索引..."):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            res = requests.post(f"{API_BASE}/upload", files=files)
            if res.status_code == 200:
                st.success("成功建立索引！")

# 初始化聊天历史
if "messages" not in st.session_state:
    st.session_state.messages = []

# ================= 1. 渲染历史消息 =================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        # 如果历史消息里有思考过程，用折叠框（expander）装起来
        if msg.get("statuses"):
            with st.expander("🛠️ 查看 Agent 思考与执行过程"):
                for s in msg["statuses"]:
                    st.write(f"⚙️ {s}")
                    
        st.markdown(msg["content"])
        
        if msg.get("files"):
            for file in msg["files"]:
                safe_file = urllib.parse.quote(file)
                st.markdown(f"📥 **[点击下载文件: {file}]({API_BASE}/download/{safe_file})**")

# ================= 2. 接收用户输入 =================
if prompt := st.chat_input("请输入你的指令..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

# ================= 3. 处理流式请求 =================
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_user_msg = st.session_state.messages[-1]["content"]
    
    with st.chat_message("assistant"):
        # 两个占位符：一个给状态框，一个给打字机文本
        status_placeholder = st.empty()
        text_placeholder = st.empty()
        
        final_text = ""
        generated_files = []
        statuses = []
        history_for_api = []

        for msg in st.session_state.messages[:-1][-10:]:
            history_for_api.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        try:
            # 发送流式请求
            response = requests.post(
                f"{API_BASE}/agent",
                json={"query": last_user_msg, "history": history_for_api},
                stream=True,
                timeout=120
            )
            
            # 在界面初始化状态框
            with status_placeholder.container():
                status_ui = st.status("Agent 正在深度思考...", expanded=True)
            
            # 逐行解析 SSE
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        data = json.loads(line_str[6:])
                        
                        if data["type"] == "status":
                            statuses.append(data["content"])
                            # 往状态框里实时打印：正在调用 xxx 工具
                            status_ui.write(f"⚙️ {data['content']}")
                            
                        elif data["type"] == "text":
                            # 打字机效果
                            final_text += data["content"]
                            text_placeholder.markdown(final_text + "▌")
                            
                        elif data["type"] == "files":
                            generated_files = data["content"]
            
            # ================= 4. 流式结束，收尾工作 =================
            if statuses:
                # 将状态框收起
                status_ui.update(label="✅ 思考与执行完毕（点击展开）", state="complete", expanded=False)
            else:
                status_placeholder.empty()
                
            # 把打字机的光标去掉
            text_placeholder.markdown(final_text)
            
            if msg.get("files"):
                for file in msg["files"]:
                    safe_file = urllib.parse.quote(file)
                    st.markdown(f"📥 **[点击下载文件: {file}]({API_BASE}/download/{safe_file})**")
            
            # 存入历史记录
            st.session_state.messages.append({
                "role": "assistant", 
                "content": final_text,
                "files": generated_files,
                "statuses": statuses
            })
            
        except Exception as e:
            status_placeholder.empty()
            text_placeholder.error(f"请求出错：{str(e)}")