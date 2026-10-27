---
name: mogua
description: 顺藤摸瓜学术文献引文网络与脉络挖掘技能（Mogua / Citation Snowballing）。当用户需要从一篇或多篇种子论文（DOI、URL 或论文标题）出发，“顺藤摸瓜”挖掘核心引文网络、梳理学术源流脉络、找上下游高相关文献、构建局部知识图谱、或提到“摸瓜”、“引文网络”、“滚雪球”、“文献脉络”、“connected papers”时使用。自动爬取真实引文数据，基于影响力（Citation/Year）与亲缘度（Jaccard 参考文献重叠度）双重算法筛选出核心文献骨架，并交付本地交互式网页图谱（HTML）、静态图（PNG/SVG）与结构化导读报告。
---

# Mogua (摸瓜) — 学术文献引文网络与脉络挖掘

从单篇或多篇论文出发，依托 **OpenAlex 官方知识图谱** 真实数据源，自动进行“顺藤摸瓜”（Citation Snowballing），拒绝大模型引文幻觉，精准抽取出文献网络的骨架，并提供交互式可视化和导读。

---

## 触发场景与关键词

* **触发词**：`摸瓜`、`顺藤摸瓜`、`mogua`、`引文网络`、`文献脉络`、`找相关论文`、`滚雪球`、`文献图谱`、`学术脉络`、`connected papers`、`citation network`。
* **典型用户诉求**：
  * “以这篇论文为种子摸一下瓜：10.1016/j.cell.2024.01.025”
  * “顺藤摸瓜找一下这篇文章的关键上下游参考文献”
  * “读完这篇想看看同领域还有哪些必读经典和最新延伸，做个图谱”
  * “输入论文标题，帮我摸摸它前后的文献网络”

---

## 核心设计与评分算法

Mogua 采用双轨筛选算法，从数百篇甚至数千篇引文/参考文献中智能收敛至最核心的 30~50 篇节点：
1. **真实无幻觉**：基于 OpenAlex 实时数据接口，文献元数据、DOI 及引用关系真实客观。
2. **奠基之作（Foundations）**：按年均引用量（$\text{CitationPerYear} = \frac{\text{Citations}}{\text{Age}}$）排序，筛选出经受住时间检验的理论奠基与方法学基石。
3. **同宗延伸（Kin / Offshoots）**：按参考文献交并比（$Jaccard = \frac{|Ref_{seed} \cap Ref_{cand}|}{|Ref_{seed} \cup Ref_{cand}|}$）计算参考文献集合重合度，抓取研究关注点高度一致的直接跟进者与同门工作。
4. **近期突破（Recent Breakthroughs）**：近 3 年内兼具较高热度与参考文献亲缘度的新成果。

---

## 执行指南 (Agent 指令)

执行脚本位于当前技能的 `scripts/` 目录下（`scripts/mogua_runner.py`）。

### 1. 运行命令指南

* **Python 环境**：优先使用项目环境或已安装 `mogua` 依赖的虚拟环境中的 Python（如 `.venv/Scripts/python.exe` 或 `.venv/bin/python`；若已全局安装则直接使用 `python`）。
* **字符编码**：Windows 终端环境下推荐附带 `-X utf8` 选项避免终端中文乱码。
* **脚本路径**：Agent 执行时，将 `<skill_dir>` 自动替换为当前技能所在目录的绝对路径。

```powershell
# 1. 直接提供 DOI 运行 (默认 depth=1, max-neighbors=100)
python -X utf8 "<skill_dir>/scripts/mogua_runner.py" "10.1016/j.cell.2024.08.046"

# 2. 提供论文标题 (自动通过 OpenAlex 反查最高引相关论文 DOI 并执行)
python -X utf8 "<skill_dir>/scripts/mogua_runner.py" "Attention Is All You Need"

# 3. 获取结构化 JSON 格式数据供 Agent 深度分析
python -X utf8 "<skill_dir>/scripts/mogua_runner.py" "10.1016/j.cell.2024.08.046" --json
```

### 2. 常用参数控制

| 参数 | 默认值 | 说明 |
| :--- | :---: | :--- |
| `query` | (必填) | 论文 DOI、链接或论文完整标题 |
| `--depth` | `1` | 爬取深度。`1` 适合大部分单篇溯源；`2` 用于深度滚雪球 |
| `--max-neighbors` | `100` | 限制每篇论文抓取的最大引用/参考文献数，防巨型文献耗时过长 |
| `--top-n` | `15` | 保留的高引经典基石节点数 |
| `--top-m` | `20` | 保留的高 Jaccard 相似度亲缘节点数 |
| `--smart-expand` | `0` | 在 Depth 2 中智能筛选 Top K 关键论文进行选择性展开 |

---

## 交付与回复规范

每次执行完成后，Agent 需按照以下结构输出清晰结构化的导读汇报：

1. **🌱 种子论文基本信息**：
   * 标题、发表年份、期刊、第一作者/通讯作者、当前总被引量、DOI 链接。
2. **🏛️ 领域奠基之作（Foundations - 巨人的肩膀）**：
   * 列出年均引用量最高的 3~5 篇经典，标明年份与核心贡献方向。
3. **🧬 核心亲缘文献（Kin / Direct Offshoots - 紧密同宗）**：
   * 列出与种子文献参考文献重合度最高的 3~5 篇论文（说明共同研究的方法或问题）。
4. **🚀 近年重要进展（Recent Highlights）**：
   * 列出近 3 年内的高权重成果。
5. **📊 图谱文件交互链接**：
   * 必须提供可直接点击的文件链接（file 协议格式，直接从脚本输出中的实际绝对路径提取）：
     * 🌐 **交互式网页图谱**：`[打开交互式网络图谱](file:///<path_to_html>)`（用户双击可在浏览器中拖拽节点、缩放与探索）
     * 🖼️ **静态全景图**：`[查看高清网络图 PNG](file:///<path_to_png>)`
     * 📄 **数据清单**：`[核心节点明细 CSV](file:///<path_to_csv>)`
6. **主动追问后续动作**：
   * 提示用户：“是否需要挑选其中感兴趣的文献，通过 `scansci-pdf` 自动下载全文 PDF？”
