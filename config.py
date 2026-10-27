import os
import chromadb
from openai import OpenAI
from pydantic import BaseModel
from tavily import TavilyClient

#上传文件保存目录
UPLOAD_DIR = "uploads"

#创建chroma客户端，保存数据，获取或创建向量集合
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="documents")

#搜索请求体
class SearchRequest(BaseModel):
    query: str
    top_k: int = 3

#问答请求体
class AskRequest(BaseModel):
    query: str
    top_k: int = 3

#Agent请求体
class AgentRequest(BaseModel):
    query: str
    history: list[dict] = []

#模型api(rerank，embedding)       #默认硅基流动，模型免费，完全替换需要进入rag.py进行检查替换
client = OpenAI(
    api_key=os.environ.get("SILICONFLOW_API_KEY"),
    base_url="https://api.siliconflow.cn/v1"
)

#chat模型api(Deepseek-v4.1-flash)       #默认硅基流动，替换需要进入main.py中agent流进行检查替换
chat_client = OpenAI(
    api_key=os.environ.get("SILICONFLOW_API_KEY"),      #填写对应模型api key
    base_url="https://api.siliconflow.cn/v1"       #根据使用需求自行更换对应url
)

#联网工具api
tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

#文档输出路径
OUTPUT_DIR = "outputs"