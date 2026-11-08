# Paper nên thêm vào kho `data/papers_brain`

Lý do: kho hiện có 31 bài (2015–2023, mới nhất là 2023), thiếu các hướng mà reviewer Q1/Q2 nêu (BraTS 2022+, Mamba/SSM, SAM/foundation model, diffusion cho khôi phục modality). Code không bù được khoảng trống này; chỉ có bài thật trong kho mới đưa được vào survey.

> Tên bài viết theo trí nhớ, CHƯA kiểm tra trên nguồn. Tìm theo tên, kiểm tra năm/venue/DOI và giấy phép (ưu tiên open access, arXiv) trước khi nạp. Không đưa DOI/arXiv ID vào đây khi chưa mở nguồn.

## 1. BraTS 2022–2025 (làm survey không còn dừng ở 2021)
- BraTS 2023 Africa (glioma ở Sub-Saharan Africa)
- BraTS 2023 Pediatric Tumors (BraTS-PEDs)
- BraTS 2023 Metastases (BraTS-METS)
- BraTS 2023 Brain MR Image Synthesis for Tumor Segmentation (BraSyn): đúng chủ đề thiếu modality
- Bài tổng hợp ASNR-MICCAI BraTS 2023 nếu có bản open access

## 2. Mamba / State Space Models
- Mamba: Linear-Time Sequence Modeling with Selective State Spaces
- U-Mamba: Enhancing Long-range Dependency for Biomedical Image Segmentation
- SegMamba: Long-range Sequential Modeling Mamba for 3D Medical Image Segmentation

## 3. Foundation model / SAM
- Segment Anything
- Segment Anything in Medical Images (MedSAM)
- SAM-Med3D
- Segment Anything Model for Medical Image Analysis: an Experimental Study

## 4. Diffusion / generative cho khôi phục ảnh khuyết
- Denoising Diffusion Probabilistic Models
- Diffusion Models in Medical Imaging: A Comprehensive Survey (tìm bản survey diffusion y tế gần nhất)
- Một bài diffusion cho missing-modality MRI synthesis (tìm theo từ khoá "diffusion missing modality MRI synthesis brain tumor")

## 5. Missing-modality bổ sung (khác nhóm đã có)
- RFNet: Region-aware Fusion Network for Incomplete Multi-modal Brain Tumor Segmentation
- Learnable Cross-modal Knowledge Distillation for Multi-modal Learning with Missing Modality
- Một bài 2024–2025 về prompt/knowledge distillation cho missing modality (tìm theo từ khoá)

## 6. Kiến trúc/benchmark hiện đại (cho bảng hiệu năng tính toán)
- 3D UX-Net
- MedNeXt
- nnU-Net Revisited: A Call for Rigorous Validation in 3D Medical Image Segmentation

## Sau khi thêm
1. Đặt PDF vào `data/papers_brain/`, nạp qua luồng upload/seed hiện có (không tự động trong task này).
2. Chạy lại survey. Chỉ khi extractor thấy `± x` in nguyên văn thì cột Spread mới có số; nguồn không báo thì vẫn là `NR`.
3. Mục tiêu thực tế: 21 -> 40+ bài là khả thi; 80–150 bài như reviewer đòi cần nguồn tìm kiếm có hệ thống thật (PubMed/IEEE/WoS), nằm ngoài những gì kho PDF nội bộ làm được. Khi đó mới được viết PRISMA, và chỉ với số liệu sàng lọc thật.
