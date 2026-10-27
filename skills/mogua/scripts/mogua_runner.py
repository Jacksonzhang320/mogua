#!/usr/bin/env python3
"""Mogua (摸瓜) - 顺藤摸瓜学术文献引文网络与脉络挖掘执行器"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def find_workspace() -> Path:
    """Dynamically locate the Mogua workspace / pipeline root."""
    if os.environ.get("MOGUA_WORKSPACE"):
        p = Path(os.environ["MOGUA_WORKSPACE"]).resolve()
        if (p / "run_pipeline.py").exists():
            return p

    # Current working directory
    cwd = Path.cwd().resolve()
    if (cwd / "run_pipeline.py").exists():
        return cwd

    for parent in cwd.parents:
        if (parent / "run_pipeline.py").exists():
            return parent

    # Relative to this script (e.g. repo/skills/mogua/scripts/...)
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir, *script_dir.parents]:
        if (parent / "run_pipeline.py").exists():
            return parent

    # Check if pipeline_modules or run_pipeline is importable (when installed via pip/uv)
    try:
        import pipeline_modules
        if hasattr(pipeline_modules, "__file__") and pipeline_modules.__file__:
            mod_p = Path(pipeline_modules.__file__).resolve().parent
            if (mod_p / "run_pipeline.py").exists():
                return mod_p
    except Exception:
        pass

    try:
        import run_pipeline
        if hasattr(run_pipeline, "__file__") and run_pipeline.__file__:
            mod_p = Path(run_pipeline.__file__).resolve().parent
            if (mod_p / "run_pipeline.py").exists():
                return mod_p
    except Exception:
        pass

    return cwd


WORKSPACE = find_workspace()
RUN_PIPELINE = WORKSPACE / "run_pipeline.py"


def find_python() -> str:
    """Find the best python executable to run the pipeline."""
    # 1. If currently executing under a python that has pipeline_modules, use sys.executable
    try:
        import pipeline_modules  # noqa: F401
        return sys.executable
    except ImportError:
        pass

    # 2. Check WORKSPACE / .venv
    venv_py = WORKSPACE / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv_py.exists():
        return str(venv_py)

    # 3. Check CWD / .venv
    cwd_venv_py = Path.cwd() / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if cwd_venv_py.exists():
        return str(cwd_venv_py)

    # 4. Check if mogua command is in PATH
    import shutil
    mogua_cmd = shutil.which("mogua")
    if mogua_cmd:
        bin_dir = Path(mogua_cmd).parent
        candidate = bin_dir / ("python.exe" if os.name == "nt" else "python")
        if candidate.exists():
            return str(candidate)

    return sys.executable


PYTHON_EXE = find_python()

sys.path.insert(0, str(WORKSPACE))
try:
    import config_local
    OPENALEX_KEY = getattr(config_local, "OPENALEX_API_KEY", "")
except ImportError:
    OPENALEX_KEY = os.environ.get("OPENALEX_API_KEY", "")


def normalize_doi(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    val = value.strip().lower()
    val = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", val)
    val = re.sub(r"^doi:\s*", "", val)
    val = val.rstrip("/.,; ")
    return val if val.startswith("10.") and "/" in val else None


def resolve_doi_from_title(title_query: str) -> dict[str, str] | None:
    """Use OpenAlex to search title and obtain DOI."""
    import requests

    headers = {"User-Agent": "mogua-skill/1.0 (academic-citation-crawler)"}
    params: dict[str, str | int] = {
        "filter": f"title.search:{title_query}",
        "sort": "cited_by_count:desc",
        "per_page": 5,
    }
    if OPENALEX_KEY:
        params["api_key"] = OPENALEX_KEY

    try:
        r = requests.get("https://api.openalex.org/works", params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            for item in data.get("results", []):
                doi = normalize_doi(item.get("doi"))
                if doi:
                    return {
                        "doi": doi,
                        "title": item.get("title", ""),
                        "year": str(item.get("publication_year", "")),
                        "citations": item.get("cited_by_count", 0),
                        "journal": (item.get("primary_location") or {}).get("source", {}).get("display_name", "") if isinstance(item.get("primary_location"), dict) else "",
                    }
    except Exception as exc:
        print(f"Error searching OpenAlex: {exc}", file=sys.stderr)
    return None


def run_pipeline(
    doi: str,
    output_dir: Path | None = None,
    depth: int = 1,
    max_neighbors: int = 100,
    top_n: int = 15,
    top_m: int = 20,
    smart_expand: int = 0,
) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", doi.lower()).strip("_")[-48:]
    target_out = output_dir or (WORKSPACE / "runs" / f"{slug}_d{depth}")
    target_out.mkdir(parents=True, exist_ok=True)

    if RUN_PIPELINE.exists():
        cmd = [
            PYTHON_EXE,
            str(RUN_PIPELINE),
            "--doi", doi,
            "--output-dir", str(target_out),
            "--depth", str(depth),
            "--max-neighbors", str(max_neighbors),
            "--top-n", str(top_n),
            "--top-m", str(top_m),
        ]
    else:
        cmd = [
            PYTHON_EXE,
            "-m", "run_pipeline",
            "--doi", doi,
            "--output-dir", str(target_out),
            "--depth", str(depth),
            "--max-neighbors", str(max_neighbors),
            "--top-n", str(top_n),
            "--top-m", str(top_m),
        ]
    if smart_expand > 0:
        cmd.extend(["--smart-expand", str(smart_expand)])

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True, text=True, encoding="utf-8", env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Pipeline run failed (code {result.returncode}):\n{result.stderr}\n{result.stdout}")

    return target_out


def parse_results(run_dir: Path) -> dict[str, object]:
    analysis_dir = run_dir / "analysis_results"
    summary_path = analysis_dir / "summary.json"
    nodes_path = analysis_dir / "nodes_core.csv"

    summary = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    nodes: list[dict[str, str]] = []
    if nodes_path.exists():
        with open(nodes_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            nodes = list(reader)

    seed_node = next((n for n in nodes if n.get("IsSeed") == "1"), None)
    if not seed_node and nodes:
        seed_node = nodes[0]

    other_nodes = [n for n in nodes if n != seed_node]

    # Foundations: highest CitationPerYear
    foundations = sorted(
        other_nodes,
        key=lambda x: float(x.get("CitationPerYear", 0) or 0),
        reverse=True
    )[:5]

    # Kin: highest Similarity (Jaccard on references)
    kin = sorted(
        other_nodes,
        key=lambda x: float(x.get("Similarity", 0) or 0),
        reverse=True
    )[:5]

    # Recent high-impact: year within last 3 years, sorted by AdjustedScore
    current_year = 2026
    recent_nodes = [n for n in other_nodes if n.get("Year") and n["Year"].isdigit() and int(n["Year"]) >= current_year - 3]
    recent = sorted(
        recent_nodes,
        key=lambda x: float(x.get("AdjustedScore", 0) or 0),
        reverse=True
    )[:5]

    html_file = analysis_dir / "core_network_enhanced.html"
    png_file = analysis_dir / "core_network_enhanced.png"
    svg_file = analysis_dir / "core_network_enhanced.svg"

    return {
        "summary": summary,
        "seed": seed_node,
        "foundations": foundations,
        "kin": kin,
        "recent": recent,
        "total_core_nodes": len(nodes),
        "files": {
            "html": str(html_file.resolve()) if html_file.exists() else "",
            "png": str(png_file.resolve()) if png_file.exists() else "",
            "svg": str(svg_file.resolve()) if svg_file.exists() else "",
            "nodes_csv": str(nodes_path.resolve()) if nodes_path.exists() else "",
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Mogua: 顺藤摸瓜学术文献引文网络挖掘工具")
    parser.add_argument("query", help="论文 DOI、链接或论文标题")
    parser.add_argument("--depth", type=int, default=1, help="爬取深度 (默认 1)")
    parser.add_argument("--max-neighbors", type=int, default=100, help="每篇论文最大邻居数 (默认 100)")
    parser.add_argument("--top-n", type=int, default=15, help="保留高引核心节点数 (默认 15)")
    parser.add_argument("--top-m", type=int, default=20, help="保留强相似节点数 (默认 20)")
    parser.add_argument("--smart-expand", type=int, default=0, help="深度2智能扩展Top-K论文数 (默认 0)")
    parser.add_argument("--output-dir", type=Path, help="自定义输出目录")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    args = parser.parse_args()

    raw_query = args.query.strip()
    doi = normalize_doi(raw_query)

    if not doi:
        # Try title search via OpenAlex
        match = resolve_doi_from_title(raw_query)
        if match and match.get("doi"):
            doi = match["doi"]
            if not args.json:
                print(f"[Mogua] 通过标题检索锁定论文: 《{match.get('title')}》 ({match.get('year')})")
                print(f"[Mogua] 解析得到 DOI: {doi}")
        else:
            print(f"[Mogua 错误] 未能识别输入的 DOI，亦未能通过标题搜索匹配到论文: '{raw_query}'", file=sys.stderr)
            sys.exit(1)

    if not args.json:
        print(f"[Mogua] 开始对种子文献顺藤摸瓜: {doi}")
        print(f"[Mogua] 参数配置: depth={args.depth}, neighbors={args.max_neighbors}, top_n={args.top_n}, top_m={args.top_m}")

    run_dir = run_pipeline(
        doi,
        output_dir=args.output_dir,
        depth=args.depth,
        max_neighbors=args.max_neighbors,
        top_n=args.top_n,
        top_m=args.top_m,
        smart_expand=args.smart_expand,
    )

    results = parse_results(run_dir)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    # Text output
    seed = results.get("seed") or {}
    print("\n" + "=" * 60)
    print(f"🌱 种子文献: {seed.get('Title')} ({seed.get('Year')})")
    print(f"   DOI: {seed.get('DOI')} | 期刊: {seed.get('Journal')} | 被引: {seed.get('CitedByCount')}")
    print(f"   作者: {seed.get('Authors')}")
    print("=" * 60)

    print("\n🏛️ 奠基之作 (高年均引用 Top 5 - 该领域的理论与方法基石):")
    for idx, f in enumerate(results.get("foundations", []), start=1):
        print(f"  {idx}. 《{f.get('Title')}》 ({f.get('Year')}) - {f.get('Journal')}")
        print(f"     DOI: {f.get('DOI')} | 年均引用: {float(f.get('CitationPerYear',0)):.1f} | 相似度: {float(f.get('Similarity',0)):.2%}")

    print("\n🧬 强相关亲缘文献 (参考文献重合度 Top 5 - 脉络直接延伸与共同关注点):")
    for idx, k in enumerate(results.get("kin", []), start=1):
        print(f"  {idx}. 《{k.get('Title')}》 ({k.get('Year')}) - {k.get('Journal')}")
        print(f"     DOI: {k.get('DOI')} | 参考文献 Jaccard 相似度: {float(k.get('Similarity',0)):.2%} | 被引: {k.get('CitedByCount')}")

    recents = results.get("recent", [])
    if recents:
        print("\n🚀 近年重要进展 (近3年高权重新成果):")
        for idx, r in enumerate(recents, start=1):
            print(f"  {idx}. 《{r.get('Title')}》 ({r.get('Year')}) - {r.get('Journal')}")
            print(f"     DOI: {r.get('DOI')} | 被引: {r.get('CitedByCount')}")

    files = results.get("files", {})
    print("\n📊 可视化与分析文件交付:")
    if files.get("html"):
        print(f"  - 交互式网页图谱 (点击直接探索): {files['html']}")
    if files.get("png"):
        print(f"  - 静态图谱图片: {files['png']}")
    if files.get("nodes_csv"):
        print(f"  - 核心节点完整列表: {files['nodes_csv']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
