from docx import Document
from rank_bm25 import BM25Okapi
from config import collection, client
import hashlib
import jieba
import md2text
import os
import pdfplumber
import requests

#提取txt文本
def extract_text_from_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

#提取md文本
def extract_text_from_md(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return md2text.to_text(f.read(), keep_image_alt=False)

#提取pdf文本
def extract_text_from_pdf(file_path: str) -> str:
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

#提取docx文本
def extract_text_from_docx(file_path: str) -> str:
    doc = Document(file_path)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text

#提取文本
def extract_text(file_path: str, content_type: str) -> str:
    if content_type == "text/plain":
        return extract_text_from_txt(file_path)
    elif content_type == "text/markdown":
        return extract_text_from_md(file_path)
    elif content_type == "application/pdf":
        return extract_text_from_pdf(file_path)
    elif content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"不支持的文件类型:{content_type}")

#分割长文本
def split_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    把长文本分割为小块
    chunk_size：最大文本块
    overlap：相邻块间重叠字符，防止语义断链
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
        if start >= len(text):
            break
    return chunks

#调用embedding来转换文本为向量
def get_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        model="BAAI/bge-large-zh-v1.5",
        input=text
    )
    return response.data[0].embedding

#内容指纹：同一份内容只保留一份索引
def _doc_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

#按metadata字段清理旧分块，返回清理数量
def _delete_existing(key: str, value: str) -> int:
    try:
        existing = collection.get(where={key: value})
    except Exception as e:
        print(f"[索引] 查询旧分块失败（{key}={value}）：{e}")
        return 0
    old_ids = existing.get("ids") or []
    if old_ids:
        collection.delete(ids=old_ids)
    return len(old_ids)

#转化文本并存入向量库
def index_text(text: str, source: str) -> int:
    chunks = split_text(text)
    if not chunks:
        return 0

    doc_id = _doc_id(text)
    #id用内容指纹，不用文件名：重名文件不会互相覆盖，同一份内容换名字上传也不会重复入库
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    #生成向量
    embeddings = [get_embedding(chunk) for chunk in chunks]
    #元数据
    metadatas = [{"source":source, "chunk_index": i, "doc_id": doc_id} for i in range(len(chunks))]

    #先清旧数据再写：重传同名文档不会残留旧分块（文档变短时旧chunk原本会一直留在库里）
    removed_same_source = _delete_existing("source", source)
    removed_same_content = _delete_existing("doc_id", doc_id)
    if removed_same_source or removed_same_content:
        print(f"[索引] {source} 清理旧分块：同名 {removed_same_source} 个，同内容 {removed_same_content} 个")

    collection.add(
        ids = ids,
        embeddings = embeddings,
        documents = chunks,
        metadatas = metadatas
    )
    return len(chunks)

#bm25重排序
def bm25_search(query: str, top_k: int = 5) -> list[dict]:
    all_data = collection.get()
    documents = all_data["documents"]
    metadatas = all_data["metadatas"]

    if not documents:
        return []

    tokenized_corpus = [jieba.lcut(doc) for doc in documents]
    bm25 = BM25Okapi(tokenized_corpus)

    tokenized_query = jieba.lcut(query)
    scores = bm25.get_scores(tokenized_query)

    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    
    results = []
    for i in top_indices:
        results.append({
            "text": documents[i],
            "source": metadatas[i]["source"],
            "score": scores[i]
        })
    return results

#向量融合
def reciprocal_rank_fusion(results_list: list[list[dict]], k: int = 60) -> list[dict]:
    fused_scores = {}
    doc_map = {}

    for results in results_list:
        for rank, item in enumerate(results):
            doc_id = item["text"]
            doc_map[doc_id] = item
            if doc_id not in fused_scores:
                fused_scores[doc_id] = 0
            fused_scores[doc_id] += 1 / (k + rank + 1)

    sorted_docs = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[doc_id] for doc_id, _ in sorted_docs]

#rerank重排序
def rerank(query: str, candidates: list[dict], top_n: int = 3) -> list[dict]:
    if not candidates:
        return []
    
    # 提取候选文本
    documents = [item["text"] for item in candidates]
    
    # 构造 API 请求(OPENAI格式不支持rerank)
    url = "https://api.siliconflow.cn/v1/rerank"
    headers = {
        "Authorization": f"Bearer {os.environ.get('SILICONFLOW_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "BAAI/bge-reranker-v2-m3",  # 硅基流动上的 Rerank 模型
        "query": query,
        "documents": documents,
        "top_n": top_n,
        "return_documents": False  # 不返回原文档内容，只返回索引和分数，节省带宽
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # 解析结果并映射回原始候选列表
        final_results = []
        for item in data.get("results", []):
            original_candidate = candidates[item["index"]]
            original_candidate["rerank_score"] = item["relevance_score"]
            final_results.append(original_candidate)
            
        return final_results
        
    except Exception as e:
        print(f"Rerank API 调用失败: {e}")
        # 降级策略：如果 Rerank 失败，直接返回前 top_n 个候选（保证系统不崩溃）
        return candidates[:top_n]

#检索相关文本块
def search_similar(query: str, top_k: int = 3) -> list[dict]:
    query_embedding = get_embedding(query)
    vector_results = collection.query(
        query_embeddings = [query_embedding],
        n_results = 10
    )

    vector_items = []
    for i in range(len(vector_results["documents"][0])):
        vector_items.append({
            "text": vector_results["documents"][0][i],
            "source": vector_results["metadatas"][0][i]["source"],
        })

    # 2. BM25 检索（取 top 10）
    bm25_items = bm25_search(query, top_k=10)
    
    # 3. RRF 融合
    fused = reciprocal_rank_fusion([vector_items, bm25_items])
    
    # 4. 重排序，取 top_k
    final_results = rerank(query, fused, top_n=top_k)

    return final_results