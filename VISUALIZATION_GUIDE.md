# 可视化生成完整流程：从 9,805 篇到 36 个节点

## 📊 数据流动全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        数据流动与筛选流程                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  OpenAlex API                                                       │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 1: 数据获取 (9,805 篇原始 JSON)                        │   │
│  │                                                               │   │
│  │  raw_data/                                                   │   │
│  │    ├── W7128429791.json  (种子论文)                         │   │
│  │    ├── W2104783780.json  (被引文献)                         │   │
│  │    ├── W2794283863.json  (参考文献)                         │   │
│  │    └── ... (9,802 个其他文件)                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 2: 元数据提取                                           │   │
│  │                                                               │   │
│  │  从每个 JSON 提取:                                           │   │
│  │    - Id: W7128429791                                         │   │
│  │    - Title: "Cortical traveling..."                         │   │
│  │    - Year: 2026                                             │   │
│  │    - CitedByCount: 0                                        │   │
│  │    - DOI: "10.1016/j.neuron..."                             │   │
│  │    - Authors: "Jace Cruddas; ..."                           │   │
│  │    - ReferencedWorks: [Wxxx, Wyyy, ...]  ← 用于相似度计算   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 3: 评分与筛选 (核心算法)                                │   │
│  │                                                               │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ A. 影响力评分 (CitationPerYear)                      │   │   │
│  │  │                                                      │   │   │
│  │  │  论文 | 年份 | 被引数 | 年龄 | CitationPerYear       │   │   │
│  │  │  -----|------|--------|------|----------------       │   │   │
│  │  │  R    | 2000 | 352817 | 27  | 13,071 ⭐ Top 1      │   │   │
│  │  │  LSTM | 1997 | 94647  | 30  | 3,155 ⭐ Top 2       │   │   │
│  │  │  ...  | ...  | ...    | ... | ...                   │   │   │
│  │  │  种子 | 2026 | 0      | 1   | 0 (但强制包含)        │   │   │
│  │  │                                                      │   │   │
│  │  │  ✅ 选出 Top 15 → 高影响力集合                        │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                               │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ B. 相似度评分 (Jaccard on References)                │   │   │
│  │  │                                                      │   │   │
│  │  │  种子论文参考文献: {A, B, C, D, E}                   │   │   │
│  │  │                                                      │   │   │
│  │  │  候选X: {A, B, F, G}        → Jaccard = 2/7 = 0.29  │   │   │
│  │  │  候选Y: {A, B, C, H}        → Jaccard = 3/6 = 0.50  │   │   │
│  │  │  候选Z: {C, D, E, I, J}     → Jaccard = 3/7 = 0.43  │   │   │
│  │  │                                                      │   │   │
│  │  │  ✅ 选出 Top 20 → 高相似度集合                        │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                               │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ C. 合并核心节点                                      │   │   │
│  │  │                                                      │   │   │
│  │  │  Core_Nodes = Seeds (1)                             │   │   │
│  │  │              ∪ High_Impact (15)                     │   │   │
│  │  │              ∪ High_Similarity (20)                 │   │   │
│  │  │              = 36 unique nodes                      │   │   │
│  │  │                                                      │   │   │
│  │  │  注意: 可能有重叠！                                 │   │   │
│  │  │  - 种子论文可能也是高相似度                          │   │   │
│  │  │  - 高影响力论文可能也是高相似度                      │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 4: 构建边关系                                           │   │
│  │                                                               │   │
│  │  FOR each node IN core_nodes:                                │   │
│  │    FOR each ref IN node.referenced_works:                    │   │
│  │      IF ref IN core_nodes:                                   │   │
│  │        ADD edge (node → ref)                                │   │
│  │                                                               │   │
│  │  结果: 68 条有向边                                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 5: 节点属性增强                                         │   │
│  │                                                               │   │
│  │  从原始 JSON 重新读取:                                        │   │
│  │    - primary_location.source.display_name → 期刊             │   │
│  │    - concepts → 研究领域                                     │   │
│  │                                                               │   │
│  │  FOR each node:                                              │   │
│  │    node.label = "First Author et al.\n{Journal}\n{Year}"    │   │
│  │    node.color = ClassifyByDomain(concepts)                   │   │
│  │    node.size = 10 + log(citations) * 3                       │   │
│  │    node.title = "{Title}\n{Journal}\n{Authors}\n..."        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 6: NetworkX + Pyvis 生成可视化                         │   │
│  │                                                               │   │
│  │  1. 创建 NetworkX 有向图                                     │   │
│  │  2. 添加节点 (36个, 带属性)                                  │   │
│  │  3. 添加边 (68条, 有向)                                      │   │
│  │  4. 导入 Pyvis                                               │   │
│  │  5. 配置物理引擎 (Barnes-Hut)                                │   │
│  │  6. 生成 HTML + JavaScript                                   │   │
│  │  7. 注入自定义图例                                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Step 7: 交互式 HTML                                          │   │
│  │                                                               │   │
│  │  core_network_enhanced.html (31KB)                          │   │
│  │    ├── vis.js (物理引擎 + 渲染)                              │   │
│  │    ├── 节点数据 (36个)                                       │   │
│  │    ├── 边数据 (68条)                                         │   │
│  │    ├── 可拖动图例                                             │   │
│  │    └── 物理配置                                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔍 逐步演示：具体例子

