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

## � 安装步骤

### 环境要求

- Python 3.8 或更高版本
- 网络连接（用于调用 AI API）

### 安装依赖

```bash
cd src/backend
pip install -r requirements.txt
```

### 配置 API Key

在 `src/backend/` 目录下创建 `.env` 文件：

```env
API_KEY=your_siliconflow_api_key_here
ADMIN_PASSWORD=your_admin_password
```

> **注意**: 请使用 SiliconFlow API Key

## � 启动应用

### 方式一：Python 直接运行

```bash
cd src/backend
python app.py
```

### 方式二：使用启动脚本

```bash
# Windows
.\tavern\start.bat

# PowerShell
.\tavern\start.ps1
```

### 访问应用

启动后访问：**http://localhost:9000**

可以通过樱花内网穿透，共享给他人游玩，这种技术方式比较简单，而且相对好用。

## 📁 项目结构

```
ai_chat/
├── docs/                      # 项目文档
│   ├── 项目架构和相关规范.md    # 架构与规范说明
│   ├── 问题反馈与报告.md        # 问题清单
│   └── 项目记忆.md             # 项目共同记忆
├── scripts/                   # 工具脚本
├── src/                       # 源代码
│   └── backend/               # Flask 应用
│       ├── app.py             # 主应用程序
│       ├── static/            # 前端资源文件
│       │   ├── script.js      # 主脚本
│       │   ├── style.css      # 样式文件
│       │   ├── feedback.js    # 反馈模块脚本
│       │   └── feedback.css   # 反馈模块样式
│       ├── templates/         # HTML 模板
│       │   ├── index.html     # 首页
│       │   ├── dashboard.html # 仪表盘
│       │   ├── feedback.html  # 反馈页面
│       │   └── spectate.html  # 观战页面
│       ├── instance/          # SQLite 数据库
│       └── requirements.txt   # Python 依赖
├── release/                   # 发布版本
└── tavern/                    # 启动入口
```

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

## � 开发模式

### 修改代码

所有代码修改应在 `src/backend/` 目录进行，修改后会自动同步到 `release/` 目录。

### 运行测试

```bash
python scripts/test_rpg.py
```

### 重置数据库

```bash
python scripts/reset_db.py
```

## 📄 许可证

MIT License