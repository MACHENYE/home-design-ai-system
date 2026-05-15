# 家装智能设计系统部署文档

本文档用于记录本系统在本地开发环境和云服务器环境中的部署步骤，覆盖前端、后端、MySQL、Redis、Nginx、文件上传目录和环境变量配置。

## 1. 系统组成

- 前端：Vue 3 + Vite + Element Plus
- 后端：FastAPI + Uvicorn
- 数据库：MySQL 8.0
- 缓存与任务队列：Redis
- 图片生成：NanoBanana API
- 智能推荐与提示词优化：阿里云百炼千问 API
- 静态资源与上传文件：本地目录或云服务器 Nginx 目录

## 2. 本地运行环境

建议版本：

- Python 3.11
- Node.js 18 或以上
- MySQL 8.0
- Redis 5 或以上

本项目默认后端端口：

```text
http://127.0.0.1:8001
```

前端打包后由 FastAPI 挂载到：

```text
http://127.0.0.1:8001/app/
```

## 3. MySQL 配置

创建数据库：

```sql
CREATE DATABASE home_design_ai
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
```

本机连接示例：

```text
Host: 127.0.0.1
Port: 3306
User: root
Database: home_design_ai
```

项目启动时会自动创建和补齐以下核心表：

- `users`：用户信息
- `sessions`：登录会话
- `tasks`：生成任务
- `design_records`：生成方案记录
- `favorite_schemes`：收藏方案
- `system_logs`：系统运行日志

系统会自动维护外键和索引，用于提升用户记录查询、管理员筛选、任务状态查询和日志检索效率。

## 4. Redis 配置

Redis 用于两个场景：

- 缓存管理员统计数据和智能推荐结果
- 作为轻量任务队列保存待生成任务

本机默认地址：

```text
redis://127.0.0.1:6379/0
```

检查 Redis 是否正常：

```powershell
redis-cli ping
```

正常返回：

```text
PONG
```

## 5. 后端环境变量

后端环境变量文件：

```text
backend/.env
```

核心配置示例：

```env
NANOBANANA_API_KEY=你的NanoBanana密钥
NANOBANANA_BASE_URL=https://api.nanobananaapi.ai/api/v1/nanobanana

DATABASE_URL=mysql+pymysql://root:你的密码@127.0.0.1:3306/home_design_ai
REDIS_URL=redis://127.0.0.1:6379/0

PUBLIC_BASE_URL=http://127.0.0.1:8001
UPLOADS_DIR=./uploads
FRONTEND_DIR=../frontend

VISION_RECOMMENDATION_ENABLED=true
BAILIAN_API_KEY=你的百炼APIKey
BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
BAILIAN_VISION_MODEL=qwen3-vl-plus
BAILIAN_TEXT_MODEL=qwen-plus

GENERATION_QUEUE_ENABLED=true
GENERATION_QUEUE_POLL_TIMEOUT_S=2
```

如果需要服务器保存上传图片，可以启用远程上传：

```env
REMOTE_UPLOAD_ENABLED=true
REMOTE_UPLOAD_HOST=你的服务器公网IP
REMOTE_UPLOAD_PORT=22
REMOTE_UPLOAD_USER=root
REMOTE_UPLOAD_PASSWORD=你的服务器密码
REMOTE_UPLOAD_DIR=/home/home-design/uploads
REMOTE_PUBLIC_BASE_URL=http://你的服务器公网IP/uploads
```

## 6. 安装后端依赖

进入后端目录：

```powershell
cd backend
```

安装依赖：

```powershell
uv pip install -r requirements.txt --python .\.venv\Scripts\python.exe
```

或使用普通 pip：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 7. 前端依赖与打包

进入前端目录：

```powershell
cd frontend
```

安装依赖：

```powershell
npm install
```

打包：

```powershell
npm run build
```

打包产物会生成在：

```text
frontend/dist
```

后端会自动挂载这个目录到 `/app/`。

## 8. 启动系统

在项目根目录执行：

```powershell
.\start_fullstack.bat
```

或手动启动后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

访问地址：

```text
http://127.0.0.1:8001/app/
```

健康检查：

```text
http://127.0.0.1:8001/healthz
```

## 9. 云服务器上传目录

如果使用云服务器保存上传图片，先创建目录：

```bash
sudo mkdir -p /home/home-design/uploads
sudo chmod 755 /home/home-design/uploads
```

Nginx 配置示例：

```nginx
server {
    listen 80;
    server_name 你的服务器公网IP;

    location /uploads/ {
        alias /home/home-design/uploads/;
        autoindex off;
    }

    location /api/v1/nanobanana/callback {
        proxy_pass http://127.0.0.1:8001/api/v1/nanobanana/callback;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

测试上传目录：

```text
http://你的服务器公网IP/uploads/test.txt
```

测试回调接口：

```text
http://你的服务器公网IP/api/v1/nanobanana/callback
```

## 10. 系统日志与异常追踪

系统运行日志保存到 MySQL 表：

```text
system_logs
```

记录内容包括：

- 用户注册、登录、退出
- 图片上传
- 生成任务提交
- 后台生成任务成功或失败
- NanoBanana 回调
- 提示词优化
- 评分反馈
- 收藏与删除操作
- 服务端异常和 500 错误

管理员接口：

```text
GET /api/v1/admin/logs
```

可选参数：

```text
limit
level
action
username
start_at
end_at
```

论文中可描述为：系统通过日志表记录关键业务行为、接口耗时和异常信息，为运行监控、问题追踪和管理员审计提供支持。

## 11. Redis 任务队列

队列名称：

```text
home_design:generation_queue
```

流程：

1. 用户提交生成请求
2. FastAPI 创建本地任务并写入 MySQL
3. 任务 ID 写入 Redis 队列
4. 后台 worker 从 Redis 取任务
5. worker 调用 NanoBanana
6. 回调或轮询更新任务状态

论文中可描述为：系统基于 Redis 实现轻量异步任务队列，将请求提交与大模型调用解耦，提升接口响应速度和系统稳定性。

## 12. 常见问题

### 12.1 MySQL 未启动

检查服务：

```powershell
Get-Service MySQL
```

启动服务：

```powershell
Start-Service MySQL
```

### 12.2 Redis 未启动

检查服务：

```powershell
Get-Service Redis
```

启动服务：

```powershell
Start-Service Redis
```

### 12.3 前端页面没有更新

重新打包前端：

```powershell
cd frontend
npm run build
```

然后重启后端。

### 12.4 图片生成接口无法访问上传图片

真实调用 NanoBanana 时，图片 URL 必须能被公网访问。可以使用：

- 云服务器 Nginx 静态目录
- OSS
- 内网穿透工具

如果使用云服务器，确认 `REMOTE_PUBLIC_BASE_URL` 是公网可访问地址。

### 12.5 管理后台没有数据

检查是否连接到了正确的 MySQL 数据库：

```sql
USE home_design_ai;
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM design_records;
```

确认 `backend/.env` 中的 `DATABASE_URL` 指向同一个数据库。
