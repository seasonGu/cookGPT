# cookGPT

菜谱问答应用:菜谱数据(腾讯云 MySQL)→ 向量检索(Milvus Lite)→ 问答。目前已完成:登录注册 + 问答页前端(检索/生成待接入)。

## 目录结构

| 目录 | 说明 |
| --- | --- |
| `backend/` | FastAPI(Python 3.12):JWT 认证 + SQLite 用户库 + 问答占位接口 |
| `frontend/` | Vue 3 + Vite:登录页、问答页 |
| `recipes.sql` / `generate_recipes.py` | 菜谱表结构与 10000 条中文菜谱测试数据 |

## 启动开发环境

```bash
# 0. 配置环境变量(导入向量时才需要 MySQL/API key)
cp .env.example .env && vim .env

# 1. 后端(默认 8000 端口,被占用时用 COOKGPT_PORT 覆盖)
uv run python main.py

# 2. 前端(默认代理 /api → 127.0.0.1:8000,后端换了端口用 VITE_API_TARGET 覆盖)
cd frontend && npm install && npm run dev
# 后端在 8001 时:
# VITE_API_TARGET=http://127.0.0.1:8001 npm run dev
```

浏览器打开 http://localhost:5173,演示账号 `admin / admin123456`(也可在登录页直接注册)。

## 技术选型(已定)

- **Embedding**:bge-m3 API(硅基流动),1024 维 —— 2GB 服务器零内存开销
- **向量库**:Milvus Lite(进程内,~200MB;Standalone 最低要 4GB,跑不动)
- **Rerank**:暂不上,后续需要走 API
- **生成**:DeepSeek-V4 官方 API(默认 `deepseek-v4-flash`,SSE 流式返回);embedding 在硅基流动、LLM 在 DeepSeek 官方,两个 key 分开
- **认证**:JWT(Bearer)+ stdlib pbkdf2 密码哈希,用户存本地 SQLite

## 全量导入菜谱向量(已完成)

MySQL 10k 菜谱 → bge-m3 向量 → Milvus Lite,一次批量任务:

```bash
uv run python -m backend.scripts.import_recipes --full            # 全量导入
uv run python -m backend.scripts.import_recipes --limit 50        # 冒烟:只导前 50 条
uv run python -m backend.scripts.import_recipes --start-id 5001   # 断点续跑
uv run python -m backend.scripts.import_recipes --fake-embed      # 联调管道(随机向量,不调 API)
```

- 按菜谱 id **upsert 幂等**,中断重跑不会产生重复
- 流式分批:MySQL 每次读 500 行、API 每次 32 条,2GB 服务器内存平稳
- 429 限速自动指数退避重试;跑完自带检索冒烟测试
- **注意**:Milvus Lite 是单进程嵌入库,导入任务必须和应用服务**串行**——应用停着时跑导入,跑完再起应用

### 云端部署执行顺序

```bash
uv sync                                                       # 装依赖
# 配好 .env(MySQL 内网地址 / SILICONFLOW_API_KEY / COOKGPT_SECRET)
uv run python -m backend.scripts.import_recipes --full         # 1. 先导入(应用未启动)
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 # 2. 再起应用(systemd 托管)
```

两个坑:① `COOKGPT_MILVUS_DIR` 必须挂持久盘,否则重启丢库要重导;② 查询时也要调 embedding API,服务器需出站外网、key 常驻环境变量。

## 问答 Agent 架构(已完成,LangGraph)

`/api/chat` 每次提问跑一张四节点图(`backend/app/agent.py`),检索封装为工具(`backend/app/tools.py`):

```
parse ──> retrieve ──> critique ──(通过/重试耗尽)──> generate ──> END
(意图解析)   (检索工具)    (搭配审核)   │未通过且未耗尽      (最终生成,流式)
                                      └──────────> retrieve(带审核反馈重新检索)
```

| 节点 | 职责 |
| --- | --- |
| parse | LLM 把口语需求解析成结构化约束(检索词 + 忌口 + 备注),如「来大姨妈」→「温补暖身汤」 |
| retrieve | 调用 `search_recipes_tool`:bge-m3 向量召回 + 忌口标量过滤 + 菜名去重 + MySQL 取完整菜谱;审核反馈会并入下一轮检索 |
| critique | LLM 充当主厨/营养师审核菜单(忌口冲突硬约束、荤素搭配、多样性),不通过则带反馈重试,最多 2 次防死循环 |
| generate | 把审核通过的菜单转成有情绪价值的回答,**流式生成器**返回给接口层推流 |

