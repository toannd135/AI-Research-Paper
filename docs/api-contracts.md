# API contracts

Nguồn sự thật: code ở `app/api/routes/*` và `app/core/schemas.py`; OpenAPI tại `/docs` khi chạy API. Cập nhật tệp này khi đổi endpoint.

## Quy ước chung
- Xác thực: `Authorization: Bearer <JWT>` (login/register trả token). Riêng tải PDF dùng `get_current_user_or_query_token` (token trong query để mở tab mới).
- Phân quyền: user thường chỉ thấy dữ liệu có `user_id` của mình; `admin` thấy tất cả (`can_access`). Không có quyền -> 404 (không lộ tồn tại).
- Lỗi: `{"detail": "<tiếng Việt>"}`; LLM không khả dụng -> 503; lỗi không lường -> 500 qua `unhandled_exception_handler`.
- Trạng thái dùng chung (paper & research): `pending | processing | done | failed`.
- Chỉ dùng CORS từ `cors_origins`.

## Auth `/auth`
| Method | Path | Ghi chú |
|---|---|---|
| POST | /register | 201 `AuthResponse`; có thể tắt bằng `allow_registration` |
| POST | /login | `AuthResponse` (token + user) |
| GET | /me | `UserOut` |
| GET | /users | admin: danh sách user |
| PATCH | /users/{user_id} | admin: đổi role/is_active |

## Papers `/papers` (cần đăng nhập)
| Method | Path | Ghi chú |
|---|---|---|
| POST | /upload | multipart PDF; 201 `PaperUploadResponse`; enqueue `process_paper` |
| GET | "" | `PaperListResponse` |
| GET | /{paper_id} | `PaperStatusResponse` (status, error) |
| POST | /{paper_id}/reprocess | chạy lại pipeline |
| DELETE | /{paper_id} | 204; xóa file + vector |

## Research `/research`
| Method | Path | Ghi chú |
|---|---|---|
| GET | "" | `?limit&offset&status`; trả `{items[], total, limit, offset}` (items: id, question, refined_question, status, has_report, citation_count, error, created_at) |
| POST | / | body `ResearchRequest` (question, clarification_answers, audience, field, contribution_type, target_venue, user_results). Trả `ResearchTaskResponse` (status `pending`) **hoặc** `ResearchClarificationResponse` (`needs_clarification` + questions). Enqueue `run_research` |
| GET | /{task_id} | `ResearchTaskResponse`: report, citations[], research_model (dict hoặc null), error |
| DELETE | /{task_id} | 204 |
| GET | /{task_id}/bib | BibTeX |
| GET | /{task_id}/latex | LaTeX |
| GET | /{task_id}/pdf | `?engine=html\|typst&columns=1\|2` |

## Chat (cần đăng nhập)
| Method | Path | Ghi chú |
|---|---|---|
| POST | /chat | body `ChatRequest` (question, paper_id?, conversation_id?, research_task_id?, model?) -> `ChatResponse` kèm citations; 404 nếu không có ngữ cảnh |
| GET | /chat/models | model khả dụng |
| GET | /conversations | danh sách phiên của user |
| GET | /conversations/by-research/{task_id} | phiên gắn research |
| GET | /conversations/{conversation_id} | chi tiết + messages |

## Sources
| GET | /sources/search?query&limit | Tìm OpenAlex (query tự dịch sang tiếng Anh); lỗi OpenAlex -> lỗi upstream |

## Quy tắc đổi API
Thêm field = tương thích ngược (optional). Đổi/bỏ field phải cập nhật `frontend/src/types.ts` + `frontend/src/client/api` cùng lúc.
