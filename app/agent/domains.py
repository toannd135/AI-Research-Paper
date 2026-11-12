"""Ba chế độ nghiên cứu tách biệt hoàn toàn, chọn theo kho dữ liệu (workspace.domain):

- general   : không chọn kho → tìm trên OpenAlex/thư viện chung, prompt và kiểm tra CHUNG, không có thuật ngữ MRI hay deepfake.
- mri_brain : chỉ prompt/kiểm tra MRI não (Dice/HD95, vùng WT/TC/ET, chuỗi T1/T1c/T2/FLAIR, missing-modality, độ tin cậy lâm sàng).
- deepfake  : chỉ prompt/kiểm tra phát hiện deepfake (AUC/EER/ACC, cross-dataset/cross-generator, frame/video-level).

Giống app/core/scope.py: worker Celery chạy mỗi lần một task trong một tiến trình, nên biến cấp module là đủ và
được thấy từ các thread con của LangGraph. tasks.py đặt lại domain ở ĐẦU mỗi task, nên task trước không rò sang task sau.
"""

from __future__ import annotations

import re
from typing import Any

GENERAL = "general"
MRI_BRAIN = "mri_brain"
DEEPFAKE = "deepfake"
DOMAINS = (GENERAL, MRI_BRAIN, DEEPFAKE)
DOMAIN_LABELS = {GENERAL: "Chung (OpenAlex)", MRI_BRAIN: "MRI não", DEEPFAKE: "Deepfake"}

_current: str = GENERAL


def normalize_domain(value: str | None) -> str:
    key = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return key if key in DOMAINS else GENERAL


def set_domain(value: str | None) -> None:
    global _current
    _current = normalize_domain(value)


def current_domain() -> str:
    return _current


def is_mri() -> bool:
    return _current == MRI_BRAIN


def is_deepfake() -> bool:
    return _current == DEEPFAKE


# ---------- trích xuất số liệu (extractor) ----------
_COMMON_EXTRACT_RULES = (
    "value must be the number EXACTLY as printed in the passage. Use null for any field the passage does not state; "
    "never guess, convert or compute. variant = ablation variant name (e.g. 'w/o X') or null for the full model. "
    "spread = the number printed after '±' for that value (std/CI half-width) EXACTLY as printed, else null; "
    "spread_type is SD, SE or CI95 only if the passage says which, else null. "
    "If there are no numeric results, return []."
)
_FIELDS = '{"paper_id","model","dataset","dataset_version","split","region","metric","value","unit","variant","modality","table","spread","spread_type"}'

_EXTRACT: dict[str, dict[str, Any]] = {
    GENERAL: {
        "key_re": re.compile(
            r"\b(acc|accuracy|f1|precision|recall|sensitivity|specificity|auc|auroc|map|average precision|iou|miou|jaccard"
            r"|psnr|ssim|lpips|fid|bleu|rouge|rmse|mae|mse|r2"
            r"|params?|parameters|gflops|flops|inference|latency|throughput)\b",
            re.I,
        ),
        "prompt": (
            "Extract quantitative results from the passages. Return ONLY a JSON list; each item: " + _FIELDS + ". "
            "metric is the metric name as printed (e.g. Accuracy, F1, Precision, Recall, Sensitivity, Specificity, AUC, mAP, AP, IoU, mIoU, "
            "Jaccard, PSNR, SSIM, LPIPS, FID, BLEU, ROUGE, RMSE, MAE, Params, GFLOPs, InferenceTime). region is always null. modality is null. "
            "unit is ratio|percent|dB|M|G|ms or null. "
            "Put the evaluation split/setting in split only if printed. " + _COMMON_EXTRACT_RULES
        ),
        "regions": {},
    },
    MRI_BRAIN: {
        "key_re": re.compile(
            r"\b(dice|dsc|hd95|hausdorff|assd|asd|nsd|iou|miou|jaccard|sensitivity|specificity|precision|recall"
            r"|psnr|ssim|params?|parameters|gflops|flops|inference|latency)\b",
            re.I,
        ),
        "prompt": (
            "Extract quantitative brain-MRI segmentation results from the passages. Return ONLY a JSON list; each item: " + _FIELDS + ". "
            "metric is one of Dice, HD95, ASSD, NSD, IoU, Jaccard, Sensitivity, Specificity, Precision, Recall, PSNR, SSIM, Params, GFLOPs, "
            "InferenceTime. region is WT/TC/ET/AVG or null (null for non-segmentation metrics). unit is ratio|percent|mm|dB|M|G|ms or null. "
            "modality = list of the MRI sequences used as input (T1, T1c, T2, FLAIR) only if printed, else null. "
            "dataset_version = e.g. the BraTS edition year only if printed. " + _COMMON_EXTRACT_RULES
        ),
        "regions": {
            "wt": "WT", "tc": "TC", "et": "ET", "whole tumor": "WT", "tumor core": "TC", "enhancing tumor": "ET",
            "avg": "AVG", "average": "AVG", "mean": "AVG",
        },
    },
    DEEPFAKE: {
        "key_re": re.compile(r"\b(auc|auroc|eer|hter|acc|accuracy|f1|ap|average precision|precision|recall|log ?loss|tpr|fpr|params?|parameters|gflops|flops|inference|latency|fps)\b", re.I),
        "prompt": (
            "Extract quantitative deepfake-detection results from the passages. Return ONLY a JSON list; each item: " + _FIELDS + ". "
            "metric is one of AUC, EER, HTER, ACC, AP, F1, Precision, Recall, LogLoss, TPR, Params, GFLOPs, InferenceTime. region is always null. unit is ratio|percent|M|G|ms or null. "
            "Put the evaluation setting (e.g. 'cross-dataset', 'cross-generator', 'cross-manipulation', 'in-domain', 'frame-level', 'video-level', 'c23', 'c40') "
            "in split only if printed; dataset = e.g. FaceForensics++, Celeb-DF, DFDC only if printed; "
            "modality = list of input modalities (video, audio, image) only if printed, else null. " + _COMMON_EXTRACT_RULES
        ),
        "regions": {},
    },
}


