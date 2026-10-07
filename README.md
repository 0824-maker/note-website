# 学科笔记智能整理站（note-agent）

> 一个**按学科知识形态自动整理**的课程笔记站 —— 从"把笔记堆在一起"升级为"让每一科按它自己的知识形态被重新组织"。

## 这是什么

这是我的一个**个性化改造项目**。起点是 [obsidian-publish-mkdocs](https://github.com/jobindjohn/obsidian-publish-mkdocs) 模板（一个通用的"把笔记发布到 GitHub Pages"的工具），但它的能力只到"发布"，解决不了我的真实痛点。

## 我的真实问题

我 4 门课的笔记形态完全不同，但原始笔记把它们**全部拍平成同一种无层级列表**：

| 问题 | 具体表现 |
|---|---|
| Markdown 语法损坏 | `#标题` 井号后没空格 → 标题层级全失效 |
| 内容被拍平 | 每行都加 `-` → 分不清题目/答案/章节 |
| 学科差异被抹平 | 毛概(问答)、计网(公式)、英语(语料)、C语言(代码) 全用一种方式硬塞 |
| 公式损坏 | `10的七次方`、`2*10的八次方`，上标丢失 |
| 无法检索 | 只能 Ctrl+F 翻列表 |

## 我的解法：学科感知的智能整理

核心是 `tools/process_notes.py` —— 一个**不依赖 API Key、纯本地可运行**的整理脚本。它按学科类型走不同策略：

| 学科 | 知识形态 | 处理策略 |
|---|---|---|
| 毛概 | 问答型 | Q&A 卡片化，答案折叠，章节自动分离 |
| 信息网络化基础 | 计算型 | 公式还原（`10的七次方`→`10^(7)`）+ 题目/解答分离 |
| 通用英语三 | 语言型 | 按单元切分长语料，句子断行 |
| 计算机程序设计原理 | 代码型 | 自动识别代码片段并加语法高亮 |

## 目录结构

```
note-agent/
├── notes_raw/              # 【输入】原始笔记（你平时随手记的，格式很乱）
│   ├── mg.md               #   毛概
│   ├── xxwlh.md            #   信息网络化基础
│   ├── english.md          #   通用英语三
│   └── jsj.md              #   计算机程序设计原理
├── tools/
│   ├── process_notes.py    # 【核心】智能整理脚本（本项目魔改点）
│   └── search_notes.py     # 本地知识点检索工具
├── docs/                   # 【输出】整理后的站点内容（脚本自动生成）
│   ├── index.md            #   首页
│   ├── research.md         #   方案调研与差异分析
│   └── *.md                #   整理后的各科笔记
├── build_index/
│   └── _index.json         #   知识点检索索引（95 条）
├── screenshots/            # 站点效果截图
├── mkdocs.yml              # 站点配置
├── requirements.txt        # Python 依赖
└── README.md
```

## 快速开始（本地跑通）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 整理笔记（核心一步：把 notes_raw/ 的乱笔记整理进 docs/）
python3 tools/process_notes.py

# 3. 按知识点检索（不用开浏览器）
python3 tools/search_notes.py 信道            # 全库搜
python3 tools/search_notes.py -s 毛概 实事求是 # 限定学科搜

# 4. 本地预览（浏览器打开 http://127.0.0.1:8000）
mkdocs serve

# 5. 构建静态站点（产物在 site/）
mkdocs build
```

## 换个专业怎么用

改 `tools/process_notes.py` 顶部的 `SUBJECTS` 表，把你的课程和对应的知识形态填进去即可复刻这套流程。

## 与现成方案的差异

详见站点的 [方案对比](docs/research.md) 页：现成方案解决"发布"，我的项目解决"整理"。
