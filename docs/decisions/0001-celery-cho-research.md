# 0001 — Research chạy nền bằng Celery, không trong request
Trạng thái: accepted
**Bối cảnh:** một research task gồm ~10 lời gọi LLM tuần tự + embedding/rerank CPU, có thể tới ~1 giờ.
**Quyết định:** `POST /research` chỉ tạo `ResearchTask(pending)` và `run_research.delay(id)`; client poll `GET /research/{id}`. Queue riêng `research_queue`, `acks_late`, `prefetch=1`, time limit 3600s.
**Hệ quả:** request nhanh, chịu restart worker; cần trạng thái `pending/processing/done/failed` và `error` rõ ràng; agent không được import từ `api`.
