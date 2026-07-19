# 抖音下载器 GUI 版

基于 [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader) 的图形界面版本，支持批量下载抖音无水印视频、图集、合集、音乐等。

## 功能

- 🔗 **链接下载**：粘贴抖音分享链接、用户主页、合集链接，按合集筛选，一键批量下载
- ⚙️ **设置管理**：Cookie 独立存储在 `.cookies.json`，不混入配置文件
- 📋 **下载记录**：查看历史下载，支持搜索、右键打开目录
- 📝 **侧边日志**：可折叠的实时日志面板

## 快速开始

### 环境要求

- Python 3.9+
- Windows / macOS / Linux

### 安装

```bash
git clone https://github.com/你的用户名/douyin-downloader.git
cd douyin-downloader

# 创建虚拟环境
python -m venv .venv

# 安装依赖
.venv\Scripts\pip install -r requirements.txt     # Windows
.venv/bin/pip install -r requirements.txt         # macOS / Linux
```

### 运行 GUI

```bash
.venv\Scripts\python desktop_app.py               # Windows
.venv/bin/python desktop_app.py                   # macOS / Linux
```

### 打包为 EXE（可选）

```powershell
powershell -File build_desktop_app.ps1
```

打包后在 `dist\DouyinDownloader\DouyinDownloader.exe`。

## 使用指南

### 第一步：获取 Cookie

1. 用浏览器打开 [抖音网页版](https://www.douyin.com) 并登录
2. 按 `F12` → Application → Cookies → 全选复制
3. 粘贴到软件的「⚙️ 设置」标签页，需要这 7 个字段：
   `passport_csrf_token` `odin_tt` `sessionid` `sid_guard` `sid_tt` `uid_tt` `n_mh`
4. 点「保存配置」

### 第二步：粘贴链接

1. 切换到「🔗 链接下载」标签页
2. 粘贴抖音链接（一行一个），支持：
   - 视频 / 图文：`https://www.douyin.com/video/...` 或 `https://v.douyin.com/...`
   - 用户主页：`https://www.douyin.com/user/...`
   - 合集链接：`https://www.douyin.com/collection/...`
3. 勾选要下载的内容（主页作品 / 喜欢 / 合集 / 音乐）
4. 点「解析链接」

### 第三步：筛选与下载

1. 解析完成后，用筛选下拉框按合集过滤
2. 勾选「全选」或手动选择作品，右键可「全选此合集」
3. 选择下载选项（封面 / 音乐 / 头像 / JSON / 增量）
4. 点右下角「开始下载」

## 配置说明

首次运行自动从 `config.example.yml` 生成 `config.yml`。Cookie 独立存储在 `.cookies.json`，不会被提交到 Git。

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `path` | 下载目录 | `./Downloaded/` |
| `thread` | 并发数（固定 3） | 3 |
| `cover` | 下载封面图片 | true |
| `music` | 额外下载 MP3 音频 | false |
| `avatar` | 下载作者头像 | true |
| `json` | 保存作品元数据 JSON | true |
| `increase` | 增量下载（跳过已下载） | false |

## 开发

```bash
pip install -e ".[dev]"
python -m pytest tests/
ruff check .
```

## 许可

MIT License

基于 [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader)（MIT License）
