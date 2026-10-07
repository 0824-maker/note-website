#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search_notes.py —— 本地知识点检索工具

解决"考前想按知识点查找，只能 Ctrl+F 翻列表"的痛点。
读取 process_notes.py 生成的 build_index/_index.json，按关键词检索知识点。

用法：
    python3 tools/search_notes.py 信道          # 单关键词
    python3 tools/search_notes.py 毛概 实事求是  # 多关键词（AND）
    python3 tools/search_notes.py -s 计网 信道   # 限定学科（模糊匹配学科名）
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_FILE = ROOT / "build_index" / "_index.json"

# 学科名的模糊别名 -> 索引里的学科全名
SUBJECT_ALIASES = {
    "毛概": "毛概", "概": "毛概",
    "计网": "信息网络化基础", "网络": "信息网络化基础", "xxwlh": "信息网络化基础",
    "英语": "通用英语三", "english": "通用英语三",
    "c语言": "计算机程序设计原理", "程序": "计算机程序设计原理", "jsj": "计算机程序设计原理",
}


def main():
    args = sys.argv[1:]
    subject_filter = None
    if "-s" in args:
        i = args.index("-s")
        raw = args[i + 1]
        subject_filter = SUBJECT_ALIASES.get(raw, raw)
        args = args[:i] + args[i + 2:]

    if not args:
        print(__doc__)
        sys.exit(1)

    if not INDEX_FILE.exists():
        print("索引不存在，请先运行: python3 tools/process_notes.py")
        sys.exit(1)

    records = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    if subject_filter:
        records = [r for r in records if subject_filter in r["subject"]]

    # 多关键词 AND 匹配
    hits = [r for r in records if all(kw in r["text"] for kw in args)]

    if not hits:
        print(f"没有找到包含 {' 且包含 '.join(args)} 的知识点。")
        return

    print(f"共找到 {len(hits)} 条（关键词：{' + '.join(args)}"
          + (f"，学科：{subject_filter}" if subject_filter else "") + "）\n")

    # 按学科分组展示
    current = None
    for r in hits[:40]:
        if r["subject"] != current:
            current = r["subject"]
            print(f"—— {current} " + "-" * 40)
        text = r["text"] if len(r["text"]) <= 100 else r["text"][:100] + "…"
        print(f"  [{r['source']}] {text}")
    if len(hits) > 40:
        print(f"\n… 还有 {len(hits) - 40} 条，试着加更精确的关键词。")


if __name__ == "__main__":
    main()
