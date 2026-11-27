<!--
SPDX-FileCopyrightText: 2026 OpenTrix Procurement contributors
SPDX-License-Identifier: Apache-2.0
-->

# Báo cáo M5

## Kết luận

- **M5 — PASS.** Ứng dụng mua sắm thứ ba vận hành qua Platform API v1 trên PostgreSQL, Keycloak và ingress HTTPS.
- **Tích hợp theo tài liệu — PASS sau khi bổ sung cấu hình ở phía ứng dụng.** Nguồn là ADR-C001, OpenAPI, schema,
  manifest mẫu, cấu hình triển khai đã công bố và hướng dẫn Keycloak. Lần cấu hình đầu tiên không đạt phân loại actor
  trong audit. Không cần đọc Java để chẩn đoán hay sửa vấn đề này.
- **Ứng dụng độc lập — PASS.** Manifest mới, CLI Python thư viện chuẩn và bộ kiểm thử thuộc repo M5. Hai stack M5 dùng
  image backend từ Platform ghim SHA, cùng manifest HR 1.1.0 và IT 1.0.0 có sẵn ở SHA đó làm fixture quyền liên ứng dụng.
  ESM, hai BFF và giao diện React không được khởi động trong các stack M5.

## Mốc Git và diff

| Repo | Commit đối chiếu | Tệp đổi | Dòng thêm | Dòng xóa |
| --- | --- | ---: | ---: | ---: |
| Platform | `f401b6e79930a1386e71e92a91ae6a909cfa1e59` | 0 | 0 | 0 |
| ESM | `a4db6fe2127a936c85ee20aa2d3cf557fa107c3f` | 0 | 0 | 0 |

`git diff --exit-code --no-ext-diff <SHA> --` trả mã 0 và diff rỗng trong từng repo.
`git status --short --untracked-files=all` cũng rỗng. HEAD của hai repo trùng đúng hai mốc trên.
M5 chỉ đọc bản checkout Platform rồi tạo Git archive trong repo mua sắm. M5 không thao tác trên container hay volume ESM
và Platform có sẵn. Kiểm tra 51 bí mật sinh cục bộ từ ba fixture, không tìm thấy giá trị nào trong mã Git theo dõi. Commit triển khai được kiểm tra từ clone sạch là
`e8595f5a18f5968a21cd48b52df574a5bf9c8622`. Bản sửa restart `267b4c9c0d8063a4740f9cab10786d15fd1313b4`
được kiểm lại trên cả hai stack và chỉ đổi tham số của lệnh restart.

## Nghiệm thu live

Môi trường Windows, Python 3.14.2, Git 2.45.1.windows.1, Docker Engine 29.7.2, Compose 5.4.0, PostgreSQL 17.11,
Keycloak 26.8.0 và Caddy 2.10.2. Stack chính `opentrix-procurement-m5-verified` dùng cổng 18444. Clone sạch
`opentrix-procurement-m5-fresh` dùng cổng 18445, sinh realm, CA và volume riêng. Cả hai chỉ publish HTTPS trên loopback.

