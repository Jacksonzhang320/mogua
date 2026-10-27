from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

try:
    import config_local as _local_config
except ImportError:
    _local_config = None


LOG = logging.getLogger("paper_connection")
OC_INDEX_URL = "https://opencitations.net/index/api/v2"
OC_META_URL = "https://opencitations.net/meta/api/v1/metadata"
_LOCAL_OA_URL = getattr(_local_config, "OPENALEX_API_URL", "") if _local_config else ""
_LOCAL_OA_KEY = getattr(_local_config, "OPENALEX_API_KEY", "") if _local_config else ""
OA_API_URL = (os.environ.get("OPENALEX_API_URL") or _LOCAL_OA_URL or "https://api.openalex.org").rstrip("/")


def normalize_doi(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    value = value.rstrip("/.,; ")
    return value if value.startswith("10.") and "/" in value else None


def paper_id(doi: str) -> str:
    return "D" + hashlib.sha1(doi.encode("utf-8")).hexdigest()[:12]


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _split_dois(value: str | None) -> list[str]:
    if not value:
        return []
    values = []
    for item in value.split(";"):
        doi = normalize_doi(item)
        if doi:
            values.append(doi)
    return values


def _clean_authors(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s*\[[^]]*]", "", value).strip()


class Step2_NetworkCrawler:
    """Recover the citation crawler interface using strict DOI citation edges.

    A processed paper is one OpenCitations metadata response saved under raw_data/.
    FETCH_DEPTH=1 processes the seed and every direct reference/citation, while also
    recording their outward edges. This is normally sufficient for a compact core.
    """

    def __init__(
        self,
        output_path: str | Path,
        seed_dois: Iterable[str],
        *,
        fetch_depth: int = 1,
        max_neighbors: int = 200,
        delay_sec: float = 1.05,
        max_items: int | None = None,
        provider: str = "auto",
    ) -> None:
        self.output_path = Path(output_path)
        self.raw_data_dir = self.output_path / "raw_data"
        self.checkpoint_dir = self.output_path / "checkpoints"
        self.progress_file = self.output_path / "progress.json"
        self.manifest_file = self.checkpoint_dir / "manifest.json"
        self.seed_dois = [doi for value in seed_dois if (doi := normalize_doi(value))]
        self.fetch_depth = max(0, fetch_depth)
        self.max_neighbors = max(1, max_neighbors)
        self.delay_sec = max(1.05, delay_sec)
        self.max_items = max_items
        self.openalex_key = (os.environ.get("OPENALEX_API_KEY") or _LOCAL_OA_KEY).strip()
        self.provider = "openalex" if provider == "auto" else provider
        if self.provider not in {"openalex", "opencitations"}:
            raise ValueError(f"Unsupported provider: {self.provider}")
        if self.provider == "openalex" and not self.openalex_key:
            LOG.info("Running OpenAlex in public/unauthenticated mode. For higher rate limits, set OPENALEX_API_KEY.")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "mogua/1.0 (academic-citation-crawler; mailto:mogua@example.com)"})
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> dict[str, dict[str, object]]:
        if not self.manifest_file.exists():
            return {}
        try:
            return json.loads(self.manifest_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _get_json(self, url: str) -> object | None:
        waits = (2, 5, 12, 30)
        for attempt, wait_sec in enumerate(waits, start=1):
            try:
                response = self.session.get(url, timeout=60)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    pause = min(60.0, float(retry_after)) if retry_after else wait_sec
                    LOG.warning("OpenCitations rate limit; wait %.1fs", pause)
                    time.sleep(pause)
                    continue
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                LOG.warning("Request %s/%s failed for %s: %s", attempt, len(waits), url, exc)
                if attempt < len(waits):
                    time.sleep(wait_sec)
        return None

    def _get_openalex(self, path: str, params: dict[str, object] | None = None) -> object | None:
        query = dict(params or {})
        if self.openalex_key:
            query["api_key"] = self.openalex_key
        url = f"{OA_API_URL}/{path.lstrip('/')}"
        waits = (2, 5, 12, 30)
        for attempt, wait_sec in enumerate(waits, start=1):
            try:
                response = self.session.get(url, params=query, timeout=60)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    pause = min(60.0, float(retry_after)) if retry_after else wait_sec
                    LOG.warning("OpenAlex rate limit; wait %.1fs", pause)
                    time.sleep(pause)
                    continue
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                LOG.warning("OpenAlex request %s/%s failed for %s: %s", attempt, len(waits), url, exc)
                if attempt < len(waits):
                    time.sleep(wait_sec)
        return None

    @staticmethod
    def _doi_from_pid(value: str) -> str | None:
        match = re.search(r"(?:^|\s)doi:([^\s]+)", value, flags=re.IGNORECASE)
        return normalize_doi(match.group(1)) if match else None

    def _request_opencitations(self, doi: str) -> list[dict[str, object]]:
        meta = self._get_json(f"{OC_META_URL}/doi:{doi}")
        refs = self._get_json(f"{OC_INDEX_URL}/references/doi:{doi}")
        cites = self._get_json(f"{OC_INDEX_URL}/citations/doi:{doi}")
        meta_rows = meta if isinstance(meta, list) else []
        row = dict(meta_rows[0]) if meta_rows else {}
        ref_rows = refs if isinstance(refs, list) else []
        cite_rows = cites if isinstance(cites, list) else []
        ref_dois = [self._doi_from_pid(str(item.get("cited", ""))) for item in ref_rows if isinstance(item, dict)]
        cite_dois = [self._doi_from_pid(str(item.get("citing", ""))) for item in cite_rows if isinstance(item, dict)]
        ref_dois = [value for value in ref_dois if value]
        cite_dois = [value for value in cite_dois if value]
        if row or ref_dois or cite_dois:
            row["doi"] = doi
            row["year"] = str(row.get("pub_date") or "")[:4]
            venue = str(row.get("venue") or "")
            row["source_title"] = re.sub(r"\s*\[[^]]*].*$", "", venue).strip()
            row["reference"] = "; ".join(ref_dois)
            row["citation"] = "; ".join(cite_dois)
            row["citation_count"] = len(cite_dois)
            row["oa_link"] = ""
            return [row]
        return []

    def _openalex_dois_for_ids(self, work_ids: list[str]) -> list[str]:
        dois: list[str] = []
        for start in range(0, len(work_ids), 100):
            chunk = work_ids[start : start + 100]
            data = self._get_openalex(
                "works",
                {
                    "filter": "openalex_id:" + "|".join(chunk),
                    "per_page": 100,
                    "select": "id,doi",
                },
            )
            if not isinstance(data, dict):
                continue
            for item in data.get("results", []):
                doi = normalize_doi(item.get("doi")) if isinstance(item, dict) else None
                if doi:
                    dois.append(doi)
        return dois

    def _request_openalex(self, doi: str) -> list[dict[str, object]]:
        work = self._get_openalex(
            f"works/https://doi.org/{doi}",
            {
                "select": (
                    "id,doi,title,publication_year,cited_by_count,referenced_works,"
                    "primary_location,authorships,open_access"
                )
            },
        )
        if not isinstance(work, dict) or not work.get("id"):
            return []
        work_id = str(work["id"]).rsplit("/", 1)[-1]
        ref_ids = [str(value).rsplit("/", 1)[-1] for value in work.get("referenced_works", [])]
        refs = self._openalex_dois_for_ids(ref_ids)[: self.max_neighbors]
        cites: list[str] = []
        page = 1
        while len(cites) < self.max_neighbors:
            data = self._get_openalex(
                "works",
                {
                    "filter": f"cites:{work_id}",
                    "per_page": min(100, self.max_neighbors - len(cites)),
                    "page": page,
                    "select": "id,doi",
                },
            )
            if not isinstance(data, dict):
                break
            results = data.get("results", [])
            if not results:
                break
            for item in results:
                cited_doi = normalize_doi(item.get("doi")) if isinstance(item, dict) else None
                if cited_doi:
                    cites.append(cited_doi)
            if len(results) < int(data.get("meta", {}).get("per_page") or 100):
                break
            page += 1
        location = work.get("primary_location") or {}
        source = location.get("source") or {} if isinstance(location, dict) else {}
        oa = work.get("open_access") or {}
        authors = []
        for authorship in work.get("authorships", []):
            author = authorship.get("author") or {} if isinstance(authorship, dict) else {}
            name = author.get("display_name") if isinstance(author, dict) else None
            if name:
                authors.append(str(name))
        row = {
            "doi": doi,
            "title": work.get("title") or "",
            "pub_date": str(work.get("publication_year") or ""),
            "year": str(work.get("publication_year") or ""),
            "author": "; ".join(authors),
            "venue": source.get("display_name", "") if isinstance(source, dict) else "",
            "source_title": source.get("display_name", "") if isinstance(source, dict) else "",
            "reference": "; ".join(dict.fromkeys(refs)),
            "citation": "; ".join(dict.fromkeys(cites)),
            "citation_count": int(work.get("cited_by_count") or 0),
            "oa_link": oa.get("oa_url", "") if isinstance(oa, dict) else "",
            "openalex_id": work_id,
        }
        return [row]

    def _request(self, doi: str) -> list[dict[str, object]]:
        if self.provider == "openalex":
            return self._request_openalex(doi)
        return self._request_opencitations(doi)

    def _progress(
        self,
        *,
        stage: str,
        done: int,
        total: int,
        current: str,
        started: float,
    ) -> None:
        elapsed = max(0.0, time.time() - started)
        rate = done / elapsed if done and elapsed else 0.0
        eta = (total - done) / rate if rate and total >= done else None
        payload = {
            "stage": stage,
            "done": done,
            "total": total,
            "percent": round(100.0 * done / total, 2) if total else 0.0,
            "current_item": current,
            "elapsed_sec": round(elapsed, 1),
            "eta_sec": round(eta, 1) if eta is not None else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            _atomic_json(self.progress_file, payload)
        except OSError as exc:
            LOG.warning("Could not update progress.json: %s", exc)

    def run(self) -> dict[str, str]:
        if not self.seed_dois:
            raise ValueError("No valid seed DOI")
        manifest = self._load_manifest()
        processed = {
            doi
            for doi, item in manifest.items()
            if item.get("status") == "ok" and item.get("provider", "opencitations") == self.provider
        }
        known = set(self.seed_dois)
        layer = set(self.seed_dois)
        started = time.time()
        completed_this_run = 0
        scheduled_total = len(layer)
        LOG.info("Step2 start: provider=%s, depth=%s, cached=%s", self.provider, self.fetch_depth, len(processed))

        for depth in range(self.fetch_depth + 1):
            if not layer:
                break
            next_layer: set[str] = set()
            for doi in sorted(layer):
                if self.max_items is not None and completed_this_run >= self.max_items:
                    self._progress(
                        stage="trial_stopped",
                        done=completed_this_run,
                        total=max(scheduled_total, completed_this_run),
                        current=doi,
                        started=started,
                    )
                    return {doi: paper_id(doi) for doi in known}
                if doi in processed:
                    item = manifest[doi]
                    refs = list(item.get("references", []))
                    cites = list(item.get("citations", []))
                else:
                    rows = self._request(doi)
                    row = rows[0] if rows else {}
                    refs = _split_dois(str(row.get("reference", "")))[: self.max_neighbors]
                    cites = _split_dois(str(row.get("citation", "")))[: self.max_neighbors]
                    pid = paper_id(doi)
                    raw_path = self.raw_data_dir / f"{pid}.json"
                    raw_path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
                    status = "ok" if row else "missing"
                    manifest[doi] = {
                        "id": pid,
                        "status": status,
                        "depth": depth,
                        "references": refs,
                        "citations": cites,
                        "file": raw_path.name,
                        "provider": self.provider,
                    }
                    _atomic_json(self.manifest_file, manifest)
                    if status == "ok":
                        processed.add(doi)
                    completed_this_run += 1
                    time.sleep(self.delay_sec)

                if depth < self.fetch_depth:
                    next_layer.update(refs)
                    next_layer.update(cites)
                known.update(refs)
                known.update(cites)
                self._progress(
                    stage=f"crawl_depth_{depth}",
                    done=completed_this_run,
                    total=max(scheduled_total, completed_this_run),
                    current=doi,
                    started=started,
                )
            next_layer -= known - next_layer
            layer = next_layer - processed
            scheduled_total += len(layer)
            LOG.info("Depth %s complete; next=%s, known=%s", depth, len(layer), len(known))

        cache_path = self.output_path / "doi_to_id_cache.json"
        try:
            id_cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        except (OSError, json.JSONDecodeError):
            id_cache = {}
        id_cache.update({doi: paper_id(doi) for doi in sorted(known)})
        _atomic_json(cache_path, id_cache)
        self._progress(
            stage="crawl_complete",
            done=completed_this_run,
            total=completed_this_run,
            current="",
            started=started,
        )
        LOG.info("Step2 complete: processed=%s, known=%s", len(processed), len(known))
        return {doi: paper_id(doi) for doi in known}

    def smart_expand_depth2(self, top_k: int = 100, min_connections: int = 2) -> list[str]:
        """Discover and fetch metadata for the top-K Depth 2 DOIs based on Co-citation and Co-citing in Depth 1."""
        manifest = self._load_manifest()
        depth1_dois = {doi for doi, item in manifest.items() if item.get("depth") == 1 and item.get("status") == "ok"}
        already_processed = set(manifest.keys())

        co_cited: dict[str, int] = {}
        co_citing: dict[str, int] = {}
        for d1 in depth1_dois:
            item = manifest[d1]
            for ref in item.get("references", []):
                if ref and ref not in already_processed:
                    co_cited[ref] = co_cited.get(ref, 0) + 1
            for cite in item.get("citations", []):
                if cite and cite not in already_processed:
                    co_citing[cite] = co_citing.get(cite, 0) + 1

        all_candidates = set(co_cited.keys()) | set(co_citing.keys())
        scored = []
        for doi in all_candidates:
            c_cited = co_cited.get(doi, 0)
            c_citing = co_citing.get(doi, 0)
            if c_cited + c_citing < min_connections:
                continue
            # Weight co-citation (classic foundation) and co-citing (review/synthesis)
            score = 2.0 * c_cited + 1.0 * c_citing
            scored.append((doi, score, c_cited, c_citing))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_targets = [item[0] for item in scored[:top_k]]
        LOG.info("Smart expand: selected %d candidates (from %d connected candidates)", len(top_targets), len(scored))
        if not top_targets:
            return []

        added_dois: list[str] = []
        if self.provider == "openalex":
            for start in range(0, len(top_targets), 50):
                chunk = top_targets[start : start + 50]
                data = self._get_openalex(
                    "works",
                    {
                        "filter": "doi:" + "|".join(chunk),
                        "per_page": 50,
                        "select": (
                            "id,doi,title,publication_year,cited_by_count,referenced_works,"
                            "primary_location,authorships,open_access"
                        ),
                    },
                )
                works = data.get("results", []) if isinstance(data, dict) else []
                all_ref_ids = list({r.rsplit("/", 1)[-1] for w in works for r in w.get("referenced_works", []) if r})
                wid_to_doi: dict[str, str] = {}
                if all_ref_ids:
                    for r_start in range(0, len(all_ref_ids), 100):
                        r_chunk = all_ref_ids[r_start : r_start + 100]
                        r_data = self._get_openalex(
                            "works",
                            {
                                "filter": "openalex_id:" + "|".join(r_chunk),
                                "per_page": 100,
                                "select": "id,doi",
                            },
                        )
                        if isinstance(r_data, dict):
                            for r_item in r_data.get("results", []):
                                r_doi = normalize_doi(r_item.get("doi"))
                                if r_doi:
                                    wid = str(r_item.get("id", "")).rsplit("/", 1)[-1]
                                    wid_to_doi[wid] = r_doi

                found_dois = set()
                for work in works:
                    doi = normalize_doi(work.get("doi"))
                    if not doi or doi in manifest:
                        continue
                    found_dois.add(doi)
                    work_id = str(work.get("id", "")).rsplit("/", 1)[-1]
                    ref_ids = [str(r).rsplit("/", 1)[-1] for r in work.get("referenced_works", []) if r]
                    refs = [wid_to_doi[wid] for wid in ref_ids if wid in wid_to_doi][: self.max_neighbors]
                    location = work.get("primary_location") or {}
                    source = location.get("source") or {} if isinstance(location, dict) else {}
                    oa = work.get("open_access") or {}
                    authors = []
                    for authorship in work.get("authorships", []):
                        author = authorship.get("author") or {} if isinstance(authorship, dict) else {}
                        name = author.get("display_name") if isinstance(author, dict) else None
                        if name:
                            authors.append(str(name))

                    row = {
                        "doi": doi,
                        "title": work.get("title") or "",
                        "pub_date": str(work.get("publication_year") or ""),
                        "year": str(work.get("publication_year") or ""),
                        "author": "; ".join(authors),
                        "venue": source.get("display_name", "") if isinstance(source, dict) else "",
                        "source_title": source.get("display_name", "") if isinstance(source, dict) else "",
                        "reference": "; ".join(dict.fromkeys(refs)),
                        "citation": "",
                        "citation_count": int(work.get("cited_by_count") or 0),
                        "oa_link": oa.get("oa_url", "") if isinstance(oa, dict) else "",
                        "openalex_id": work_id,
                    }
                    pid = paper_id(doi)
                    raw_path = self.raw_data_dir / f"{pid}.json"
                    raw_path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
                    manifest[doi] = {
                        "id": pid,
                        "status": "ok",
                        "depth": 2,
                        "references": refs,
                        "citations": [],
                        "file": raw_path.name,
                        "provider": self.provider,
                        "expansion": "smart",
                    }
                    added_dois.append(doi)

                for chunk_doi in chunk:
                    if chunk_doi not in found_dois and chunk_doi not in manifest:
                        pid = paper_id(chunk_doi)
                        manifest[chunk_doi] = {
                            "id": pid,
                            "status": "missing",
                            "depth": 2,
                            "references": [],
                            "citations": [],
                            "file": "",
                            "provider": self.provider,
                            "expansion": "smart",
                        }
                _atomic_json(self.manifest_file, manifest)
                time.sleep(self.delay_sec)
        else:
            for doi in top_targets:
                if doi in manifest:
                    continue
                rows = self._request(doi)
                row = rows[0] if rows else {}
                refs = _split_dois(str(row.get("reference", "")))[: self.max_neighbors]
                cites = _split_dois(str(row.get("citation", "")))[: self.max_neighbors]
                pid = paper_id(doi)
                raw_path = self.raw_data_dir / f"{pid}.json"
                raw_path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
                status = "ok" if row else "missing"
                manifest[doi] = {
                    "id": pid,
                    "status": status,
                    "depth": 2,
                    "references": refs,
                    "citations": cites,
                    "file": raw_path.name,
                    "provider": self.provider,
                    "expansion": "smart",
                }
                _atomic_json(self.manifest_file, manifest)
                if status == "ok":
                    added_dois.append(doi)
                time.sleep(self.delay_sec)

        LOG.info("Smart expand complete: added %d Depth 2 papers to manifest", len(added_dois))
        return added_dois


class Step3_FilterAndBuild:
    def __init__(
        self,
        output_path: str | Path,
        seed_dois: Iterable[str],
        *,
        top_n: int = 15,
        top_m: int = 20,
        direct_bonus: float = 1.2,
        force: bool = False,
    ) -> None:
        self.output_path = Path(output_path)
        self.raw_data_dir = self.output_path / "raw_data"
        self.analysis_dir = self.output_path / "analysis_results"
        self.manifest_file = self.output_path / "checkpoints" / "manifest.json"
        self.seed_dois = {doi for value in seed_dois if (doi := normalize_doi(value))}
        self.top_n = max(1, top_n)
        self.top_m = max(1, top_m)
        self.direct_bonus = direct_bonus
        self.force = force
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _balanced_top(rows: list[dict[str, object]], seed_year: int, n: int) -> list[dict[str, object]]:
        groups = {
            "pre": [r for r in rows if int(r.get("Year") or 0) < seed_year],
            "same": [r for r in rows if int(r.get("Year") or 0) == seed_year],
            "post": [r for r in rows if int(r.get("Year") or 0) > seed_year],
        }
        quotas = {"pre": n // 3, "same": n // 3, "post": n - 2 * (n // 3)}
        selected: list[dict[str, object]] = []
        for key in ("pre", "same", "post"):
            groups[key].sort(key=lambda r: float(r["AdjustedScore"]), reverse=True)
            selected.extend(groups[key][: quotas[key]])
        if len(selected) < n:
            chosen = {str(r["DOI"]) for r in selected}
            rest = sorted(rows, key=lambda r: float(r["AdjustedScore"]), reverse=True)
            selected.extend(r for r in rest if str(r["DOI"]) not in chosen) 
        return selected[:n]

    def run(self, force: bool = False) -> tuple[Path, Path]:
        nodes_path = self.analysis_dir / "nodes_core.csv"
        edges_path = self.analysis_dir / "edges_core.csv"
        if not (force or self.force) and nodes_path.exists() and edges_path.exists():
            LOG.info("Step3 outputs already exist; reuse")
            return nodes_path, edges_path
        manifest = json.loads(self.manifest_file.read_text(encoding="utf-8"))
        nodes: dict[str, dict[str, object]] = {}
        references: dict[str, set[str]] = {}
        all_edges: set[tuple[str, str]] = set()

        for doi, item in manifest.items():
            if item.get("status") != "ok":
                continue
            path = self.raw_data_dir / str(item["file"])
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            refs = set(_split_dois(str(row.get("reference", ""))))
            cites = set(_split_dois(str(row.get("citation", ""))))
            references[doi] = refs
            all_edges.update((doi, target) for target in refs)
            all_edges.update((source, doi) for source in cites)
            year_text = str(row.get("year") or row.get("pub_date") or "")[:4]
            year = int(year_text) if year_text.isdigit() else 0
            nodes[doi] = {
                "Id": paper_id(doi),
                "DOI": doi,
                "Title": str(row.get("title") or ""),
                "Year": year,
                "CitedByCount": int(row.get("citation_count") or 0),
                "Authors": _clean_authors(str(row.get("author") or "")),
                "Journal": str(row.get("source_title") or row.get("venue") or ""),
                "OA_URL": str(row.get("oa_link") or ""),
            }

        if not nodes:
            raise RuntimeError("No metadata rows available for Step3")
        seed = next((doi for doi in self.seed_dois if doi in nodes), next(iter(nodes)))
        seed_year = int(nodes[seed].get("Year") or datetime.now().year)
        seed_refs = references.get(seed, set())
        current_year = datetime.now().year
        for doi, row in nodes.items():
            year = int(row.get("Year") or current_year)
            age = max(1, current_year - year + 1)
            cpy = int(row["CitedByCount"]) / age
            similarity = jaccard_similarity(seed_refs, references.get(doi, set())) if doi != seed else 1.0
            direct = doi in seed_refs or seed in references.get(doi, set())
            bonus = self.direct_bonus if direct else 1.0
            adjusted = (math.log(cpy + 1.0) + 1.0) * (math.sqrt(similarity) + 1.0) * bonus
            row.update(
                {
                    "CitationPerYear": round(cpy, 6),
                    "Similarity": round(similarity, 6),
                    "DirectCitation": int(direct),
                    "AdjustedScore": round(adjusted, 6),
                    "IsSeed": int(doi == seed),
                }
            )

        candidates = [row for doi, row in nodes.items() if doi != seed and int(row.get("Year") or 0)]
        by_score = self._balanced_top(candidates, seed_year, self.top_n)
        by_similarity = sorted(candidates, key=lambda r: float(r["Similarity"]), reverse=True)[: self.top_m]
        core_dois = {seed} | {str(r["DOI"]) for r in by_score + by_similarity}
        core_rows = [row for doi, row in nodes.items() if doi in core_dois]
        core_edges = [(paper_id(s), paper_id(t), "Directed") for s, t in all_edges if s in core_dois and t in core_dois]

        node_fields = [
            "Id", "DOI", "Title", "Year", "CitedByCount", "CitationPerYear",
            "Similarity", "AdjustedScore", "DirectCitation", "IsSeed", "Authors", "Journal", "OA_URL",
        ]
        with nodes_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=node_fields)
            writer.writeheader()
            writer.writerows(core_rows)
        with edges_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Source", "Target", "Type"])
            writer.writerows(sorted(set(core_edges)))

        with (self.analysis_dir / "edges_discovered.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["SourceDOI", "TargetDOI"])
            writer.writerows(sorted(all_edges))
        summary = {
            "seed_doi": seed,
            "seed_title": nodes[seed]["Title"],
            "metadata_nodes": len(nodes),
            "discovered_edges": len(all_edges),
            "core_nodes": len(core_rows),
            "core_edges": len(set(core_edges)),
            "source": "OpenCitations Index/Meta",
        }
        _atomic_json(self.analysis_dir / "summary.json", summary)
        LOG.info("Step3 complete: %s", summary)
        return nodes_path, edges_path
