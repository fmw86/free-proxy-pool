# socks5-filter

本项目用于收集公开免费 SOCKS5 代理，并在本机网络环境下实测筛选可用节点。

## 功能

- 从 `sources.txt` 中的多个公开源拉取 SOCKS5 列表
- 统一清洗为 `ip:port` / `[IPv6]:port` 格式并去重
- 执行 SOCKS5 握手测试
- 执行 SOCKS5 CONNECT 到 `api.ipify.org:443`
- 通过 TLS 请求确认真实出口 IP
- 按延迟排序输出可用代理和快代理
- 大列表采用有界任务队列，避免一次性创建全部并发任务占满内存

## 文件说明

- `sources.txt`：代理来源列表，每行一个 URL
- `check_socks5.py`：核心收集和检测脚本
- `run.sh`：一键重新收集并检测
- `socks5_all.txt`：聚合去重后的全部候选代理
- `socks5_alive.txt`：当前实测可用代理
- `socks5_fast.txt`：低于阈值的快代理，默认 `3000ms`
- `socks5_detail.csv`：检测明细，包含延迟、出口 IP、失败原因
- `socks5_detail.json`：JSON 格式检测明细
- `sources_result.csv`：每个来源的拉取结果和数量
- `relayproxy*.sh` / `relay_upstream-relay_proxy.py`：将筛选出的可用代理绑定到 RELAY upstream-relay key 的运维脚本

## Windows 本地使用

Windows 本地运行请看 `README.windows.md`。

快速入口：

```powershell
cd C:\path\to\socks5-filter
.\run.ps1
```

也可以双击 `run.bat`。

## 快速使用

基础代理收集和检测只需要 Python 3 标准库，无需安装额外依赖。

重新收集并筛选：

```bash
cd ./socks5-filter
./run.sh
```

测试最快的一个代理：

```bash
cd ./socks5-filter
curl --socks5-hostname "$(head -1 socks5_fast.txt)" -m 8 https://api.ipify.org
```

## 常用参数

`run.sh` 支持通过环境变量调整参数：

```bash
WORKERS=300 TIMEOUT=8 FAST_MS=5000 ./run.sh
```

只测试前 `1000` 条，适合快速验证脚本：

```bash
LIMIT=1000 ./run.sh
```

直接调用 Python 脚本：

```bash
python3 ./check_socks5.py --collect --check --workers 500 --timeout 6 --fast-ms 3000
```

只重新检测已有 `socks5_all.txt`：

```bash
python3 ./check_socks5.py --check --workers 500 --timeout 6 --fast-ms 3000
```

只重新拉取并清洗来源：

```bash
python3 ./check_socks5.py --collect --timeout 20
```

自定义用于确认出口 IP 的 HTTPS 目标：

```bash
python3 ./check_socks5.py --check --target-host api.ipify.org --target-port 443
```

`--workers`、`--timeout`、`--fast-ms` 和 `--target-port` 会拒绝零值或负值；`--limit` 可设为 `0` 表示不限制。

## 输出说明

`check_socks5.py` 默认会生成：

```text
socks5_alive.txt
socks5_fast.txt
socks5_detail.csv
socks5_detail.json
```

如需使用不同输出前缀：

```bash
python3 ./check_socks5.py --check --output-prefix test --limit 1000
```

会生成：

```text
test_alive.txt
test_fast.txt
test_detail.csv
test_detail.json
```

## 注意

免费公共 SOCKS5 代理存活时间很短，建议使用前重新检测。不要用公共免费代理登录账号、传输 Cookie、Token、私钥或其他敏感数据。

## 项目沉淀记录

### 目标

本项目沉淀为一个本机可复用的免费 SOCKS5 代理筛选工具。它不依赖 AI API，不需要模型调用，只通过本机网络环境直接拉取公开代理源，并实测筛出当前可用节点。

### 固定目录

```text
./socks5-filter
```

后续维护、运行和排查都优先在这个目录中完成，不需要移动到其他项目目录。

### 工作流

1. 从 `sources.txt` 中配置的公开源拉取 SOCKS5 列表。
2. 解析 `socks5://ip:port`、`ip:port`、`[IPv6]:port` 等格式并统一清洗。
3. 对候选代理去重，写入 `socks5_all.txt`。
4. 对每个代理执行 SOCKS5 握手。
5. 通过 SOCKS5 CONNECT 访问 `api.ipify.org:443`。
6. 完成 TLS 请求并读取出口 IP，确认代理真实可用。
7. 按总耗时排序，输出可用列表、快代理列表和明细文件。

### 核心文件