| Ca kiểm thử | Stack chính | Clone sạch | Bằng chứng |
| --- | --- | --- | --- |
| Manifest, discovery, đúng phạm vi role | PASS | PASS | `platform-migrate` exit 0, discovery trả ID, phiên bản và role đúng cho 6 danh tính |
| CRUD, list, search, validation | PASS | PASS | Tìm kiếm theo tên, số lượng 0 bị từ chối; xóa draft rồi GET trả 404 |
| Hai nhánh workflow và history | PASS | PASS | Requester submit, approver khác subject quyết định; thấy đủ 3 trạng thái trong history |
| Tự duyệt và tự từ chối | PASS | PASS | Tài khoản có cả hai role bị 403; dữ liệu, history, audit giữ nguyên |
| Thao tác sai role và bản ghi ngoài quyền sở hữu | PASS | PASS | 403 khi thiếu grant; 404 và kết quả tìm kiếm rỗng khi bản ghi bị ẩn |
| Truy cập chéo ứng dụng hai chiều | PASS | PASS | 404 khi discovery, list, read và create giữa mua sắm ↔ HR và mua sắm ↔ IT |
| Phiên bản cũ | PASS | PASS | Update, delete, transition đều trả 409 `VERSION_CONFLICT`; CLI thoát mã 3 |
| Create trùng UUID | PASS | PASS | Gửi lại payload gốc trả bản ghi hiện tại, chỉ có một CREATE trong audit; đổi payload trả 409; UUID đã xóa hoặc của actor khác trả 404 |
| Mất phản hồi và đối soát | PASS | PASS | Test bỏ phản hồi sau HTTP write thành công, xác minh CLI không tự ghi lại, GET/history tìm thấy bản ghi |
| Audit có quyền và che dữ liệu | PASS | PASS | Auditor thấy `[REDACTED]` trong mọi snapshot kiểm tra; actor được ghi `MACHINE` |
| TLS và xác thực | PASS | PASS | CA riêng được xác minh, TLS từ chối CA chưa được tin cậy, thiếu bearer trả 401 |
| Lệnh CLI thực | PASS | PASS | Chạy CLI qua tiến trình Python riêng với OAuth2 và HTTPS |
| Lưu dữ liệu sau restart | PASS | PASS | So sánh bản ghi đã duyệt, workflow history và audit trước/sau, trên cùng PostgreSQL volume |
| Tái lập từ clone sạch | — | PASS | Clone `--no-local`, xác nhận chưa có `.local`, chạy lại toàn bộ suite và restart |

Lần đầu có **11 PASS, 1 FAIL, 0 SKIP** trong 331,998 giây. Ca audit thấy `actorType=USER`
vì token thiếu `client_id`. Phản hồi audit vẫn che dữ liệu như mong đợi. Fixture ban đầu được dừng và giữ dữ liệu.

Sau khi chỉnh cấu hình, mỗi stack có **12 PASS, 0 FAIL, 0 SKIP**, cộng một kiểm tra persistence đạt sau
mỗi lần restart. Lần xác minh cuối trên mỗi stack xác nhận PostgreSQL đổi thời điểm khởi động, giữ cùng container
và volume, và migrator giữ nguyên thời điểm khởi động. Thời gian suite chính là 332,644 giây; suite clone sạch là 377,711 giây.

```powershell
python deploy/stack.py up --platform D:\olp\opentrix-v1-candidate
python -B -m tests.live -v
python deploy/stack.py restart
python -B -m tests.live verify-restart
```

Hướng dẫn đầy đủ về CA, biến môi trường, cấp danh tính và clone sạch nằm trong [Quick Start](README.md).

## Đo mức tái sử dụng

| Hạng mục | Kết quả |
| --- | --- |
| Manifest mới | 49 dòng trong `manifests/opentrix-procurement/app.json`. Hai manifest fixture sao từ Platform vào thư mục Git bỏ qua, tính 0 dòng mã mới |
| CLI mới | 240 dòng trong `procurement.py`; 0 phụ thuộc Python bên ngoài |
| Mã triển khai | 145 dòng trong `deploy/stack.py` |
| Cấu hình theo dõi bởi Git | 25 dòng Compose, 40 dòng Caddyfile có dùng lại các biểu thức allowlist Platform, 4 dòng `.gitignore` |
| Cấu hình sinh khi chạy | Tệp Compose env, realm JSON, danh sách bí mật thử nghiệm và CA; riêng theo project, Git bỏ qua |
| Mã kiểm thử | 349 dòng trong `tests/live.py` |
| Bước triển khai thủ công | 1 lệnh `up` khi đã có hai checkout. Từ clone sạch có thêm 1 thao tác `git clone`. Để chạy song song, đặt thêm 2 biến `M5_PROJECT` và `M5_PORT` |
| Thời gian quan sát | 30 phút 54 giây, từ kiểm tra môi trường đầu tiên đến khi có bằng chứng cuối. Gồm thời gian khảo sát, chạy thử và chờ công cụ |

Số dòng lấy từ Git và tính cả dòng trống. Thời gian quan sát chỉ mô tả M5.

## Ma sát và cách xử lý

