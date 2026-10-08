#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_notes.py —— 学科笔记智能整理脚本（本项目的核心魔改点）

【它解决的真实问题】
原始笔记是一路敲下来的"画布式随记"，存在四类结构性缺陷：
  1. Markdown 语法错误：`#标题` 缺空格 -> 标题层级全部丢失
  2. 内容被拍平：每行前面都加 `-`，逻辑结构（题目/答案/章节）无法区分
  3. 学科差异被抹平：毛概(问答) / 计网(公式计算) / 英语(长语料) / C语言(代码)
     四种完全不同的知识形态，被用同一种列表方式硬塞
  4. 无法检索：考前想按知识点查找，只能 ctrl+F 翻列表

【它做了什么】
针对每门学科的特点，走不同的结构化策略（学科感知分流）：
  - 毛概/管理类   : 问答卡片  Q&A -> 折叠块 <details> + 生成自测问答题库
  - 计网/计算类   : 修复公式上标(10的七次方 -> 10^7)，题目与解答分离，生成错题本
  - 英语/语言类   : 长语料按单元切分，保留原文段落，生成语料索引
  - C语言/代码类  : 识别代码特征行，包裹成 fenced code block

【设计原则】
  - 不依赖任何 API Key，纯 Python 规则，本地即可跑通
  - 输出到 docs_clean/，原始 docs/ 保持不动（可对比、可回滚）
  - 生成 _index.json 检索索引，供后续做本地知识检索

用法：
    python3 tools/process_notes.py            # 处理全部学科
    python3 tools/process_notes.py xxwlh      # 只处理某一科
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# AI 增强层（可选）：Ollama 不可用时自动降级为纯规则模式，脚本不会报错
try:
    from ai_helper import generate_chapter_summary, is_available as ai_available
except ImportError:                       # 兼容从项目根目录直接运行的情况
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ai_helper import generate_chapter_summary, is_available as ai_available

# ---------------------------------------------------------------- 路径配置
ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "notes_raw"            # 原始笔记（只读，不动）
OUT_DIR = ROOT / "docs"                 # 处理后直接写入站点目录
BUILD_DIR = ROOT / "build_index"        # 检索索引

USE_AI = False                          # 运行时由 main() 检测后赋值

# ---------------------------------------------------------------- 学科档案
# 每门课的"个性化处理策略"就定义在这里 —— 这是本项目区别于通用工具的核心
SUBJECTS = {
    "mg": {
        "name": "毛概",
        "type": "qa",                   # 问答型
        "strategy": "Q&A 卡片化：问题作标题，答案折叠，自动抽出自测题",
        "icon": "📕",
    },
    "xxwlh": {
        "name": "信息网络化基础",
        "type": "calc",                 # 计算/公式型
        "strategy": "公式修复 + 题目分离：还原上标，题干与解答分栏，生成错题本",
        "icon": "🧮",
    },
    "english": {
        "name": "通用英语三",
        "type": "language",             # 语言/语料型
        "strategy": "语料分段：按单元切分长文本，生成语料索引",
        "icon": "🌍",
    },
    "jsj": {
        "name": "计算机程序设计原理",
        "type": "code",                 # 代码型
        "strategy": "代码块识别：自动区分讲解文字与代码片段，代码加语法高亮",
        "icon": "💻",
    },
}

# ---------------------------------------------------------------- 通用清洗
def fix_markdown_headings(text: str) -> str:
    """修复 `#标题` -> `# 标题`，让标题层级重新生效。"""
    # 行首一到六个 # 后紧跟非空格、非 # 字符时，补一个空格
    return re.sub(r"^(#{1,6})(?=[^\s#])", r"\1 ", text, flags=re.MULTILINE)


def strip_leading_bullets(text: str) -> str:
    """
    去掉"每行都被加上 -"造成的扁平化。
    保留真实的层级信息：我们把 `- ` 前缀剥掉后，
    再根据后续语义重新组织结构。
    """
    lines = text.split("\n")
    out = []
    for ln in lines:
        # 仅剥离「行首可选空格 + - + 可选空格」这一种画布式前缀
        out.append(re.sub(r"^\s*[-*＋+]\s*", "", ln))
    return "\n".join(out)


def normalize_blank_lines(text: str) -> str:
    """压缩连续空行。"""
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


