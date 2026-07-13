# 云雾酒馆 AI Chat & RPG

一款可以本地部署和游玩的 AI 聊天与文字冒险游戏应用。

## 📖 项目简介

云雾酒馆是一个集成 AI 聊天与角色扮演游戏的 Web 应用，用户可以：

- 与多种智能体进行对话互动
- 探索 17 个不同主题的游戏世界和剧情
- 创建和管理游戏会话
- 观看其他玩家的游戏过程
- 提供反馈和评价
- 体验 Three.js 3D 视觉效果（粒子背景、3D 骰子等）

## 🛠️ 技术栈

- **后端**: Flask 3.x + Flask-SQLAlchemy + Flask-Login
- **数据库**: SQLite（带连接池配置）
- **前端**: Vanilla JavaScript (ES Modules) + CSS3
- **3D 效果**: Three.js（粒子系统、装饰环、骰子动画）
- **打包工具**: PyInstaller
- **安全**: CSRF 防护、速率限制、Fernet 加密、secrets 随机数

## 📦 当前版本

**v2.2.2.1**

> 更新内容：
> - Three.js 3D 效果集成：粒子背景、登录装饰环、消息粒子特效、主题化背景、3D 骰子动画
> - 世界书扩展：从 7 个扩展到 17 个（西游、武侠、末日、蒸汽朋克、仙侠等）
> - 性能优化：admin_stats 添加时间范围过滤（默认 30 天），避免全表扫描
> - 安全修复：骰子使用 `secrets.randbelow` 替代 `random.randint`
> - 数据一致性：Feedback 用户名同步更新，修复改名后显示旧名问题
> - Bug 修复：聊天界面无响应、登录取消问题、session 自动失效问题

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

可以通过樱花内网穿透，共享给他人游玩，这种技术方式比较简单，而且相对好用。

## 📁 项目结构

```
ai_chat/
├── 启动.bat                      # 🚀 根目录一键启动脚本
├── README.md                     # 📖 项目说明文档
├── .gitignore                    # Git 忽略规则
├── scripts/                      # 🛠️ 工具脚本（6个）
│   ├── build.bat                 # 构建发布版脚本
│   ├── bump_version.py           # 版本号递增管理
│   ├── release_start.bat         # 发布版启动脚本（用于release/）
│   ├── release_start.ps1         # 发布版启动脚本（PS版）
│   ├── reset_db.py               # 数据库重置
│   └── test_rpg.py               # RPG功能测试
├── trea_html/                    # 🎨 交互式体验版（单文件HTML）
│   └── 云雾酒馆交互体验.html      # 可体验的HTML演示文件
├── src/                          # 📦 源码目录 ⭐
│   └── backend/                  # 🔧 Flask应用
│       ├── app.py                # ⭐ 主应用（约3436行，22区块分区注释）
│       ├── config.py             # ⚙️ 配置管理（数据库连接池、环境变量）
│       ├── models.py             # 📊 12个SQLAlchemy数据模型
│       ├── state.py              # 📡 全局状态（rpg_sessions、锁保护）
│       ├── .env                  # 环境变量
│       ├── requirements.txt      # Python依赖（11个包）
│       ├── version.json          # 版本号
│       ├── CHANGELOG.json        # 变更日志
│       ├── instance/             # SQLite数据库
│       ├── blueprints/           # 📦 5个功能模块
│       │   ├── auth.py           # 🔐 认证（登录/注册/改密/速率限制）
│       │   ├── chat.py           # 💬 聊天（智能体/消息/历史/速率限制）
│       │   ├── rpg.py            # ⚔️ 跑团（世界书/开局/行动/SSE/观战）
│       │   ├── admin.py          # 📊 管理后台（用户/统计/配置）
│       │   └── feedback.py       # 📝 反馈（提交/列表/管理）
│       ├── utils/                # 🛠️ 工具模块
│       │   ├── ai_service.py     # 🤖 AI调用封装（模型配置、积分扣减、骰子）
│       │   ├── json_io.py        # 📄 JSON文件操作（带线程锁）
│       │   └── security.py       # 🔒 安全工具（加密/CSRF/速率限制）
│       ├── static/               # 🎨 前端静态资源（17个JS模块）
│       │   ├── app.js            # 🚪 ES Module 入口（DOMContentLoaded 初始化）
│       │   ├── state.js          # 📡 共享状态对象
│       │   ├── utils.js          # 🛠️ 通用工具函数（$ / escapeHtml / toast 等）
│       │   ├── api.js            # 🔌 API 调用层（JSON/SSE流式）
│       │   ├── renderer.js       # 📝 Markdown 渲染、状态/故事线渲染
│       │   ├── auth.js           # 🔐 认证 UI（登录/注册/版本/退出）
│       │   ├── chat.js           # 💬 聊天模式（智能体/消息/会话）
│       │   ├── rpg.js            # ⚔️ 跑团核心（世界书/开局/行动/围观）
│       │   ├── agent-ui.js       # 🤖 智能体管理 UI
│       │   ├── world-ui.js       # 🌍 世界书管理 UI
│       │   ├── admin.js          # 📊 管理员面板
│       │   ├── personal-api.js   # 🔑 个人 API 配置
│       │   ├── exchange.js       # 🎫 兑换码/投稿
│       │   ├── three-bg.js       # ✨ Three.js 3D效果（粒子/装饰环/骰子）
│       │   ├── three-card.js     # 🃏 3D卡片翻转效果
│       │   ├── three-config.js   # ⚙️ Three.js 配置中心（主题/粒子/骰子参数）
│       │   ├── style.css         # 🎨 样式表（约3120行，9区块分区注释）
│       │   ├── feedback.js       # 📝 反馈模块（约391行，9区块分区注释）
│       │   ├── feedback.css      # 📝 反馈页样式（约352行，6区块分区注释）
│       │   ├── sw.js             # 🔄 Service Worker（PWA支持）
│       │   ├── manifest.json     # 📱 PWA配置
│       │   ├── icons/            # 📱 PWA图标
│       │   │   ├── icon-192.png  # 192x192图标
│       │   │   └── icon-512.png  # 512x512图标
│       │   └── reward_qrcode.png # 💰 打赏二维码
│       └── templates/            # 📄 Jinja2模板
│           ├── index.html        # 🏠 主页面（约580行）
│           ├── feedback.html     # 📝 反馈页（119行）
│           ├── dashboard.html    # 📊 管理面板（297行）
│           └── spectate.html     # 👀 观战页（67行）
└── release/                      # 📦 发布版（含tavern.exe）
    ├── tavern.exe                # 📦 可执行文件（16MB）
    ├── .env / *.json / scripts   # 📄 同步配置文件
    ├── static/                   # 🎨 同步前端资源
    └── templates/                # 📄 同步模板
```

