import os
import json
import numpy as np
from typing import List,Dict
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("Qwen_API_KEY")
client=OpenAI(
    api_key=api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
#“定位当前 Python 脚本所在的目录，并指向该目录下的 docs 文件夹。”
#dirname 是 "directory name"（目录名）的缩写。
#先找到自己的位置然后跳转到 docs 文件夹
DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")
INDEX_DIR = os.path.join(os.path.dirname(__file__), "index")
os.makedirs(INDEX_DIR, exist_ok=True)

VEC_PATH = os.path.join(INDEX_DIR, "vectors.npy")
META_PATH = os.path.join(INDEX_DIR, "chunks.json")

def list_txt_files() -> List[str]:
    """掃描 docs 目錄下所有 .txt 檔案"""
    files = []
    if not os.path.exists(DOCS_DIR):
        return files
    #获取 DOCS_DIR 这个文件夹里所有文件和子文件夹的名字
    for name in os.listdir(DOCS_DIR):
        #判断 name 这个字符串（通常是文件名）.endswith(".txt"): 是否以.txt 结尾，并且忽略大小写。
        if name.lower().endswith(".txt"):
            #它只是把“文件夹路径”和“文件名”拼在一起，中间自动加上斜杠（\ 或 /）。
            #name 是文件名，比如 "file1.txt" 或 "subfolder/file2.txt"。
            #DOCS_DIR 是文件夹路径，比如 "C:/Users/user/Documents/docs" 或 "C:/Users/user/Documents/docs/subfolder"。
            files.append(os.path.join(DOCS_DIR,name))
        return files
#chunk_size切出来的每一小块，最大包含500个字符
#overlap:int=100为了防止把一句话切断导致意思不连贯，
# 切下来的第二块会包含第一块末尾的 100 个字（藕断丝连）。
def split_text(text:str,
chunk_size:int=500,overlap:int=100) -> List[str]:
    """
    调用 Qwen 的 embedding 接口，得到向量
    这里假设模型名称为 'text-embedding-v1'（Qwen 的向量模型）
    如有变动请改成你实际的 embedding 模型名
    """
    resp = client.embeddings.create(
        model="text-embedding-v1",
        input=text
    )
    vectors=[item.embedding for item in resp.data]
    #将清洗干净的python列表中的向量转换为 numpy 数组 
    # 数据精度强制指定为 32 位浮点数 
    return np.array(vectors,dtype="float32")

def build_index():
    """從 docs/ 重建索引（離線建索引，需手動調用一次）"""
    files=list_txt_files()
    if not files:
        print("docs目录下没有.txt文件")
        return
    all_chunks :List[Dict]=[]
    all_texts: List[str] = []
    for path in files:
        #安全打开文本文件的标准写法，
        # 特别针对可能包含“乱码”或未知编码字符的文件进行了容错处理。
        # encoding="utf-8": 指定文件使用 UTF-8 编码，这是最常用的 Unicode 编码方式。
        # errors="ignore": 如果遇到编码错误（比如文件包含未知字符）
        # 会忽略这些错误，而不是抛出异常。
        # 这个参数让代码在处理各种文本文件时更加健壮。
        with open(path, "r", encoding="utf-8",errors="ignore") as f:
            text=f.read()
        chunks = split_text(text)
        for i, ch in enumerate(chunks):
            print(f"第 {i} 个分块的内容是: {ch}")
            all_texts.append(ch)
            all_chunks.append({
                "text": ch,
                #os.path.basename(path) 获取文件名，不包括路径
                "source":os.path.basename(path),
                "chunk_id":i
            })
    if not all_texts:
        print("⚠ 沒有切出任何 chunk")
        return
    print(f"切出了 {len(all_texts)} 个分块,開始做 embedding ..")
    vectors=embed_texts(all_texts)