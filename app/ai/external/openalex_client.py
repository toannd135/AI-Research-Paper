"""Client gọi OpenAlex API (https://api.openalex.org) — tìm paper thật theo chủ đề."""

import httpx

from app.core.config import get_settings

_MAX_PER_PAGE = 200  # giới hạn cứng của OpenAlex cho tham số per-page


class OpenAlexError(Exception):
    pass


def search_works(query: str, count: int = 25) -> list[dict]:
    """Tìm tối đa `count` work khớp `query`, tự phân trang vì OpenAlex giới hạn
    per-page ở 200 (count lớn hơn 200 sẽ gọi nhiều request kế tiếp nhau).

    Dùng cursor pagination (không dùng `page=`): với `search=`, thứ hạng relevance
    được tính lại mỗi request và có thể xê dịch nhẹ giữa các request riêng biệt
    (search cluster của OpenAlex cân bằng tải qua nhiều node) — `page=2,3,...` từng
    bị trùng/thiếu kết quả giữa các trang vì lý do này; cursor tránh được vì nó mã
    hoá vị trí đã dừng, không phụ thuộc việc tính lại điểm relevance.
    """
    settings = get_settings()
    results: list[dict] = []
    cursor: str | None = "*"

    while len(results) < count and cursor:
        per_page = min(_MAX_PER_PAGE, count - len(results))
        params: dict[str, str | int] = {"search": query, "per_page": per_page, "cursor": cursor}
        if settings.open_alex_api_key:
            params["api_key"] = settings.open_alex_api_key

        try:
            response = httpx.get(f"{settings.open_alex_api_url}/works", params=params, timeout=20.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenAlexError(f"Lỗi gọi OpenAlex API: {exc}") from exc

        data = response.json()
        batch = data.get("results", [])
        if not batch:
            break
        results.extend(batch)
        cursor = data.get("meta", {}).get("next_cursor")

    return results[:count]
