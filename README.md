# 飞牛 fnOS Docker Compose → .fpk 打包工具

WebUI 工具：上传 docker-compose.yml + 图标，一键生成可在飞牛应用中心安装的 `.fpk`。

## 功能

- 拖拽上传 compose 和图标
- 自动生成飞牛应用项目结构
- 支持桌面入口（ui/config）
- 可选调用 fnpack 直接打包
- Docker 一键部署

宿主机路径,容器路径,用途
- ./data/fnpack/,/data/fnpack/,fnpack 二进制
- ./data/output/,/data/output/,生成的项目和 .fpk
- ./data/cache/,/data/cache/,缓存
- 端口

### 容器是 Linux，所以必须用 Linux 版 fnpack，不能用Windows 版。
- 打开官网：https://developer.fnnas.com/
- 下载：
- fnpack-1.2.3-linux-amd64（x86 机器）
- 或 fnpack-1.2.3-linux-arm64（ARM 机器）
- 下载后**改名**为**fnpac**k放到宿主机fnpack路径