让我用实际数据演示整个过程：

### 第一步：从原始数据开始

```bash
# 检查原始数据
$ ls raw_data/ | wc -l
9805

# 查看种子论文的 JSON
$ cat raw_data/W7128429791.json | jq '.title, .year, .cited_by_count'
"Cortical traveling waves in time and space..."
2026
0

# 查看种子论文引用了谁
$ cat raw_data/W7128429791.json | jq '.referenced_works[0:3]'
[
  "https://openalex.org/W650934453",
  "https://openalex.org/W1449393047",
  "https://openalex.org/W1491926324"
]
```

### 第二步：提取所有论文的元数据

```python
# 伪代码
all_metadata = []
for json_file in raw_data_dir:
    data = load_json(json_file)

    # 提取基本信息
    metadata = {
        'Id': data['id'].split('/')[-1],
        'Title': data['title'],
        'Year': data['publication_year'],
        'CitedByCount': data['cited_by_count'],
        'DOI': data['doi'],
        'Authors': join_authors(data['authorships']),
        'ReferencedWorks': extract_ids(data['referenced_works'])  # ← 关键！
    }
    all_metadata.append(metadata)

# 结果: 9,805 行的元数据表
# 保存到: nodes_full.csv (内部使用，不输出)
```

### 第三步：计算影响力分数

```python
# 对每一篇论文计算
for paper in all_metadata:
    age = 2026 - paper['Year'] + 1
    citation_per_year = paper['CitedByCount'] / age

# 排序并取 Top 15
sorted_by_impact = sorted(all_metadata,
                         key=lambda x: x['citation_per_year'],
                         reverse=True)

top_15_impact = sorted_by_impact[:15]

# 结果示例:
# 1. R (2000) - 352817 cites → 13071 cites/year
# 2. LSTM (1997) - 94647 cites → 3155 cites/year
# ...
# 15. Nature Reviews Neuroscience (2018) - 616 cites → 77 cites/year
```

### 第四步：计算相似度分数

```python
# 获取种子论文的参考文献集合
seed_refs = set(seed_paper['ReferencedWorks'])
# {W650934453, W1449393047, W1491926324, ...}

# 对每篇非种子论文计算 Jaccard 相似度
similarity_scores = {}
for paper in all_metadata:
    if paper['Id'] == seed_id:
        continue

    paper_refs = set(paper['ReferencedWorks'])
    if not paper_refs:
        continue

    # Jaccard 相似度
    intersection = len(seed_refs & paper_refs)
    union = len(seed_refs | paper_refs)
    jaccard = intersection / union if union > 0 else 0

    if jaccard > 0:
        similarity_scores[paper['Id']] = jaccard

# 排序并取 Top 20
top_20_similarity = sorted(similarity_scores.items(),
                          key=lambda x: x[1],
                          reverse=True)[:20]

# 结果示例:
# 1. W2794283863 → 0.45 (Cortical travelling waves review)
# 2. W2104783780 → 0.38 (Traveling Waves in Visual Cortex)
# ...
```

### 第五步：合并并去重