- `sources.txt`：公开代理源清单，后续新增/删除来源改这里。
- `check_socks5.py`：核心逻辑，负责拉取、清洗、握手、CONNECT、测速和结果输出。
- `run.sh`：日常一键入口，适合手动运行或被其他本地任务调用。
- `requirements.txt`：RELAY 代理绑定功能所需的 `PySocks`、`PyYAML`；基础筛选脚本只用 Python 3 标准库。

### 输出文件

- `socks5_all.txt`：所有候选代理，去重后的 `ip:port` 格式。
- `socks5_alive.txt`：本机当前实测可用代理。
- `socks5_fast.txt`：低于 `FAST_MS` 阈值的快代理，默认 `3000ms`。
- `socks5_detail.csv`：检测明细，适合人工查看和排序。
- `socks5_detail.json`：检测明细，适合程序读取。
- `sources_result.csv`：每个来源的拉取状态、数量和耗时。

### 当前基线

首次完整筛选时的结果如下，仅代表当时网络环境和代理状态：

```text
候选代理：126382
可用代理：1383
快代理：142
快代理阈值：3000ms
```

免费公共代理变化很快，后续使用时应以重新运行后的结果为准。

### 日常命令

完整重新收集并筛选：

```bash
cd ./socks5-filter
./run.sh
```

降低并发、放宽超时和快代理阈值：

```bash
cd ./socks5-filter
WORKERS=300 TIMEOUT=8 FAST_MS=5000 ./run.sh
```

只快速测试前 `1000` 条候选：

```bash
cd ./socks5-filter
LIMIT=1000 ./run.sh
```

只重新检测已有候选列表：

```bash
cd ./socks5-filter
python3 ./check_socks5.py --check --workers 500 --timeout 6 --fast-ms 3000
```

只重新拉取并清洗来源：

```bash
cd ./socks5-filter
python3 ./check_socks5.py --collect --timeout 20
```

### 使用建议

- 优先使用 `socks5_fast.txt`，如果数量不够再看 `socks5_alive.txt`。
- 使用前先抽测前几条，公共代理可能几分钟内失效。
- 如果误杀太多，可以把 `TIMEOUT` 调到 `8` 或 `10`。
- 如果机器负载过高，可以把 `WORKERS` 从 `500` 降到 `200` 或 `300`。
- 不要用这些公共代理传输账号、Cookie、Token、SSH 私钥等敏感信息。


## RELAY 代理绑定脚本

除了收集和筛选代理，本项目还提供一组运维脚本，用于把筛出的可用 SOCKS5 代理绑定到 RELAY upstream-relay key，并做健康检查和自动修复。核心逻辑在 `relay_upstream-relay_proxy.py`，日常通过下列封装脚本调用。

首次使用 RELAY 功能前安装依赖，Ubuntu 24.04 推荐：

```bash
apt update
apt install -y python3-socks python3-yaml
```

也可以在 Python 虚拟环境中运行 `pip install -r requirements.txt`。

### 脚本说明

- `relayproxy.sh`：为 upstream-relay key 绑定 SOCKS5 代理（等价于 `apply`）。
- `relayproxycheck.sh`：检查现有 key 的代理是否可用，输出 `ok/bad/missing` 汇总。
- `relayproxyrepair.sh`：重新拉取代理池并修复失效或缺失的代理。
- `relayproxyrepairfast.sh`：修复但跳过重新拉取（`--no-refresh`），使用现有代理池，速度更快。
- `relayproxyreplace.sh`：强制替换代理（`--replace --min-stable 3`）。
- `relayproxy_summary.sh`：以上脚本的公共入口，负责运行并解析摘要，一般不直接调用。

### 常用命令

绑定代理：

```bash
cd ./socks5-filter
./relayproxy.sh
```

检查代理健康状态：

```bash
cd ./socks5-filter
./relayproxycheck.sh
```

修复失效代理（会重新拉取代理池）：

```bash
cd ./socks5-filter
./relayproxyrepair.sh
```

快速修复（复用现有代理池，不重新拉取）：

```bash
cd ./socks5-filter
./relayproxyrepairfast.sh
```

### 日志

每次运行的完整日志默认写入：

```text
./logs/<命令>-<时间戳>.log
```

可用环境变量 `RELAY_PROXY_LOG_DIR` 修改日志目录。脚本会在终端打印精简摘要（绑定/修复数量、代理池 `tested/alive/fast`、日志路径），详细信息看对应日志文件。

RELAY 配置、服务和凭据位置可通过 `RELAY_CONFIG`、`RELAY_SERVICE`、`RELAY_BASE_URL`、`RELAY_ENV_FILE` 环境变量覆盖；如果当前环境已设置 `RELAY_API_KEY`，会优先使用环境变量，不读取凭据文件。
