# free-proxy-pool

自动收集并验证免费代理与机场节点，每 3 小时在 GitHub Actions 上刷新一次，结果直接发布在仓库根目录。

**支持类型**：SOCKS5 / SOCKS4 / HTTP(S) 代理 + vmess / vless / trojan / ss / hy2 等节点订阅，全部协议均做住宅/ISP 网络识别，不限国家。

## 结果文件（根目录，每 3 小时覆盖更新）

| 文件 | 内容 |
|---|---|
| `socks5_fast.txt` | SOCKS5 快代理（<3s），优先用 |
| `socks5_alive.txt` | SOCKS5 实测可用（完整链路：握手→CONNECT→TLS→出口 IP 校验） |
| `socks5_residential.txt` | SOCKS5 住宅/ISP/移动网络候选 |
| `http_fast.txt` / `http_alive.txt` / `http_residential.txt` | HTTP(S) 代理同上 |
| `socks4_alive.txt` / `socks4_residential.txt` | SOCKS4 代理 |
| `nodes_alive.txt` | 机场节点（TCP 可达，原始 URI，导入客户端即可尝试） |
| `nodes_residential.txt` | 住宅/ISP 网络的节点 |
| `*_residential_detail.csv` | 住宅候选明细：国家/城市/ISP/ASN/是否移动网络 |
| `*_detail.csv` / `*_detail.json` | 全量检测明细（延迟、出口 IP、失败原因） |
| `updated_at.txt` | 各类型更新时间与数量统计 |

直接拉取（示例）：

```bash
curl -O https://raw.githubusercontent.com/fmw86/socks5-filter/main/socks5_fast.txt
```

## 住宅 / 家宽说明

免费公开代理列表几乎全是机房 IP，纯住宅列表不存在。本项目用 ip-api.com 给每个存活条目打网络类型标，把入口 IP 非机房（`hosting=false`，含 ISP 家宽与移动网络）的筛进 `*_residential.txt`，明细在 `*_residential_detail.csv`（可按国家、ISP 含 电信/联通/移动 过滤）。节点（nodes）为 TCP 可达性测试。

## 源配置

- `sources_socks5.txt` / `sources_http.txt` / `sources_socks4.txt`：各协议代理源（每行一个 URL）
- `node_subs.txt`：节点订阅源

增删源直接改这几个文件。本地复跑：

```bash
python3 check_socks5.py --collect --check --protocol http   # 或 socks5 / socks4
python3 collect_nodes.py --collect --check
python3 tag_residential.py --input socks5_detail.json --output-prefix socks5
```

仅 Python 3 标准库，无第三方依赖。

## 本地 Windows 使用

见 `README.windows.md`（`run.bat` 全量 / `run-quick.bat` 快速）。

## 注意

免费代理和公共节点极不稳定且不可信，结果只代表检测时刻状态。**不要**用它们传输账号、Cookie、Token、私钥等敏感信息。