```python
# 三个集合
seed_ids = {seed_id}  # 1 个
high_impact_ids = {p['Id'] for p in top_15_impact}  # 15 个
high_similarity_ids = {id for id, _ in top_20_similarity}  # 20 个

# 合并
core_node_ids = seed_ids | high_impact_ids | high_similarity_ids

# 去重 (可能有重叠)
# 例如: 某篇论文既是高影响力又与种子相似
print(f"Total unique nodes: {len(core_node_ids)}")
# 输出: 36

# 过滤元数据
core_nodes = [n for n in all_metadata if n['Id'] in core_node_ids]

# 保存到 CSV
save_csv('nodes_core.csv', core_nodes)
# 结果: 36 行
```

### 第六步：构建边关系

```python
# 只保留核心节点之间的边
core_edges = []
for source_id in core_node_ids:
    source_refs = get_refs(source_id)

    for target_id in source_refs:
        if target_id in core_node_ids:
            core_edges.append({
                'Source': source_id,
                'Target': target_id,
                'Type': 'Directed'
            })

# 去重
core_edges = unique(core_edges)

print(f"Total edges: {len(core_edges)}")
# 输出: 68

# 保存到 CSV
save_csv('edges_core.csv', core_edges)
```

### 第七步：增强节点属性

```python
# 从原始 JSON 重新读取期刊和概念
for node in core_nodes:
    # 读取原始 JSON
    json_path = f"raw_data/{node['Id']}.json"
    data = load_json(json_path)

    # 提取期刊
    location = data.get('primary_location', {})
    source = location.get('source', {})
    node['Journal'] = source.get('display_name', 'Unknown')

    # 提取概念
    node['Concepts'] = data.get('concepts', [])

    # 分类
    node['Domain'] = classify_paper(node['Title'], node['Concepts'])
```

### 第八步：生成可视化

```python
# 创建 NetworkX 图
G = nx.DiGraph()

# 添加节点
for node in core_nodes:
    G.add_node(node['Id'],
               label=format_label(node),  # "Author et al.\nJournal\nYear"
               color=DOMAIN_COLORS[node['Domain']],
               size=calculate_size(node['CitedByCount']),
               title=format_tooltip(node))  # 鼠标悬停信息

# 添加边
for edge in core_edges:
    G.add_edge(edge['Source'],
               edge['Target'])

# 使用 Pyvis 生成 HTML
net = Network(bgcolor="#1a1a2e", directed=True)
net.from_nx(G)
net.save_graph('core_network_enhanced.html')
```

---

## 📊 数据对比：9,805 → 36

| 指标 | 原始数据 | 核心网络 | 压缩比 |
|------|----------|----------|--------|
| 节点数 | 9,805 | 36 | 99.6% ↓ |
| 边数 | ~50,000 (估计) | 68 | 99.9% ↓ |
| 文件大小 | ~500MB (JSON) | 31KB (HTML) | 99.99% ↓ |

---

## 🎨 可视化技术栈

```
┌─────────────────────────────────────────────────────────────┐
│                      可视化技术栈                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Python Layer:                                              │
│    ├── pandas (数据处理)                                    │
│    ├── networkx (图结构)                                    │
│    ├── numpy (数值计算)                                     │
│    └── pyvis (HTML生成)                                     │
│                                                             │
│  HTML/JavaScript Layer:                                     │
│    ├── vis.js (物理引擎 + 渲染)                             │
│    │   ├── Barnes-Hut 算法 (力导向布局)                     │
│    │   ├── Canvas 渲染 (高性能绘图)                         │
│    │   └── 交互事件 (拖拽、缩放、悬停)                      │
│    ├── 自定义图例 (可拖动 div)                              │
│    └── 物理参数配置                                         │
│                                                             │
│  浏览器渲染:                                                │
│    └── 用户打开 HTML → vis.js 运行 → 交互式图谱             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 💡 为什么这样设计？

### Q1: 为什么要筛选到 36 个节点？
**A**: 可读性和可解释性
- 9,805 个节点无法直观理解
- 36 个节点可以人工审查每篇论文
- 核心网络保留了最重要的连接

### Q2: 不在核心网络中的论文就浪费了吗？
**A**: 不！它们用于计算
- 相似度计算需要所有论文的参考文献
- 影响力排序需要所有论文的数据
- 只是最终展示时只显示最相关的

### Q3: 可以调整核心网络大小吗？
**A**: 可以！修改参数
```python
TOP_N_BY_CITATION_SCORE = 30  # 增加到 30
TOP_M_BY_SIMILARITY = 40       # 增加到 40
# 结果: 核心网络会更大 (约 60-70 个节点)
```

---

生成时间: 2026-03-20
