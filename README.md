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

Bằng chứng (cùng một bộ chấm cho cả hai bản, chạy bằng benchmark.py):

M2	M3
40 ca cũ (kiểm tra regression)	39/40	40/40, không ca nào bị hỏng thêm
20 ca mới	9/20	20/20
Truy cập ngoài quyền	0	0
Từ chối sai	5%	0%
Trả lời sai (nên từ chối mà lại trả lời)	7%	0%
Nhóm mốc thời gian trong câu hỏi	38%	100%
Nhóm kiểm chứng nguồn	0%	100%
Test tự động	[27]	[47]
Kết quả đầy đủ: benchmark_results/mission2.md, benchmark_results/mission3_final.md. Độ ổn định khi Gemini lỗi được kiểm bằng tests/test_resilience.py (mô phỏng timeout và mất kết nối).

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