> **docs/ 目录**: 本地开发文档，包含项目架构、问题报告、代码索引等，**禁止同步到 GitHub**。

## 🎮 使用说明

### 1. 首页

进入首页后，选择智能体和游戏世界，输入角色名开始对话或游戏。

### 2. 聊天模式

- 支持与 5 种不同性格的智能体多轮对话
- 实时流式显示 AI 回复（打字机效果）
- 可以切换不同的智能体和模型（支持自有 API 配置）
- 消息发送时触发粒子特效

### 3. 跑团 RPG 模式

- 17 个主题世界书可选（西游、武侠、末日、蒸汽朋克等）
- SSE 流式逐字输出剧情
- 骰子检定系统（d20，带 3D 动画）
- 角色状态追踪（HP/MP/EXP）
- 观战模式：实时观看其他玩家的游戏过程

### 4. Three.js 3D 效果

- 粒子背景动画（80 个粒子）
- 登录页装饰环（3 层旋转动画）
- 消息发送粒子特效
- 主题化背景（根据世界书切换颜色）
- 3D 骰子滚动动画

### 5. 管理后台

- 用户管理（积分、角色、用户名修改）
- 智能体和模型管理
- 反馈审核
- 实时统计面板（时间范围过滤）
- 全部会话查看

### 6. PWA 支持

- 支持安装为桌面应用（需要浏览器支持）
- 离线资源缓存，提升加载速度

## 📊 功能矩阵

| 功能模块 | 状态 | 说明 |
|---------|:----:|------|
| AI 聊天 | ✅ | 5 智能体 + 多模型 + 历史管理 |
| 文字 RPG | ✅ | 17 世界书 + SSE 流式 + 骰子检定 |
| Three.js 3D | ✅ | 粒子背景 + 装饰环 + 骰子动画 |
| 用户认证 | ✅ | 登录/注册/改密 + 速率限制 |
| 积分系统 | ✅ | 扣减/充值 + 积分不足提示 |
| 观战模式 | ✅ | 2 秒轮询 + 实时同步 |
| 反馈系统 | ✅ | 提交/列表/审核/统计 |
| 管理后台 | ✅ | 用户管理 + 统计面板 + 配置 |
| PWA | ✅ | 安装 + 离线缓存 |

## 🛡️ 安全特性

- **CSRF 防护**: 所有 POST/PUT/DELETE 请求强制 CSRF token（登录/注册除外）
- **速率限制**: 登录 5 次/60 秒，注册 3 次/60 分钟，改密 5 次/300 秒
- **API 密钥加密**: 使用 Fernet 加密存储，`encrypt_value`/`decrypt_value` 封装
- **随机数安全**: 骰子使用 `secrets.randbelow` 替代 `random.randint`
- **并发安全**: JSON 文件操作使用 `threading.Lock()` 保护
- **输入验证**: 所有用户输入经过 `sanitize_input` 过滤

## 📝 开发规则

### 修改入口

- **唯一入口**: 所有代码修改必须在 `src/backend/` 目录进行
- **同步规则**: 修改完成后同步到 `release/`（前端文件及数据文件）
- **禁止操作**: 直接在 `release/` 中修改代码

### 关键约束

- 端口必须为 9000
- JSON_AS_ASCII = False（支持中文）
- JSON 文件操作必须使用 threading.Lock() 保护
- 所有 POST/PUT/DELETE 请求必须包含 CSRF token（登录/注册除外）
- token_version 仅在改密或强制登出时递增（避免积分操作导致 session 失效）

### 代码分区规范

项目采用统一的分区注释标准，所有源码文件分为多个功能区块：

| 文件 | 区块数 | 说明 |
|------|:------:|------|
| app.py | 22 | Flask 主应用 |
| blueprints/ | 5 | 功能模块（auth/chat/rpg/admin/feedback） |
| utils/ | 3 | 工具模块（ai_service/json_io/security） |
| static/ | 17 | 前端 ES Modules |
| style.css | 9 | 样式表 |

## 📄 许可证

MIT License
