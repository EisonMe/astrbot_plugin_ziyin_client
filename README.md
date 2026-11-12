# 紫音 Windows 远程客户端 AstrBot 插件

将 AstrBot 连接到一台可路由访问的 Windows 紫音客户端（默认端口 17643）。插件不会自动安装到 AstrBot；请使用 AstrBot 官方插件管理器从 GitHub 安装本仓库。

## 配置

1. 在 AstrBot 插件管理器使用 GitHub 仓库地址：`https://github.com/EisonMe/astrbot_plugin_ziyin_client`。
2. 在插件配置填写 `base_url`，例如 `https://192.168.1.100:17643`。这里必须是 AstrBot 主机可访问的 Windows LAN/VPN 地址。`localhost` 只在 AstrBot 与 Windows 客户端同机时适用。
3. 在紫音客户端 WebUI/托盘的受信任管理操作中获取 API Key，放入插件密钥字段。密钥仅以 Bearer Header 发送，不写日志。
4. 默认 TLS 证书和主机名验证开启。若使用安装器生成的自签名证书，在受信任通道取得 `server.cer`，核对指纹后运行 `openssl x509 -inform DER -in server.cer -out server.pem`，把 `server.pem` 的绝对路径填入 AstrBot 主机上的 `ca_file`；地址须匹配证书 SAN 中的安装时 IPv4。指纹只能作为额外校验，不能取代 CA。不要关闭验证。明文 HTTP 默认关闭。
5. 默认只允许私聊，群聊关闭；文件写入关闭，桌面控制关闭。仅 AstrBot 管理员或明确列入 `allowed_users` 的账号可调用。写文件还需显式启用，并始终仅限管理员。
6. 首次只调用 `ziyin_client_health` 做连通性检查。插件不会在安装时连接客户端。

## 工具

- `ziyin_client_health`：读取健康状态与连接设置。
- `ziyin_client_run`：以 Windows 服务账户执行 PowerShell。命令具有高权限，调用前须获得用户明确授权。
- `ziyin_client_status`：查询任务结果或最近任务。
- `ziyin_client_cancel`：请求取消任务，不回滚副作用。
- `ziyin_client_files`：列目录/下载；写入/删除默认关闭，启用后仅管理员可操作。
- `ziyin_client_desktop_status`：只读查询本机托盘桌面授权状态。
- `ziyin_client_screenshot`：将截图直接发送给当前聊天用户。模型不会自动看见图像，不能声称已核验画面。
- `ziyin_client_desktop_input`：鼠标/键盘输入，仅在插件显式启用桌面控制且本机托盘授权后执行。

桌面控制默认关闭。请在本机托盘手动授权，且锁屏、登录界面、UAC 安全桌面与 RDP 不可用。

## 开发与测试

```bash
python -m unittest discover -s tests -v
```

在已安装 AstrBot 依赖的 Python 环境运行测试。测试加载 AstrBot API，但不启动或修改 AstrBot 实例，也不会连接真实 Windows 客户端。真实联调需要用户提供可达 URL、API Key 和受信任证书。