- 所有 LLM 调用 `thinking: disabled`(DeepSeek V4 思考会挤占 max_tokens 导致空回复,已实测踩坑)
- 前端增量渲染 + 多轮上下文(最近 3 轮);任一环节失败以流内 `{"error"}` 事件返回
- Milvus `load_collection` 是异步的,`ensure_collection` 会等待加载完成,避免进程重启后首次检索为空

## 对话历史(已完成)

- 左侧会话栏:新建/切换/删除,标题取第一句提问
- 对话记录存**腾讯云 MySQL**(`conversation` / `message` 两表,启动时自动建表)
- `/api/chat` 不传 `conversation_id` 时后端自动建会话;多轮上下文优先读库里的历史
- 会话按用户名隔离,他人不可见/不可删

⚠️ 开发备忘:pymysql 的 `with conn:` 退出时**不提交事务**(1.2.0 实测回滚),所有 MySQL 写操作必须走 `backend/app/mysql.py` 的 `get_conn`(已封装 commit/rollback/close)。

## 快速部署到腾讯云(2GB 服务器)

### 方式 A:Docker(推荐,最简单)

单容器单端口,天然符合 Milvus Lite 单进程约束;实测容器内存约 140MB,2GB 服务器富余。

```bash
# 1. 服务器准备(腾讯云轻量选「Docker CE」应用镜像,或手动装 Docker)
sudo mkdir -p /opt/cookgpt && sudo chown -R $(whoami) /opt/cookgpt

# 2. 上传项目到 /opt/cookgpt/cookGPT(代码 + .env;密钥在 .env 里,由 compose 运行时注入,不进镜像)
rsync -az --exclude .venv --exclude frontend/node_modules --exclude data ./ ubuntu@服务器IP:/opt/cookgpt/cookGPT/

# 3. 已有向量数据拷入项目 data 目录(compose 挂载 ./data),10k 条免重导
ssh ubuntu@服务器IP "mkdir -p /opt/cookgpt/cookGPT/data"
scp -r backend/data/* ubuntu@服务器IP:/opt/cookgpt/cookGPT/data/

# 4. 构建并启动
ssh ubuntu@服务器IP "cd /opt/cookgpt/cookGPT && docker compose up -d --build"
docker compose logs -f   # 看日志
```

- 服务器在国内,给 Docker 配镜像加速(否则拉不动基础镜像):
  `/etc/docker/daemon.json` → `{"registry-mirrors": ["https://docker.m.daocloud.io"]}` 然后 `systemctl restart docker`
- 腾讯云控制台安全组放行 TCP 8000 → 访问 `http://服务器IP:8000`
- 更新:`rsync` 重传后 `docker compose up -d --build`

### 方式 B:裸机 + systemd

```bash
# 1. 服务器一次性准备(腾讯云轻量 Ubuntu):
ssh ubuntu@服务器IP "sudo mkdir -p /data/cookgpt && sudo chown -R \$(whoami) /data/cookgpt"

# 2. 本机执行一键部署(首次部署与日常更新通用):
SERVER=ubuntu@服务器IP ./deploy/deploy.sh

# 3. 服务器上改一次 .env,向量库指向持久盘:
ssh ubuntu@服务器IP "sed -i 's|# COOKGPT_MILVUS_DIR=.*|COOKGPT_MILVUS_DIR=/data/cookgpt/milvus|' /opt/cookgpt/.env \
  && sudo systemctl restart cookgpt"
```

- **MySQL**:同一台腾讯云 MySQL,注意它的安全组/白名单要放行服务器出口 IP(你本机已能连,新服务器 IP 也要加)
- **日志**:`ssh ubuntu@服务器IP "sudo journalctl -u cookgpt -f"`
- **systemd 文件**:`deploy/cookgpt.service`(User 字段按实际用户名改;`--workers 1` 是硬性要求)

## 待接入(TODO)

- 菜谱新增/变更后的增量同步(现阶段只做全量)

---

## 菜谱数据部分