def extract_profile() -> dict[str, Any]:
    return _EXTRACT[_current]


# ---------- thuật ngữ (science QA) ----------
_COMMON_TERMS: tuple[tuple[str, ...], ...] = (
    (r"\bgeneralization\b", r"\bgeneralisation\b"),
    (r"\bmodeling\b", r"\bmodelling\b"),
    (r"\bmultimodal\b", r"\bmulti-modal\b"),
    (r"\bcross-modal\b", r"\bcross modal\b", r"\bcrossmodal\b"),
    (r"\bcross-dataset\b", r"\bcross dataset\b"),
    (r"\bvision-language\b", r"\bvision language\b"),
    (r"\bAUROC\b", r"\bAUC-ROC\b", r"\bROC-AUC\b"),
)
_DOMAIN_TERMS: dict[str, tuple[tuple[str, ...], ...]] = {
    GENERAL: (),
    MRI_BRAIN: (
        (r"\bT1c\b", r"\bT1ce\b", r"\bT1Gd\b", r"\bT1-Gd\b", r"\bT1\+C\b", r"\bT1 post-contrast\b"),
        (r"\bHD95\b", r"\bHD 95\b", r"\b95% Hausdorff\b", r"\bHausdorff95\b"),
        (r"\btumor\b", r"\btumour\b"),
        (r"\bfull-modal\b", r"\bfull-modality\b", r"\bfull modality\b"),
    ),
    DEEPFAKE: (
        (r"\bdeepfakes?\b", r"\bdeep-fakes?\b", r"\bdeep fakes?\b"),
        (r"\bcross-generator\b", r"\bcross generator\b"),
        (r"\bCeleb-DF\b", r"\bCelebDF\b", r"\bCeleb DF\b"),
        (r"\bFaceForensics\+\+\b", r"\bFF\+\+\b"),
    ),
}


def term_groups() -> tuple[tuple[str, ...], ...]:
    return _COMMON_TERMS + _DOMAIN_TERMS[_current]


