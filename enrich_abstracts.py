from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    import config_local as _local_config
except ImportError:
    _local_config = None

from pipeline_modules import OA_API_URL, _atomic_json, normalize_doi


LOG = logging.getLogger("paper_connection.enrich")
UA = "paper-connection/3.2 (citation-network)"


def _get_json(session: requests.Session, url: str, params: dict[str, object] | None = None) -> object | None:
    waits = (2, 8)
    query = dict(params or {})
    for attempt, wait_sec in enumerate(waits, start=1):
        try:
            response = session.get(url, params=query, timeout=60)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                pause = min(60.0, float(retry_after)) if retry_after else wait_sec
                LOG.warning("Rate limit on %s; wait %.1fs", url, pause)
                time.sleep(pause)
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            LOG.warning("Request %s/%s failed for %s: %s", attempt, len(waits), url, exc)
            if attempt < len(waits):
                time.sleep(wait_sec)
    return None


def _rehydrate_inverted_index(inverted: object) -> str:
    """OpenAlex stores abstracts as word -> position lists; rebuild plain text."""
    if not isinstance(inverted, dict):
        return ""
    words = [""] * (1 + max((p for spots in inverted.values() if isinstance(spots, list) for p in spots if isinstance(p, int)), default=-1))
    for word, spots in inverted.items():
        for position in spots if isinstance(spots, list) else []:
            if isinstance(position, int):
                words[position] = str(word)
    return " ".join(word for word in words if word)


def abstract_openalex(session: requests.Session, doi: str, api_key: str) -> str:
    params: dict[str, object] = {"select": "abstract_inverted_index"}
    if api_key:
        params["api_key"] = api_key
    data = _get_json(session, f"{OA_API_URL}/works/doi:{doi}", params)
    if not isinstance(data, dict):
        return ""
    return _rehydrate_inverted_index(data.get("abstract_inverted_index"))


def abstract_crossref(session: requests.Session, doi: str) -> str:
    data = _get_json(session, f"https://api.crossref.org/works/{doi}")
    if not isinstance(data, dict):
        return ""
    raw = str((data.get("message") or {}).get("abstract") or "")
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", raw)).split())


def abstract_semantic_scholar(session: requests.Session, doi: str) -> str:
    data = _get_json(
        session,
        f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
        {"fields": "abstract"},
    )
    if not isinstance(data, dict):
        return ""
    return " ".join(str(data.get("abstract") or "").split())


def fetch_abstract(session: requests.Session, doi: str, source: str, api_key: str) -> tuple[str, str]:
    chain: list[tuple[str, callable]] = []
    if source in ("auto", "openalex"):
        chain.append(("openalex", lambda: abstract_openalex(session, doi, api_key)))
    if source in ("auto", "crossref"):
        chain.append(("crossref", lambda: abstract_crossref(session, doi)))
    if source in ("auto", "semantic_scholar"):
        chain.append(("semantic_scholar", lambda: abstract_semantic_scholar(session, doi)))
    for name, fetch in chain:
        text = fetch()
        if text:
            return text, name
    return "", "none"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill abstracts for an existing paper_connection run")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source", choices=("auto", "openalex", "crossref", "semantic_scholar"), default="auto")
    parser.add_argument("--delay", type=float, default=1.05)
    parser.add_argument("--limit", type=int, help="Process at most this many DOIs (trial)")
    parser.add_argument("--force", action="store_true", help="Refetch even DOIs that already have an abstract")
    parser.add_argument("--retry-empty", action="store_true", help="Retry DOIs previously attempted without result")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    manifest_path = run_dir / "checkpoints" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dois = sorted(doi for doi, item in manifest.items() if item.get("status") == "ok" and normalize_doi(doi))
    if not dois:
        raise SystemExit(f"No processed DOIs in {manifest_path}")

    out_dir = run_dir / "enrichment"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "abstracts.json"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(out_dir / "enrich.log", encoding="utf-8")],
    )

    cache: dict[str, dict[str, object]] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    if args.force:
        todo = dois
    elif args.retry_empty:
        todo = [doi for doi in dois if not str(cache.get(doi, {}).get("abstract") or "")]
    else:
        todo = [doi for doi in dois if doi not in cache]
    if args.limit is not None:
        todo = todo[: args.limit]

    openalex_key = (os.environ.get("OPENALEX_API_KEY") or getattr(_local_config, "OPENALEX_API_KEY", "")).strip()
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    for index, doi in enumerate(todo, start=1):
        abstract, source = fetch_abstract(session, doi, args.source, openalex_key)
        if abstract:
            LOG.info("[%d/%d] %s: %d chars via %s", index, len(todo), doi, len(abstract), source)
        else:
            LOG.info("[%d/%d] %s: no abstract", index, len(todo), doi)
        cache[doi] = {
            "abstract": abstract,
            "source": source,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _atomic_json(cache_path, cache)
        time.sleep(max(0.0, args.delay))

    with_abstract = sum(1 for doi in dois if cache.get(doi, {}).get("abstract"))
    by_source = Counter(
        str(cache[doi]["source"]) for doi in dois if cache.get(doi, {}).get("abstract")
    )
    missing = [doi for doi in dois if not cache.get(doi, {}).get("abstract")]
    LOG.info(
        "Enrichment complete: %d/%d abstracts (%s); missing: %d",
        with_abstract,
        len(dois),
        ", ".join(f"{name}={count}" for name, count in sorted(by_source.items())),
        len(missing),
    )
    for doi in missing[:10]:
        LOG.info("No abstract: %s", doi)
    LOG.info("Cache: %s", cache_path)


if __name__ == "__main__":
    main()