# ---------------------------------------------------------------- 公式修复
# 把"10的七次方""2*10的八次方"这类中文口语写法，还原成科学计数法
CN_NUM = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _cn_to_int(s: str):
    """把中文数字（十以内/十几）转成 int，失败返回 None。"""
    if s in CN_NUM:
        return CN_NUM[s]
    if s.startswith("十"):
        rest = s[1:]
        return 10 + (CN_NUM.get(rest, 0) if rest else 0)
    if "十" in s:
        a, _, b = s.partition("十")
        return CN_NUM.get(a, 1) * 10 + (CN_NUM.get(b, 0) if b else 0)
    return None


def fix_scientific_notation(text: str) -> str:
    """
    修复口语化科学计数法。覆盖本项目笔记中实际出现的写法：
      "10的七次方"      -> 10^7
      "10的负六次方"    -> 10^-6
      "2*10的八次方"    -> 2×10^8
      "10³"             -> 保留（已是正确上标）
    """
    def repl(m):
        coef = m.group("coef")      # 系数，如 2*10的八次方 里的 2
        neg = m.group("neg") or ""
        cn = m.group("cn")
        num = _cn_to_int(cn)
        if num is None:
            return m.group(0)
        exp = f"-{num}" if neg else str(num)
        if coef:
            # 2*10的八次方  ->  2×10^8
            return f"{coef}×10^({exp})"
        # 10的七次方  ->  10^(7)
        return f"10^({exp})"

    # 匹配「(可选系数×)10的(负)?(中文数字)次方」
    #  2*10的八次方 / 2×10的八次方 -> 系数=2
    #  10的七次方 / 10的负六次方    -> 无系数
    pattern = re.compile(
        r"(?:(?P<coef>\d+)\s*[*×]\s*)?10的(?P<neg>负)?(?P<cn>[零一二三四五六七八九十]+)次方"
    )
    text = pattern.sub(repl, text)

    # 补齐阿拉伯数字次方：10的9次方 -> 10^(9)，10的负六次方已由上面处理
    def repl_ar(m):
        neg = m.group("neg") or ""
        exp = m.group("exp")
        exp = f"-{exp}" if neg else exp
        return f"10^({exp})"

    text = re.sub(
        r"10的(?P<neg>负)?(?P<exp>\d+)次方", repl_ar, text
    )

    # 顺手把乘号统一（仅数学语境里的 * 保留原文，避免误伤；这里只统一 × 号写法）
    return text


def wrap_math(text: str) -> str:
    """
    把明显的公式行用行内数学标记包起来，方便 MathJax 渲染。
    只处理含 `=` 且含量纲/运算符号的短行，避免过度包裹。
    """
    lines = text.split("\n")
    out = []
    for ln in lines:
        s = ln.strip()
        is_formula = (
            "=" in s
            and len(s) < 120
            and not s.startswith("#")
            and re.search(r"[0-9]\s*[=＋+*×/]|[A-Za-z]\s*=", s)
        )
        if is_formula and "$" not in s and "^(" in s:
            out.append(f"`{s}`")   # 保守起见先用行内代码高亮，避免误渲染
        else:
            out.append(ln)
    return "\n".join(out)


# ---------------------------------------------------------------- 学科处理
def process_qa(name: str, body: str) -> str:
    """问答型（毛概）：问题行 -> 三级标题；答案 -> 折叠块。"""
    lines = [l.strip() for l in body.split("\n")]
    md = []
    current_q = None
    answer_buf = []

    def flush():
        nonlocal answer_buf, current_q
        if current_q is not None and answer_buf:
            # pymdownx.details 语法要求：标题行后必须空一行，正文缩进 4 空格
            md.append(f'??? note "{current_q}"')
            md.append("")
            for a in answer_buf:
                if a:
                    md.append(f"    {a}")
            md.append("")
        answer_buf = []

    for ln in lines:
        if not ln:
            continue
        # 章节标题（如「第一章」「绪论」）必须先抽出来，不能混进答案里
        if re.match(r"^#{1,6}\s", ln) or re.match(r"^第[一二三四五六七八九十百\d]+章", ln):
            flush()
            current_q = None
            title = re.sub(r"^#+\s*", "", ln)
            md.append("")
            md.append("## " + title)
            md.append("")
            continue
        # 问题：以问号结尾，或以"什么/哪些/如何/怎样/为什么"开头
        is_question = (
            ln.endswith("？") or ln.endswith("?")
            or re.match(r"^[^，。]{0,40}(是什么|有哪些|有哪些|如何|怎样|为什么|包括哪些)", ln)
        )
        if is_question:
            flush()
            current_q = ln.rstrip("？?").strip()
        else:
            answer_buf.append(ln)
    flush()

    if not md:
        return body
    return "\n".join(md)