# ---------- prompt viết bài ----------
_RULES: dict[str, str] = {
    GENERAL: (
        "DOMAIN SCOPE (general literature search):\n"
        "   - Treat the topic on its own terms: use only the terminology, datasets and metrics of the field the question is about, "
        "as they appear in the evidence; do not import conventions from unrelated application domains.\n"
    ),
    MRI_BRAIN: (
        "DOMAIN SCOPE (brain MRI):\n"
        "   - The corpus is brain-MRI research (e.g. glioma/tumor segmentation, BraTS). Use its conventions: Dice and HD95 per region "
        "(whole tumor WT, tumor core TC, enhancing tumor ET are three different quantities), MRI sequences T1/T1c/T2/FLAIR, "
        "missing-modality robustness, and clinical reliability (external/multi-centre validation, scanner/protocol shift, uncertainty).\n"
        "   - When averaging Dice over the number of available modalities, also give the min/max or per-subset values.\n"
        "   - Keep segmentation, missing-modality-learning and synthesis-only methods in clearly separated taxonomy groups.\n"
        "   - Never say the records carry a missing-modality configuration unless the EVIDENCE LIMITS report missing-modality groups.\n"
    ),
    DEEPFAKE: (
        "DOMAIN SCOPE (deepfake detection):\n"
        "   - The corpus is deepfake / face-forgery / synthetic-media detection research. Use its conventions: AUC, EER, ACC, AP; "
        "frame-level vs video-level evaluation; in-domain vs cross-dataset, cross-manipulation and cross-generator generalization "
        "(e.g. FaceForensics++ → Celeb-DF/DFDC); robustness to compression, resizing and adversarial perturbation.\n"
        "   - Values from different evaluation settings (in-domain vs cross-dataset, frame vs video level, compression level c23/c40) "
        "are not comparable; keep them in separate columns or tables.\n"
        "   - Separate method families clearly (spatial artifact, frequency-domain, temporal/biological-signal, multimodal audio-visual, "
        "foundation-model/CLIP-based) and do not mix generation methods with detection methods.\n"
    ),
}


def domain_rules() -> str:
    return _RULES[_current]


# Câu chữ trong khung chặng viết bài (synthesize_node._STAGE_STRUCTURES) theo từng chế độ.
_STAGE_TEXT: dict[str, dict[str, str]] = {
    "comparability_example": {
        GENERAL: "sub-group/class (e.g. different classes, subsets or task variants are different quantities)",
        MRI_BRAIN: "sub-region/class (e.g. whole tumor, tumor core and enhancing tumor are three different quantities)",
        DEEPFAKE: "evaluation setting (e.g. in-domain, cross-dataset and cross-generator results, or frame-level and video-level scores, are different quantities)",
    },
    "extraction_fields": {
        GENERAL: "architecture, dataset and version, metrics, reported values, stated limitations",
        MRI_BRAIN: "architecture, dataset and version, input MRI modalities, tumor sub-regions, metrics, reported values, stated limitations",
        DEEPFAKE: "architecture, training/test datasets, manipulation or generator types, evaluation setting, metrics, reported values, stated limitations",
    },
    "table_group_col": {
        GENERAL: "class/subset, metric, value",
        MRI_BRAIN: "sub-region (WT/TC/ET), metric, value",
        DEEPFAKE: "evaluation setting (in-domain/cross-dataset/cross-generator, frame/video level), metric, value",
    },
    "chart_examples": {
        GENERAL: (
            "(e.g. one barh ranking of a single metric, one grouped bar across datasets, one heatmap of methods x datasets), "
            "each restricted to ONE comparable setting (same dataset version, same split, same metric)"
        ),
        MRI_BRAIN: (
            "(e.g. one barh ranking of a single metric, one grouped bar across regions, one heatmap of methods x regions, "
            "or a line over the number of available modalities when the sources report it), each restricted to ONE comparable setting "
            "(same dataset version, same region, same metric)"
        ),
        DEEPFAKE: (
            "(e.g. one barh ranking of in-domain AUC, one grouped bar of cross-dataset AUC across test sets, one heatmap of methods x test datasets), "
            "each restricted to ONE comparable setting (same training set, same test set, same frame/video level, same metric)"
        ),
    },
    "chart_split": {
        GENERAL: (
            "Split the evidence into separate charts, one per dataset/metric. Never plot values from incomparable settings on one axis, "
            "never mix different metrics or a metric with parameter counts,"
        ),
        MRI_BRAIN: (
            "Split the evidence into separate charts, e.g. Dice for whole tumor, Dice for tumor core, Dice for enhancing tumor on the same dataset version, "
            "or HD95 on its own; one chart per region/metric. Never plot values from incomparable settings on one axis, never mix Dice with HD95 or with parameter counts,"
        ),
        DEEPFAKE: (
            "Split the evidence into separate charts, e.g. in-domain AUC, cross-dataset AUC and EER each on their own; one chart per setting/metric. "
            "Never plot values from incomparable settings on one axis, never mix AUC with EER or with parameter counts,"
        ),
    },
    "robustness_heading": {
        GENERAL: "### 6.2 Generalization, Robustness & Deployment Concerns\n",
        MRI_BRAIN: "### 6.2 Generalization, Robustness & Clinical/Deployment Concerns\n",
        DEEPFAKE: "### 6.2 Generalization, Robustness & Deployment Concerns\n",
    },
    "robustness_body": {
        GENERAL: (
            "- Go beyond accuracy: treat reliability as separate dimensions — external validation, distribution shift, uncertainty estimation and calibration, "
            "failure / out-of-distribution detection, robustness to noisy or missing inputs, computational cost, and reproducibility (code availability). "
        ),
        MRI_BRAIN: (
            "- Go beyond accuracy: treat clinical reliability as separate dimensions — external / multi-centre validation, scanner or protocol shift, uncertainty estimation and calibration, "
            "failure / out-of-distribution detection, robustness to absent or corrupted inputs, computational cost, and reproducibility (code availability). "
        ),
        DEEPFAKE: (
            "- Go beyond in-domain accuracy: treat reliability as separate dimensions — cross-dataset and cross-generator generalization, unseen manipulation types, "
            "robustness to compression/resizing/adversarial perturbation, calibration and open-set detection, real-time cost, and reproducibility (code availability). "
        ),
    },
}


