# 云雾酒馆 AI Chat & RPG

> 一款可以本地部署和游玩的 AI 聊天与跑团应用，需要自行配置 API Key。

## 🚀 快速开始

### 环境要求
- Python 3.8+
- Git（用于代码同步）

### 安装依赖
```bash
cd src/backend
pip install -r requirements.txt
```

### 配置环境变量
编辑 `src/backend/.env`：
```env
API_KEY=your_api_key_here
ADMIN_PASSWORD=your_admin_password
```

### 启动应用
```bash
# 开发模式
python src/backend/app.py

# 或使用启动脚本
.\tavern\start.bat
```

访问 http://localhost:9000

---

## 📐 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Flask 2.x |
| 数据库 | SQLite |
| 前端 | Vanilla JS + CSS3 |
| 打包 | PyInstaller |
| 版本控制 | Git |

---

## 🔧 开发规范

### 1. Git 同步规则（强制）

> **每次修改后必须执行以下操作**，确保代码及时同步到远程仓库。

#### 修改流程
```bash
# 1. 修改代码后，先同步 release/ 目录
copy src/backend/static/* release/static/
copy src/backend/templates/* release/templates/
copy src/backend/app.py release/app.py

# 2. 查看变更
git status

# 3. 添加变更
git add .

# 4. 提交（必须包含版本号和修改说明）
git commit -m "v2.x.x: 描述你的修改内容"

# 5. 推送
git push origin main
```

#### 提交信息规范
```
v2.x.x: 修改类型 - 具体描述

示例:
v2.0.6: fix - 修复C3玩家名存储型XSS
v2.0.7: feat - 添加AI行为评估脚本
v2.0.8: refactor - 清理无用代码
```

#### 分支策略
- `main`：主分支，保持稳定可运行状态
- 开发直接在 `main` 分支进行，确保每次提交都是可运行的

### 2. 代码修改规范

#### 修改入口
- **唯一入口**: 所有代码修改必须在 `src/backend/` 目录进行
- **同步规则**: 修改完成后同步到 `release/`（前端文件及数据文件）
- **禁止操作**: 直接在 `release/` 中修改代码

#### 关键约束
- 端口必须为 9000
- JSON_AS_ASCII = False（支持中文）
- JSON 文件操作必须使用 `threading.Lock()` 保护
- 异常处理必须使用 `except Exception as e:` 而非裸 `except:`

#### 修改后检查清单
- [ ] `version.json` 和 `CHANGELOG.json` 在 `src/backend/`、`release/` 间是否一致
- [ ] 新增的 API 路由是否有正确的认证装饰器
- [ ] 新增的 API 返回值中是否包含 `api_key` 等敏感字段（应过滤）
- [ ] 文档更新（问题反馈与报告.md → 项目架构和相关规范.md → 项目记忆.md）
- [ ] 运行 `python docs/AI行为评估脚本.py --auto` 进行自评

### 3. 安全规范

- **XSS 防护**: 所有用户输入必须通过 `escapeHtml()` 转义
- **SQL 注入**: 使用参数化查询，禁止字符串拼接
- **敏感信息**: API Key、密码等敏感信息必须过滤，禁止明文返回
- **SSRF 防护**: URL 参数必须通过 `is_safe_url()` 校验
- **CSRF 防护**: 所有 POST 请求必须验证会话

### 4. 文档同步规则

每次修改后必须按以下顺序更新文档：

1. **问题反馈与报告.md** - 记录新发现的问题或标记已修复的问题
2. **项目架构和相关规范.md** - 更新版本历史和问题统计
3. **项目记忆.md** - 更新变更摘要、待办优先级、已知风险
4. **README.md** - （如有必要）更新使用说明

---

## 📁 项目结构

```
ai_chat/
├── docs/                      # 文档
│   ├── 项目架构和相关规范.md    # 架构规范（必读）
│   ├── 问题反馈与报告.md        # 问题清单
│   ├── 项目记忆.md             # AI 共同记忆
│   ├── 优化建议.md             # 优化建议（需审批）
│   └── AI行为评估脚本.py        # AI 行为评估工具
├── scripts/                   # 工具脚本
├── src/                       # 源码
│   └── backend/               # Flask 应用（唯一修改入口）
│       ├── app.py             # 主应用
│       ├── static/            # 前端资源
│       ├── templates/         # Jinja2 模板
│       └── instance/          # SQLite 数据库
├── release/                   # 发布版（自动同步）
└── tavern/                    # 开发启动入口
```

---

## 📋 AI 行为评估

AI 在执行任务前后必须阅读并运行 `docs/AI行为评估脚本.py`：

```bash
# 自动评估
python docs/AI行为评估脚本.py --auto

# 交互式评估
python docs/AI行为评估脚本.py

# 生成报告
python docs/AI行为评估脚本.py --report
```

评估维度：
- 规范遵循（15%）
- 代码质量（15%）
- 安全意识（20%）
- 问题处理（15%）
- 文档同步（10%）
- 任务完成度（10%）
- 错误处理（10%）
- 效率优化（5%）

---

## 🔒 安全提醒

1. 永远不要将 `.env` 文件提交到 Git（已在 `.gitignore` 中忽略）
2. 定期更换 API Key
3. 仅允许管理员账户访问后台功能
4. 注意过滤用户输入，防止 XSS 和 SQL 注入

---

## 📄 许可证

MIT License - 详见 LICENSE 文件