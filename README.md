# 云雾酒馆 AI Chat & RPG

一款可以本地部署和游玩的 AI 聊天与文字冒险游戏应用。

## 📖 项目简介

云雾酒馆是一个集成 AI 聊天与角色扮演游戏的 Web 应用，用户可以：

- 与多种智能体进行对话互动
- 探索不同的游戏世界和剧情
- 创建和管理游戏会话
- 观看其他玩家的游戏过程
- 提供反馈和评价

## 🛠️ 技术栈

- **后端**: Flask 3.x
- **数据库**: SQLite
- **前端**: Vanilla JavaScript + CSS3
- **打包工具**: PyInstaller

## 📦 当前版本

**v2.1.5**

> 代码逻辑分类重组完成：5个源码文件添加统一分区注释（合计64区块），提升代码可维护性。

## 🚀 快速开始

### 环境要求

- Python 3.8 或更高版本
- 网络连接（用于调用 AI API）

### 方式一：一键启动（推荐）

```bash
# Windows
双击根目录的 启动.bat
```

启动脚本会优先检测 `release/tavern.exe`，存在则启动发布版，否则回退到 Python 开发版。

### 方式二：Python 直接运行

```bash
cd src/backend
pip install -r requirements.txt
python app.py
```

### 访问应用

启动后访问：**http://localhost:9000**

默认管理员账户：`admin / 123456`

> **注意**: 默认使用公开 AI API，无需配置 API Key 即可体验。如需使用自有 API，在 `src/backend/.env` 中配置。

## 📁 项目结构

```
ai_chat/
├── 启动.bat                      # 🚀 根目录一键启动脚本（v2.1.5新增）
├── .gitignore                    # Git 忽略规则
├── scripts/                      # 🛠️ 工具脚本（8个）
│   ├── build.bat                 # 构建脚本
│   ├── bump_version.py           # 版本号递增
│   ├── bump_version.ps1          # 版本号递增（PS版）
│   ├── check_user.py             # 用户查询
│   ├── launch.py                 # 快速启动
│   ├── reset_db.py               # 数据库重置
│   ├── start_fresh.py            # 全新开始
│   └── test_rpg.py               # RPG 测试
├── src/                          # 📦 源码目录 ⭐
│   └── backend/                  # 🔧 Flask应用
│       ├── app.py                # ⭐ 主应用（约2634行，22区块分区注释）
│       ├── .env                  # 环境变量
│       ├── requirements.txt      # Python依赖
│       ├── version.json          # 版本号
│       ├── CHANGELOG.json        # 变更日志
│       ├── agents.json           # 智能体数据
│       ├── feedback.json         # 反馈数据
│       ├── rpg_sessions.json     # RPG会话
│       ├── worldbooks.json       # 世界书
│       ├── world_ratings.json    # 世界评价
│       ├── world_submissions.json# 世界投稿
│       ├── usage_log.json        # 使用日志
│       ├── instance/             # SQLite数据库
│       ├── static/               # 前端静态资源
│       │   ├── script.js         # 前端主逻辑（约2654行，18区块分区注释）
│       │   ├── style.css         # 样式表（约2600行，9区块分区注释）
│       │   ├── feedback.js       # 反馈模块（约391行，9区块分区注释）
│       │   ├── feedback.css      # 反馈页样式（约352行，6区块分区注释）
│       │   └── reward_qrcode.png # 打赏二维码
│       └── templates/            # Jinja2模板
│           ├── index.html        # 主页面（约580行）
│           ├── feedback.html     # 反馈页（119行）
│           ├── dashboard.html    # 管理面板（297行）
│           └── spectate.html     # 观战页（67行）
├── tavern/                       # 🚀 开发启动入口（仅保留启动脚本+数据库备份）
│   ├── .env                      # 环境变量
│   ├── start.bat                 # 启动脚本
│   ├── start.ps1                 # 启动脚本（PS版）
│   └── instance/tavern.db.bak    # 数据库备份
└── release/                      # 📦 发布版（含tavern.exe）
    ├── tavern.exe                # 可执行文件（16MB）
    ├── .env / *.json / scripts   # 同步文件
    ├── static/                   # 同步前端资源
    └── templates/                # 同步模板
```

> **docs/ 目录**: 本地开发文档，包含项目架构、问题报告、代码索引等，**禁止同步到 GitHub**。
> **.trae/ 目录**: AI 代理内部工作目录，**禁止同步到 GitHub**。

## 🎮 使用说明

### 1. 首页

进入首页后，选择智能体和游戏世界，输入角色名开始对话或游戏。

### 2. 对话功能

- 支持多轮对话
- 实时显示 AI 回复
- 可以切换不同的智能体和模型

### 3. 游戏世界

- 提供多个预设的游戏世界
- 每个世界有独特的剧情和角色
- 支持自由探索和剧情推进

### 4. 观战模式

- 可以观看其他玩家的游戏过程
- 实时同步游戏状态

### 5. 反馈系统

- 可以对游戏体验进行评价
- 提交建议和问题

## 📝 开发规则

### 修改入口

- **唯一入口**: 所有代码修改必须在 `src/backend/` 目录进行
- **同步规则**: 修改完成后同步到 `release/`（前端文件及数据文件）
- **禁止操作**: 直接在 `release/` 中修改代码

### 关键约束

- 端口必须为 9000
- JSON_AS_ASCII = False
- JSON 文件操作必须使用 threading.Lock() 保护
- 所有 POST/PUT/DELETE 请求必须包含 CSRF token（登录/注册除外）

### 代码分区规范

项目采用统一的分区注释标准，所有源码文件分为多个功能区块：

| 文件 | 区块数 | 说明 |
|------|:------:|------|
| app.py | 22 | Flask 主应用 |
| script.js | 18 | 前端主逻辑 |
| style.css | 9 | 样式表 |
| feedback.js | 9 | 反馈模块 |
| feedback.css | 6 | 反馈页样式 |

## 📄 许可证

MIT License
