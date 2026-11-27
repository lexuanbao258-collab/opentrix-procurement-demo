<!--
SPDX-FileCopyrightText: 2026 OpenTrix Procurement contributors
SPDX-License-Identifier: Apache-2.0
-->

# OpenTrix Procurement CLI

Ứng dụng thử nghiệm M5 cho yêu cầu mua sắm nội bộ. Manifest `opentrix-procurement@1.0.0` khai báo thực thể
`purchaseRequest` và luồng `DRAFT → PENDING → APPROVED / REJECTED`. CLI dùng thư viện chuẩn Python và Platform API v1.

## Khởi chạy

Cần Git, `tar`, Python 3.10 trở lên và Docker chạy Linux containers với Compose 2.24.4 trở lên.
Cần bản checkout Git chứa Platform commit `f401b6e79930a1386e71e92a91ae6a909cfa1e59`.
Docker phải tải được base image và dùng được kho phụ thuộc Gradle trong lần build không có cache.

Từ repo này, chạy lệnh sau bằng PowerShell. Trên hệ điều hành khác, đổi đường dẫn Platform tương ứng.

```powershell
python deploy/stack.py up --platform D:\olp\opentrix-v1-candidate
python deploy/stack.py ps
```

Lệnh `up` trích đúng commit vào thư mục dữ liệu của project, khởi động PostgreSQL, Keycloak, Platform và Caddy trong project
`opentrix-procurement-m5-verified`. Compose `platform-migrate` chạy bằng tài khoản chủ schema và mount thư mục manifest chỉ đọc
trước khi backend khởi động. Backend chờ readiness và discovery của realm Keycloak. Trong lần đăng ký đầu tiên,
thư mục gồm manifest mới cùng hai manifest IT và HR nguyên bản
từ Platform để kiểm thử quyền liên ứng dụng. Stack chạy độc lập với repo ESM. Chọn project và cổng riêng bằng
`M5_PROJECT` (tiền tố `opentrix-procurement-`) và `M5_PORT` (mặc định `18444`) khi cần một bản chạy song song.

`up` tự sinh mật khẩu và import realm thử nghiệm vào Keycloak. Các client OAuth2 bí mật chỉ dùng `client_credentials`.
Role trên resource client `tricore-api` xuất hiện trong `resource_access.tricore-api.roles`; token có audience
`tricore-api`. Scope `service_account` thêm claim `client_id` để audit nhận đúng loại danh tính. Client chính là `m5-requester`, `m5-approver`, `m5-auditor`. Client `m5-dual`, `m5-hr` và
`m5-it` phục vụ kiểm thử âm tính. Quyền sở hữu thuộc về service account theo issuer và subject. Mọi người dùng
chung thông tin xác thực sẽ chia sẻ cùng quyền sở hữu và cùng danh tính trong audit.

## Chạy CLI

Caddy tạo CA riêng và lưu bản sao công khai ở `.local/<project>/caddy-root.crt`. Python xác minh CA và hostname
`localhost` cho cả API và điểm cấp token. Chỉ cổng HTTPS được publish ra host. Keycloak và Platform dùng
issuer HTTP trên loopback bên trong namespace của stack.

```powershell
$m5Local = '.local/opentrix-procurement-m5-verified'
$env:PROCUREMENT_API_URL = 'https://localhost:18444'
$env:PROCUREMENT_CA_FILE = (Resolve-Path "$m5Local/caddy-root.crt").Path
function Set-M5Identity([string]$Role) {
    $env:PROCUREMENT_CLIENT_ID = "m5-$Role"
    $env:PROCUREMENT_CLIENT_SECRET = (Get-Content -Raw "$m5Local/accounts.json" | ConvertFrom-Json).$Role
}
Set-M5Identity requester
python procurement.py apps
python procurement.py app
python procurement.py entity
$id = [guid]::NewGuid().ToString()
python procurement.py create --id $id --item 'Synthetic keyboard' --quantity 2 --unit-price-minor 2500 --justification 'M5 fixture'
python procurement.py search keyboard
python procurement.py read $id
python procurement.py submit $id --version 0
Set-M5Identity approver
python procurement.py workflow $id
python procurement.py approve $id --version 1
python procurement.py history $id
Set-M5Identity auditor
python procurement.py audit --id $id
```

