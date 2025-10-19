# z2p

## 描述
这是一个名为 `z2p` 的项目，z2p 是一个基于 FastAPI 构建的 AI 模型代理服务，提供与 OpenAI 兼容的 API 接口，支持聊天补全、模型管理和文件上传等功能。本项目作为 AI 服务的代理层，提供统一的 API 接口和增强的功能特性。

## 功能特性

- 🚀 基于 FastAPI 的高性能 API 服务
- 💬 支持流式和非流式聊天补全
- 🤖 多模型支持与动态模型列表
- 🔐 安全的身份验证机制
- 📁 文件上传与处理功能
- 🐳 Docker 容器化部署
- 📊 完整的日志记录和监控
- 🔄 智能错误处理和重试机制
- 🌐 CORS 跨域支持

## 安装

### 前提条件
- Python 3.13+
- Docker (可选，用于容器化部署)

### 本地安装
1. 克隆仓库:
   ```bash
   git clone https://github.com/YuCat-OVO/z2p.git
   cd z2p
   ```

2. 创建并激活虚拟环境:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   .\venv\Scripts\activate   # Windows
   ```

3. 安装依赖:
   ```bash
   uv pip install -r uv.lock
   ```
   (注意: 本项目使用 `uv` 进行依赖管理，请确保已安装 `uv`。如果未安装，请参考 `pyproject.toml` 手动安装依赖。)

### Docker 安装
1. 构建 Docker 镜像:
   ```bash
   docker build -t z2p .
   ```

2. 运行容器:
   ```bash
   docker run -p 8001:8001 z2p
   ```

## 使用

### 启动应用
在本地安装后，可以通过以下命令启动应用:
```bash
python src/z2p_svc/app.py
```
或者使用 ASGI 服务器 (例如 Uvicorn):
```bash
uvicorn src.z2p_svc.asgi:application --host 0.0.0.0 --port 8001
```

### API 文档
应用启动后，可以在以下路径访问交互式 API 文档:
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

### 主要 API 端点

#### 聊天补全
```bash
POST /v1/chat/completions
Content-Type: application/json
Authorization: Bearer <your_access_token>

{
  "model": "glm-4.6",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 8192
}
```

#### 获取模型列表
```bash
GET /v1/models
Authorization: Bearer <your_access_token>
```

#### 流式聊天补全
```bash
POST /v1/chat/completions
Content-Type: application/json
Authorization: Bearer <your_access_token>

{
  "model": "glm-4.6",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "stream": true
}
```

## 配置

项目配置通过环境变量管理，请参考 `.env.example` 文件设置必要的环境变量。

### 主要环境变量

- `APP_ENV`: 应用环境 (development/production)
- `HOST`: 服务器监听地址 (默认: 0.0.0.0)
- `PORT`: 服务器监听端口 (默认: 8001)
- `LOG_LEVEL`: 日志级别 (DEBUG/INFO/WARNING/ERROR)
- `VERBOSE_LOGGING`: 是否启用详细日志 (true/false)
- `PROXY_URL`: 代理目标 URL
- `SECRET_KEY`: 应用密钥

## 开发

### 项目结构
```
z2p/
├── src/z2p_svc/
│   ├── app.py          # FastAPI 应用主模块
│   ├── routes.py       # API 路由定义
│   ├── config.py       # 配置管理
│   ├── chat_service.py # 聊天服务逻辑
│   ├── model_service.py # 模型服务逻辑
│   ├── auth_service.py # 认证服务
│   ├── file_uploader.py # 文件上传服务
│   └── models.py       # 数据模型定义
├── tests/              # 测试文件
├── Dockerfile          # Docker 构建文件
└── pyproject.toml      # 项目配置
```

### 运行测试
```bash
pytest
```

### 代码覆盖率
```bash
pytest --cov=z2p_svc --cov-report=html
```

### 开发环境设置
1. 复制环境变量文件:
   ```bash
   cp .env.example .env.development
   ```
2. 修改 `.env.development` 中的配置
3. 设置 `APP_ENV=development`

## 部署

### Docker 部署

#### 本地构建和运行
```bash
# 构建镜像
docker build -t z2p .

# 运行容器
docker run -d \
  --name z2p \
  -p 8001:8001 \
  -e APP_ENV=production \
  -e LOG_LEVEL=INFO \
  z2p
```

#### 使用预构建镜像
项目通过 GitHub Actions 自动构建并推送到以下镜像仓库：

- **Docker Hub**: `docker.io/yucatovo/z2p`
- **GitHub Container Registry**: `ghcr.io/yucat-ovo/z2p`

```bash
# 从 Docker Hub 拉取
docker pull docker.io/yucatovo/z2p:latest

# 从 GitHub Container Registry 拉取
docker pull ghcr.io/yucat-ovo/z2p:latest
```

### 使用 Granian 服务器
项目默认使用 Granian ASGI 服务器，提供高性能的 Python Web 服务。

### 环境变量配置
Docker 容器支持以下环境变量：

- `HOST`: 服务器监听地址 (默认: 0.0.0.0)
- `PORT`: 服务器监听端口 (默认: 8001)
- `WORKERS`: 工作进程数 (默认: 1)
- `LOG_LEVEL`: 日志级别 (默认: info)
- `APP_ENV`: 应用环境 (development/production)

### GitHub Actions 自动化
项目配置了自动化的 Docker 镜像构建和推送工作流：

- **触发条件**: 推送到 main 分支，或手动触发
- **构建平台**: linux/amd64
- **推送目标**: Docker Hub 和 GitHub Container Registry
- **标签策略**: `latest` 和 Git 短提交哈希

### 生产环境部署示例
```bash
docker run -d \
  --name z2p \
  --restart unless-stopped \
  -p 8001:8001 \
  -e APP_ENV=production \
  -e LOG_LEVEL=WARNING \
  -e WORKERS=4 \
  docker.io/yucatovo/z2p:latest
```

## 贡献
欢迎贡献！请遵循以下步骤:
1. Fork 仓库。
2. 创建新的功能分支 (`git checkout -b feature/AwesomeFeature`)。
3. 提交您的更改 (`git commit -m 'Add some AwesomeFeature'`)。
4. 推送到分支 (`git push origin feature/AwesomeFeature`)。
5. 提交 Pull Request。

## 许可证
本项目根据 `LICENSE.txt` 文件中的许可证进行分发。

## 联系
如果您有任何问题或建议，请提交 Issues。