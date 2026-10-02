import json

# Đọc trực tiếp từ file JSON bằng json.load (không dùng json.loads trên chuỗi)
with open("result.json", "r", encoding="utf-8") as f:
    data = json.load(f)

report_content = data["report"]

# Xuất ra file markdown
output_path = "literature_review.md"
with open(output_path, "w", encoding="utf-8") as file:
    file.write(report_content)

print(f"Đã xuất báo cáo thành công ra file: {output_path}")