# blogger_routes.py
import os, json, asyncio
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from openai import OpenAI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from blogger_db import init_db, save_article, get_articles
from blogger_db import init_db, save_article, get_articles, get_article_by_id
router = APIRouter()   # ← 关键：不是 app，是 router！
#Jinja2Templates 是 FastAPI 封装的 Jinja2 模板引擎对象。directory='templates' 指定了 HTML 模板文件夹的位置。
templates = Jinja2Templates(directory='templates')

# 复用 main.py 里的 Qwen 客户端配置
client = OpenAI(
    api_key=os.getenv('Qwen_API_KEY'),
    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
)
async def generate_article(topic: str = 'AI 最新新闻') -> dict:
    """
    完整的文章生成流程
    返回: {'title': ..., 'content': ..., 'topic': ...}
    """
    # ── Step 1: 搜索最新信息 ──────────────────────────
    # 复用 main.py 里的 search_google，但这里直接内联调用 Serper API
    import requests
    serper_key = os.getenv('SERPER_API_KEY')
    search_resp = requests.post(
        'https://google.serper.dev/search',
        headers={
            'X-API-KEY': serper_key,
            'Content-Type': 'application/json'},
            #问题'q'，语言'zh-cn'，数量'num'，地区'gl': 'cn'
            json={'q': topic, 'gl': 'cn', 'hl': 'zh-cn', 'num': 10},
            timeout=15        # 超时时间为 15 秒
    )
#.json() 是把 响应内容（通常是 JSON 格式的字符串）解析成 Python 字典或列表。
#['organic'] 就是 取字典里 key 为 "organic" 的值，也就是搜索结果。
    organic = search_resp.json().get('organic', [])[:8]
      # 把搜索结果拼成可读文本
    new_text=''.join([
        f"标题：{item.get('title','')}摘要：{item.get('snippet','')}"
        for item in organic
    ])
# ── Step 2: 让 AI 提炼 3 条最重要新闻 ──────────
# 先做一个【摘要】，减少最终写作时的 token 消耗
    summary_resp=client.chat.completions.create(
     model='qwen3-max',
        messages=[
            {'role': 'system', 'content': '你是资深科技编辑，擅长提炼重要新闻。'},
            {'role': 'user', 'content':
                f'从以下新闻中提炼3条最重要的，每条给出：【标题】【一句话核心内容】{new_text}'}
        ]
    )
    top3_news=summary_resp.choices[0].message.content
    # ── Step 3: 写完整文章 ───────────────────────────
    article_resp = client.chat.completions.create(
        model='qwen3-max',
        messages=[
            {'role': 'system', 'content':
                '你是幽默风趣的科技博主，擅写公众号爆款文章。'
                '风格要求：接地气、有梗、适当用emoji，读者是爱好AI的年轻人。'},
            {'role': 'user', 'content':
                f'基于以下3条新闻写一篇800字公众号文章，'
                f'要有吸引人的标题、开头、每条新闻的点评、结尾金句。{top3_news}'}
        ]
    )
    full_article = article_resp.choices[0].message.content
     # 提取标题（文章第一行通常就是标题）
#full_article 是一个 字符串，比如整篇文章的内容。
# # .strip() 会 去掉字符串开头和结尾的空白字符（空格、换行符 \n、制表符 \t 等）
    lines = full_article.strip().split('\n')
#if lines else topic → 如果 lines 不是空列表，就取第一行，否则用 topic 作为标题。lines[0] → 
# 文章的第一行，一般是标题。.strip('#') → 去掉标题开头的 #（Markdown 风格的标题标记）。
# .strip() → 再去掉标题开头或结尾的空格。
    title =lines[0].strip('#').strip() if lines else topic
    return {'title': title, 'content': full_article, 'topic': topic}

#------------------------------------------------------------------
# 创建调度器（asyncio 版本，与 FastAPI 的异步环境兼容）
scheduler = AsyncIOScheduler(timezone='Asia/Shanghai')
# 每天 08:00 自动运行scheduler.scheduled_job(...)@ 符号这是 Python 的 装饰器（decorator）。
#scheduler 一般是 APScheduler（Python 的高级定时任务库）创建的调度器对象。
@scheduler.scheduled_job('cron', hour=8, minute=0)
async def daily_job():
    print('⏰ 定时任务触发：开始生成今日文章...')
    result = await generate_article('今日 中国最新新闻')
    await save_article(
    result['title'],
    result['content'],
    result['topic'],
    'draft'
    )
    print(f'✅ 文章已保存：{result["title"]}')
@router.on_event('startup')
async def startup():
    await init_db()

    if not scheduler.running:
        scheduler.start()

    print('🚀 Auto-Blogger 已启动，定时任务已注册')
@router.get('/blogger', response_class=HTMLResponse)
async def blogger_page(request: Request):
    """文章管理后台页面"""
    articles = await get_articles(limit=20)
    return templates.TemplateResponse('blogger.html', {
        'request': request,
        'articles': articles
    })

@router.post('/api/blogger/generate')
async def api_generate(data: dict = None):
    """手动触发生成文章（用于测试，不用等到早上8点）"""
#(data or {})data 是字典,返回 datadata 是 None返回{},data 是空返回 {}
    topic=(data or {}).get('topic','今日新闻热点')
    result=await generate_article(topic)
    await save_article(result['title'], result['content'], result['topic'])
    return {'ok': True, 'title': result['title']}
@router.get('/api/blogger/articles')
async def api_articles():
    """获取文章列表（给前端 JS 调用）"""
    articles = await get_articles()
    return articles

# 2. 在文件末尾添加详情页路由
@router.get('/blogger/article/{article_id}', response_class=HTMLResponse)
async def article_detail(request: Request, article_id: int):
    """文章详情页"""
    article = await get_article_by_id(article_id)
    
    if not article:
        return HTMLResponse(content="<h1>文章不存在或已被删除</h1>", status_code=404)

    return templates.TemplateResponse('article_detail.html', {
        'request': request,
        'article': article
    })
