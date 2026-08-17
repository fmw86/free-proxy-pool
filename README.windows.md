# Windows 使用说明

本项目可以直接复制到 Windows 本地运行，用于筛选你当前 Windows 网络环境下可用的免费 SOCKS5 代理。

## 环境要求

- Windows10 / Windows11
- Python3.10 或更新版本
- PowerShell5+，Windows 自带即可

安装 Python 时建议勾选 `Add python.exe to PATH`。

## 运行方式

PowerShell 进入项目目录后执行：

```powershell
cd C:\path\to\socks5-filter
.\run.ps1
```

也可以双击：

```text
run.bat
```

`run.bat` 会调用 `run.ps1`，运行结束后会暂停窗口，方便查看结果。

## 默认参数

Windows 默认参数比 Linux VPS 保守：

```text
WORKERS=200
TIMEOUT=8
FAST_MS=5000
LIMIT=0
```

原因是 Windows 本机大量并发 TCP 连接更容易受到防火墙、杀毒软件或系统端口限制影响。

## 自定义参数

临时调整并发、超时和快代理阈值：

```powershell
$env:WORKERS="200"
$env:TIMEOUT="8"
$env:FAST_MS="5000"
.\run.ps1
```

只快速测试前 `1000` 条：

```powershell
$env:LIMIT="1000"
.\run.ps1
```

恢复完整测试：

```powershell
Remove-Item Env:LIMIT -ErrorAction SilentlyContinue
.\run.ps1
```

## 输出文件

运行完成后，结果会生成在项目目录：

```text
socks5_all.txt
socks5_alive.txt
socks5_fast.txt
socks5_detail.csv
socks5_detail.json
sources_result.csv
```

优先使用：

```text
socks5_fast.txt
```

如果快代理数量不够，再看：

```text
socks5_alive.txt
```

## 测试单个代理

PowerShell 示例：

```powershell
curl.exe --socks5-hostname "IP:PORT" -m 8 https://api.ipify.org
```

例如：

```powershell
curl.exe --socks5-hostname "127.0.0.1:1080" -m 8 https://api.ipify.org
```

## 常见问题

### 无法运行脚本

如果 PowerShell 提示执行策略限制，可以用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

或者直接双击 `run.bat`。

### Python 找不到

确认 Python 已安装并加入 PATH：

```powershell
python --version
```

如果无输出，重新安装 Python，并勾选 `Add python.exe to PATH`。

### 速度慢或卡住

降低并发：

```powershell
$env:WORKERS="100"
.\run.ps1
```

或者只先测少量：

```powershell
$env:LIMIT="1000"
.\run.ps1
```

### Windows 防火墙提示

这是大量出站连接触发的正常现象。允许 Python 出站连接即可。

## 注意

免费公共 SOCKS5 代理不稳定，筛选结果只代表当前时间和当前网络环境。不要用公共代理传输账号、Cookie、Token、SSH 私钥等敏感信息。