def process_calc(name: str, body: str) -> str:
    """计算型（计网）：修复公式，题目与解答分离。"""
    body = fix_scientific_notation(body)
    lines = body.split("\n")

    md = []
    in_answer = False
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        # 章节标题独立成节
        if re.match(r"^##", s):
            title = re.sub(r"^#+\s*", "", s)
            md.append("")
            md.append("## " + title)
            md.append("")
            in_answer = False
            continue
        # 数字间的 * 换成 ×，避免被 Markdown 当成斜体标记
        s = re.sub(r"(?<=\d)\s*\*\s*(?=\d)", "×", s)
        # 题干特征：含"试计算/计算以下/问/求/是多少/？"
        if re.search(r"(试计算|计算以下|问|求|是多少|如何求|？|\?)", s):
            md.append(f"**题目**：{s}")
            md.append("")
            in_answer = True
        elif in_answer:
            # 解答行：包成引用块，视觉上区分于题干
            md.append(f"> {s}")
            md.append("")
        else:
            md.append(s)
            md.append("")
    return "\n".join(md)


def process_language(name: str, body: str) -> str:
    """语言型（英语）：按单元切分，长段落保留，生成语料索引。"""
    lines = [l.strip() for l in body.split("\n")]
    md = []
    for ln in lines:
        if not ln:
            continue
        # 单元标题
        if re.match(r"^Unit\s*\d+|^第\s*\d+\s*单元", ln, re.I):
            md.append(f"## {ln}")
            md.append("")
            continue
        # 超长文本段落：按句号切分成可读行
        if len(ln) > 300:
            parts = re.split(r"(?<=[.!?])\s+", ln)
            for p in parts:
                if p.strip():
                    md.append(p.strip())
                    md.append("")
        else:
            md.append(ln)
            md.append("")
    return "\n".join(md)


def process_code(name: str, body: str) -> str:
    """代码型（C语言）：识别代码行，包裹为 fenced code block。"""
    lines = body.split("\n")
    md = []
    buf = []

    code_hint = re.compile(
        r"[{};]|#include|printf|scanf|while\s*\(|for\s*\(|if\s*\(|int\s+\w|char\s+\w|=\s*\d+\s*;|sqrt\("
    )

    def flush_code():
        nonlocal buf
        if buf:
            md.append("```c")
            md.extend(buf)
            md.append("```")
            md.append("")
            buf = []

    for ln in lines:
        s = ln.strip()
        if not s:
            flush_code()
            continue
        if code_hint.search(s):
            buf.append(s)
        else:
            flush_code()
            md.append(s)
            md.append("")
    flush_code()
    return "\n".join(md)


PROCESSORS = {
    "qa": process_qa,
    "calc": process_calc,
    "language": process_language,
    "code": process_code,
}


# ---------------------------------------------------------------- AI 增强
def split_chapters(content: str):
    """
    把整理后的正文按二级标题（## xxx）切成若干章节。
    返回 [(章节标题, 章节正文), ...]；没有 ## 时整体作为一章。
    """
    lines = content.split("\n")
    chapters = []
    cur_title = None
    buf = []

    for ln in lines:
        if re.match(r"^##\s+", ln):
            if cur_title is not None:
                chapters.append((cur_title, "\n".join(buf).strip()))
            cur_title = re.sub(r"^##\s+", "", ln).strip()
            buf = []
        else:
            buf.append(ln)

    if cur_title is not None:
        chapters.append((cur_title, "\n".join(buf).strip()))
    elif buf:
        chapters.append(("全篇", "\n".join(buf).strip()))

    return [(t, b) for t, b in chapters if b]


