import json
from app.agent.format_sanitizer import sanitize_academic_markdown

# Đọc trực tiếp từ file JSON bằng json.load (không dùng json.loads trên chuỗi)
with open("result.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Tự động chuẩn hóa toàn diện cú pháp Mermaid, LaTeX math, code blocks trước khi xuất
report_content = sanitize_academic_markdown(data["report"])

# Xuất ra file markdown
output_path = "literature_review.md"
with open(output_path, "w", encoding="utf-8") as file:
    file.write(report_content)

print(f"Đã xuất báo cáo thành công ra file: {output_path}")