#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_helper.py —— 学科笔记整理智能体的「AI 层」

【为什么要加这一层】
process_notes.py 是纯规则（正则 if-else）方案，快、免费、确定性好，
但它只能处理"预料之内"的笔记形态：问句必须以 ？ 结尾、公式必须是
已知的中文次方写法……一旦超出规则，就会漏判或错判。

这一层把"规则搞不定"的部分交给本地大模型（Ollama），从而让整个
项目从「规则脚本」升级为「AI 智能体」：
    - 规则层：处理 90% 的确定性工作（不花 token、不联网）
    - AI 层  ：处理 10% 的模糊判断 + 生成章节摘要

【它具体做两件事】
1. generate_chapter_summary(subject, chapter_title, chapter_text)
   为一个章节生成「本章摘要 + 核心考点」，写入汇总页。
2. classify_sentence(sentence, candidates)
   规则认不出的问句，交给 AI 判断它到底是"问题"还是"答案"。

【设计原则】
- 完全可选：Ollama 没装 / 没启动时，自动降级为纯规则模式，脚本不会报错。
- 纯本地：默认连 http://localhost:11434，数据不出电脑。
- 零依赖冲突：用标准库 urllib 调 Ollama 的 HTTP 接口，不需要额外 pip 包。

用法：
    # 先确保 Ollama 已启动、且已拉取模型
    ollama serve
    ollama pull qwen2.5:3b

    # 然后正常跑主脚本，AI 层会自动生效
    python3 tools/process_notes.py

    # 想临时关闭 AI（只跑规则）
    AI_ENABLED=0 python3 tools/process_notes.py
"""

import json
import os
import urllib.error
import urllib.request

# ---------------------------------------------------------------- 配置
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
AI_ENABLED = os.environ.get("AI_ENABLED", "1") != "0"

# 单次请求超时（秒）。本地 3b 模型在普通笔记本上通常几秒内返回。
TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))


# ---------------------------------------------------------------- 底层调用
def _chat(prompt: str, system: str = "") -> str:
    """调用 Ollama 的 /api/chat 接口，返回模型输出文本。失败抛异常。"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3},   # 整理笔记要稳定，不要发挥
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data.get("message") or {}).get("content", "").strip()


def is_available() -> bool:
    """检测 Ollama 是否可用（已启动且模型存在）。"""
    if not AI_ENABLED:
        return False
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
        names = [m.get("name", "") for m in tags.get("models", [])]
        # 模型名可能带 :latest 后缀，用前缀匹配
        base = OLLAMA_MODEL.split(":")[0]
        return any(n.split(":")[0] == base for n in names)
    except Exception:
        return False


# ---------------------------------------------------------------- 能力 1：章节摘要
SUMMARY_SYSTEM = (
    "你是一个学科笔记整理助手。你的任务是把学生凌乱的课堂笔记"
    "整理成简洁的复习材料。要求：语言精炼、忠实于原文、不编造原文没有的内容。"
)


def generate_chapter_summary(subject_name: str, chapter_title: str,
                             chapter_text: str) -> str:
    """
    为一个章节生成摘要。
    返回 Markdown 文本（含「本章摘要」与「核心考点」），失败返回空串。
    """
    if len(chapter_text.strip()) < 10:
        return ""

    prompt = f"""下面是《{subject_name}》中「{chapter_title}」的课堂笔记原文。请整理成复习材料。

笔记原文：
\"\"\"
{chapter_text[:3000]}
\"\"\"

请严格按以下 Markdown 格式输出，不要添加任何额外说明：

### 本章摘要
（用 3-5 句话概括本章讲了什么，要顺着笔记的逻辑，不要发散）

### 核心考点
- （考点 1）
- （考点 2）
- （考点 3，最多 5 条）
"""

    try:
        out = _chat(prompt, SUMMARY_SYSTEM)
        return out
    except Exception as e:
        print(f"    [AI 摘要失败] {chapter_title}: {e}")
        return ""


# ---------------------------------------------------------------- 能力 2：问句兜底判断
CLASSIFY_SYSTEM = "你是一个文本分类器，只输出一个词，不要解释。"


def classify_sentence(sentence: str) -> str:
    """
    规则认不出的句子，交给 AI 判断它是「问题」还是「答案」。
    返回 'question' 或 'answer'；不可用时返回 'unknown'。
    """
    prompt = (
        "判断下面这句话在一份课堂笔记里，属于「提问（问题）」还是「陈述（答案）」。\n"
        "只回答 question 或 answer，不要任何其他内容。\n\n"
        f"句子：{sentence[:200]}"
    )
    try:
        out = _chat(prompt, CLASSIFY_SYSTEM).lower()
        if "question" in out:
            return "question"
        if "answer" in out:
            return "answer"
    except Exception:
        pass
    return "unknown"
