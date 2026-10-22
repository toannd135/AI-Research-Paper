"""Hồ sơ lĩnh vực (field) và đối tượng đọc (audience): điều chỉnh vai trò, mục bắt buộc, metric, hình ảnh và giọng văn.

Không có hồ sơ nào được phép bịa số liệu/hình: các gợi ý ở đây chỉ nói nên trình bày GÌ khi evidence có dữ liệu.
"""

from __future__ import annotations

import re
from typing import Any

DEFAULT_FIELD = "computing"
DEFAULT_AUDIENCE = "lecturer"

FIELD_PROFILES: dict[str, dict[str, Any]] = {
    "computing": {
        "label": "Computer Science & AI",
        "role": "nhà khoa học máy tính và AI researcher",
        "keywords": [],
        "metrics": "accuracy, F1, precision/recall, latency, throughput, parameter count, cost",
        "figures": "architecture/pipeline diagrams, benchmark bar charts, accuracy-vs-cost trade-off charts",
        "stage4": "",
        # Danh sách cũ của search_node: chỉ có nghĩa khi đề tài thuộc CS/NLP.
        "off_domain": [
            "wildfire", "forest fire", "fire fighting", "fire detection",
            "crop yield", "soil moisture", "plant pathology", "agricultural",
            "solar cell", "photovoltaic", "power inverter", "traffic flow",
            "dermatology lesion", "bone fracture detection",
        ],
    },
    "computer_vision": {
        "label": "Image Processing & Computer Vision",
        "role": "nhà nghiên cứu thị giác máy tính và xử lý ảnh",
        "keywords": [
            "image", "hình ảnh", "xử lý ảnh", "computer vision", "thị giác máy", "segmentation", "phân đoạn", "object detection",
            "phát hiện đối tượng", "denois", "khử nhiễu", "super-resolution", "siêu phân giải", "deblur",
            "inpainting", "video", "camera", "pixel", "convolutional", "yolo", "diffusion model",
        ],
        "metrics": "PSNR, SSIM, LPIPS, FID, mAP, IoU/mIoU, top-1 accuracy, FPS",
        "figures": "real input/output image comparisons from the source papers, qualitative failure cases, metric bar charts",
        "stage4": (
            "### Qualitative Visual Comparison\n"
            "- Show real figures from the AVAILABLE FIGURES list (```image blocks) that illustrate inputs, outputs or failure cases, "
            "and discuss what they show visually. If no figure is available, describe the visual differences reported in the evidence in prose."
        ),
        "off_domain": [],
    },
    "environment": {
        "label": "Environmental Science",
        "role": "nhà khoa học môi trường",
        "keywords": [
            "environment", "môi trường", "pollution", "ô nhiễm", "pm2.5", "pm10", "air quality", "chất lượng không khí",
            "climate", "khí hậu", "emission", "phát thải", "carbon", "water quality", "nước thải", "waste", "rác thải",
            "biodiversity", "đa dạng sinh học", "deforestation", "phá rừng", "wildfire", "cháy rừng", "flood", "lũ lụt",
            "drought", "hạn hán", "sustainab", "bền vững", "ecosystem", "hệ sinh thái",
        ],
        "metrics": "concentrations with units (µg/m³, mg/L, ppm), emissions (t CO2-eq), trends per year, regional comparisons, exceedance of standards (WHO/QCVN)",
        "figures": "real field/site photographs from the source papers, time-series line charts, regional comparison bar charts, study-area maps",
        "stage4": (
            "### Spatio-Temporal Evidence & Field Observations\n"
            "- Present reported measurements as time-series (```chart type line, labels = years) or regional comparisons, always with units and the standard they are compared against. "
            "Use real site/field photographs or maps from the AVAILABLE FIGURES list when present."
        ),
        "off_domain": [],
    },
    "medicine": {
        "label": "Medicine & Health Sciences",
        "role": "nhà nghiên cứu y sinh và lâm sàng",
        "keywords": [
            "medical", "y tế", "y khoa", "clinical", "lâm sàng", "patient", "bệnh nhân", "disease", "bệnh", "diagnos",
            "chẩn đoán", "cancer", "ung thư", "drug", "thuốc", "therapy", "điều trị", "hospital", "bệnh viện",
            "epidemiolog", "dịch tễ", "mri", "ct scan", "x-ray", "dermatology", "da liễu",
        ],
        "metrics": "sensitivity, specificity, AUC, odds ratio/hazard ratio with 95% CI, p-value, sample size N, incidence/prevalence",
        "figures": "real clinical/medical images from the source papers, forest-plot-style comparisons, cohort flow diagrams",
        "stage4": (
            "### Clinical Evidence Summary\n"
            "- Report study design, population and sample size N for every result; give effect sizes with confidence intervals when reported. "
            "Never present results as clinical advice."
        ),
        "off_domain": [],
    },
    "economics": {
        "label": "Economics & Business",
        "role": "nhà kinh tế học",
        "keywords": [
            "econom", "kinh tế", "gdp", "inflation", "lạm phát", "market", "thị trường", "finance", "tài chính",
            "investment", "đầu tư", "trade", "thương mại", "business", "doanh nghiệp", "labor", "lao động",
            "poverty", "nghèo", "price", "tax", "thuế", "fdi",
        ],
        "metrics": "growth rates (%), elasticities, regression coefficients with standard errors, monetary values with currency and year",
        "figures": "time-series of indicators, cross-country/region comparison bars, policy flow diagrams",
        "stage4": (
            "### Empirical Indicators & Comparative Evidence\n"
            "- Compare reported indicators across countries/sectors/periods; always state currency, base year and data source [n]."
        ),
        "off_domain": [],
    },
    "education": {
        "label": "Education",
        "role": "nhà nghiên cứu giáo dục",
        "keywords": [
            "education", "giáo dục", "learning outcome", "kết quả học tập", "học sinh",
            "teacher", "giáo viên", "curriculum", "chương trình đào tạo", "classroom", "lớp học",
            "e-learning", "pedagog", "sư phạm", "university", "đại học",
        ],
        "metrics": "effect sizes (Cohen's d, Hedges' g), pre/post scores, sample size N, retention/completion rates",
        "figures": "pre/post comparison charts, intervention flow diagrams, real classroom/material illustrations from the source papers",
        "stage4": (
            "### Learning-Outcome Evidence\n"
            "- Summarize reported interventions with sample size, context (level, country) and effect sizes; separate experimental from correlational evidence."
        ),
        "off_domain": [],
    },
}