def stage_text(key: str) -> str:
    return _STAGE_TEXT[key][_current]


# ---------- lĩnh vực cố định theo chế độ (không để LLM đoán → khung bài ổn định giữa các lần chạy) ----------
_DOMAIN_FIELD: dict[str, str | None] = {GENERAL: None, MRI_BRAIN: "medicine", DEEPFAKE: "computer_vision"}


def domain_field() -> str | None:
    return _DOMAIN_FIELD[_current]


# ---------- mục con riêng của Section 5 (Comparative Evidence Synthesis) ----------
_STAGE4: dict[str, str] = {
    GENERAL: "",
    MRI_BRAIN: (
        "### Missing-Modality Robustness\n"
        "- How performance changes when one or more MRI sequences (T1, T1c, T2, FLAIR) are absent: discuss the missing-modality "
        "coverage matrix and degradation chart if they appear in the text (refer to them by their Figure/Table number), which "
        "sequences matter most according to the sources, and which subsets were never evaluated. Report Δ only where the same "
        "source gives both the full-modality and the reduced-modality result. If the EVIDENCE LIMITS report no missing-modality "
        "record, say that no quantitative degradation matrix could be built and discuss only what the cited passages state in prose."
    ),
    DEEPFAKE: (
        "- In 5.1, the benchmark table must use the columns | Dataset | Manipulation / generator types | Real / fake size (as reported) | "
        "Compression or quality levels | Ref |, filling a cell only from the evidence and writing '–' otherwise.\n"
        "### Cross-Dataset & Cross-Generator Generalization\n"
        "- Contrast in-domain results with cross-dataset (e.g. trained on FaceForensics++, tested on Celeb-DF/DFDC), cross-manipulation "
        "and cross-generator (unseen GAN/diffusion generators) results. Use the cross-dataset table if it appears in the text "
        "(refer to it by its Table number); give the in-domain → cross-dataset drop only when the same source reports both. "
        "Explain which method families generalize better and why, according to the sources.\n"
        "### Robustness to Compression & Perturbation\n"
        "- Results under video compression (e.g. c23/c40), resizing, blur/noise and adversarial perturbation, frame-level vs video-level "
        "aggregation, and real-time cost. If the evidence reports none, state that it was not found in the retrieved evidence."
    ),
}


def domain_stage4() -> str:
    return _STAGE4[_current]


# ---------- metric chính cho biểu đồ đánh đổi hiệu năng–tham số ----------
_TRADEOFF_METRICS: dict[str, tuple[str, ...]] = {
    GENERAL: ("accuracy", "acc", "f1", "map", "auc", "auroc"),
    MRI_BRAIN: ("dice",),
    DEEPFAKE: ("auc", "auroc", "acc", "accuracy"),
}


def tradeoff_metrics() -> tuple[str, ...]:
    return _TRADEOFF_METRICS[_current]


# ---------- metric cho truy vấn lấy bảng kết quả (search_node._results_query) ----------
_RESULT_QUERY_METRICS: dict[str, str | None] = {
    GENERAL: None,  # dùng metric của lĩnh vực (profiles.py)
    MRI_BRAIN: "Dice HD95 whole tumor WT tumor core TC enhancing tumor ET sensitivity ASSD",
    DEEPFAKE: "AUC EER ACC AP cross-dataset in-domain frame-level video-level",
}


def result_query_metrics() -> str | None:
    return _RESULT_QUERY_METRICS[_current]
