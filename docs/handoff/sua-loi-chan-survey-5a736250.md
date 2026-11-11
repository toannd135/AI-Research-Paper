# Sửa lỗi hệ thống từ bản survey brain `5a736250` (soạn 2026-11-11)

Bản xuất: `data/exports/paper_5a736250_test4.pdf` (23 trang, draft). Gate: `data/papers_brain/validation/5a736250-b275-45b0-a477-31b94bc29335.json` — passed=false, 7 chặn, 75 cảnh báo; `redacted_cells` = 0. Văn bản từng trang: scratchpad phiên trước (mất) → tự `pdftotext` lại.

## Môi trường đã dựng (đừng làm lại)
- Stack docker `paperai-*` (5433/6380/6333). KHÔNG chạy `docker compose -p paperai_bt`; không đổi cổng compose về 5432/6379 (host đã có postgres/redis chiếm).
- Chạy app trên host: `source scripts/host_env.sh` (mới, chưa commit) rồi uvicorn/celery. Venv đã sửa đường dẫn cũ `/CODE/paperai`.
- Workspace "MRI brain" `72166c1a-9db1-41e1-904d-26a3e5f326c9` = 52 paper done (admin@gmail.com / admin). 2 survey mới: `cf53af46…`, `c6a0b451…` (authors Frontiers trong catalog tạm "Latif et al., Lee SW" — cần sửa tay).
- Body request: `/tmp/req.json` (có workspace_id). Migration 0009 đã chạy.

## Chẩn đoán: gate chỉ báo, gần như không sửa
`synthesize_node` (app/agent/nodes/synthesize_node.py:928-1011): gate chạy 2 lần, bước sửa tất định duy nhất là `redact_untraced_cells` (chỉ bảng). 4 nhóm lỗi chặn không có bước sửa:
1. **Số không truy vết được trong biểu đồ** (6 giá trị): `redact.py` bỏ qua ```chart. Sửa: gỡ điểm UNTRACED trong chart (đặt null; renderer bỏ nhãn rỗng qua `keep_idx`), location `series s, point v` (traceability.py:58).
2. **Chart trộn ET/TC/WT** (2 chart, `quant_check.check_chart_block`): chart do `postprocess_report` sinh (min_charts=3). Sửa: giữ series một vùng (vùng nhiều series nhất), ghi caption — KHÔNG tách chart (lệch số Figure).
3. **"ledger … missing-modality configuration" khi sổ cái không có** (`consistency_check.check_ledger_claims`): sửa tất định — bỏ cụm `missing-modality configuration(s)` khỏi câu bị bắt (khi missing_groups=0).
4. **Độ phủ 7/52 chưa cite**: phải chèn TRƯỚC `clean_and_deduplicate_citations_ex` (dùng chỉ số citations thô): đoạn/bảng "Other corpus studies" liệt kê tiêu đề catalog + [k]; chỉ mệnh đề sự thật (tiêu đề), không bịa kết quả.
Vị trí: (2)(3) sau `postprocess_report`/`strip_dangling_citations`, trước `finalize_structure_report`; (1) trong `_verify_final_report` cạnh redact; (4) trước dedupe.

## Lỗi tham chiếu agent đọc PDF thấy (gate không bắt)
- Tr.13 `[52, Table 1]`: chỉ có 45 ref → `strip_dangling_citations` không bắt dạng `[n, Table k]`.
- "six-axis taxonomy (Table 1)" (thật là Table 3); "Figure 1 … taxonomy-tree" (thật là Figure 2) → `finalize_structure_report` gán theo vị trí; nên khớp theo nội dung caption (taxonomy).
- "376 records from 12 papers" vs log "từ 32 paper"; Figure 9 "26 sources" không giải thích.

## Checklist
1. [x] Ghi bước + cách kiểm chứng vào `docs/implementation-plan.md` (task >1 tệp).
2. [x] Module mới `app/agent/evidence/repair.py` (chart region, chart untraced, ledger phrase, uncited block) + test `app/agent/tests/test_repair.py` (không gọi LLM).
3. [x] Nối vào `synthesize_node`; sửa `strip_dangling_citations` cho `[n, …]`; khớp Table/Figure theo caption.
4. [x] `ruff check app` + `pytest app/agent -q`; cập nhật `docs/architecture.md` (bước repair sau gate).
5. [ ] Chạy lại research (worker restart) → test5, so 7 lỗi chặn.

## Kiểm chứng sau sửa (2026-11-11)
- Replay offline trên report 5a736250: chặn 7 → 1 (còn độ phủ 7/52 vì add_uncited_corpus cần chỉ số thô — chỉ có hiệu lực ở lượt chạy mới; thử riêng: chèn đúng cuối §3).
- Script/kết quả: scratchpad phiên trước (verify.py, r1-r3.py) — có thể đã mất.

## Bug còn lại (review + replay đã tái hiện) — sửa kèm test
1. repair.py:221 `redact_untraced_chart_points`: bỏ ≥2 chart → ordinal đếm trên `out` đã sửa, xoá nhầm nhãn/câu của hình còn giữ, lùi số 2 lần. Dùng số hình gốc, sửa giảm dần.
2. report_structure.py:369 `rematch_refs_by_caption`: câu nhắc 2 bảng → đổi nhầm (cắt pre/post tại ref gần nhất); đổi cả "[3, Table 1]" của nguồn (bỏ qua match trong ngoặc citation); đổi nhầm "Table 1 of the Draft Basis"; dòng bắt đầu "**Table N**"/"**Figure N**" inline bị coi là caption (:376) nên "**Figure 1** taxonomy-tree" không sửa.
3. report_structure.py:25/154: `[n, Table k]` không được remap trong `clean_and_deduplicate_citations_ex` → strip xoá cite hợp lệ hoặc trỏ sai paper. Remap bằng orig_to_new. strip bỏ qua fence → "[52, Table 1]" trong caption chart sống sót (gate `\[(\d+)\]` cũng không bắt).
4. `_LOCATED_CITE_RE` ăn khoảng toán học "[0, L]" → chỉ nhận định vị Table|Fig|Figure|p.|pp.|Sec|Eq + số.
5. repair.py:277 `add_uncited_corpus`: cite dạng cụm "[1, 2]"/"[3–3]" bị coi chưa cite → dùng `expand_citation_clusters(text)`.
6. repair.py:238-245 `repair_ledger_claims` làm rỗng heading "## 4. Missing-modality results in the ledger" → bỏ qua dòng "#"/"|".
7. repair.py:249/266 chỉ bảo vệ fence mermaid/chart/image/table; gộp khoảng trắng toàn chunk (phá ```python, hard-break) → dùng `_split_fences`, chỉ gộp trong câu đã sửa.
8. repair_chart_regions: caption còn "three tumor sub-regions" sau khi chỉ giữ WT.
9. (có sẵn, không do repair) `renumber_sections` đổi số heading nhưng không cập nhật "Section 7/6.2" trong thân bài.

## Đang chờ
- Người dùng xác nhận phạm vi: sửa cả 4 nhóm chặn + 3 lỗi tham chiếu, hay chỉ nhóm chặn.
- Task cũ `34f90f99…` (28/10) kẹt `processing` — hỏi có xoá không.