1. README và `docs/INTEGRATION.md`, `docs/API.md`, `docs/DEPLOYMENT.md` tập trung vào Helpdesk/Portal cũ.
   Phải tìm ADR-C001 để có hợp đồng Platform mới, cơ chế đăng ký và yêu cầu quyền của token. OpenAPI khai báo bearer JWT,
   nhưng không dạy cách tạo service account và không liệt kê giá trị `actorType`.
2. Demo mặc định kéo Portal BFF và chiếm các cổng cố định. Cổng 8443/8180 đã được stack ESM hiện có sử dụng. Đọc cấu hình
   Compose để tìm mount `/apps`, user chạy migration và allowlist ingress. Overlay M5 chọn project/volume, cổng host và
   thư mục manifest riêng. Ingress chỉ proxy endpoint cấp token và các tuyến nghiệp vụ công bố trong OpenAPI v1.
3. Realm mẫu có client credentials, audience và role scope; danh sách scope sao theo mẫu thiếu `service_account`.
   Token hợp lệ nhưng audit ghi `USER`. Thêm scope để Keycloak phát `client_id` trùng `azp`, rồi chạy trên realm mới
   vì `start-dev --import-realm` giữ realm đã tồn tại. Bài kiểm thử kiểm trực tiếp hai claim và loại actor.
   [Keycloak Upgrading Guide](https://www.keycloak.org/docs/26.7.4/upgrading/)
4. API và điểm cấp token dùng HTTPS ở host, issuer của backend vẫn là HTTP loopback trong stack. URL dùng IP trực tiếp
   đã gây lỗi TLS `TLSV1_ALERT_INTERNAL_ERROR` ở bước readiness trước khi chạy test; hostname `localhost` với CA đúng hoạt động và giữ kiểm tra SNI.
   [Caddy Global Options](https://caddyserver.com/docs/caddyfile/options#strict_sni_host)
5. Runtime đăng ký cảnh báo `Unknown keyword sensitive` từ validator JSON Schema dù manifest hợp lệ và audit redaction
   chạy đúng. Kiểm chứng redaction qua API thay vì suy luận từ cảnh báo.
6. Sandbox đọc repo dưới tài khoản khác và không có quyền Docker. Dùng `git -c safe.directory=…` theo từng lệnh và
   quyền Docker theo từng thao tác. Caddy 2.10.2 chưa có image riêng nên tải image đúng phiên bản. Khi một lệnh ghi nhiều
   tệp vượt giới hạn PowerShell trên Windows, chia nhỏ lệnh. Git báo chuyển LF/CRLF và clone sạch vẫn chạy được.
7. Compose `restart` mặc định chạy lại `platform-migrate` khi restart dịch vụ phụ thuộc. Thêm `--no-deps` để lần kiểm
   persistence chỉ restart bốn dịch vụ runtime, rồi kiểm lại thời điểm khởi động migrator cùng PostgreSQL volume.

## Giới hạn và đề xuất M6

- Cold build và máy khác chưa được kiểm tra; clone sạch dùng cache build Docker trên máy hiện tại. Kiểm thử mất phản hồi
  bỏ ACK phía client sau giao dịch thật. Chưa chèn lỗi ở bước commit DB. CLI hiển thị trạng thái đối soát theo quyền,
  không khẳng định kết quả của PUT/DELETE/transition chỉ từ một GET.
- Dùng đơn vị tiền tệ nhỏ nhất với số nguyên. Không khai báo tiền tệ, tổng tiền hay tuyến phê duyệt. Quyền sở hữu
  service account không phân biệt cá nhân. Việc tạo lại container Keycloak có thể đổi subject. Ca cô lập IT dùng manifest
  Platform 1.0.0, không dùng workflow ticket IT của ESM 1.1.0.
- **M6.** Thêm hướng dẫn Platform API v1 ngay từ README. Cung cấp recipe Compose Platform-only với cổng, CA, thư mục
  manifest, thứ tự register/restart và lưu volume. Thêm recipe Keycloak `client_credentials` với audience, role scope,
  `service_account`, ví dụ `actorType` và cách kiểm claim. Nêu rõ ngữ nghĩa 403/404/409, `STORE_UNAVAILABLE` so với
  `COMMIT_OUTCOME_UNKNOWN`, điều kiện gửi lại UUID gốc và ý nghĩa cảnh báo `sensitive`.
