"""Test chọn thiết bị: ưu tiên GPU còn đủ VRAM, lùi về CPU khi thiếu, tôn trọng cấu hình ép cứng."""

import sys
import types
from unittest.mock import MagicMock

import pytest

from app.ai.device import is_out_of_memory, load_with_fallback, resolve_device

GIB = 1024**3


@pytest.fixture(autouse=True)
def _reset_forced_cpu(monkeypatch):
    """Cờ ép CPU là state toàn tiến trình -> reset trước mỗi test để không lệ thuộc thứ tự chạy."""
    import app.ai.device as device_mod

    monkeypatch.setattr(device_mod, "_forced_cpu", False)


def _fake_torch(monkeypatch, *, cuda_available=False, devices=(), mps=False):
    """devices: list (free_bytes, total_bytes) cho từng GPU."""
    torch = types.ModuleType("torch")

    class _OOM(RuntimeError):
        pass

    torch.OutOfMemoryError = _OOM
    torch.cuda = types.SimpleNamespace(
        is_available=lambda: cuda_available,
        device_count=lambda: len(devices),
        mem_get_info=lambda i: devices[i],
        get_device_properties=lambda i: types.SimpleNamespace(name=f"FakeGPU{i}"),
        empty_cache=lambda: None,
    )
    torch.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: mps))
    monkeypatch.setitem(sys.modules, "torch", torch)
    return torch


def test_prefers_gpu_when_enough_free_vram(monkeypatch):
    _fake_torch(monkeypatch, cuda_available=True, devices=[(6 * GIB, 8 * GIB)])
    assert resolve_device("auto") == "cuda:0"


def test_falls_back_to_cpu_when_vram_is_tight(monkeypatch):
    """GPU 5.67 GiB đã bị chiếm gần hết -> không đẩy model lên, tránh CUDA OOM."""
    _fake_torch(monkeypatch, cuda_available=True, devices=[(1 * GIB, 6 * GIB)])
    assert resolve_device("auto") == "cpu"


def test_picks_second_gpu_when_first_is_busy(monkeypatch):
    _fake_torch(monkeypatch, cuda_available=True, devices=[(0.5 * GIB, 8 * GIB), (7 * GIB, 8 * GIB)])
    assert resolve_device("auto") == "cuda:1"


def test_uses_cpu_when_no_accelerator(monkeypatch):
    _fake_torch(monkeypatch, cuda_available=False)
    assert resolve_device("auto") == "cpu"


def test_uses_mps_when_available(monkeypatch):
    _fake_torch(monkeypatch, cuda_available=False, mps=True)
    assert resolve_device("auto") == "mps"


@pytest.mark.parametrize("forced", ["cpu", "cuda", "cuda:1", "mps"])
def test_explicit_setting_is_respected(monkeypatch, forced):
    """Cấu hình ép cứng phải được tôn trọng, không bị phần tự dò ghi đè."""
    _fake_torch(monkeypatch, cuda_available=True, devices=[(8 * GIB, 8 * GIB)])
    assert resolve_device(forced) == forced


def test_load_with_fallback_retries_on_cpu_after_oom(monkeypatch):
    torch = _fake_torch(monkeypatch, cuda_available=True, devices=[(8 * GIB, 8 * GIB)])
    attempts = []

    def load(device):
        attempts.append(device)
        if device != "cpu":
            raise torch.OutOfMemoryError("CUDA out of memory")
        return MagicMock(name="model-on-cpu")

    model, used = load_with_fallback(load, "cuda:0", "Embedding model")
    assert attempts == ["cuda:0", "cpu"]
    assert used == "cpu" and model is not None


def test_load_with_fallback_does_not_swallow_other_errors(monkeypatch):
    _fake_torch(monkeypatch, cuda_available=True, devices=[(8 * GIB, 8 * GIB)])

    def load(device):
        raise ValueError("tên model sai")

    with pytest.raises(ValueError, match="tên model sai"):
        load_with_fallback(load, "cuda:0", "Embedding model")


def test_is_out_of_memory_detects_runtime_error(monkeypatch):
    _fake_torch(monkeypatch, cuda_available=True, devices=[(8 * GIB, 8 * GIB)])
    assert is_out_of_memory(RuntimeError("CUDA out of memory. Tried to allocate 2 GiB"))
    assert not is_out_of_memory(RuntimeError("shape mismatch"))


def test_run_with_oom_fallback_retries_after_reloading_on_cpu(monkeypatch):
    """Tràn VRAM lúc encode batch lớn phải tự nạp lại trên CPU, không làm hỏng cả task Celery."""
    import app.ai.device as device_mod

    monkeypatch.setattr(device_mod, "_forced_cpu", False)
    torch = _fake_torch(monkeypatch, cuda_available=True, devices=[(8 * GIB, 8 * GIB)])
    calls, reloads = [], []

    def run():
        calls.append(device_mod.cpu_is_forced())
        if not device_mod.cpu_is_forced():
            raise torch.OutOfMemoryError("CUDA out of memory")
        return "kết quả"

    assert device_mod.run_with_oom_fallback(run, on_oom=lambda: reloads.append(1), label="Embedding") == "kết quả"
    assert calls == [False, True]      # chạy lần 2 sau khi đã ép CPU
    assert reloads == [1]              # model được nạp lại đúng một lần
    assert device_mod.resolve_device("auto") == "cpu"  # các lần nạp sau đi thẳng CPU


def test_run_with_oom_fallback_propagates_other_errors(monkeypatch):
    import app.ai.device as device_mod

    monkeypatch.setattr(device_mod, "_forced_cpu", False)
    _fake_torch(monkeypatch, cuda_available=True, devices=[(8 * GIB, 8 * GIB)])

    def run():
        raise ValueError("lỗi khác")

    with pytest.raises(ValueError, match="lỗi khác"):
        device_mod.run_with_oom_fallback(run, on_oom=lambda: None, label="Reranker")


def test_forced_cpu_overrides_auto_detection(monkeypatch):
    import app.ai.device as device_mod

    monkeypatch.setattr(device_mod, "_forced_cpu", False)
    _fake_torch(monkeypatch, cuda_available=True, devices=[(8 * GIB, 8 * GIB)])
    assert device_mod.resolve_device("auto") == "cuda:0"

    device_mod.force_cpu()
    assert device_mod.resolve_device("auto") == "cpu"


def test_load_once_loads_a_single_time_under_concurrency():
    import time
    from concurrent.futures import ThreadPoolExecutor

    from app.ai.device import load_once

    calls = []

    @load_once
    def slow_load():
        calls.append(1)
        time.sleep(0.2)
        return object()

    with ThreadPoolExecutor(max_workers=5) as pool:
        models = list(pool.map(lambda _: slow_load(), range(5)))
    assert len(calls) == 1
    assert len({id(m) for m in models}) == 1
    slow_load.cache_clear()
    slow_load()
    assert len(calls) == 2
