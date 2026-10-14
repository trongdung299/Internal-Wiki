# Tri thức nội bộ Appota — MVP (Mission 2)

Mỗi nhân sự hỏi một câu và nhận câu trả lời đúng với **đơn vị, quyền truy cập và phiên bản đang hiệu lực** của mình, kèm căn cứ. Không chắc thì nói rõ, không đoán.

> Toàn bộ dữ liệu (`data/`) là giả lập: 1 Tập đoàn, 3 công ty, vài phòng/nhóm, 16 tài liệu, 10 người dùng. Không có dữ liệu thật của Appota.

## Phần được chứng minh trong MVP

**Lọc theo hồ sơ người hỏi trước khi AI thấy dữ liệu**, rồi phân giải phiên bản/cấp bậc/mâu thuẫn bằng quy tắc. Cùng câu *"Quy định nghỉ phép của tôi như thế nào?"*:

| Người hỏi | Kết quả |
|---|---|
| Linh (Cty A / Marketing / Digital) | 14 ngày (D03 v3), sàn Tập đoàn 12 ngày |
| Minh (Cty B / Kỹ thuật) | 12 ngày (D05) |
| Tuấn (Cty C) | Cty ghi 10 nhưng sàn Tập đoàn là 12 → áp dụng 12 + cảnh báo |

## Luồng xử lý

```
Hồ sơ người dùng → Lọc cứng bằng code (quyền + đơn vị + hiệu lực)
 → Hybrid: BM25 + bge-m3 (Qdrant) → RRF → Giải xung đột bằng quy tắc
 → LLM diễn đạt có trích dẫn (Gemini) → Code đối chiếu số/ngày/trích dẫn với nguồn
 → Trả lời + căn cứ | hoặc nói rõ chưa chắc, chuyển HR/owner
```

| File | Vai trò |
|---|---|
| `config.py` | Cấu hình từ `.env` |
| `core.py` | Policy engine, chunk, truy xuất hybrid, resolve |
| `llm.py` | Gemini, phân tích câu hỏi, sinh câu trả lời, kiểm tra bám nguồn |
| `pipeline.py` | Luồng 6 bước + CLI |
| `app.py` | Giao diện Streamlit |
| `tests/test_kb.py` | Test tự động (policy, resolve, verify, truy xuất, pipeline) |
| `eval_report.py` | Chạy bộ tình huống và ghi `EVAL_RESULTS.md` |

## Chạy local

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # điền GEMINI_API_KEY (bỏ trống = chế độ local, không cần API)
python pipeline.py --user linh "Quy định nghỉ phép của tôi như thế nào?" --debug
streamlit run app.py
python -m pytest tests/
python eval_report.py
```

Lần đầu chạy sẽ tải bge-m3 (~2GB). Chạy offline nhanh (không tải model): `EMBEDDER=hash LLM_PROVIDER=local` (chỉ để test logic, không phản ánh chất lượng truy xuất thật).

Người dùng giả để thử: `python pipeline.py` (không tham số) in danh sách.

## Bộ kiểm thử

Xem `EVAL_RESULTS.md` (định dạng *Kỳ vọng → Kết quả thực tế → Đạt/Chưa đạt → Điều học được*, gồm ca tốt, ca khó và ca chưa tốt) và `tests/test_kb.py`. Tiêu chí cứng: **0 ca lộ tài liệu ngoài quyền**, được kiểm tra bằng test thuộc tính trên mọi cặp (người dùng, tài liệu) và mọi lần truy xuất.

## 3 câu hỏi bắt buộc

**1. Phần quan trọng nhất là gì? Vì sao tin hướng này khả thi?**
Lọc theo quyền/đơn vị/hiệu lực bằng code trước khi truy xuất và trước khi LLM nhìn thấy dữ liệu, cộng quy tắc phân giải phiên bản/cấp bậc. Nếu phần này đúng thì dù LLM diễn đạt kém, nội dung ngoài quyền cũng không thể xuất hiện, vì nó không bao giờ tới LLM. Bằng chứng: test thuộc tính không có ca rò rỉ, và cùng một câu hỏi cho ba người ra ba kết quả đúng như bảng trên.

**2. So với Mission 1, đã đổi gì?**
- *BM25 chạy trong code, Qdrant chỉ lưu dense bge-m3* (kế hoạch ghi Qdrant hỗ trợ cả sparse). Lý do: BM25 tính trên tập đã lọc quyền nên thống kê IDF không rò rỉ từ tài liệu ngoài quyền.
- *Truy xuất không còn quyết định tài liệu nào được dùng.* Ban đầu hình dung lấy top-k rồi giải xung đột, nhưng top-k có thể bỏ sót tài liệu "floor" của cấp trên (ví dụ sàn 12 ngày của Tập đoàn). Nay chủ đề được xác định trước, `resolve` chạy trên toàn bộ tài liệu đã lọc của chủ đề đó; truy xuất dùng để xác định chủ đề khi câu hỏi không rõ và kiểm tra có căn cứ.
- *Thêm kiểm tra chủ đề ngoài quyền*: hỏi tài liệu ngoài quyền và hỏi tài liệu không tồn tại nhận cùng một câu từ chối, để không lộ sự tồn tại của tài liệu.
- *Thêm chế độ local và fallback*: Gemini lỗi thì dùng câu trả lời mẫu, vẫn đi qua bước kiểm tra bám nguồn.

**3. Trường hợp dễ sai nhất?**
Xác định chủ đề và đơn vị từ câu hỏi (phần duy nhất còn phụ thuộc ngôn ngữ):
- Câu diễn đạt đời thường không có từ khóa (*"một năm tôi được off bao nhiêu hôm?"*) → ở chế độ local bị từ chối sai (xem ca 11 trong `EVAL_RESULTS.md`).
- Người hỏi nói *"Phòng Kỹ thuật"* mà tên trong dữ liệu là *"Phòng Kỹ thuật (A)"* → không phát hiện được là hỏi đơn vị khác, nên nhận mức Tập đoàn mà không có cảnh báo (ca 12).
- Prompt injection nằm trong tài liệu hợp lệ (D13): lọc quyền không chặn được vì tài liệu đó hợp lệ.

Cách phát hiện: bộ ca khó/ca thất bại trong `eval_report.py`, chạy lại sau mỗi thay đổi. Cách kiểm soát: lỗi về quyền/đơn vị luôn thiên về từ chối (an toàn) thay vì trả sai; chỉ dẫn trong tài liệu bị coi là dữ liệu; `verify` chặn mọi số/ngày không có trong nguồn (ví dụ "30 ngày" từ D13).

## Hạn chế đã biết

- Dữ liệu nhỏ (16 tài liệu), chưa đo tỷ lệ trên bộ 30–40 câu như Mission 1.
- Chưa có SSO thật, upload tự động, reranker, LLM-judge, dashboard (đã chủ động bỏ ở MVP).
- Từ đồng nghĩa trong `core.SYNONYMS` viết tay; ca ngoài danh sách phụ thuộc Gemini.
- `verify` kiểm tra số và ngày, chưa kiểm tra được câu diễn đạt sai ý mà không có số.

**Nhật ký bằng chứng:** [Xem nhật ký](<https://docs.google.com/spreadsheets/d/1pYB31-HNO5JkDnro4fy1EAqe1dTLWghNd9p3ozmr8oY/edit?usp=drive_link>)