AUDIENCE_PROFILES: dict[str, dict[str, Any]] = {
    "lecturer": {
        "end_headings": [],
        "label": "lecturers and researchers",
        "style": (
            "Full scholarly depth: methodological rigor, precise related work, formal notation where justified, "
            "explicit threats to validity and open research questions."
        ),
        "front": "",
        "end": "",
    },
    "student": {
        "end_headings": ['Key Takeaways', 'Glossary'],
        "label": "university students",
        "style": (
            "Academic but accessible: define every technical term at first use, explain the intuition before any formula, "
            "add a short concrete example after each key concept, prefer shorter paragraphs."
        ),
        "front": "",
        "end": (
            "## Key Takeaways\n"
            "- 5-7 one-sentence takeaways a student should remember, each grounded in the paper.\n\n"
            "## Glossary\n"
            "- A Markdown table | Term | Plain-language definition | for 8-12 central terms used in the paper."
        ),
    },
    "professional": {
        "end_headings": ['Practical Implications'],
        "label": "working professionals and decision makers",
        "style": (
            "Practical and concise: lead with what matters for practice, explain implications for deployment, cost, risk and readiness; "
            "keep formulas minimal and explain them in words."
        ),
        "front": (
            "## Executive Summary\n"
            "(Place right after the Keywords line, before Section 1: 4-6 hyphen bullets on the problem, what the evidence shows, "
            "practical implications and recommended next steps; numbers only with [n].)"
        ),
        "end": (
            "## Practical Implications\n"
            "- A Markdown table '**Table N: Practical Assessment**' with columns | Approach / Option | Applications | Cost & Resources | Risks | Readiness |; "
            "fill cells only from the evidence, '–' otherwise."
        ),
    },
}


def normalize_field(value: str | None) -> str | None:
    key = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return key if key in FIELD_PROFILES else None


def normalize_audience(value: str | None) -> str:
    key = (value or "").strip().lower()
    return key if key in AUDIENCE_PROFILES else DEFAULT_AUDIENCE


def detect_field(text: str) -> str:
    """Đoán lĩnh vực theo số từ khóa khớp; không đủ tín hiệu → computing."""
    lower = text.lower()
    scores = {
        name: sum(1 for kw in p["keywords"] if re.search(rf"(?<!\w){re.escape(kw)}", lower))
        for name, p in FIELD_PROFILES.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else DEFAULT_FIELD


def field_profile(state: dict) -> dict[str, Any]:
    return FIELD_PROFILES[normalize_field(state.get("field")) or DEFAULT_FIELD]


def audience_profile(state: dict) -> dict[str, str]:
    return AUDIENCE_PROFILES[normalize_audience(state.get("audience"))]


def missing_end_sections(state: dict, text: str) -> list[str]:
    """Tiêu đề cuối bài mà đối tượng đọc yêu cầu nhưng LLM chưa viết (model yếu hay bỏ qua)."""
    return [
        h for h in audience_profile(state)["end_headings"]
        if not re.search(rf"^#{{2,3}}\s*{re.escape(h)}\b", text, re.MULTILINE | re.IGNORECASE)
    ]


def adaptation_rules(state: dict) -> str:
    """Khối quy tắc chèn vào system prompt của mọi chặng viết bài."""
    field, audience = field_profile(state), audience_profile(state)
    return (
        "FIELD & AUDIENCE ADAPTATION:\n"
        f"   - Field: {field['label']}. Use the conventions, terminology and standard metrics of this field "
        f"({field['metrics']}) whenever the evidence reports them; do not force computer-science benchmark framing on other fields.\n"
        f"   - Preferred visual evidence: {field['figures']} — only from real data or AVAILABLE FIGURES.\n"
        f"   - Target readers: {audience['label']}. {audience['style']}\n"
    )
