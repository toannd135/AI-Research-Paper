"""Chỉ dẫn riêng cho đề tài deepfake, chỉ dùng bởi `scripts/run_deepfake.py`.

Luồng chính (web/API/Celery) không import module này: prompt gốc giữ nguyên, phần thêm được nối vào
system prompt ngay lúc gọi LLM thông qua `OverlayGateway`.
"""

import json
import logging
import time
from pathlib import Path

from app.ai.llm_gateway.base import LLMGateway, LLMResponse, Message

logger = logging.getLogger(__name__)

_HEADER = "\n\nDEEPFAKE DOMAIN GUIDANCE (adds to the rules above; never relaxes the evidence, citation or output-format rules):\n"

OVERLAYS: dict[str, str] = {
    "plan": (
        "The corpus is a fixed local set of deepfake papers. Make the queries, in English, jointly cover: "
        "forgery types (face swap, face reenactment, entire face synthesis, GAN-based, diffusion-based, audio or audio-visual forgery); "
        "detection cues (spatial artifacts, frequency-domain traces, temporal inconsistency, identity consistency, multimodal mismatch); "
        "benchmarks and protocols (FaceForensics++, Celeb-DF, DFDC, DeeperForensics, WildDeepfake when relevant; intra-dataset, cross-dataset, cross-manipulation); "
        "generalization and robustness (unseen generators, compression, perturbation, adversarial attack). "
        "Keep the required JSON format and number of queries."
    ),
    "analyze": (
        "Organize the analysis by detection cue and by forgery type. Treat the evaluation protocol as part of every result: "
        "name the train dataset, test dataset, compression level (for example c23/c40) and whether the score is frame-level or video-level when the source states them. "
        "Compare numbers only inside the same protocol. Separate intra-dataset performance from cross-dataset and cross-manipulation generalization, "
        "and report the gap only when one source gives both values under a stated protocol. "
        "Note which approaches have been tested on diffusion-generated content and which only on older GAN or face-swap data. "
        "The dataset and method names here are guidance only: mention a result only if the evidence contains it."
    ),
    "blueprint": (
        "Use taxonomy axes suited to deepfake detection, such as forgery type, detection cue, temporal scope (frame or video) and learning setting; "
        "keep only axes the evidence supports. Make at least one research question about generalization across datasets or unseen generators, "
        "phrased so that it remains answerable if the corpus has limited evidence."
    ),
    "section": (
        "Keep deepfake terminology consistent: detection is not generation, and face swap, reenactment and full synthesis are distinct. "
        "Every table or chart comparing detectors must state or group by dataset pair, protocol, and frame-level or video-level scoring; "
        "never rank methods across different protocols. AUC, EER and ACC are different metrics and must not share one axis or column. "
        "Discuss generalization, robustness to compression and perturbation, and limits of benchmark datasets where the evidence allows. "
        "Do not state any dataset size, score or release year that is absent from the evidence."
    ),
}

EXTRACT_OVERLAY = (
    " Deepfake detection passages: use dataset for the test dataset exactly as printed. "
    "Put the protocol words exactly as printed in split, for example 'cross-dataset', 'intra-dataset', 'frame-level', 'video-level', 'c23' or 'c40'. "
    "Do not infer a protocol, compression level or scoring level the passage does not print."
)

# Theo thứ tự kiểm tra; dấu hiệu lấy từ prompt gốc, `test_deepfake_overlay` kiểm tra chúng còn khớp.
_STAGE_MARKERS = (
    ("plan", "Bạn lập kế hoạch tìm kiếm tài liệu"),
    ("analyze", "Bạn là chuyên gia nghiên cứu khoa học cao cấp"),
    ("analyze", "độc lập xuất sắc"),
    ("extract", "Extract quantitative results from the passages"),
    ("blueprint", "Research Blueprint"),
    ("section", "for a top-tier peer-reviewed academic paper"),
)


def classify_stage(system_prompt: str) -> str | None:
    """Tên chặng theo system prompt; None với các lời gọi phụ (sửa mermaid, dịch, kiểm tra...)."""
    return next((stage for stage, marker in _STAGE_MARKERS if marker in system_prompt), None)


def with_overlay(messages: list[Message]) -> tuple[list[Message], str | None]:
    """Bản sao `messages` với chỉ dẫn deepfake nối vào system prompt đầu tiên, kèm tên chặng."""
    if not messages or messages[0].role != "system":
        return messages, None
    stage = classify_stage(messages[0].content)
    overlay = OVERLAYS.get(stage or "")
    if overlay is None:
        return messages, stage
    return [Message(role="system", content=messages[0].content + _HEADER + overlay), *messages[1:]], stage


class OverlayGateway(LLMGateway):
    """Bọc gateway thật: thêm chỉ dẫn deepfake và ghi log prompt ra JSONL.

    Graph truyền model_name="default" khi llm được inject nên luôn dùng model thật đã giữ ở đây.
    """

    def __init__(self, inner: LLMGateway, model_name: str, log_path: Path) -> None:
        self._inner = inner
        self._model_name = model_name
        self._log_path = log_path

    def generate(self, messages: list[Message], model_name: str) -> LLMResponse:
        final, stage = with_overlay(messages)
        start = time.perf_counter()
        response = self._inner.generate(final, self._model_name)
        self._log({"stage": stage, "seconds": round(time.perf_counter() - start, 1), "model": response.model, "system": final[0].content if final else "", "response_chars": len(response.text)})
        return response

    def _log(self, entry: dict) -> None:
        try:
            with self._log_path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("Không ghi được log prompt %s", self._log_path, exc_info=True)
