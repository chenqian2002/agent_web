import aiosqlite, os

DB_PATH = 'blogger.db'   # 数据库文件路径
async def init_db():
    #with上下文连接器aiosqlite.connect(DB_PATH)异步连接数据库
    async with aiosqlite.connect(DB_PATH) as db:
        #await异步必须写db.execute()执行sql语句
        await db.execute('''
        
            CREATE TABLE IF NOT EXISTS articles (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                title   TEXT,      -- 文章标题
                content TEXT,      -- 文章正文（AI写的）
                topic   TEXT,      -- 搜索主题
                status  TEXT,      -- 状态: draft / published
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')#INTEGER整型，PRIMARY KEY主键（id不能重复），AUTOINCREMENT自增
        await db.commit() #提交数据库修改，把数据真正保存到数据库文件里
async def save_article(title, content, topic, status='draft'):
    async with aiosqlite.connect(DB_PATH) as db:
         await db.execute(
            'INSERT INTO articles (title,content,topic,status) VALUES (?,?,?,?)',
            (title, content, topic, status)
        )
         await db.commit()
         #•async with aiosqlite.connect()：每次操作都开新连接，用完自动关闭，防止连接泄漏
async def get_articles(limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        #row_factory决定数据库查询结果用什么格式返回
        db.row_factory = aiosqlite.Row  # 让结果可以像字典一样访问让数据库查询结果可以用字段名访问aiosqlite.Row
        cur = await db.execute(
            #查询articles表的数据通过created_at降序排列，限制数量为limit
            'SELECT * FROM articles ORDER BY created_at DESC LIMIT ?', (limit,)
        )
        rows = await cur.fetchall()
        #.fetchall()把所有的查询结果一次性取出来返回列表
        return [dict(r) for r in rows]
# --- 在 blogger_db.py 文件底部添加 ---

async def get_article_by_id(article_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # 根据 ID 查询单条数据
        async with db.execute('SELECT * FROM articles WHERE id = ?', (article_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            return None