提供菜谱表结构与 10000 条随机中文菜谱测试数据，可直接导入腾讯云 MySQL（TencentDB / TDSQL-C）。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `recipes.sql` | 建表语句 + 10000 条菜谱数据（每 500 行一条批量 INSERT，约 10 MB） |
| `generate_recipes.py` | 数据生成脚本（纯标准库，可重复运行 / 自定义条数） |

## 表结构

单表 `recipe`，字段与需求一一对应：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT UNSIGNED PK | 食谱ID |
| `name` | VARCHAR(128) | 食谱名称 |
| `description` | TEXT | 食谱说明 |
| `ingredients` | JSON | 食材：`[{"name": "五花肉", "amount": "500克"}, ...]` |
| `steps` | JSON | 步骤：`["步骤1", "步骤2", ...]` |
| `dietary` | VARCHAR(255) | 忌口（逗号分隔，如 `海鲜、辛辣`，无则为 `无`） |
| `tags` | VARCHAR(255) | 标签（逗号分隔，如 `麻辣,简单,肉菜,川菜,下饭菜`） |
| `servings` | TINYINT UNSIGNED | 适用人数（1-6） |
| `image_url` | VARCHAR(512) | 图片（当前为占位地址，需替换） |
| `nutrition` | JSON | 营养成分（每 100 克）：热量/蛋白质/脂肪/碳水/钠 |
| `remark` | VARCHAR(255) | 备注 |
| `created_at` / `updated_at` | DATETIME | 创建/更新时间 |

引擎 InnoDB，字符集 utf8mb4。

## 重新生成数据

```bash
uv run python generate_recipes.py          # 生成 10000 条
uv run python generate_recipes.py 50000    # 自定义条数
```

## 部署到腾讯云

### 1. 创建数据库实例

腾讯云控制台 → 云数据库 MySQL（或 TDSQL-C MySQL 版），建议：

- 版本 **MySQL 5.7 或 8.0**（`ingredients`/`steps`/`nutrition` 用了 JSON 列，需要 5.7+）
- 字符集默认即可（建表语句已显式指定 `utf8mb4`）
- 实例规格按需选择（1 核 1 GB 即可满足这 1 万条数据）

### 2. 导入数据（任选其一）

**方式 A：控制台导入（最简单）**

实例 → 数据库管理 → 导入，上传 `recipes.sql`，选择目标库执行。

**方式 B：mysql 命令行（推荐，最快）**

```bash
mysql -h <实例内网地址> -P 3306 -u <用户名> -p <数据库名> < recipes.sql
```

> 外网访问需先在控制台开启实例外网地址并配置安全组放行 3306；
> 生产环境建议用 DTS 或从同 VPC 的云服务器导入。

**方式 C：图形化工具**

Navicat / DataGrip / 腾讯云数据库管理工具连接后直接运行 SQL 文件。

### 3. 导入后验证

```sql
SELECT COUNT(*) FROM recipe;            -- 应为 10000
SELECT COUNT(DISTINCT name) FROM recipe; -- 约 6000 个不重名菜名
```

## 常用查询示例

```sql
-- 按标签查（FIND_IN_SET 精确匹配单个标签）
SELECT * FROM recipe WHERE FIND_IN_SET('减脂餐', tags) LIMIT 20;

-- 按忌口过滤（不含海鲜的菜）
SELECT * FROM recipe WHERE dietary NOT LIKE '%海鲜%';

-- JSON 查询：取第一样食材
SELECT name, ingredients->>'$[0].name' AS 主料 FROM recipe WHERE id = 1;

-- 按热量排序
SELECT name, nutrition->>'$.热量_kcal' AS kcal
FROM recipe ORDER BY CAST(nutrition->>'$.热量_kcal' AS UNSIGNED) LIMIT 10;
```

## 注意事项

- **图片**：`image_url` 目前是 `https://cdn.example.com/recipes/xxxxx.jpg` 占位地址，上线前替换为真实图片（如腾讯云 COS 地址），可执行：
  `UPDATE recipe SET image_url = REPLACE(image_url, 'https://cdn.example.com', '<你的COS域名>');`
- **JSON 列**：MySQL 5.6 及以下不支持，需要时把 JSON 列改成 TEXT 再导入。
- 数据为随机生成的测试数据，菜名/步骤仅供参考，不保证烹饪上的严谨性。
