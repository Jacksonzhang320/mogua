from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

from pipeline_modules import OA_API_URL, Step2_NetworkCrawler, Step3_FilterAndBuild, normalize_doi

try:
    import config_local
    OPENALEX_KEY = getattr(config_local, "OPENALEX_API_KEY", "")
except ImportError:
    OPENALEX_KEY = os.environ.get("OPENALEX_API_KEY", "")


def resolve_doi_from_title(title_query: str) -> dict[str, str] | None:
    headers = {"User-Agent": "mogua/1.0 (academic-citation-crawler)"}
    params: dict[str, str | int] = {
        "filter": f"title.search:{title_query}",
        "sort": "cited_by_count:desc",
        "per_page": 5,
    }
    if OPENALEX_KEY:
        params["api_key"] = OPENALEX_KEY

    try:
        r = requests.get(f"{OA_API_URL}/works", params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            for item in data.get("results", []):
                doi = normalize_doi(item.get("doi"))
                if doi:
                    return {
                        "doi": doi,
                        "title": item.get("title", ""),
                        "year": str(item.get("publication_year", "")),
                        "citations": str(item.get("cited_by_count", 0)),
                    }
    except Exception as exc:
        logging.warning("Failed to search title via OpenAlex: %s", exc)
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mogua: Recoverable DOI citation-network pipeline")
    parser.add_argument("query", nargs="?", default="", help="Paper DOI, URL, or Title")
    parser.add_argument("--doi", default="", help="Explicit Paper DOI")
    parser.add_argument("--output-dir", type=Path, help="Custom output directory")
    parser.add_argument("--depth", type=int, default=1, help="Crawl depth (default: 1)")
    parser.add_argument("--max-neighbors", type=int, default=100, help="Max references/citations per paper (default: 100)")
    parser.add_argument("--top-n", type=int, default=15, help="Core high-impact nodes (default: 15)")
    parser.add_argument("--top-m", type=int, default=20, help="Core similarity nodes (default: 20)")
    parser.add_argument("--max-items", type=int, help="Trial limit")
    parser.add_argument("--provider", choices=("auto", "openalex", "opencitations"), default="auto")
    parser.add_argument("--skip-plot", action="store_true", help="Skip visualization generation")
    parser.add_argument("--smart-expand", type=int, default=0, help="Top K Depth 2 papers to selectively expand")
    parser.add_argument("--force", action="store_true", help="Force rebuilding analysis results even if they exist")
    return parser.parse_args()


def main() -> Path:
    args = parse_args()
    raw = (args.doi or args.query or "").strip()
    if not raw:
        raise SystemExit("Error: Please provide a paper DOI or title. Run with --help for usage.")

    doi = normalize_doi(raw)
    if not doi:
        # Attempt title lookup
        print(f"[Mogua] Searching OpenAlex for title: '{raw}'...")
        match = resolve_doi_from_title(raw)
        if match and match.get("doi"):
            doi = match["doi"]
            print(f"[Mogua] Found: 《{match.get('title')}》 ({match.get('year')}) | Citations: {match.get('citations')}")
            print(f"[Mogua] Resolved DOI: {doi}")
        else:
            raise SystemExit(f"Error: Could not resolve DOI for: '{raw}'")

    slug = re.sub(r"[^a-z0-9]+", "_", doi.lower()).strip("_")[-48:]
    out = args.output_dir or Path("runs") / f"{slug}_d{args.depth}"
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "run.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
    )
    (out / "seed_dois.txt").write_text(doi + "\n", encoding="utf-8")
    logging.info("Run directory: %s", out.resolve())

    crawler = Step2_NetworkCrawler(
        out,
        [doi],
        fetch_depth=args.depth,
        max_neighbors=args.max_neighbors,
        max_items=args.max_items,
        provider=args.provider,
    )
    crawler.run()
    if args.max_items is not None:
        logging.info("Trial finished after max-items=%s", args.max_items)
        return out

    if args.smart_expand > 0:
        crawler.smart_expand_depth2(top_k=args.smart_expand)

    rebuild = args.force or (args.smart_expand > 0)
    Step3_FilterAndBuild(out, [doi], top_n=args.top_n, top_m=args.top_m, force=rebuild).run(force=rebuild)

    if not args.skip_plot:
        plot_script = Path(__file__).resolve().parent / "plotting" / "plot_enhanced.py"
        subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                str(plot_script),
                "--nodes",
                str(out / "analysis_results" / "nodes_core.csv"),
                "--edges",
                str(out / "analysis_results" / "edges_core.csv"),
                "--output",
                str(out / "analysis_results" / "core_network_enhanced"),
            ],
            check=True,
        )

    logging.info("Pipeline complete: %s", out.resolve())
    html_path = out / "analysis_results" / "core_network_enhanced.html"
    if html_path.exists():
        print(f"\n[Mogua] Visual map generated: {html_path.resolve()}")
    return out


if __name__ == "__main__":
    main()
