#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py —— 学科笔记智能体（工具式）的本地网页后端

【它是什么】
把原本"敲命令行"的笔记整理流程，包成一个网页应用：
    粘贴/上传笔记  →  AI 自动判学科、分章节、生成摘要  →  存入笔记库  →  发布到网站

【和原项目的关系】
- 复用 tools/process_notes.py 里的学科档案、清洗规则、学科分流策略
- 复用 tools/ai_helper.py 里的 Ollama 调用
- 复用 MkDocs 站点作为最终展示
本文件只做一件事：给它们加一个"能操作的界面"。

【启动】
    python3 webapp/app.py
然后浏览器打开  http://127.0.0.1:5000
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

# ---------------------------------------------------------------- 路径
ROOT = Path(__file__).resolve().parent.parent          # 项目根目录
NOTES_RAW = ROOT / "notes_raw"
DOCS = ROOT / "docs"
TOOLS = ROOT / "tools"

sys.path.insert(0, str(TOOLS))

# 复用已有的模块（import 失败时给出清晰提示）
try:
    import ai_helper
    from process_notes import (
        SUBJECTS,
        fix_markdown_headings,
        normalize_blank_lines,
        strip_leading_bullets,
        PROCESSORS,
    )
except ImportError as e:
    print(f"[错误] 无法加载 tools 下的模块：{e}")
    print("       请确认 webapp/ 与 tools/ 在同一项目目录下。")
    sys.exit(1)

app = Flask(__name__)

# ---------------------------------------------------------------- 学科识别
# 学科关键词表：用于在 AI 不可用时的规则兜底识别
SUBJECT_KEYWORDS = {
    "mg": ["马克思主义", "毛泽东思想", "社会主义", "党的", "革命", "实事求是",
           "中国特色", "邓小平", "三个代表", "科学发展观"],
    "xxwlh": ["信道", "码元", "时延", "传输速率", "协议", "分组", "报文", "CDMA",
              "TCP", "IP", "带宽", "香农", "奈氏"],
    "english": ["unit", "the ", "teacher", "english", "listening", "reading",
                "vocabulary", "grammar"],
    "jsj": ["printf", "scanf", "int ", "char ", "#include", "for(", "while(",
            "main(", "函数", "指针", "数组"],
}


def guess_subject_by_rules(text: str) -> str:
    """规则兜底：按关键词命中数为文本打学科标签。"""
    low = text.lower()
    scores = {}
    for key, kws in SUBJECT_KEYWORDS.items():
        scores[key] = sum(1 for k in kws if k.lower() in low)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "mg"


def guess_subject_by_ai(text: str) -> str:
    """让 AI 判断这段笔记属于哪个学科。失败返回空串。"""
    if not ai_helper.is_available():
        return ""
    options = "\n".join(
        f"- {k}: {v['name']}（{v['type']}型，特征：{v['strategy']}）"
        for k, v in SUBJECTS.items()
    )
    prompt = (
        "下面是一段学生课堂笔记，请判断它属于哪一门课。\n\n"
        f"可选课程：\n{options}\n\n"
        f"笔记内容：\n{text[:800]}\n\n"
        "只回答课程代号（mg / xxwlh / english / jsj 之一），不要任何其他内容。"
    )
    try:
        out = ai_helper._chat(prompt, "你是一个学科分类器，只输出一个代号。").lower()
        for key in SUBJECTS:
            if key in out:
                return key
    except Exception:
        pass
    return ""


def detect_subject(text: str, hint: str = "") -> tuple:
    """
    判断学科。返回 (学科代号, 判断依据说明)。
    hint 为用户手动指定的学科，优先级最高。
    """
    if hint and hint in SUBJECTS:
        return hint, "手动指定"
    ai_key = guess_subject_by_ai(text)
    if ai_key:
        return ai_key, "AI 判断"
    return guess_subject_by_rules(text), "规则兜底"


# ---------------------------------------------------------------- 处理核心
def process_text(raw_text: str, subject_key: str):
    """
    对一段文本执行完整整理流程，返回整理后的 Markdown 正文。
    流程与 process_notes.py 保持一致：清洗 -> 学科分流 -> AI 摘要。
    """
    info = SUBJECTS[subject_key]

    text = fix_markdown_headings(raw_text)
    text = strip_leading_bullets(text)
    text = normalize_blank_lines(text)

    processor = PROCESSORS.get(info["type"])
    body = processor(subject_key, text) if processor else text

    if ai_helper.is_available():
        try:
            from process_notes import add_ai_summaries
            body = add_ai_summaries(info["name"], body, use_ai=True)
        except Exception as e:
            print(f"[AI 摘要跳过] {e}")

    return body


