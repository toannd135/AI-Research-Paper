# Bàn giao: đối chiếu & đồng bộ frontend ↔ paperai (2026-11-11)

## Đã xong
- Backend `GET /conversations` -> phân trang `{items,total,limit,offset}` + `message_count`, `last_message`,
  `research_task_id`, lọc `paper_id` (`app/api/routes/chat.py`); test trong `app/api/tests/test_chat_route.py`;
  doc `docs/api-contracts.md`. Trước đó trả mảng -> admin Dashboard/Hội thoại crash.
- Backend: tên file zip LaTeX theo template (`-ieee.zip` / `-cvpr.zip`).
- Frontend (repo riêng `../frontend`, CHƯA commit, lẫn với thay đổi dở của người dùng ở 8 tệp):
  - `client/api/research.ts`: `researchExportUrl`/`fetchResearchExport` (pdf|latex|bib, template, draft);
    tham số `download` (backend không đọc) -> `draft`; `workspace_id` khi POST /research.
  - `client/lib/useOpenResearchPdf.ts`: hook `useResearchExport` — PDF mở tab, zip/bib tải về;
    409 Quality Gate -> modal "Xuất bản nháp" (`?draft=true`).
  - `ArticleView.tsx`: chọn IEEE/CVPR, PDF mặc định LaTeX (trước là Typst), nút LaTeX zip + BibTeX.
  - `ResearchJobsPage.tsx` dùng hook chung; `ConversationsPage.tsx` sửa câu "chưa có xác thực".
  - Workspace: `client/api/workspaces.ts`, `client/state/workspaceStore.ts` (localStorage),
    `client/components/WorkspacePicker.tsx` (sidebar). Upload + POST /research gửi `workspace_id`;
    có phiên thì không gọi /sources/search (chế độ chỉ PDF nội bộ).
  - `papers.ts`: `uploadPaper(file, workspaceId)`, `listPapers({workspaceId})`.

## Kiểm chứng
- `pytest app/api/tests -q` pass; `npm run check` 0 error (6 warning react-refresh có sẵn).
- Smoke qua proxy Vite: /conversations, /workspaces, /bib 200; /latex,/pdf 409 khi gate fail, `draft=true` 200
  (zip cvpr, PDF LaTeX ~9s).
- Chưa bấm thử UI trên trình duyệt (modal draft, picker phiên).

## Đang chờ
- Người dùng test UI; commit frontend tách riêng phần export/workspace khỏi thay đổi dở của họ.
- `ruff check app/api` có 17 lỗi cũ ở `research.py`, `sources.py`, tests — chưa sửa (ngoài phạm vi).
- Admin `PapersPage` upload vẫn vào thư viện chung (không chọn phiên); chưa hiện cột workspace.
- uvicorn --reload treo khi có request LLM dở dang lúc reload (graceful shutdown chờ) — cân nhắc timeout LLM.
