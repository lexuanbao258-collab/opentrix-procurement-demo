<!--
SPDX-FileCopyrightText: 2026 OpenTrix Procurement contributors
SPDX-License-Identifier: Apache-2.0
-->

# OpenTrix Procurement

> **Language / Ngôn ngữ:** English (below) · [Tiếng Việt](#tiếng-việt-bản-gốc)

An **independently implemented** application on the OpenTrix Platform public API: internal purchase requests with a
manifest (`opentrix-procurement@1.0.0`), a Python standard-library CLI, its own deployment overlay and tests. It shares no
code and no database with the Platform or with the ESM application, and ran on the frozen Platform runtime
`f401b6e79930a1386e71e92a91ae6a909cfa1e59` with **0 changed Platform runtime files**.

> **Status: a competition-ready, self-hosted demonstration candidate, not a production-certified system.** Synthetic data
> only. This repository is a **local checkout; no public remote has been approved.**

Workflow: `DRAFT → PENDING → APPROVED / REJECTED`. Roles: `requester`, `approver`, `auditor`. The approver can never be the
request's creator (`notByCreator`); the justification is `sensitive` and appears as `[REDACTED]` in audit.

**Documentation (Platform repository):** [product overview](https://github.com/lexuanbao258-collab/opentrix-v1-candidate/blob/621c32999668203f40363009aabe83ec66287c37/docs/candidate/README.md) ·
[**Developer guide**](https://github.com/lexuanbao258-collab/opentrix-v1-candidate/blob/621c32999668203f40363009aabe83ec66287c37/docs/candidate/DEVELOPER-GUIDE.md) (this application is its worked example) · [API guide](https://github.com/lexuanbao258-collab/opentrix-v1-candidate/blob/621c32999668203f40363009aabe83ec66287c37/docs/candidate/API-GUIDE.md) ·
[Validation summary](https://github.com/lexuanbao258-collab/opentrix-v1-candidate/blob/621c32999668203f40363009aabe83ec66287c37/docs/candidate/VALIDATION.md) · [M5 report](M5-REPORT.md) (Vietnamese).

## Quick start (tested in M6.3)

Requirements: Git, `tar`, Python 3.10+, Docker with Linux containers and Compose 2.24.4+. M6.3
used Windows 11, Git Bash, Python 3.14.2, Engine 29.7.2 and Compose 5.4.0. Linux and macOS
remain unverified. Keep 20 GB free and stop below 10 GB.

Procurement applies its own deployment overlay at the frozen Platform runtime `f401b6e79930a1386e71e92a91ae6a909cfa1e59`.
The standalone example pins Procurement to the accepted M6.3 documentation commit `33a8bbf36f6f2daeb178ef405f8023561146c4d7`,
which includes the M6.1-FIX implementation `f86777755fbcfde249881af0ee3064cca1de35a1`. For M6.4 use the exact candidate SHAs
from the release manifest. Set `PROCUREMENT_GIT_SOURCE` to the Git checkout or bundle supplied by the owner.

```bash
git clone --no-checkout https://github.com/lexuanbao258-collab/opentrix-v1-candidate.git opentrix-platform-runtime
git -C opentrix-platform-runtime checkout --detach f401b6e79930a1386e71e92a91ae6a909cfa1e59
git clone --no-local --no-checkout "$PROCUREMENT_GIT_SOURCE" opentrix-procurement-demo
git -C opentrix-procurement-demo checkout --detach 33a8bbf36f6f2daeb178ef405f8023561146c4d7
cd opentrix-procurement-demo
python deploy/stack.py up --platform ../opentrix-platform-runtime
python deploy/stack.py ps
```

`up` extracts the pinned commit with `git archive`, generates every secret and the Keycloak realm, registers the manifests
with the controlled `platform-migrate` step, waits for Keycloak to be healthy before starting the backend, starts Caddy
HTTPS and exports its CA to `.local/<project>/caddy-root.crt`. Default project `opentrix-procurement-m5-verified`, HTTPS
port `18444` on `127.0.0.1`; set `M5_PROJECT` (prefix `opentrix-procurement-`) and `M5_PORT` to run another stack beside it.
If Docker answers `all predefined address pools have been fully subnetted`, ask the operator to allocate an unused Docker subnet.

### Credentials

`.local/<project>/accounts.json`, `compose.env` and `realm.json` hold randomly generated secrets, are mode 0600 and are
ignored by Git. Never commit, paste or screenshot them. The CLI reads the client secret from the environment, never from
arguments. The machine clients are `m5-requester`, `m5-approver`, `m5-auditor` (main) and `m5-dual`, `m5-hr`, `m5-it`
(negative tests). They use OAuth2 `client_credentials`; the realm gives them the `service_account` scope so audit records
`actorType: MACHINE`. Ownership belongs to the service account: everyone sharing a secret shares one identity.

### Run the CLI (Git Bash)

```bash
P=opentrix-procurement-m5-verified; export PROCUREMENT_API_URL=https://localhost:18444
export PROCUREMENT_CA_FILE="$PWD/.local/$P/caddy-root.crt"
use() { export PROCUREMENT_CLIENT_ID="m5-$1"
  PROCUREMENT_CLIENT_SECRET=$(python -I -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" ".local/$P/accounts.json" "$1")
  export PROCUREMENT_CLIENT_SECRET; }
use requester; python procurement.py apps && python procurement.py entity
ID=$(python -c "import uuid;print(uuid.uuid4())")
python procurement.py create --id "$ID" --item 'Synthetic keyboard' --quantity 2 --unit-price-minor 2500 --justification 'demo'
python procurement.py search keyboard && python procurement.py submit "$ID" --version 0
use approver; python procurement.py workflow "$ID" && python procurement.py approve "$ID" --version 1 && python procurement.py history "$ID"
use auditor;  python procurement.py audit --id "$ID"
```

The PowerShell equivalent is in the Vietnamese section below. Use the hostname `localhost` (not an IP) and keep
`PROCUREMENT_CA_FILE`: the CLI verifies the CA and hostname for both the API and the token endpoint.
`list`, `search` and `audit` take `--limit` and `--offset`; `update ID --version N` needs all four fields; `delete` and
`update` work only in `DRAFT`; `reject ID --version N` rejects a `PENDING` request. `python procurement.py COMMAND --help`.

**Exit codes.** `3` = version conflict: re-read, decide again. `4` = write outcome unknown: run `reconcile ID` (reads
the record and history with your current permissions). The CLI never replays a write by itself; to replay a create, reuse
the same `--id` and the original data. The CLI prints the create UUID before sending.

### Verify

```bash
python -B -m unittest tests.test_procurement -v     # 2 unit tests
python -B -m tests.live -v                          # 12 live checks, about 5 to 6 minutes
python deploy/stack.py restart && python -B -m tests.live verify-restart
```

Executed in M6.3 on an isolated project (port 18463): unit 2 passed, live 12 passed, restart and persistence check
passed. Details: [Validation summary](https://github.com/lexuanbao258-collab/opentrix-v1-candidate/blob/621c32999668203f40363009aabe83ec66287c37/docs/candidate/VALIDATION.md).

### Stop without deleting data

`python deploy/stack.py stop` stops backend, ingress, Keycloak and PostgreSQL and keeps the volumes. `restart` waits for
Keycloak before the backend. Do not run `docker compose down -v` or delete volumes unless you intend to lose the data.
Re-creating the Keycloak container changes subjects, so ownership of older records must then be reviewed.

## Limitations

Prices are integers in minor currency units; the manifest has no currency, totals, limits or approval routing. Search
covers the item name only. Keycloak runs in demo mode, no rate limiting, one organisation, no hosted CI (no remote). See
the Platform [security and limitations](https://github.com/lexuanbao258-collab/opentrix-v1-candidate/blob/621c32999668203f40363009aabe83ec66287c37/docs/candidate/SECURITY-LIMITATIONS.md).

## License and attribution

Apache-2.0: [LICENSE](LICENSE), [NOTICE](NOTICE) (Caddyfile adapted from the Platform ingress, Apache-2.0, TRICORE
contributors), [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). AI-assisted development is disclosed in NOTICE (Codex for
M5 and M6.1-FIX; Claude for the M6.3 documentation); the owner should confirm the complete tool list. Candidate work
carries no upstream approval.

---

<a id="tiếng-việt-bản-gốc"></a>

## Tiếng Việt (bản gốc)

### OpenTrix Procurement CLI

Ứng dụng thử nghiệm M5 cho yêu cầu mua sắm nội bộ. Manifest `opentrix-procurement@1.0.0` khai báo thực thể
`purchaseRequest` và luồng `DRAFT → PENDING → APPROVED / REJECTED`. CLI dùng thư viện chuẩn Python và Platform API v1.

## Khởi chạy

Cần Git, `tar`, Python 3.10 trở lên và Docker chạy Linux containers với Compose 2.24.4 trở lên.
Cần bản checkout Git chứa Platform commit `f401b6e79930a1386e71e92a91ae6a909cfa1e59`.
Docker phải tải được base image và dùng được kho phụ thuộc Gradle trong lần build không có cache.

Từ repo này, chạy lệnh sau bằng PowerShell. Trên hệ điều hành khác, đổi đường dẫn Platform tương ứng.

Chạy từ thư mục cha và đặt `$env:PROCUREMENT_GIT_SOURCE` thành đường dẫn repo Git hoặc bundle do chủ sở hữu cung cấp.

```powershell
git clone --no-checkout https://github.com/lexuanbao258-collab/opentrix-v1-candidate.git opentrix-platform-runtime
git -C opentrix-platform-runtime checkout --detach f401b6e79930a1386e71e92a91ae6a909cfa1e59
git clone --no-local --no-checkout $env:PROCUREMENT_GIT_SOURCE opentrix-procurement-demo
git -C opentrix-procurement-demo checkout --detach 33a8bbf36f6f2daeb178ef405f8023561146c4d7
Set-Location opentrix-procurement-demo
python deploy/stack.py up --platform ../opentrix-platform-runtime
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

Để kiểm tra từ clone mới trên cùng máy, clone repo bằng `git clone --no-local --no-checkout $env:PROCUREMENT_GIT_SOURCE opentrix-procurement-fresh`, sau đó chạy `git -C opentrix-procurement-fresh checkout --detach 33a8bbf36f6f2daeb178ef405f8023561146c4d7`.
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
