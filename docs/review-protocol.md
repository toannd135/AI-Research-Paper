# Khai báo giao thức tổng quan thật (`review_protocol.json`)

Hệ thống KHÔNG tự tạo cơ sở dữ liệu, chuỗi tìm kiếm, số sàng lọc, số người đánh giá hay sơ đồ PRISMA.
Khi bạn đã thực hiện tìm kiếm và sàng lọc thật, ghi lại vào `<UPLOAD_DIR>/review_protocol.json` (cạnh `catalog.json`).
Kho PDF phải chứa đúng `counts.included` nghiên cứu đã chọn.

Khi tệp hợp lệ thì hệ thống sẽ:
- đưa nguyên văn vào mục 2 (Review Methodology),
- chèn sơ đồ luồng dựng đúng từ các số đã khai báo,
- cho phép ghi "systematic review/PRISMA" (`systematic`), hoặc chỉ PRISMA-ScR (`scoping`).

Khi tệp sai, cảnh báo `review_protocol.json không hợp lệ` hiện trong `validation_report` và bài giữ mô tả trung thực
"narrative review trên kho tuyển chọn, retrieval coverage".

```json
{
  "review_type": "systematic",                 // narrative | scoping | systematic
  "guideline": "PRISMA 2020",                  // systematic: PRISMA 2020|none · scoping: PRISMA-ScR|none · narrative: none
  "databases": [
    {"name": "PubMed", "search_string": "(glioma OR glioblastoma) AND (MRI) AND (\"missing modality\" OR \"incomplete modalities\")",
     "date": "2026-11-01", "hits": 214}
  ],
  "date_range": "2015-01 to 2026-10",
  "inclusion_criteria": ["Evaluated on a BraTS edition", "Reports Dice or HD95", "Peer-reviewed or arXiv with code"],
  "exclusion_criteria": ["No quantitative segmentation results", "Non-English"],
  "counts": {
    "identified": 214, "other_sources": 0, "duplicates_removed": 40, "screened": 174,
    "excluded_screening": 120, "full_text_assessed": 54,
    "excluded_full_text": {"No BraTS evaluation": 9, "No missing-modality or fusion analysis": 10},
    "included": 35
  },
  "reviewers": {"screening": 2, "extraction": 1, "disagreement_resolution": "discussion with a third author"},
  "quality_assessment": "CLAIM checklist items 7-9 and 20-24, applied by one author",
  "extraction_verification": "all automatically extracted values in Tables 3-5 checked against the source PDF by one author"
}
```
(Xóa các chú thích `//` trước khi lưu; JSON không cho phép chú thích.)

Các kiểm tra số học:
- tổng `hits` + `other_sources` = `identified`
- `identified − duplicates_removed = screened`
- `screened − excluded_screening = full_text_assessed`
- `full_text_assessed − Σexcluded_full_text = included`
- `included` = số paper trong `catalog.json`

Có từ 2 người sàng lọc trở lên thì bắt buộc khai báo `disagreement_resolution`. Chỉ có 1 người thì ghi 1, đừng ghi 2.
