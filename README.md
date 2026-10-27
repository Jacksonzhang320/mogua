# 🍈 Mogua (摸瓜)

> **From One Paper to an Entire Citation Network · 从单篇论文到一个网络**  
> 真实可溯源的文献脉络与知识图谱挖掘工具（本地轻量 Connected Papers 替代方案 + AI Agent 原生技能）

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](pyproject.toml)
[![Data Source: OpenAlex](https://img.shields.io/badge/Data%20Source-OpenAlex%20API-orange.svg)](https://openalex.org)
[![Agent Ready](https://img.shields.io/badge/AI%20Agent-Skill%20Ready-purple.svg)](skills/mogua)

---

## 🌟 为什么需要 Mogua？

在阅读学术论文时，最耗时的一步往往是**“顺藤摸瓜”**（Citation Snowballing）：
* *这篇文章究竟站在哪些巨人的肩膀上？（历史奠基文献）*
* *有哪些同行在用同样的方法或关注同样的问题？（核心亲缘文献）*
* *这个领域最近有哪些最重要的后续突破？（最新进展）*

传统的商业工具（如 Connected Papers、ResearchRabbit、Litmaps）要么限制免费次数、收取高昂月费，要么必须依赖云端且无法本地深度定制；而直接让商业大模型推荐文献，又极其容易遭遇**“引用幻觉”**（编造假 DOI、虚构作者与年份）。

**Mogua (摸瓜)** 提供了一套纯本地、完全免费、真实可信的解决方案：从输入一篇种子论文开始，全自动抓取引文拓扑，经过严格的双轨数学算法筛选，最终交付**单文件交互式知识图谱**与结构化导读。

---

## ✨ 核心特性

### 1. 真实可溯源，拒绝大模型幻觉 (100% Grounded & Verifiable)
* 底层数据直连全球最大开放学术知识库 **OpenAlex 官方 API**（涵盖数亿篇论文、作者与引文图谱）；
* 每一篇入选文献、每一条引用边均有确凿的真实 DOI 证据链，杜绝任何生成式大模型的虚构幻觉。

### 2. 双轨收敛算法 (Dual-Ranked Distillation)
从一篇种子论文出发，其上下游关联文献往往迅速膨胀至数千篇（造成“毛线团乱麻”）。Mogua 采用双轨算法，精准收敛为 **30~50 篇骨架核心网络**：
* 🏛️ **历史奠基（Foundations）**：按年均引用量（$\text{CitationPerYear} = \frac{\text{Citations}}{\text{Age}}$）排序，筛选出经受住时间检验的理论与方法学基石；
* 🧬 **同宗亲缘（Direct Kin）**：基于参考文献集合交并比（$\text{Jaccard} = \frac{|Ref_A \cap Ref_B|}{|Ref_A \cup Ref_B|}$）计算**书目耦合（Bibliographic Coupling）**，精准锁定研究切入点最为紧密的同行工作；
* 🚀 **近年突破（Recent Advances）**：自动提炼近 3 年的高权重学术新成果。

### 3. 高颜值、可靠稳定的单文件交互图谱 (Reliable Interactive Vis)
* **单文件 HTML 离线秒开**：基于 Vis.js 构建，内嵌离线资产，无需配置复杂的前后端服务或数据库，双击即可在任意浏览器打开；
* **三维切换模式**：
  * 🌐 **主题社群（Topic Clusters）**：基于图论模块度（Modularity）自动识别研究子方向社群；
  * 🏷️ **学术角色（Academic Roles）**：一目了然区分种子、基石、亲缘与最新成果；
  * 📅 **时间线渐变（Timeline Gradient）**：从早期经典到最新文献的渐变热力图；
* **防晃动自稳定物理引擎**：自动稳定后自动冻结物理模拟，杜绝节点乱跳漂移；
* **即时检索与高亮探索**：悬停/点击任意文献，一键高亮其一阶上下游引用链（出边/入边分色区分），点击引用链接可平滑缩放跳转；
* **全景出版级导出**：同步输出 300 DPI 高清 PNG 与矢量 SVG 静态图。

### 4. 配合下载形成完整研读闭环 (Downstream Synergy)
* 摸出核心脉络后，可无缝配合学术下载工具（如 `scansci-pdf`）或自身 Open Access 直链，一键批量获取全文 PDF，形成 **“种子论文 ➔ 引文网络 ➔ 骨架筛选 ➔ 极速下载 ➔ 精读解析”** 的完整研究链路。

### 5. 双重形态：命令行工具 + AI Agent 原生技能
* **CLI 命令行**：科学家与程序员在终端一行命令快速出图；
* **AI Agent Skill**：原生支持 Claude Code、Antigravity、Cursor、Codex 等智能体，用户只需在对话中说一句“以这篇论文为种子顺藤摸瓜”，Agent 即可自动执行并生成结构化分析。

---

## 🚀 快速上手 (Quick Start)

### 1. 一键安装环境（二选一）

#### 方式 A：全局独立安装（强烈推荐，隔离依赖且跨项目可用）
推荐使用现代 `uv tool` 或 `pipx`，一行命令即可在独立隔离沙盒中安装全部依赖并自动注册 `mogua` 全局命令：
```bash
# 推荐使用 uv（极速，跨平台）：
uv tool install git+https://github.com/Jacksonzhang320/mogua.git

# 或使用 pipx：
pipx install git+https://github.com/Jacksonzhang320/mogua.git
```

#### 方式 B：源码克隆安装
```bash
# 1. 克隆真实代码仓库
git clone https://github.com/Jacksonzhang320/mogua.git
cd mogua

# 2. 安装依赖（支持普通安装与可编辑开发模式）
uv venv
uv pip install -e .
# 或使用标准 pip: pip install -e .
```

### 2. 配置 OpenAlex API Key（可选，推荐配置以获得更高频控）

OpenAlex API 默认支持免 Key 直接访问（自动走公共 Polite 队列）。若需进行大规模爬取，建议免费申请 Key 获取每秒 10~20 次并发：
1. 访问 [https://openalex.org/](https://openalex.org/) 注册账号并在个人设置中复制 API Key；
2. **配置方式（二选一）：**
   * **方式 A（配置文件）**：复制 `config_local.example.py` 为 `config_local.py`，填入 `OPENALEX_API_KEY = "your_key"`；
   * **方式 B（环境变量）**：
     ```bash
     export OPENALEX_API_KEY="your_key_here"      # Linux/macOS
     $env:OPENALEX_API_KEY="your_key_here"        # Windows PowerShell
     ```

---

## 💻 命令行使用 (CLI Usage)

```bash
# 1. 传入任意 DOI（支持纯 DOI 或 doi.org 链接）
mogua "10.1016/j.cell.2024.08.046"

# 2. 直接传入论文标题（自动连接 OpenAlex 检索权威文献并反查 DOI）
mogua "Attention Is All You Need"

# 3. 自定义参数（控制挖掘深度与节点数量）
mogua --doi "10.1038/nature14539" --depth 1 --max-neighbors 100 --top-n 15 --top-m 20
```

### 核心参数说明

| 参数 | 默认值 | 作用说明 |
| :--- | :---: | :--- |
| `query` / `--doi` | (必填) | 论文 DOI、链接或论文完整标题 |
| `--depth` | `1` | 爬取深度。`1` 适合大部分单篇溯源；`2` 用于深度二级滚雪球 |
| `--max-neighbors` | `100` | 限制每篇论文抓取的最大引用/参考文献数，防巨型文献耗时过长 |
| `--top-n` | `15` | 保留的高引经典基石节点数 |
| `--top-m` | `20` | 保留的高 Jaccard 相似度亲缘节点数 |
| `--smart-expand` | `0` | 在 Depth 2 中智能筛选 Top K 关键论文进行选择性展开 |
| `--skip-plot` | `False` | 仅计算网络数据，跳过 HTML/PNG 出图 |

---

## 🤖 AI Agent 技能集成 (Agent Skill)

Mogua 仓库自带开箱即用的 Agent Skill 定义，位于 `skills/mogua/`。

### 安装到您的 Agent

克隆项目并执行过环境安装（`uv pip install -e .` 或 `pip install -e .`）后，即可挂载到各大智能体：

* **Antigravity / Codex 用户**：
  将 `skills/mogua` 文件夹复制或软链接至 `~/.agents/skills/mogua`；
* **Claude Code 用户**：
  将 `skills/mogua` 复制到当前项目的 `.claude/skills/mogua` 或全局 skills 目录。

> 💡 **零路径配置**：Skill 内部执行脚本具备自适应工作区与 Python 探测能力，只要在已安装 `mogua` 依赖的环境下运行，无需手动修改任何硬编码绝对路径。

### 在 Agent 对话中一键唤醒
安装完成后，在日常对话中只需简单输入自然语言：
> * “以这篇论文为种子摸一下瓜：`10.1016/j.cell.2024.08.046`”  
> * “顺藤摸瓜找一下《Attention Is All You Need》的核心脉络”  
> * “读完这篇想做个文献图谱，帮我摸摸它前后的关键文献”

Agent 将自动在后台调用 Mogua 挖掘核心引文，并返回分类导读表格（奠基之作、同宗亲缘、最新进展）与可直接点击查看的本地 HTML 图谱。

---

## 📊 输出产物说明

运行完成后，结果将保存在 `runs/<slug>_d<depth>/analysis_results/` 目录下：

```text
analysis_results/
├── core_network_enhanced.html    # 🌟 单文件独立交互式网页图谱（双击在浏览器中探索）
├── core_network_enhanced.png     # 🖼️ 300 DPI 高清全景网络图（可用于论文、报告或 PPT）
├── core_network_enhanced.svg     # 📐 矢量图（无损缩放，支持矢量制图软件二次排版）
├── nodes_core.csv                # 📄 核心节点明细表（含 DOI、引用量、年均引用、Jaccard 分数）
├── edges_core.csv                # 🔗 核心节点之间的引用关系拓扑边
└── summary.json                  # 📋 全局汇总统计（总抓取量、收敛率、核心节点数）
```

---

## 📄 开源协议 (License)

本项目采用 [MIT License](LICENSE) 许可协议。
欢迎提出 Issue 与 Pull Request！