`PROCUREMENT_TOKEN_URL` tùy chọn trỏ đến điểm cấp token HTTPS, mặc định lấy từ `PROCUREMENT_API_URL` và realm
`tricore`. Nếu dùng chứng chỉ từ CA hệ thống, có thể bỏ `PROCUREMENT_CA_FILE`. Các tệp `accounts.json`,
`compose.env` và `realm.json` trong `.local/<project>/` chứa bí mật thử nghiệm và được Git bỏ qua.

`list`, `search` và `audit` hỗ trợ `--limit` và `--offset`. Dùng `update ID --version N` với đủ bốn trường
hoặc `delete ID --version N` khi bản ghi còn `DRAFT`. Dùng `reject ID --version N` để từ chối yêu cầu `PENDING`.
Xem cú pháp từng lệnh bằng `python procurement.py COMMAND --help`.

Mã thoát 3 báo xung đột phiên bản. Đọc lại bản ghi và xem thay đổi trước khi gửi thao tác mới. Mã thoát 4 báo
kết quả ghi chưa rõ. Chạy `reconcile ID` để đọc bản ghi và history theo quyền hiện tại. Nếu cần gửi lại create,
giữ nguyên UUID và đủ dữ liệu gốc. CLI luôn in UUID trước khi gửi create, kể cả khi tự sinh UUID.
GET 404 có thể là bản ghi thiếu hoặc bị ẩn. Sau PUT, DELETE hoặc transition, GET/history có thể cung cấp bằng chứng
nhưng không phải lúc nào cũng xác định dứt khoát thao tác nào đã commit. CLI không tự gửi lại thao tác ghi.

## Kiểm thử

```powershell
python -B -m unittest tests.test_procurement -v
python -B -m tests.live -v
python deploy/stack.py restart
python -B -m tests.live verify-restart
```

Để kiểm tra từ clone mới trên cùng máy, clone repo bằng `git clone --no-local <đường-dẫn-repo-này> <thư-mục-mới>`.
Chọn `$env:M5_PROJECT = 'opentrix-procurement-m5-fresh'` và `$env:M5_PORT = '18445'` trong shell của clone.
Lặp lại `up` và các lệnh kiểm thử ở trên. `python deploy/stack.py stop` dừng riêng stack đã chọn và giữ volume.

## Giới hạn

Giá được lưu dưới dạng số nguyên đơn vị tiền tệ nhỏ nhất. Manifest không khai báo mã tiền tệ, tổng tiền, hạn mức
hay tuyến phê duyệt. Tìm kiếm áp dụng cho tên mặt hàng. Lý do mua sắm hiển thị cho vai trò có quyền đọc bản ghi
và được che trong audit. Chỉ dùng dữ liệu tổng hợp. Keycloak chạy ở chế độ demo và giữ danh tính qua restart
container. Nếu tạo lại container Keycloak, subject có thể thay đổi và quyền sở hữu dữ liệu cũ cần được xem lại.
Nếu cổng bị chiếm, chọn `M5_PORT` khác. Nếu TLS lỗi, kiểm tra đúng hostname và CA của project đang chạy.

Xem kết quả, điểm vướng và đề xuất M6 trong [báo cáo M5](M5-REPORT.md).

## Giấy phép

Codex hỗ trợ triển khai, viết tài liệu và kiểm chứng M5 và M6.1-FIX. Xem [Apache-2.0](LICENSE), [NOTICE](NOTICE),
[giấy phép phụ thuộc](THIRD-PARTY-NOTICES.md) và [Platform tại mốc runtime ghim](https://github.com/lexuanbao258-collab/opentrix-v1-candidate/tree/f401b6e79930a1386e71e92a91ae6a909cfa1e59).
