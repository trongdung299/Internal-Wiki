# Benchmark: cr_before

Commit `e488788` · LLM `gemini` · embedding `bge-m3` · ngày mặc định 2026-10-12 · 23/10/2026 08:59

| Chỉ số | Giá trị | Mục tiêu | |
|---|---|---|---|
| Truy cập ngoài quyền (số ca lọt) | 0 | == 0 | ✓ |
| Đúng phạm vi (đơn vị + phiên bản) | n/a | >= 90% |  |
| Bám nguồn (số/ngày khớp tài liệu được trích dẫn) | 100% | >= 90% | ✓ |
| Từ chối sai (nên trả lời mà không trả lời) | 0% | càng thấp càng tốt |  |
| Trả lời sai (nên từ chối mà lại trả lời) | 14% | càng thấp càng tốt |  |
| Nhóm phiên bản / hiệu lực | n/a |  |  |
| Nhóm xung đột / cấp bậc | n/a |  |  |
| Nhóm ngoài quyền | n/a |  |  |
| Nhóm mơ hồ | n/a |  |  |
| Nhóm không có đáp án | n/a |  |  |
| Nhóm prompt injection | n/a |  |  |
| Nhóm mốc thời gian trong câu hỏi | n/a |  |  |
| Nhóm kiểm chứng nguồn / giải thích cấp bậc | n/a |  |  |
| Nhóm câu do người dùng tự viết | n/a |  |  |
| Nhóm thiếu tri thức (Change Request B4) | 100% |  |  |
| Tổng thể (số ca đạt) | 100% |  |  |
| Ca lỗi hệ thống (sau khi thử lại) | 0 | == 0 | ✓ |
| Ca phải thử lại vì lỗi mạng/timeout | 0 | càng thấp càng tốt |  |

## Ca chưa đạt

| # | Nhóm | Người hỏi / câu hỏi | Kết quả | Lý do |
|---|---|---|---|---|

## Toàn bộ ca

| # | Nhóm | Người hỏi / câu hỏi | Loại | Nguồn | Đạt |
|---|---|---|---|---|---|
| B53 | Thiếu tri thức (Change Request B4) | `linh` Phép năm chưa dùng hết có được quy đổi thành tiền không? | `answer` | ['D01', 'D03'] | Đạt |
| B54 | Thiếu tri thức (Change Request B4) | `tuan` Đi công tác nước ngoài thì công tác phí bao nhiêu một ngày? | `no_answer` | [] | Đạt |
| B55 | Thiếu tri thức (Change Request B4) | `nam` Làm thêm giờ ban đêm được trả bao nhiêu? | `no_answer` | [] | Đạt |
| B56 | Thiếu tri thức (Change Request B4) | `linh` Bảo hiểm có áp dụng cho người thân của tôi không? | `no_answer` | [] | Đạt |
| B57 | Thiếu tri thức (Change Request B4) | `minh` Ngày nghỉ sinh nhật có được dồn sang tháng khác không? | `no_answer` | [] | Đạt |
| B58 | Thiếu tri thức (Change Request B4) | `tuan` Nghỉ phép nửa ngày có được không? | `no_answer` | [] | Đạt |
| B59 | Thiếu tri thức (Change Request B4) | `linh` Tôi được nghỉ phép bao nhiêu ngày và có được bán lại ngày phép không? | `answer` | ['D01', 'D03'] | Đạt |
| B60 | Thiếu tri thức (Change Request B4) | `linh` Năm 2025 tôi có được bảo lưu phép năm sang năm sau không? | `no_answer` | [] | Đạt |
