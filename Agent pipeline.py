import os
import json
import requests
from typing import TypedDict, Annotated
from dotenv import load_dotenv

# LangGraph 核心导入
from langgraph.graph import StateGraph, END

# LLM
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()
# ============================================================
# 🧩 第一步：定义 State（共享黑板）
#
# TypedDict 就是一个"带字段名的字典"
# 每个字段就是黑板上的一格，所有 Agent 都能读写
# ============================================================
class ArticleState(TypedDict):
    topic: str           # 用户输入的主题（只读，不会变）
    news_text: str       # 搜索Agent 写入：搜集到的原始新闻
    article: str         # 写作Agent 写入：生成的文章
    score: int           # 审核Agent 写入：质量评分 0-10
    feedback: str        # 审核Agent 写入：修改意见
    revision_count: int  # 重写次数计数器（防止无限循环）

# ============================================================
# 🔧 初始化工具
# ============================================================

llm = ChatOpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model="qwen-plus",
    temperature=0.7,
)
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
# ============================================================
# 🤖 第二步：定义每个 Agent（节点函数）
#
# 【规则】每个节点函数：
#   - 接收参数：state（当前黑板内容）
#   - 返回值：一个字典，只包含"你这个节点更新的字段"
#   LangGraph 会自动把返回的字典合并回 state
# ============================================================

# ── Agent 1：搜索Agent ──────────────────────────────────────
def search_node(state: ArticleState) -> dict:
    """
    职责：根据主题搜索最新资讯
    读取 state 字段：topic
    写入 state 字段：news_text
    """
    print(f"\n🔍 [搜索Agent] 开始搜索：{state['topic']}")
    topic = state["topic"]
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={"q": topic, "gl": "cn", "hl": "zh-cn", "num": 8},
            timeout=15,
        )
        organic=resp.json().get("organic",'')[:6]
        news_text ="\n".json([
            f"【{i+1}】标题：{item.get('title', '')}\n摘要：{item.get('snippet', '')}"
            for i, item in enumerate(organic)
        ])
    


