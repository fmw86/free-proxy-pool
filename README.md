# free-proxy-pool

自动收集并验证免费代理与机场节点，每 3 小时在 GitHub Actions 上自动刷新，**结果直接发布在本仓库根目录**。任何设备打开本仓库即可取用，无需安装、无需运行任何脚本。

**支持类型**：SOCKS5 / SOCKS4 / HTTP(S) 代理 + vmess / vless / trojan / ss / hy2 等机场节点，全部做住宅/ISP 网络识别，不限国家。

## 直接使用（其他设备）

筛选好的结果就是仓库根目录下的 txt 文件，每 3 小时自动覆盖更新（更新时间见 `updated_at.txt`）。三种取用方式任选：

**方式一：网页直接复制** —— 打开 [仓库首页](https://github.com/fmw86/free-proxy-pool)，点开任意结果文件（如 `socks5_fast.txt`），右上角复制按钮即可。

**方式二：命令行下载**（任何有 curl/wget 的设备，Linux/Mac/Windows/手机 Termux 通用）

```bash
# ⭐ 住宅/家宽 IP 汇总（全协议去重合并，一个文件全齐）
curl -O https://raw.githubusercontent.com/fmw86/free-proxy-pool/main/residential.txt

# SOCKS5 快代理（延迟 <3s，优先用）
curl -O https://raw.githubusercontent.com/fmw86/free-proxy-pool/main/socks5_fast.txt

# HTTP 代理快代理
curl -O https://raw.githubusercontent.com/fmw86/free-proxy-pool/main/http_fast.txt
```

**方式三：克隆整个仓库**

```bash
git clone https://github.com/fmw86/free-proxy-pool.git
```

**测试某个代理是否可用**（任何设备）：

```bash
curl --socks5-hostname "$(head -1 socks5_fast.txt)" -m 8 https://api.ipify.org
```

返回的 IP 就是该代理的出口 IP。

**机场节点导入**：把下面的链接作为"订阅链接"填进 v2rayN / Clash / Shadowrocket / NekoBox 等客户端即可批量导入约 3000 个节点：

```
https://raw.githubusercontent.com/fmw86/free-proxy-pool/main/nodes_alive.txt
```

## 结果文件说明（根目录，每 3 小时覆盖更新）

**按用途选文件**：

| 你想要 | 用这个文件 |
|---|---|
| 住宅/家宽 IP（不分协议，最方便） | `residential.txt` |
| 某个协议的住宅 IP | `socks5_residential.txt` / `http_residential.txt` |
| 挑特定国家的家宽 | `*_residential_detail.csv`（有 country/ISP/ASN 列） |
| 速度最快的代理 | `socks5_fast.txt` / `http_fast.txt` |
| 全部可用代理 | `socks5_alive.txt` / `http_alive.txt` |
| 机场节点 | `nodes_alive.txt` |

**完整文件清单**：

| 文件 | 内容 |
|---|---|
| `residential.txt` | ⭐ 全协议住宅/ISP/移动网络 IP 汇总（socks5+http+socks4 去重合并） |
| `socks5_fast.txt` | SOCKS5 快代理（<3s），优先用 |
| `socks5_alive.txt` | SOCKS5 实测可用（完整链路：握手→CONNECT→TLS→出口 IP 校验） |
| `http_fast.txt` / `http_alive.txt` | HTTP(S) 代理（快 / 全部可用） |
| `socks4_alive.txt` | SOCKS4 代理（该协议免费源质量差，经常为空属正常） |
| `nodes_alive.txt` | 机场节点 URI（vmess/vless/trojan/ss/hy2） |
| `*_residential.txt` | 各协议各自的住宅候选 |
| `*_residential_detail.csv` | 住宅候选明细：国家/城市/ISP/ASN/是否移动网络 |
| `nodes_detail.csv` | 节点明细（协议/地址/可达性/ISP） |
| `*_detail.csv` / `*_detail.json` | 全量检测明细（延迟、出口 IP、失败原因） |
| `updated_at.txt` | 各类型更新时间与数量统计，**先看这个判断新鲜度** |

## 住宅 / 家宽 IP 怎么来的

免费公开代理列表 99% 是机房 IP，纯住宅列表不存在。本项目的做法：每个代理测活后，通过 ip-api.com 查询其入口 IP 的网络属性，把**非机房 IP**（`hosting=false`，即 ISP 家宽、移动网络）单独筛出——这就是 `residential.txt` 的来源，通常每轮 400~500 条。

**筛选特定国家家宽**（以中国为例）：下载 `socks5_residential_detail.csv` 或 `http_residential_detail.csv`，按 `country` 列 = China、`isp` 列含 电信/联通/移动 过滤即可。也可用命令行：

```bash
curl -s https://raw.githubusercontent.com/fmw86/free-proxy-pool/main/http_residential_detail.csv | grep China
```

注意：住宅候选只是网络属性判断，稳定性仍取决于代理本身，用前先测。

## 检测方式（结果可信度）

- **代理类（socks5/http/socks4）**：不只测端口通，走完整链路——SOCKS5/HTTP 握手 → 通过代理 CONNECT 到 `api.ipify.org:443` → TLS 请求确认出口 IP。`alive` = 真实可用的 HTTPS 代理。
- **节点类（nodes）**：聚合 4 个公开订阅，TCP 连通性测试 + 入口 IP 属性标注。能连上不等于协议配置可用，导入客户端后以实际连接为准。
- 检测跑在 GitHub Actions（美国机房出口），与你本机网络环境不同，重要场景请先自测。

## 源配置

- `sources_socks5.txt` / `sources_http.txt` / `sources_socks4.txt`：各协议代理源（每行一个 URL，`#` 注释）
- `node_subs.txt`：节点订阅源

增删源直接改这几个文件。本地复跑（仅 Python 3 标准库，无第三方依赖）：

```bash
python3 check_socks5.py --collect --check --protocol http   # 或 socks5 / socks4
python3 collect_nodes.py --collect --check                  # 节点订阅
python3 tag_residential.py --input socks5_detail.json --output-prefix socks5
```

本地 Windows 使用见 `README.windows.md`（`run.bat` 全量 / `run-quick.bat` 快速）。

## 注意

免费代理和公共节点极不稳定且不可信，结果只代表检测时刻状态。**不要**用它们传输账号、Cookie、Token、私钥等敏感信息。