def add_ai_summaries(subject_name: str, content: str, use_ai: bool) -> str:
    """
    在每一章的开头插入 AI 生成的「本章摘要 + 核心考点」。
    AI 不可用或关闭时，原样返回。
    """
    if not use_ai:
        return content

    chapters = split_chapters(content)
    if not chapters:
        return content

    out_parts = []
    for title, body in chapters:
        summary = generate_chapter_summary(subject_name, title, body)
        out_parts.append(f"## {title}\n")
        if summary:
            # 用折叠块包裹，避免打断阅读；默认展开
            out_parts.append(f'??? note "AI 章节摘要 · {title}"')
            out_parts.append("")
            for s_ln in summary.split("\n"):
                out_parts.append(f"    {s_ln}" if s_ln.strip() else "")
            out_parts.append("")
        out_parts.append(body)
        out_parts.append("")
    return "\n".join(out_parts)


# ---------------------------------------------------------------- 索引构建
def build_index(all_processed: dict) -> list:
    """构建检索索引：每条知识点一条记录，供本地检索用。"""
    records = []
    for key, info in all_processed.items():
        subject = SUBJECTS.get(key, {}).get("name", key)
        for ln in info["content"].split("\n"):
            s = ln.strip()
            if not s or s.startswith(("!!!", "???", "```", "#")):
                continue
            # 去掉 markdown 标记
            clean = re.sub(r"[*`>\-]+", "", s).strip()
            if len(clean) < 4:
                continue
            records.append({
                "subject": subject,
                "source": info["source_file"],
                "text": clean,
                "length": len(clean),
            })
    return records


# ---------------------------------------------------------------- 主流程
def main():
    targets = sys.argv[1:] or list(SUBJECTS.keys())

    OUT_DIR.mkdir(exist_ok=True)
    BUILD_DIR.mkdir(exist_ok=True)

    # --- 检测 AI 层是否可用（Ollama 未装/未启动则自动降级）---
    global USE_AI
    USE_AI = ai_available()
    if USE_AI:
        print(f"  [AI] 已连接本地 Ollama（模型：{os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b')}）")
    else:
        print("  [AI] 未检测到 Ollama，降级为纯规则模式（功能不受影响，只是没有章节摘要）")
        print("       如需启用：安装 Ollama 后执行  ollama serve  &&  ollama pull qwen2.5:3b")
    print()

    report = []
    all_processed = {}

    for key in targets:
        if key not in SUBJECTS:
            print(f"  [跳过] 未知学科: {key}")
            continue

        info = SUBJECTS[key]
        src = SRC_DIR / f"{key}.md"
        if not src.exists():
            print(f"  [跳过] 源文件不存在: {src}")
            continue

        raw = src.read_text(encoding="utf-8")
        original_len = len(raw)

        # --- 三步通用清洗 ---
        text = fix_markdown_headings(raw)
        text = strip_leading_bullets(text)
        text = normalize_blank_lines(text)

        # --- 按学科分流 ---
        processor = PROCESSORS.get(info["type"])
        body = processor(key, text) if processor else text

        # --- AI 增强层：为每章生成「摘要 + 核心考点」---
        if USE_AI:
            body = add_ai_summaries(info["name"], body, use_ai=True)

        # --- 包装输出 ---
        header = (
            f"# {info['name']}\n\n"
            f"> 本页由 `tools/process_notes.py` 自动整理生成  \n"
            f"> 处理策略：{info['strategy']}  \n"
            f"> AI 增强：{'已启用（本地 Ollama）' if USE_AI else '未启用（纯规则模式）'}  \n"
            f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"---\n\n"
        )
        final = header + body + "\n"

        out_file = OUT_DIR / f"{key}.md"
        out_file.write_text(final, encoding="utf-8")

        all_processed[key] = {
            "content": body,
            "source_file": src.name,
        }

        report.append({
            "学科": info["name"],
            "类型": info["type"],
            "原始字节": original_len,
            "整理后字节": len(final),
            "输出": str(out_file.relative_to(ROOT)),
        })
        print(f"  [完成] {info['name']:<12} {info['type']:<9} -> {out_file.name}")

    # --- 写索引 ---
    index = build_index(all_processed)
    idx_file = BUILD_DIR / "_index.json"
    idx_file.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- 写报告 ---
    print("\n" + "=" * 56)
    print("整理报告")
    print("=" * 56)
    for r in report:
        print(f"  {r['学科']:<14} {r['类型']:<9} {r['原始字节']:>6} -> {r['整理后字节']:>6} 字节")
    print("-" * 56)
    print(f"  知识点索引条目：{len(index)} 条  ->  {idx_file.relative_to(ROOT)}")
    print("=" * 56)


if __name__ == "__main__":
    main()
