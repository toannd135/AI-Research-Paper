"""Chọn thiết bị chạy model embedding/reranker: ưu tiên GPU, tự lùi về CPU khi không khả dụng.

Vì sao không chỉ dùng `torch.cuda.is_available()`:
máy dev của dự án có GPU 5.67 GiB, nạp đồng thời BGE-M3 (~2.3 GiB) và cross-encoder reranker
từng gây `torch.OutOfMemoryError` (xem docs/task.md). Nên ngoài việc dò GPU, module còn:

1. Kiểm tra VRAM còn trống có đủ ngưỡng tối thiểu cho model sắp nạp hay không.
2. Cung cấp `load_with_fallback()` để nếu vẫn OOM lúc nạp thì nạp lại trên CPU thay vì làm hỏng
   cả tiến trình worker.

Đặt EMBEDDING_DEVICE=cpu|cuda|cuda:1|mps trong .env để ép thủ công, bỏ qua toàn bộ phần tự dò.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

AUTO = "auto"

# VRAM trống tối thiểu để dám đưa 1 model lên GPU. BGE-M3 chiếm ~2.3 GiB; để dư cho
# activation lúc encode theo batch và cho model thứ hai (reranker) nạp sau.
_MIN_FREE_VRAM_BYTES = 3 * 1024**3


def _cuda_device_with_free_memory(min_free_bytes: int) -> str | None:
    """Trả về 'cuda:<i>' của GPU đầu tiên còn đủ VRAM trống, hoặc None."""
    import torch

    if not torch.cuda.is_available():
        return None
    for index in range(torch.cuda.device_count()):
        try:
            free, total = torch.cuda.mem_get_info(index)
        except Exception as exc:  # driver lỗi/không đọc được -> coi như không dùng được
            logger.warning("Không đọc được bộ nhớ GPU %d: %s", index, exc)
            continue
        name = torch.cuda.get_device_properties(index).name
        if free >= min_free_bytes:
            logger.info(
                "Chọn GPU %d (%s): trống %.2f/%.2f GiB", index, name, free / 2**30, total / 2**30
            )
            return f"cuda:{index}"
        logger.info(
            "Bỏ qua GPU %d (%s): chỉ còn %.2f GiB trống, cần tối thiểu %.2f GiB",
            index, name, free / 2**30, min_free_bytes / 2**30,
        )
    return None


def resolve_device(preferred: str = AUTO, min_free_bytes: int = _MIN_FREE_VRAM_BYTES) -> str:
    """Quyết định thiết bị thực tế.

    `preferred` khác 'auto' được tôn trọng nguyên vẹn (kể cả 'cuda' trên máy không có GPU —
    để lỗi hiện rõ thay vì âm thầm chạy chậm trên CPU trái ý người cấu hình).
    """
    if _forced_cpu:
        return "cpu"

    if preferred and preferred.strip().lower() != AUTO:
        return preferred.strip()

    try:
        import torch
    except ImportError:
        logger.warning("Không import được torch, dùng CPU")
        return "cpu"

    device = _cuda_device_with_free_memory(min_free_bytes)
    if device:
        return device

    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        logger.info("Dùng Apple MPS")
        return "mps"

    logger.info("Không có GPU khả dụng, dùng CPU")
    return "cpu"


def is_out_of_memory(exc: BaseException) -> bool:
    """Nhận diện lỗi hết bộ nhớ GPU (torch.OutOfMemoryError hoặc RuntimeError chứa 'out of memory')."""
    import torch

    oom_cls = getattr(torch, "OutOfMemoryError", None)
    if oom_cls is not None and isinstance(exc, oom_cls):
        return True
    return isinstance(exc, RuntimeError) and "out of memory" in str(exc).lower()


# Khi đã tràn VRAM một lần, mọi lần nạp sau trong tiến trình này đi thẳng xuống CPU:
# GPU rõ ràng không đủ cho tải thực tế, thử lại chỉ tốn thời gian và lại hỏng giữa chừng.
_forced_cpu = False


def force_cpu() -> None:
    """Đánh dấu tiến trình này phải dùng CPU cho mọi model nạp về sau."""
    global _forced_cpu
    _forced_cpu = True


def cpu_is_forced() -> bool:
    return _forced_cpu


def free_gpu_memory() -> None:
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:  # không có torch/CUDA thì bỏ qua
        pass


def run_with_oom_fallback(
    run: Callable[[], T],
    *,
    on_oom: Callable[[], None],
    label: str,
) -> T:
    """Chạy `run()`; nếu tràn VRAM thì ép CPU, gọi `on_oom()` để nạp lại model rồi thử lại 1 lần.

    Cần thiết vì `load_with_fallback` chỉ bảo vệ lúc nạp model: batch lớn lúc encode/rerank mới
    là nơi VRAM thực sự bị đẩy tới hạn, và một lần OOM ở đó sẽ làm hỏng cả task Celery.
    """
    try:
        return run()
    except Exception as exc:
        if not is_out_of_memory(exc):
            raise
        logger.warning("%s tràn VRAM lúc chạy, chuyển hẳn sang CPU và thử lại: %s", label, exc)
        force_cpu()
        free_gpu_memory()
        on_oom()
        return run()


def load_with_fallback(load: Callable[[str], T], device: str, label: str) -> tuple[T, str]:
    """Nạp model trên `device`; nếu hết VRAM thì nạp lại trên CPU. Trả về (model, device đã dùng)."""
    if device == "cpu":
        return load("cpu"), "cpu"
    try:
        return load(device), device
    except Exception as exc:
        if not is_out_of_memory(exc):
            raise
        logger.warning("%s hết VRAM trên %s, chuyển sang CPU: %s", label, device, exc)
        force_cpu()
        free_gpu_memory()
        return load("cpu"), "cpu"


def load_once(load: Callable[[], T]) -> Callable[[], T]:
    """Như lru_cache cho hàm không tham số, nhưng chỉ MỘT luồng nạp model khi nhiều luồng gọi cùng lúc.

    `lru_cache` không chặn nhiều luồng cùng lọt vào nhánh miss: retrieve_evidence chạy 5 sub-query
    song song nên từng nạp BGE-M3 5 lần (hết VRAM rồi 5 bản trên CPU, ~10 GiB RAM).
    """
    lock = threading.Lock()
    holder: list[T] = []

    def get() -> T:
        if holder:
            return holder[0]
        with lock:
            if not holder:
                holder.append(load())
            return holder[0]

    def cache_clear() -> None:
        with lock:
            holder.clear()

    get.cache_clear = cache_clear  # type: ignore[attr-defined]
    return get
