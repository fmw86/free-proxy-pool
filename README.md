# free-proxy-pool

自动收集并验证免费代理与机场节点，每 3 小时在 GitHub Actions 上自动刷新，**结果直接发布在本仓库根目录**。任何设备打开本仓库即可取用，无需安装、无需运行任何脚本。

**支持类型**：SOCKS5 / SOCKS4 / HTTP(S) 代理 + vmess / vless / trojan / ss / hy2 等机场节点，全部做住宅/ISP 网络识别，不限国家。

## 直接使用（其他设备）

筛选好的结果就是仓库根目录下的 txt 文件，每 3 小时自动覆盖更新。三种取用方式任选：

**方式一：网页直接复制** —— 打开 [仓库首页](https://github.com/fmw86/free-proxy-pool)，点开任意结果文件（如 `socks5_fast.txt`），右上角复制按钮即可。

**方式二：命令行单文件下载**（任何有 curl/wget 的设备）

```bash
# SOCKS5 快代理（优先用这个）
curl -O https://raw.githubusercontent.com/fmw86/free-proxy-pool/main/socks5_fast.txt

# HTTP 代理
curl -O https://raw.githubusercontent.com/fmw86/free-proxy-pool/main/http_fast.txt

# 住宅/家宽候选
curl -O https://raw.githubusercontent.com/fmw86/free-proxy-pool/main/socks5_residential.txt
```

**方式三：克隆整个仓库**

```bash
git clone https://github.com/fmw86/free-proxy-pool.git
```

**直接测试某个代理**（任何设备）：

```bash
curl --socks5-hostname "$(head -1 socks5_fast.txt)" -m 8 https://api.ipify.org
```

**机场节点**：`nodes_alive.txt` 每行是一个节点 URI，把该文件的 raw 链接作为"订阅链接"填进 v2rayN / Clash / Shadowrocket 等客户端即可批量导入：

```
https://raw.githubusercontent.com/fmw86/free-proxy-pool/main/nodes_alive.txt
```

## 结果文件（根目录，每 3 小时覆盖更新）

| 文件 | 内容 |
|---|---|
| `socks5_fast.txt` | SOCKS5 快代理（<3s），优先用 |
| `socks5_alive.txt` | SOCKS5 实测可用（完整链路：握手→CONNECT→TLS→出口 IP 校验） |
| `http_fast.txt` / `http_alive.txt` | HTTP(S) 代理（快 / 全部可用） |
| `socks4_alive.txt` | SOCKS4 代理 |
| `nodes_alive.txt` | 机场节点（TCP 可达，原始 URI） |
| `*_residential.txt` | 各类型住宅/ISP/移动网络候选（不限国家） |
| `*_residential_detail.csv` | 住宅候选明细：国家/城市/ISP/ASN/是否移动网络 |
| `*_detail.csv` / `*_detail.json` | 全量检测明细（延迟、出口 IP、失败原因） |
| `updated_at.txt` | 各类型更新时间与数量统计，**先看这个判断新鲜度** |

## 住宅 / 家宽说明

免费公开代理列表几乎全是机房 IP，纯住宅列表不存在。本项目用 ip-api.com 给每个存活条目打网络类型标，把入口 IP 非机房（`hosting=false`，含 ISP 家宽与移动网络）的筛进 `*_residential.txt`。找特定国家家宽：打开对应的 `*_residential_detail.csv`，按 `country` 列和 `isp` 列（如 China + 电信/联通/移动）过滤。节点（nodes）为 TCP 可达性测试。

## 源配置

- `sources_socks5.txt` / `sources_http.txt` / `sources_socks4.txt`：各协议代理源（每行一个 URL）
- `node_subs.txt`：节点订阅源

增删源直接改这几个文件。本地复跑（仅 Python 3 标准库，无第三方依赖）：

```bash
python3 check_socks5.py --collect --check --protocol http   # 或 socks5 / socks4
python3 collect_nodes.py --collect --check
python3 tag_residential.py --input socks5_detail.json --output-prefix socks5
```

## 本地 Windows 使用

见 `README.windows.md`（`run.bat` 全量 / `run-quick.bat` 快速）。

## 注意

免费代理和公共节点极不稳定且不可信，结果只代表检测时刻状态（GitHub Actions 出口网络与你本机不完全一致，重要场景先自测）。**不要**用它们传输账号、Cookie、Token、私钥等敏感信息。
