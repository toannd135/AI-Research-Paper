"""Chạy thử research agent cho đề tài deepfake với prompt riêng, chỉ dùng PDF trong data/papers_deepfake.

Luồng chính (web/API/Celery) và prompt gốc không đổi. Script cần Qdrant, Redis (cache embedding) và API key LLM; không cần Postgres, không tạo research task.

Cách dùng (từ thư mục gốc repo, sau `docker start ai-research-paper-qdrant-1 ai-research-paper-redis-1`):
    .venv/bin/python scripts/run_deepfake.py --dry-run             # kiểm tra kho + in prompt, không gọi LLM
    .venv/bin/python scripts/run_deepfake.py --index-only          # lập chỉ mục PDF còn thiếu vào Qdrant (chạy một lần)
    .venv/bin/python scripts/run_deepfake.py                       # chạy với câu hỏi mặc định
    .venv/bin/python scripts/run_deepfake.py "Câu hỏi nghiên cứu"

Kết quả: output/deepfake/<thời-gian>/ (report.md, report.pdf, citations.json, validation_report.json, ledger.csv, prompts.jsonl).
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PAPERS_DIR = ROOT / "data" / "papers_deepfake"
OUTPUT_ROOT = ROOT / "output" / "deepfake"
DEFAULT_QUESTION = (
    "A survey of deepfake detection methods: taxonomy of detection cues, evaluation protocols, "
    "and generalization across datasets and unseen generators"
)

logger = logging.getLogger("run_deepfake")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chạy thử research agent cho đề tài deepfake (chỉ dùng PDF có sẵn).")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION, help="câu hỏi nghiên cứu")
    parser.add_argument("--dry-run", action="store_true", help="kiểm tra kho và in prompt, không gọi LLM")
    parser.add_argument("--index-only", action="store_true", help="lập chỉ mục các PDF chưa có trong Qdrant rồi dừng")
    parser.add_argument("--max-papers", type=int, default=20, help="số PDF dùng (nửa trích dẫn nhiều nhất, nửa mới nhất); 0 = tất cả")
    parser.add_argument("--contribution", default="survey", choices=["new_method", "improvement", "comparison", "system", "survey"])
    parser.add_argument("--context-tokens", type=int, default=30000, help="giới hạn context; kho lớn cần cao hơn mặc định 8000 của .env")
    return parser.parse_args(argv)


def paper_ids(directory: Path) -> dict[str, Path]:
    """paper_id -> đường dẫn; paper_id là tên file dạng UUID, file khác không có vector tương ứng nên bỏ qua."""
    found: dict[str, Path] = {}
    for path in sorted(directory.glob("*.pdf")):
        try:
            found[str(uuid.UUID(path.stem))] = path
        except ValueError:
            continue  # bản sao mang tên gốc của bài báo, xem `apply_manifest`
    return found


def indexed_ids(ids: set[str]) -> set[str] | None:
    """Các paper có vector trong Qdrant; None nếu không kết nối được."""
    from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

    from app.pipeline.vector_store.qdrant_client import list_paper_ids

    try:
        return ids & list_paper_ids()
    except (ResponseHandlingException, UnexpectedResponse, OSError):
        logger.exception("Không kết nối được Qdrant")
        return None


def index_papers(papers: dict[str, Path]) -> int:
    """Parse -> chunk -> embed -> Qdrant, không cần Postgres; một PDF lỗi không dừng cả lượt. Trả về số PDF đã xử lý."""
    from app.ai.embedding.service import embed_batch
    from app.pipeline.chunking.semantic_chunker import chunk_pages
    from app.pipeline.figures import extract_figures, figures_dir
    from app.pipeline.parser.pdf_parser import parse_pdf
    from app.pipeline.vector_store.qdrant_client import ensure_collection, upsert_chunks

    done = 0
    for n, (pid, path) in enumerate(papers.items(), start=1):
        try:
            chunks = chunk_pages(pid, parse_pdf(str(path)))
            if not chunks:
                logger.warning("%s: không trích được nội dung, bỏ qua", path.name)
                continue
            vectors = embed_batch([c.text for c in chunks])
            ensure_collection(vector_size=len(vectors[0]))
            upsert_chunks(chunks, vectors)
            if not figures_dir(pid).exists():
                extract_figures(str(path), figures_dir(pid), source_title=path.name)
            done += 1
            logger.info("Đã lập chỉ mục %d/%d: %s (%d chunk)", n, len(papers), pid, len(chunks))
        except (OSError, RuntimeError, ValueError):
            logger.exception("Không lập chỉ mục được %s", path.name)
    return done


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_items(papers: dict[str, Path], directory: Path) -> dict[str, dict]:
    """paper_id -> mục của `_manifest.json`; manifest ghi theo tên file gốc nên ghép qua nội dung file giống hệt nhau."""
    manifest_path = directory / "_manifest.json"
    if not manifest_path.is_file():
        return {}
    by_hash = {}
    for item in json.loads(manifest_path.read_text(encoding="utf-8")):
        source = directory / item["file"]
        if source.is_file():
            by_hash[_sha256(source)] = item
    return {pid: by_hash[digest] for pid, path in papers.items() if (digest := _sha256(path)) in by_hash}


def select_papers(papers: dict[str, Path], directory: Path, limit: int) -> dict[str, Path]:
    """Chọn cố định `limit` bài (lập chỉ mục và chạy thật dùng cùng một tập): nửa trích dẫn nhiều nhất, phần còn lại mới nhất."""
    if limit <= 0 or limit >= len(papers):
        return papers
    items = manifest_items(papers, directory)

    def number(pid: str, key: str) -> int:
        return int(items.get(pid, {}).get(key) or 0)

    chosen = sorted(papers, key=lambda p: (-number(p, "cited"), p))[: limit // 2]
    rest = sorted((p for p in papers if p not in chosen), key=lambda p: (-number(p, "year"), -number(p, "cited"), p))
    picked = {*chosen, *rest[: limit - len(chosen)]}
    return {pid: path for pid, path in papers.items() if pid in picked}


def apply_manifest(catalog: dict[str, dict[str, str]], papers: dict[str, Path], directory: Path) -> None:
    """Ghi đè title/year/doi bằng `_manifest.json`, chính xác hơn đọc từ PDF."""
    for pid, item in manifest_items(papers, directory).items():
        if pid in catalog:
            doi = str(item.get("doi") or "").removeprefix("https://doi.org/")
            catalog[pid].update({"title": item["title"], "year": str(item.get("year") or "")})
            if doi.startswith("10."):
                catalog[pid]["doi"] = doi
            elif doi:  # manifest ghi mã arXiv vào trường doi; đó là nơi công bố, không phải DOI
                catalog[pid]["venue"] = catalog[pid]["venue"] or doi


def build_catalog(papers: dict[str, Path]) -> dict[str, dict[str, str]]:
    from app.agent.evidence.citation_cleaner import file_catalog
    from app.pipeline.paper_metadata import extract_paper_metadata

    curated = file_catalog()
    catalog = {pid: dict(curated.get(pid) or extract_paper_metadata(str(path), path.name)) for pid, path in papers.items()}
    apply_manifest(catalog, papers, PAPERS_DIR)
    return catalog


def print_dry_run(papers: dict[str, Path], usable: set[str] | None, catalog: dict[str, dict[str, str]]) -> None:
    from app.agent.overlays.deepfake import EXTRACT_OVERLAY, OVERLAYS

    print(f"PDF sẽ dùng trong {PAPERS_DIR}: {len(papers)}")
    for meta in sorted(catalog.values(), key=lambda m: m["year"], reverse=True):
        print(f"  {meta['year'] or '----'}  {meta['title'][:90]}")
    print("Qdrant: không kết nối được" if usable is None else f"Đã có vector trong Qdrant: {len(usable)}/{len(papers)}")
    print(f"Thiếu tiêu đề (đang dùng tên file): {sum(1 for pid, m in catalog.items() if m['title'] == pid)}")
    print(f"Thiếu tác giả: {sum(1 for m in catalog.values() if not m['authors'])}, thiếu năm: {sum(1 for m in catalog.values() if not m['year'])}")
    for stage, text in {**OVERLAYS, "extract": EXTRACT_OVERLAY.strip()}.items():
        print(f"\n--- Prompt thêm cho chặng {stage} ---\n{text}")


def write_outputs(out_dir: Path, state: dict) -> None:
    from app.agent.evidence.ledger_export import export_ledger_csv
    from app.agent.format_sanitizer import sanitize_academic_markdown
    from app.pipeline.export.pdf_renderer import report_to_pdf

    report = sanitize_academic_markdown(state.get("report", ""))
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    citations = [c.model_dump() for c in state.get("citations", [])]
    (out_dir / "citations.json").write_text(json.dumps(citations, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "validation_report.json").write_text(
        json.dumps(state.get("validation_report") or {}, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    if state.get("results"):
        export_ledger_csv(state["results"], out_dir / "ledger.csv")
    try:
        (out_dir / "report.pdf").write_bytes(report_to_pdf(report))
    except Exception:  # lỗi xuất PDF không được làm mất report.md của cả lượt chạy
        logger.exception("Không xuất được PDF; report.md vẫn đã lưu")


def main(argv: list[str] | None = None, llm=None) -> int:
    """`llm` thay gateway thật khi test."""
    args = parse_args(argv)
    # Phải đặt trước khi settings được đọc lần đầu; chỉ có tác dụng trong tiến trình này.
    os.environ["UPLOAD_DIR"] = str(PAPERS_DIR)
    os.environ["EXTERNAL_SEARCH_ENABLED"] = "false"
    os.environ["CONTEXT_TOKEN_LIMIT"] = str(args.context_tokens)

    papers = select_papers(paper_ids(PAPERS_DIR), PAPERS_DIR, args.max_papers)
    usable = indexed_ids(set(papers))
    if args.index_only:
        if usable is None:
            print("Chưa kết nối được Qdrant.", file=sys.stderr)
            return 2
        done = index_papers({pid: path for pid, path in papers.items() if pid not in usable})
        print(f"Đã lập chỉ mục thêm {done} PDF; tổng cộng {len(usable) + done}/{len(papers)}.")
        return 0
    catalog = build_catalog(papers)
    if args.dry_run:
        print_dry_run(papers, usable, catalog)
        return 0
    if not usable:
        print("Không có PDF deepfake nào trong Qdrant (hoặc Qdrant chưa bật). Chạy --index-only trước.", file=sys.stderr)
        return 2
    if len(usable) < len(papers):
        logger.warning("Chỉ dùng %d/%d PDF: số còn lại chưa có vector trong Qdrant", len(usable), len(papers))

    from app.agent.evidence import extractor
    from app.agent.graph import run_graph
    from app.agent.nodes.synthesize_node import InsufficientEvidenceError
    from app.agent.overlays.deepfake import EXTRACT_OVERLAY, OverlayGateway
    from app.ai.llm_gateway.base import LLMGatewayError
    from app.ai.llm_gateway.default import get_default_agent_gateway
    from app.core.scope import set_allowed_paper_ids, set_local_only, set_run_catalog

    # Sửa trong tiến trình này: cache trích xuất khóa theo prompt nên không lẫn với kết quả của luồng chính.
    extractor._PROMPT += EXTRACT_OVERLAY
    set_allowed_paper_ids(usable)
    set_local_only(True)
    set_run_catalog({pid: catalog[pid] for pid in usable})

    out_dir = OUTPUT_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True)
    inner, model_name = get_default_agent_gateway(llm)
    gateway = OverlayGateway(inner, model_name, out_dir / "prompts.jsonl")
    try:
        state = run_graph(args.question, llm=gateway, field="computer_vision", contribution_type=args.contribution)
    except (LLMGatewayError, InsufficientEvidenceError):
        logger.exception("Lượt chạy thất bại; xem prompt đã gửi tại %s", out_dir / "prompts.jsonl")
        return 1
    write_outputs(out_dir, state)
    print(f"Xong: {out_dir}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    raise SystemExit(main())
