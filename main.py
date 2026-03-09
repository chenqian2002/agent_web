from multiprocessing.connection import answer_challenge
import os
import json
import httpx
from openai import OpenAI
from pydantic import BaseModel
from typing import List
import requests
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import PromptTemplate
try:
    from langchain.chains import RetrievalQA
except ImportError:
    from langchain_classic.chains import RetrievalQA
from dotenv import load_dotenv
load_dotenv()

from rag_langchain import get_embeddings
from langchain_core.documents import Document
from rag_langchain import ask as query_knowledge_base

from blogger_routes import router as blogger_router



# 创建 FastAPI 应用
app= FastAPI(title="My API")
app.include_router(blogger_router)
#挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")
templates=Jinja2Templates(directory="templates")

SERPER_API_KEY = os.getenv("SERPER_API_KEY")



#初始化客户端
client=OpenAI(
    
   api_key=os.getenv("Qwen_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",

    )
#工具定义
# 修改 main.py 中的 tool_schema
tool_schema = [
    {
        "type": "function",
        "function": {
            "name": "search_google",
            "description": "当用户询问天气、股票、或是最新的互联网新闻时使用此工具。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "搜索关键词"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_knowledge_base",
            "description": "当用户询问关于【本公司产品、上传的文件内容、具体业务细节】时使用此工具。",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string", "description": "用户的问题"}},
                "required": ["question"]
            }
        }
    }
]
def search_google(query :str)->str:
    """调用 Serper API 进行 Google 搜索"""
    url="https://google.serper.dev/search"
    payload=json.dumps({
        "q": query,
        "gl": "cn",
        "hl": "zh-cn"
})
    headers={
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type':'application/json'

  }

     # 发送请求
    response=requests.post(url,headers=headers,data=payload,timeout=10)
    if response.status_code==200:
        data=response.json()
        organic=data.get("organic",[])[:10]

        if not organic:
            return "未找到相关信息"

        #拼接结果
        results=[]
        for item in organic:
            title=item.get("title","")
            snippet = item.get("snippet", "无摘要")
            results.append(f"标题：{title}\n内容：{snippet}\n")
            #换行和连接
        return "\n".join(results)
    else:
        return f"请求失败：{response.text}"
    #定义路由（页面访问入口）
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """首页"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/search", response_class=HTMLResponse)
async def search(request: Request,query:str = Form(...)):
    """处理搜索请求"""
    result=search_google(query)
    return templates.TemplateResponse("index.html", 
    {"request": request, "query": query,"result": result})
@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """关于页面"""
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/chat", response_class=HTMLResponse)
async def chat(request: Request):
    """聊天页面"""
    return templates.TemplateResponse("chat.html", {"request": request})
#文件问答
@app.get("/docsqa", response_class=HTMLResponse)
async def docsqa_page(request: Request):
    """文件问答页面"""
    return templates.TemplateResponse("docsqa.html", {"request": request})


# 存储聊天请求
class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []


class DocsQARequest(BaseModel):
    question: str


# ---------- LangChain RAG 知識庫問答 API ----------
@app.post("/api/docsqa")
async def docsqa_ask(data: DocsQARequest):
    """對知識庫提問，回傳答案與參考來源"""
    from rag_langchain import ask
    result = ask(data.question)
    return result


@app.post("/api/docsqa/upload")
#File(...)必填参数（required）。file: UploadFile = File(None)可选上传
#接收表单问题question: str = Form(...)
async def docsqa_upload(file: UploadFile= File(...)
, question: str = Form(...)):
    """
    上傳單一文件並對該文件進行 RAG 問答（不寫入永久資料庫）
    """
    ## 1. 把上傳的檔案讀成文字（先只支援純文字 .txt）
    #异步读取await file.read()
    content_bytes=await file.read()
    try:
        text=content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # decode()二进制数据 解码还原为 人类可读的文本（字符串）
        text = content_bytes.decode("utf-8", errors="ignore")
    # 2. 包裝成 LangChain 的 Document
    docs=[
        Document(
            page_content=text,
#用来标记信息的来源。sourcefile.filename: 这是从上传的文件对象中获取的文件名（例如 report.pdf）
            metadata={"source": file.filename}
            )

    ]
    # 3. 切片
    splitter=RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=80,
        length_function=len,
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
        )
#文本分割器（Text Splitter）
    splits = splitter.split_documents(docs)
## 4. 臨時向量庫（只在記憶體裡）
     # 4. 臨時向量庫（只在記憶體裡）
    #embeddings = OpenAIEmbeddings(
    #    api_key=os.getenv("Qwen_API_KEY"),
    #    model="text-embedding-v3"
    #)
    embeddings =get_embeddings()

    vectorstore = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
    )
 #最相似的 4 段文本（"k": 4）search_kwargs搜索意思相近的4条
    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

     # 5. Prompt + LLM（回答用 Qwen）
    prompt = PromptTemplate.from_template(
        "你是一個文件問答助手，請僅根據以下內容回答問題。"
        "若內容中沒有相關資訊，請說「文件中沒有說明」。\n\n"
        "文件內容：\n{context}\n\n"
        "問題：{question}\n\n"
        "請用繁體中文回答："
    )
    
    llm=ChatOpenAI(
        openai_api_key=os.getenv("QWEN_API_KEY"),
        openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3-max",
        temperature=0.2,
    )

    qa=RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )
    result = qa.invoke({"query": question})
    answer=result.get("result", "")
    sources=[]
    for doc in result.get("sources", []):
        sources.append({
            "content": doc.page_content[:300] + 
            ("..." if len(doc.page_content) > 300 else ""),
            "source": doc.metadata.get("source", file.filename),
        })
    return {"answer": answer, "sources": sources}

@app.post("/api/docsqa/build")
async def docsqa_build():
    """重建知識庫索引（從 docs/ 讀取 .txt 並寫入 Chroma）"""
    from rag_langchain import build_index
    result = build_index()
    return result

@app.post("/api/chat")
async def chat_api(data: ChatRequest):
    """聊天 API - AI 自己决定是否搜索"""
    
    # 1. 定义系统提示词
    system_prompt = (
        "你是一个专业的网站智能客服。"
        "1. 如果用户问公司内部业务或文档内容，优先使用 lookup_knowledge_base 工具。"
        "2. 如果用户问实时新闻或外部信息，使用 search_google 工具。"
        "3. 如果是打招呼，直接礼貌回复。"
        "请用亲切、专业的语气回答。"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(data.history)
    messages.append({"role": "user", "content": data.message})

    try:
        # --- 第一轮：让 AI 思考 ---
        response = client.chat.completions.create(
            model="qwen3-max",
            messages=messages,
            tools=tool_schema
        )
        msg = response.choices[0].message
        
        # --- 判断 AI 是否想调用工具 ---
        if msg.tool_calls:
            print("🤖 AI 决定调用工具...")
            tool_call = msg.tool_calls[0]
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            
            tool_result = "" # 初始化结果变量

            # 🛠️ 分支 A: 查知识库 (参数是 question)
            if func_name == "lookup_knowledge_base":
                # 获取参数，防止报错用 .get
                question_text = args.get("question") 
                print(f"📝 查找知识库: {question_text}")
                
                # 调用 RAG 函数
                rag_response = query_knowledge_base(question_text)
                
                # rag_response 是字典，需要转成字符串给 AI 看
                tool_result = f"知识库检索结果：{rag_response.get('answer', '未找到相关信息')}"

            # 🔍 分支 B: 搜 Google (参数是 query)
            elif func_name == "search_google":
                query_text = args.get("query")
                print(f"🔎 搜索 Google: {query_text}")
                
                # 调用搜索函数
                tool_result = search_google(query_text)

            # --- 第二轮：把工具结果喂回给 AI 进行总结 ---
            messages.append(msg) # 添加 AI 的工具调用请求
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(tool_result) # 确保内容是字符串
            })

            # 再次请求 AI 生成最终回复
            final_response = client.chat.completions.create(
                model="qwen3-max",
                messages=messages
            )
            return {"reply": final_response.choices[0].message.content}

        # --- 如果不需要工具，直接返回 ---
        else:
            return {"reply": msg.content}

    except Exception as e:
        print(f"❌ 后端报错详情: {str(e)}") # 这一点很重要，能在终端看到具体错误
        return {"reply": f"抱歉，客服系统出错了: {str(e)}"}
print(app.routes)
if __name__ == "__main__":
    import uvicorn
    print("🚀 启动服务器: http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
   