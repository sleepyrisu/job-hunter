# AI Job Hunter

AI 驱动的求职助手：自动抓取招聘信息、按你的简历评估匹配度、生成求职信，并通过网页仪表盘实时查看进度。

上传简历到仪表盘后会自动开始搜索匹配的工作，无需手动点击"开始"。

## 核心功能

- **简历即配置**：上传 PDF / Word / Markdown / TXT 简历，自动提取技能、关键词、地点偏好并写回 `settings.json`；上传完成后立即自动启动后台搜索流程
- **多平台抓取**：Indeed、LinkedIn、JobStreet（RSS / jobspy / 浏览器代理三种后端）
- **多维度匹配评分**：技能权重、学历要求、经验年限、薪资解析、公司风险、时效性、地点偏好（可插拔规则引擎）
- **求职信生成**：为高匹配岗位批量生成 Tailored Cover Letter
- **后台定时调度**：可按小时自动重复搜索（`/api/scheduler`）
- **申请跟踪**：记录已投递 / 面试 / 录用 / 拒绝状态
- **本地仪表盘**：Flask Web UI，实时进度、一键运行 / 停止 / 重置
- **通知**：邮件 + Telegram 告警，新匹配岗位即时推送

## 快速开始

```bash
# 1. 配置环境变量（API 密钥、DASHBOARD_TOKEN）
copy .env.example .env

# 2. 安装依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt   # 仅开发/测试需要

# 3. 可选：安装 Playwright 浏览器（浏览器代理抓取才需要）
playwright install chromium

# 4. 启动
python app.py
```

打开 <http://localhost:8888>。若设置了 `DASHBOARD_TOKEN`，首次访问会要求输入访问密码。

> 完全离线可用：默认 `use_ai=false`，无需任何 AI API 密钥即可完成抓取 + 规则评分 + 求职信基础流程。

## 工作流程

```
上传简历 (resume.pdf/.docx/.md)
      │
      ▼
resume_parser ──► resume_scanner ──► settings.json（关键词/地点）
      │                                    │
      ▼                                    ▼
      └────────► main.run_job_hunter() ◄── 或 仪表盘 [运行] / 定时调度
                     │
      ┌──────────────┼───────────────┐
      ▼              ▼               ▼
 jobspy/RSS   规则引擎评分     AI 评分(可选)
      │              │               │
      ▼              ▼               ▼
   去重/入库  ──► jobs.db ──► 求职信生成 ──► 邮件/Telegram 告警
```

## 评分机制

每个岗位按 0-100 打分（详见 `rule_filter.py`、`score_adjuster.py`）：

- 技能匹配（关键词加权，区分 programming / framework / data / cloud / RPA / AI）
- 学历要求（欢迎 Diploma/应届 vs 要求 Degree）
- 经验年限（要求 3+ 年惩罚）
- 薪资解析与对比
- 公司风险（诈骗/黑名单检测）
- 职位时效（30 天窗口）
- 地点与 MNC/KL 调岗偏好

## 架构

```
app.py                     入口（app factory + 启动逻辑，gunicorn 兼容）
webapp/
  __init__.py              create_app() 工厂：蓝图注册 + 安全中间件
  security.py              Token 认证 / CSRF / 限流 / 安全响应头
  state.py                 运行状态 + 后台 runner + 调度器
  routes/                  蓝图：dashboard / jobs / settings / run / scheduler / browser / resume
config.py                  配置加载（settings.json + .env 覆盖 + 校验告警）
models.py                  领域模型（Job / Application / UserProfile）+ 校验
repositories.py            仓储层（JobRepository / UserProfileRepository）
schema_migrations.py       SQLite schema 迁移（PRAGMA user_version）
database.py                数据库操作
rule_filter.py / score_adjuster.py / resume_parser.py ...   评分/解析核心
tests/                     232 个测试，覆盖率 90%+
```

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/` , `/dashboard.html` | 仪表盘页面 |
| GET  | `/api/jobs` | 全部岗位 |
| GET  | `/api/jobs/stats` | 申请状态统计 |
| POST | `/api/jobs/status` | 更新岗位状态（JSON body: `{id, status}`） |
| POST | `/api/jobs/delete` | 删除岗位（JSON body: `{id}`，支持 URL 型 id） |
| POST | `/api/jobs/delete-batch` | 批量删除（`{ids: []}`） |
| POST | `/api/jobs/clear-all` | 清空 |
| POST | `/api/upload-resume` | 上传简历（自动启动搜索） |
| POST | `/api/resume-scan` | 用 agy 重新提取关键词 |
| POST | `/api/run` | 后台开始一次完整搜索 |
| GET  | `/api/status` | 当前运行状态 |
| POST | `/api/reset` | 重置状态为 idle |
| GET/POST | `/api/settings` | 读取 / 深合并保存设置 |
| GET/POST | `/api/scheduler` | 读取 / 设置定时调度 |
| POST | `/api/browser/start` , `/api/browser/stop` | 浏览器代理抓取控制 |
| GET  | `/api/applications` | 申请记录 |

完整细节见 [docs/API.md](docs/API.md)。

## 安全

- 可选 `DASHBOARD_TOKEN` 认证（常量时间比较 `hmac.compare_digest`）
- 变更类请求 CSRF 校验（自定义请求头）
- 60 次/分钟 内存限流
- 安全响应头（CSP、`X-Frame-Options: DENY`、nosniff、HSTS、no-store）
- 上传白名单扩展名 + 16MB 上限 + 文件名防路径穿越 + 超长内容截断
- 生产用 `SECRET_KEY` 覆盖默认值
- 测试与 CI 内 `DASHBOARD_TOKEN` 使用固定测试值

## 测试与 CI

```bash
pytest                                   # 232 tests
pytest --cov=webapp --cov=... --cov-report=term-missing   # 覆盖率 ≥90%
ruff check .                             # E,F,I,UP,B,SIM 全规则
mypy webapp models.py ...                # 类型检查（核心模块）
bandit -c pyproject.toml webapp app.py ...  # 安全扫描
```

CI（`.github/workflows/ci.yml`）：Python 3.11/3.12 矩阵，ruff + mypy + bandit + pytest/覆盖率门禁（`fail_under = 90`）。

## 部署（Render.com / Docker）

- **Render**：Build `pip install -r requirements.txt && playwright install chromium --with-deps`；Start `gunicorn --bind 0.0.0.0:8888 --workers 2 --threads 4 app:app`
- **Docker**：`docker build -t ai-job-hunter .`（见 `Dockerfile`）

## 文档目录

- `docs/API.md` — API 参考
- `docs/ARCHITECTURE.md` — 架构与数据流
- `docs/SECURITY.md` — 安全模型与威胁说明

## 致谢

- 多维度评分框架的灵感来自 [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)（MIT License）

## 免责声明

- 本工具面向个人求职使用。自动抓取 LinkedIn / Indeed / JobStreet 等平台可能违反其服务条款，请控制抓取频率并自行承担风险。
- 本项目仅依赖宽松许可证（MIT / BSD / Apache）的开源库。

## License

MIT
