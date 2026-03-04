#============================================================
# LangChain RAG 知識庫問答模組
# 功能：從 docs/ 載入文件 → 切片 → 向量化 → 存 Chroma → 問答
# ============================================================
import os
import json  # ✅ [新增] 修复 NameError
import httpx # ✅ [确认] 必须保留用于 http_client
from pathlib import Path

# ❌ [删除] 原本错误的导入: from langchain_community.chat_models import ChatTongyi
# ✅ [修改] 从 langchain_openai 导入 ChatOpenAI
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from dotenv import load_dotenv
load_dotenv()
# LangChain 文件載入與切片
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
# 向量化與模型（Embedding 用 OpenAI，相容性最好；LLM 用 Qwen）
# from langchain_openai import OpenAIEmbeddings # 上面已经导入了，这里注释掉避免重复
# 向量庫
from langchain_community.vectorstores import Chroma
# 分數計算 / 提示模板
from langchain_core.prompts import PromptTemplate


#rag回答
try:
    # 優先從新版 langchain 匯入
    from langchain.chains import RetrievalQA
except ImportError:
    # 若環境中使用的是 classic 版本，則從這裡匯入
    from langchain_classic.chains import RetrievalQA

#--------路线设定
#获取当前脚本文件所在的目录的绝对路径，resolve()绝对路径,parent父目录
BASE_DIR=Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
CHROMA_DIR = BASE_DIR / "chroma_db"
os.makedirs(DOCS_DIR, exist_ok=True)
os.makedirs(CHROMA_DIR, exist_ok=True)
#环境变量
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_BASE_URL ="https://dashscope.aliyuncs.com/compatible-mode/v1"
_qa_chain = None

#把文字变成向量
#获取向量模型

def get_embeddings():
    """取得 Qwen 相容的 Embedding 模型（用 OpenAI 介面）"""
    return OpenAIEmbeddings(
        openai_api_key=QWEN_API_KEY,
        openai_api_base=QWEN_BASE_URL,   
          # 👇 這是解決本次報錯的絕對關鍵！強制傳送純文字，不轉成數字！
        check_embedding_ctx_length=False, 
        # 👇 這是防止 10060 網路超時的關鍵！
        http_client=httpx.Client(trust_env=False, timeout=60.0) ,
        model="text-embedding-v1",
    )

def get_llm():
    """取得 Qwen 對話模型"""
    # ✅ [修改] ChatOpenAI 使用 api_key 而不是 dashscope_api_key
    return ChatOpenAI(
        api_key=QWEN_API_KEY,      # 参数名修改
        base_url=QWEN_BASE_URL,    # 增加 base_url
        model="qwen-plus",          # 建议改为 qwen-plus 或 qwen-max
        temperature=0.4,
    )

def build_index():
    """
    步驟 1：從 docs/ 載入所有 .txt
    步驟 2：用 RecursiveCharacterTextSplitter 切片
    步驟 3：用 Qwen Embedding 向量化並存入 Chroma
    """
    if not DOCS_DIR.exists() or not any(DOCS_DIR.iterdir()):
        return {"ok": False, "message": "docs 資料夾不存在或為空"}

    loader=DirectoryLoader(
        str(DOCS_DIR),
        glob="**/*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8","autodetect_encoding": True},
    )

    documents = loader.load()
    if not documents:
        return {"ok": False, "message": "未載入到任何 .txt 檔案"}

    splitter=RecursiveCharacterTextSplitter(
        # 设置每个文本块的目标大小为 500 个字符
        chunk_size=500,
         # 设置块之间的重叠长度为 80 个字符，
         # 有助于保持上下文连贯性，防止语义在切分处丢失
        chunk_overlap=80,
         # 指定计算文本长度的函数，这里使用 Python 内置的 len (计算字符数)
        length_function=len,
         # 定义分割符列表，优先级从左到右：
    # 1. "\n\n": 优先按段落分割
    # 2. "\n": 其次按行分割
    # 3. "。！？；": 如果还是太长，按中文句子结束标点分割
    # 4. " ": 最后按空格分割
    # 5. "": 强制逐字分割
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
    )

    splits = splitter.split_documents(documents)

    embeddings = get_embeddings()

    # ⚠️ 注意：如果之前生成过不同维度的数据库，这里会报错。建议先手动删除 chroma_db 文件夹
    vectorstore = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
        collection_name="docs_qa",
    )

    # Chroma 新版会自动持久化，保留此行兼容旧版
    try:
        vectorstore.persist()
    except:
        pass

    global _qa_chain
    _qa_chain = None

    return {"ok": True, "message": f"已建立索引，共 {len(splits)} 個文本塊"}


def _get_qa_chain():
    """取得或建立 RetrievalQA 鏈（依賴 Chroma 已存在）"""
    global _qa_chain

    if _qa_chain is not None:
        return _qa_chain

    if not (CHROMA_DIR.exists() and list(CHROMA_DIR.iterdir())):
        return None

    embeddings=get_embeddings()

    vectorstore=Chroma(
        persist_directory=str(CHROMA_DIR),
        collection_name="docs_qa",
        embedding_function=embeddings ,
    )

    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

    prompt = PromptTemplate.from_template(
        "你是一個基於知識庫的問答助手，請僅根據以下「參考內容」回答問題。"
        "若參考內容中沒有相關資訊，請明確說「根據現有資料無法回答」。\n\n"
        "參考內容：\n{context}\n\n"
        "問題：{question}\n\n"
        "請用繁體中文簡潔回答："
    )

    _qa_chain = RetrievalQA.from_chain_type(
        llm=get_llm(),
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )

    return _qa_chain


def ask(question: str):
    """
    對知識庫提問。若尚未建索引則回傳友善提示。
    """
    qa=_get_qa_chain()

    if qa is None:
        return {
            "answer": "尚未建立知識庫索引，請先在頁面中點擊「重建索引」並確認 docs 資料夾內有 .txt 文件。",
            "sources": [],
        }

    try:
        result = qa.invoke({"query": question})
        # 增加安全检查
        if not isinstance(result, dict):
            # 如果返回不是字典，直接打印原始内容
            return {"answer": f"查詢時發生錯誤：API 返回非 JSON 內容：{result}", "sources": []}

        answer = result.get("result", "")

        sources=[]
        # 修正 key：RetriverQA 返回的通常是 source_documents
        source_docs = result.get("source_documents", [])
        if not source_docs:
             source_docs = result.get("sources", []) # 兼容其他可能的返回

        for doc in source_docs:
            sources.append({
                "content":doc.page_content[:300] + 
                ("..." if len(doc.page_content) > 300 else ""),
                "source": doc.metadata.get("source", ""),
            })

        return {"answer": answer, "sources": sources}

    except json.JSONDecodeError as e:
        # 捕获 JSON 解析错误
        return {"answer": f"查詢時發生錯誤：JSON解析錯誤 {str(e)}", "sources": []}
    except Exception as e:
        print(e)
        return {"answer": f"查詢時發生錯誤：{str(e)}", "sources": []}