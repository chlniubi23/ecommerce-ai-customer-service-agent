# 部署手册（DEPLOY）

本文记录本项目在腾讯轻量应用服务器上的真实部署过程与运维手册，含实际踩坑与解法。
当前线上实例：`http://134.175.48.116:3000`（前端）｜ `http://134.175.48.116:8000`（API）。

---

## 一、目标环境与架构选型

| 项 | 值 | 说明 |
|---|---|---|
| 服务器 | 腾讯轻量 2核2G/50G 盘/4M 带宽（广州） | 镜像 `Ubuntu24.04-Docker29`（Docker 29.6.1 + Compose v5.3.1 预装） |
| 后端镜像 | **slim 变体（~412MB）** | 构建参数 `EMBEDDING_PRELOAD=false`，跳过 torch 与本地 BGE 模型 |
| Embedding | 硅基流动 API `BAAI/bge-large-zh-v1.5`（1024 维） | 2G 内存跑不动本地模型；服务器索引从零重建，维度内部自洽 |
| LLM | DeepSeek（OpenAI 兼容接口） | 与本地开发一致 |
| 数据 | MySQL 8 容器（首启自动建库+种子+演示数据）+ qdrant 命名卷 | 均持久化在 docker 卷 |

内存账：MySQL ~400M + 后端 ~300M + 前端 ~120M + 系统占用，2G 内存 + **1.9G swap**（镜像自带）可平稳运行；构建期靠 swap 兜底。

## 二、首次部署步骤（复现手册）

1. **Docker 镜像加速**（国内无法直连 Docker Hub）：
   ```bash
   sudo tee /etc/docker/daemon.json <<'EOF'
   {"registry-mirrors": ["https://docker.m.daocloud.io", "https://docker.1ms.run"]}
   EOF
   sudo systemctl restart docker
   ```
2. **上传代码**。实测服务器直连 GitHub 超时，采用本机打包上传（`git archive` 860KB）：
   ```bash
   # 本机：git archive --format=tar.gz -o repo.tar.gz main，scp/sftp 至服务器
   sudo mkdir -p /opt/ecom-agent && tar -xzf repo.tar.gz -C /opt/ecom-agent
   ```
3. **写两个 env 文件**（均不入库）：
   - `/opt/ecom-agent/.env`（compose 插值）：
     `EMBEDDING_PRELOAD=false`、`NEXT_PUBLIC_API_BASE_URL=http://<IP>:8000`、`CORS_EXTRA_ORIGINS=http://<IP>:3000`、`MYSQL_ROOT_PASSWORD=<强密码>`
   - `/opt/ecom-agent/backend/.env`（运行时）：`OPENAI_*`（LLM）+ `EMBEDDING_PROVIDER=openai / EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1 / EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5 / EMBEDDING_DIM=1024 / EMBEDDING_WARMUP=false`
4. **构建并启动**：
   ```bash
   cd /opt/ecom-agent && sudo docker compose build && sudo docker compose up -d
   ```
   首启自动：MySQL 建库（01-schema/02-seed-users/03-demo 顺序）→ 后端启动前置脚本等 MySQL → qdrant 卷为空则调 API 全量重建向量索引（79 文件 → 420 向量，约 12s）→ uvicorn。
5. **防火墙**：控制台放通 TCP `3000,8000`（来源全部 IPv4，演示用途）。

## 三、实际踩坑记录（按时间线）

| # | 现象 | 根因 | 解法 |
|---|---|---|---|
| 1 | `docker pull` 超时 | 国内封锁 Docker Hub | daemon.json 配 daocloud/1ms 双镜像源 |
| 2 | `git ls-remote github.com` 无响应 | 服务器侧 GitHub 不通 | 改走本机 `git archive` 上传（860KB，几秒） |
| 3 | 索引重建报 `code 20015 参数无效`，79 文件仅入库 52 | 硅基流动 bge 系 API 单条输入上限 512 token，**父块 800 字符超限，整批（≤32 条）被连带拒绝**；本地 sentence-transformers 同为 512 token 但会自动截断，故本地从未暴露 | `embedding_provider.py`：API 侧对超长输入截断至 450 字符（对齐本地截断语义；截断只影响父块尾部，父块不参与检索命中）+ 整批失败降级为逐条请求隔离坏条目（commit `f07c553`） |
| 4 | 前端静态图 404 | Dockerfile runner 漏拷 `public/` | 补 `COPY --from=builder /app/public`（commit `b2e6e0e`） |
| 5 | 服务器登录密码遗失 | 创建时自动生成未保存 | 控制台"重置密码"在线重置（无需关机） |

## 四、运维命令速查（服务器上）

```bash
cd /opt/ecom-agent
sudo docker compose ps                 # 状态
sudo docker compose logs -f backend    # 跟日志（索引重建/审计都在里面）
sudo docker compose restart backend    # 重启后端
sudo docker compose down               # 停止（数据卷保留）
# 代码更新（GitHub 不通，走本机上传覆盖后）：
sudo docker compose build backend && sudo docker compose up -d backend
# 清空向量索引并重建（解决索引损坏/切换 Embedding 模型）：
sudo docker compose stop backend
sudo docker volume rm ecom-agent_qdrant_data
sudo docker compose up -d backend      # 启动时自动全量重建
# 重置演示业务数据（订单/退款/投诉回初始态）：
sudo docker compose exec -T db mysql -uroot -p<密码> ai_agent_commerce_demo < backend/database/demo_minimal_cn.sql
```

## 五、安全边界（如实声明）

- **演示级鉴权**：登录 token 即 user_id 明文、API 无鉴权中间件，公网部署意味着任何人都可读写演示库——仅适合求职演示，不可承载真实数据；
- 服务器 SSH 已改为强密码登录（ubuntu 用户），**建议后续改 SSH 密钥并禁用密码**；
- 两份 `.env` 含 LLM/Embedding 密钥，仅存服务器，未入 git；
- 演示数据可随时重置（见上），不要在公网环境录入真实个人信息。