# ---------------------------------------------------------------- 路由
@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@app.route("/api/status")
def api_status():
    """返回运行状态：AI 是否可用、笔记库有哪些学科。"""
    available = ai_helper.is_available()
    subjects = []
    for key, info in SUBJECTS.items():
        f = NOTES_RAW / f"{key}.md"
        subjects.append({
            "key": key,
            "name": info["name"],
            "type": info["type"],
            "icon": info["icon"],
            "exists": f.exists(),
            "size": f.stat().st_size if f.exists() else 0,
        })
    return jsonify({
        "ai_available": available,
        "ai_model": os.environ.get("OLLAMA_MODEL", "qwen2.5:3b"),
        "subjects": subjects,
    })


@app.route("/api/process", methods=["POST"])
def api_process():
    """
    核心接口：接收一段笔记文本（或上传的文件内容），
    自动判学科 -> 整理 -> 生成摘要 -> 追加进笔记库。
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    hint = (data.get("subject") or "").strip()

    if not text:
        return jsonify({"ok": False, "error": "内容为空，请粘贴或上传笔记"}), 400
    if len(text) < 10:
        return jsonify({"ok": False, "error": "内容太短，至少 10 个字符"}), 400

    # 1. 判断学科
    subject_key, how = detect_subject(text, hint)
    info = SUBJECTS[subject_key]

    # 2. 整理
    body = process_text(text, subject_key)

    # 3. 预览（取前 600 字）
    preview = body[:600] + ("…" if len(body) > 600 else "")

    return jsonify({
        "ok": True,
        "subject_key": subject_key,
        "subject_name": info["name"],
        "subject_icon": info["icon"],
        "strategy": info["strategy"],
        "detected_by": how,
        "ai_used": ai_helper.is_available(),
        "raw_length": len(text),
        "out_length": len(body),
        "preview": preview,
        "body": body,
    })


@app.route("/api/save", methods=["POST"])
def api_save():
    """把整理结果追加保存到 notes_raw/<学科>.md，并重新生成站点内容。"""
    data = request.get_json(silent=True) or {}
    subject_key = data.get("subject_key", "")
    body = data.get("body", "")

    if subject_key not in SUBJECTS:
        return jsonify({"ok": False, "error": "学科无效"}), 400
    if not body.strip():
        return jsonify({"ok": False, "error": "内容为空"}), 400

    NOTES_RAW.mkdir(exist_ok=True)
    target = NOTES_RAW / f"{subject_key}.md"

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    chunk = f"\n\n<!-- 新增于 {stamp} -->\n{body.strip()}\n"
    with open(target, "a", encoding="utf-8") as f:
        f.write(chunk)

    # 重新生成 docs（复用原脚本）
    try:
        subprocess.run(
            [sys.executable, str(TOOLS / "process_notes.py"), subject_key],
            cwd=str(ROOT), capture_output=True, timeout=600, check=False,
        )
        rebuilt = True
    except Exception:
        rebuilt = False

    return jsonify({
        "ok": True,
        "saved_to": str(target.relative_to(ROOT)),
        "rebuilt": rebuilt,
    })


@app.route("/api/publish", methods=["POST"])
def api_publish():
    """构建静态站点（等价于 mkdocs build）。"""
    try:
        r = subprocess.run(
            ["mkdocs", "build"], cwd=str(ROOT),
            capture_output=True, timeout=300, text=True,
        )
        return jsonify({
            "ok": r.returncode == 0,
            "output": (r.stdout + r.stderr)[-800:],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------------------------------------------------------------- 前端页面
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>学科笔记智能体</title>
<style>
:root{
  --primary:#3f51b5; --primary-l:#e8eaf6; --bg:#f5f6fa; --card:#fff;
  --fg:#2c3e50; --muted:#7f8c9a; --border:#e3e6ef; --ok:#27ae60; --warn:#e67e22;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--fg);line-height:1.6;font-size:14px}
.topbar{background:var(--primary);color:#fff;padding:14px 28px;
  display:flex;align-items:center;justify-content:space-between}
.topbar h1{font-size:18px;font-weight:600}
.topbar .status{font-size:12px;display:flex;align-items:center;gap:6px}
.dot{width:8px;height:8px;border-radius:50%;background:#ddd}
.dot.on{background:#4ade80;box-shadow:0 0 6px #4ade80}
.dot.off{background:#fbbf24}
.wrap{display:grid;grid-template-columns:1fr 1fr;gap:20px;
  max-width:1200px;margin:20px auto;padding:0 20px}
.card{background:var(--card);border-radius:10px;padding:20px;
  box-shadow:0 1px 4px rgba(0,0,0,.06)}
.card h2{font-size:15px;margin-bottom:14px;color:var(--primary);
  display:flex;align-items:center;gap:8px}
.card h2 .num{background:var(--primary);color:#fff;width:20px;height:20px;
  border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
  font-size:12px}
textarea{width:100%;height:220px;padding:12px;border:1px solid var(--border);
  border-radius:8px;font-family:inherit;font-size:13px;resize:vertical;
  line-height:1.7}
textarea:focus{outline:none;border-color:var(--primary)}
.row{display:flex;align-items:center;gap:10px;margin-top:12px;flex-wrap:wrap}
select{padding:8px 10px;border:1px solid var(--border);border-radius:6px;
  font-size:13px;background:#fff;cursor:pointer}
button{padding:9px 20px;border:none;border-radius:6px;font-size:13px;
  cursor:pointer;font-weight:600;transition:.2s}
.btn-main{background:var(--primary);color:#fff}
.btn-main:hover{background:#3446a0}
.btn-main:disabled{background:#b0b7d0;cursor:not-allowed}
.btn-sec{background:var(--primary-l);color:var(--primary)}
.btn-sec:hover{background:#d7dbf5}
.upload{margin-top:10px;font-size:12px;color:var(--muted)}
.upload input{font-size:12px}
.result{min-height:220px}
.placeholder{color:var(--muted);text-align:center;padding:60px 20px;font-size:13px}
.badge{display:inline-block;padding:3px 10px;border-radius:12px;
  font-size:12px;font-weight:600;background:var(--primary-l);color:var(--primary)}
.badge.ai{background:#e8f5e9;color:var(--ok)}
.meta-line{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;
  color:var(--muted);padding:10px 0;border-bottom:1px dashed var(--border);
  margin-bottom:12px}
.meta-line b{color:var(--fg)}
.preview{background:#fafbfd;border:1px solid var(--border);border-radius:8px;
  padding:14px;font-size:13px;white-space:pre-wrap;max-height:300px;
  overflow-y:auto;font-family:"SF Mono",Consolas,monospace;line-height:1.7}
.actions{margin-top:14px;display:flex;gap:10px;align-items:center}
.msg{margin-top:12px;padding:10px 14px;border-radius:6px;font-size:13px;display:none}
.msg.ok{background:#e8f5e9;color:#1b5e20;display:block}
.msg.err{background:#ffebee;color:#b71c1c;display:block}
.skills{max-width:1200px;margin:0 auto 24px;padding:0 20px}
.skills .card{padding:16px 20px}
.skill-list{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.skill{background:#fafbfd;border:1px solid var(--border);border-radius:8px;
  padding:12px}
.skill .name{font-weight:600;font-size:13px;margin-bottom:4px}
.skill .desc{font-size:11px;color:var(--muted);line-height:1.5}
.skill .type{font-size:10px;color:var(--primary);text-transform:uppercase;
  letter-spacing:.5px}
@media(max-width:820px){.wrap{grid-template-columns:1fr}
  .skill-list{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>

<div class="topbar">
  <h1>📚 学科笔记智能体</h1>
  <div class="status">
    <span class="dot" id="dot"></span>
    <span id="statusText">检测中…</span>
  </div>
</div>

<div class="skills">
  <div class="card">
    <h2 style="margin-bottom:10px">学科感知策略</h2>
    <div class="skill-list" id="skillList"></div>
  </div>
</div>

<div class="wrap">
  <div class="card">
    <h2><span class="num">1</span> 输入新笔记</h2>
    <textarea id="input" placeholder="把新记的笔记粘贴到这里，格式多乱都没关系……

例如：
第一章 概述
信道容量怎么算？C=Wlog2(1+S/N) 香农公式
码元携带两个比特 4000Hz 频带 信噪比127:1"></textarea>
    <div class="upload">
      或上传文件（.md / .txt）：<input type="file" id="file" accept=".md,.txt">
    </div>
    <div class="row">
      <span style="font-size:13px;color:var(--muted)">学科：</span>
      <select id="subject">
        <option value="">自动识别</option>
      </select>
      <button class="btn-main" id="btnProcess" onclick="doProcess()">开始整理</button>
    </div>
  </div>

  <div class="card">
    <h2><span class="num">2</span> 整理结果</h2>
    <div class="result" id="result">
      <div class="placeholder">
        粘贴笔记后点击「开始整理」<br>
        智能体会自动判断学科、分章节、生成摘要
      </div>
    </div>
    <div id="msg" class="msg"></div>
  </div>
</div>

<script>
let currentBody = '', currentSubject = '';

async function loadStatus(){
  const r = await fetch('/api/status');
  const d = await r.json();
  const dot = document.getElementById('dot');
  const txt = document.getElementById('statusText');
  if (d.ai_available) {
    dot.className = 'dot on';
    txt.textContent = 'AI 在线 · ' + d.ai_model;
  } else {
    dot.className = 'dot off';
    txt.textContent = 'AI 离线（规则模式）';
  }
  // 学科下拉
  const sel = document.getElementById('subject');
  sel.innerHTML = '<option value="">自动识别</option>';
  d.subjects.forEach(s => {
    const o = document.createElement('option');
    o.value = s.key;
    o.textContent = s.icon + ' ' + s.name;
    sel.appendChild(o);
  });
  // 策略卡片
  const list = document.getElementById('skillList');
  list.innerHTML = '';
  d.subjects.forEach(s => {
    const div = document.createElement('div');
    div.className = 'skill';
    div.innerHTML = '<div class="type">' + s.type + '</div>' +
                    '<div class="name">' + s.icon + ' ' + s.name + '</div>' +
                    '<div class="desc">共 ' + s.size + ' 字节</div>';
    list.appendChild(div);
  });
}

document.getElementById('file').addEventListener('change', e => {
  const f = e.target.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = ev => { document.getElementById('input').value = ev.target.result; };
  reader.readAsText(f, 'utf-8');
});

function showMsg(text, type){
  const m = document.getElementById('msg');
  m.textContent = text;
  m.className = 'msg ' + type;
}

async function doProcess(){
  const text = document.getElementById('input').value.trim();
  if (!text) { showMsg('请先粘贴或上传笔记内容', 'err'); return; }

  const btn = document.getElementById('btnProcess');
  btn.disabled = true;
  btn.textContent = '整理中…';
  document.getElementById('result').innerHTML =
    '<div class="placeholder">🤖 智能体正在分析…</div>';

  try {
    const r = await fetch('/api/process', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: text, subject: document.getElementById('subject').value})
    });
    const d = await r.json();
    if (!d.ok) { throw new Error(d.error || '处理失败'); }

    currentBody = d.body;
    currentSubject = d.subject_key;

    document.getElementById('result').innerHTML = `
      <div>
        <span class="badge">${d.subject_icon} ${d.subject_name}</span>
        <span class="badge ai">${d.detected_by}</span>
        ${d.ai_used ? '<span class="badge ai">AI 摘要已生成</span>' : '<span class="badge" style="background:#fff3e0;color:#e67e22">规则模式</span>'}
      </div>
      <div class="meta-line">
        <span>处理策略：<b>${d.strategy}</b></span>
      </div>
      <div class="meta-line">
        <span>原文 <b>${d.raw_length}</b> 字符</span>
        <span>→ 整理后 <b>${d.out_length}</b> 字符</span>
      </div>
      <div class="preview">${escapeHtml(d.preview)}</div>
      <div class="actions">
        <button class="btn-main" onclick="doSave()">存入笔记库</button>
        <span style="font-size:12px;color:var(--muted)">保存后会重新生成站点内容</span>
      </div>
    `;
    showMsg('整理完成。确认无误后点击「存入笔记库」。', 'ok');
  } catch(e) {
    document.getElementById('result').innerHTML =
      '<div class="placeholder">处理失败，请重试</div>';
    showMsg(e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = '开始整理';
  }
}

async function doSave(){
  if (!currentBody) return;
  try {
    const r = await fetch('/api/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({subject_key: currentSubject, body: currentBody})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || '保存失败');
    showMsg('已存入 ' + d.saved_to + (d.rebuilt ? '，站点内容已重新生成 ✅' : '（站点重新生成失败，可手动跑 process_notes.py）'), 'ok');
    loadStatus();
  } catch(e) {
    showMsg(e.message, 'err');
  }
}

function escapeHtml(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

loadStatus();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    print("=" * 56)
    print("  学科笔记智能体 · 本地网页应用")
    print("=" * 56)
    print(f"  项目根目录：{ROOT}")
    print(f"  AI 状态   ：{'在线' if ai_helper.is_available() else '离线（自动降级为规则模式）'}")
    print("  浏览器打开：http://127.0.0.1:5000")
    print("=" * 56)
    app.run(host="127.0.0.1", port=5000, debug=False)
