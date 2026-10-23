Mission 3: Cải tiến
M2 → Vấn đề mới → Quyết định → M3 → Bằng chứng → Giới hạn
M2 (trước cải tiến). Bản gắn tag mission2 (commit 076da21). Trên bộ 40 câu có đáp án chuẩn, đạt 39/40, không có ca nào lọt quyền.

Vấn đề mới. Tài liệu thay đổi theo thời gian, nhưng M2 chỉ biết hiệu lực theo ngày hôm nay. Trên 20 câu bổ sung nhắm vào yêu cầu mới, M2 chỉ đạt 9/20. Điểm nghiêm trọng nhất là trả lời sai một cách tự tin: hỏi 'Năm 2023 tôi được nghỉ phép bao nhiêu ngày?' vẫn trả 14 ngày dù không có quy định nào hiệu lực lúc đó. M2 cũng không cho người dùng đối chiếu đoạn nguyên văn của tài liệu, và sập khi Gemini timeout (chương trình dừng ở ca 17 của lần chạy benchmark đầu tiên).

Quyết định thay đổi.

Đọc mốc thời gian trong câu hỏi ('năm 2025', 'tháng 3/2026', '15/01/2026', 'năm ngoái', 'tháng 1 năm nay') làm ngày tra cứu. Chỉ ảnh hưởng hiệu lực, không bao giờ nới quyền.
Không có quy định hiệu lực tại mốc được hỏi: nói rõ mốc và bản sớm nhất, thay vì đoán.
Cho người dùng kiểm chứng: đoạn trích nguyên văn (tô vàng câu chứa số liệu), lịch sử phiên bản, người phụ trách.
Giải thích khi quy định cấp dưới thay thế, làm mức tối thiểu hoặc bổ sung cho cấp trên.
Câu hỏi nhiều chủ đề: hỏi lại thay vì trả lời một chủ đề rồi bỏ qua chủ đề còn lại.
Chịu lỗi Gemini (timeout, mất kết nối): chuyển sang câu trả lời dựng từ tài liệu gốc, có banner báo cho người dùng.
Nhật ký truy cập và test red-team: mỗi người dùng thử xin mọi tài liệu ngoài quyền.
Chủ động không thay đổi. Lõi lọc quyền, phân giải xung đột và kiểm tra bám nguồn của M2 (đã đạt mục tiêu, không có lý do đụng vào). Không làm reranker, SSO thật, Qdrant server, LLM-judge, vì không tạo được bằng chứng đo được trong thời gian này.

M3 (sau cải tiến). Module trust.py bọc ngoài pipeline.run (không sửa lõi), app.py mới hiển thị căn cứ và giải thích, một hàm trong llm.py được sửa để bắt timeout.
### Change Request B4: Thiếu tri thức
Yêu cầu: khi kho không đủ thông tin để trả lời chắc chắn, hệ thống không được đoán.
Kiểm tra: 8 ca (B53 đến B60): chủ đề có tài liệu nhưng không nêu điều được hỏi (quy đổi phép năm ra tiền,
công tác phí nước ngoài, làm thêm giờ ban đêm, bảo hiểm cho người thân, dồn ngày nghỉ sinh nhật, nghỉ nửa
ngày), trả lời một phần (có 14 ngày phép nhưng không nói chuyện bán ngày phép), và thiếu theo thời điểm
(năm 2025 chưa có quy định bảo lưu). Tôi đọc tay nguyên văn câu trả lời của cả 8 ca.
Kết quả: Mission 2 [x]/8, Mission 3 8/8.
Quyết định: không thay đổi code cho riêng CR này vì hệ thống đã đáp ứng: prompt yêu cầu chỉ dùng thông tin
trong tài liệu và từ chối khi không đủ, bước kiểm tra bám nguồn chặn số liệu lạ. Tôi chọn thêm bộ kiểm thử để
bảo vệ hành vi này khỏi hồi quy thay vì thêm tính năng chưa có bằng chứng cần thiết.
Giới hạn: ở chế độ dự phòng (khi Gemini lỗi), hệ thống không phân biệt được tài liệu có nói điều được hỏi hay
không và có thể trả nội dung tài liệu liên quan (tôi đã kiểm tra, cả 8 ca chưa đạt ở chế độ này); khẳng định
bịa không kèm số liệu chỉ được phát hiện bằng danh sách cụm từ và đọc tay.
Bằng chứng (cùng một bộ chấm cho cả hai bản, chạy bằng benchmark.py):

### 1. Kết quả tổng quan

| Chỉ số | Mission 2 | Mission 3 | Mục tiêu |
|---|---:|---:|---|
| Tổng thể (tỷ lệ ca đạt) | 81% | 99% | Càng cao càng tốt |
| Truy cập ngoài quyền (số ca lọt) | 0 | 0 | = 0 |
| Đúng phạm vi (đơn vị + phiên bản) | 95% | 100% | >= 90% |
| Bám nguồn (số/ngày khớp tài liệu được trích dẫn) | 100% | 100% | >= 90% |
| Từ chối sai | 5% | 0% | Càng thấp càng tốt |
| Trả lời sai (nên từ chối nhưng lại trả lời) | 14% | 0% | Càng thấp càng tốt |
| Lỗi hệ thống sau khi thử lại | 0 | 0 | = 0 |
| Ca phải thử lại do lỗi mạng/timeout | 6 | 1 | Càng thấp càng tốt |

### 2. Kết quả theo nhóm tình huống

| Nhóm kiểm thử | Mission 2 | Mission 3 |
|---|---:|---:|
| Phiên bản / hiệu lực | 75% | 100% |
| Xung đột / cấp bậc | 100% | 100% |
| Ngoài quyền truy cập | 100% | 100% |
| Câu hỏi mơ hồ | 100% | 100% |
| Không có đáp án | 100% | 100% |
| Prompt injection | 100% | 100% |
| Mốc thời gian trong câu hỏi | 38% | 100% |
| Kiểm chứng nguồn / giải thích cấp bậc | 0% | 100% |
| Câu hỏi do người dùng tự viết | 75% | 100% |
| Thiếu tri thức (Change Request B4) | 88% | 88% |

### 3. Regression testing và kiểm thử mới

| Nhóm kiểm thử | Mission 2 | Mission 3 |
|---|---:|---:|
| 40 ca cũ (kiểm tra regression) | 39/40 | 40/40 theo kết quả ghi nhận trước đó |
| 20 ca mới | 9/20 | 20/20 theo kết quả ghi nhận trước đó |

Tái hiện Before/After.

```powershell
git worktree add ../wiki-m2 mission2
python benchmark.py --label mission3_final --runner trust --sleep 10 --retries 3
python benchmark.py --compare benchmark_results/mission2.json benchmark_results/mission3_final.json
python -m pytest tests/ -v
```


Giới hạn còn lại.

100% đo trên bộ câu tự xây dựng. Đây là bằng chứng về không bị hỏng thêm, chưa phải bằng chứng hệ thống tổng quát hóa tốt cho câu hỏi người dùng thật.
Mốc thời gian đọc bằng quy tắc. Với cách nói lạ, hệ thống dùng ngày hôm nay.
Dữ liệu giả lập 16 tài liệu, hồ sơ người dùng giả lập, chưa có SSO thật.
**Nhật ký bằng chứng:** [Xem nhật ký](<https://docs.google.com/spreadsheets/d/1pYB31-HNO5JkDnro4fy1EAqe1dTLWghNd9p3ozmr8oY/edit?usp=drive_link>)