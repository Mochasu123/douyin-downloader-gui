# 抖音下载器 GUI 版（Douyin Downloader）

基于 [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader)（MIT License）的图形界面版本，支持**批量下载抖音无水印视频、图集、合集、音乐**等。

界面采用**白蓝渐变**现代风格：圆角按钮、平滑动画进度条、渐变横幅，纯 Tkinter 实现，无需额外运行环境。

## ✨ 功能特性

- 🔗 **链接下载**：粘贴抖音分享链接（视频 / 图文 / 短链 / 用户主页 / 合集 / 音乐），一键解析批量下载
- 🧩 **下载模式**：主页作品 / 喜欢 / 合集 / 音乐 / 收藏 / 收藏夹合集
- 🔐 **Cookie 保护**：Cookie 保存后自动锁定打码，仅「👁 查看」只读窥视，「✏️ 修改」解锁编辑，防止误改误看
- 💾 **智能保存**：「保存配置」按钮在未检测到任何改动时自动置灰，避免无效保存
- 📋 **预览表格**：解析结果按合集筛选、按列排序、状态实时变色（排队 / 下载中 / 成功 / 失败 / 跳过）
- 📈 **平滑进度**：总进度 + 单文件进度双进度条（缓动动画），下载中状态圆点呼吸动画
- 📝 **侧边日志**：入口在顶部横幅右侧，点击展开/收起，日志实时滚动
- 🗂️ **下载记录**：历史记录搜索、筛选、分页，右键打开文件所在目录
- ⚡ **工程细节**：并发下载（3 线程）、失败重试、增量下载（跳过已下载）、时间/数量过滤、SQLite 去重、`download_manifest.jsonl` 下载清单

## 🚀 使用方法

### 第一步：获取 Cookie

1. 用浏览器打开 [抖音网页版](https://www.douyin.com) 并登录
2. 按 `F12` → `Application` → `Cookies` → 全选复制
3. 打开软件 → 「⚙️ 设置」标签页 → 粘贴到 Cookie 输入框
4. 需要包含这 7 个字段：
   ```
   passport_csrf_token  odin_tt  sessionid  sid_guard  sid_tt  uid_tt  n_mh
   ```
5. 点击「保存配置」——保存后 Cookie 会自动锁定打码

> 💡 Cookie 锁定后：
> - 「👁 查看」——只读显示明文（不可编辑）
> - 「✏️ 修改」——解锁进入编辑模式，改完保存后重新锁定
> - 「✕ 取消」——放弃修改，恢复保存时的值

### 第二步：粘贴链接并解析

1. 切换到「🔗 链接下载」标签页
2. 粘贴抖音链接（一行一个），支持：
   - 视频 / 图文：`https://www.douyin.com/video/...` 或短链 `https://v.douyin.com/...`
   - 用户主页：`https://www.douyin.com/user/...`
   - 合集：`https://www.douyin.com/collection/...`
   - 音乐：`https://www.douyin.com/music/...`
3. 勾选下载模式（主页作品 / 喜欢 / 合集 / 音乐）
4. 点击「解析链接」，作品列表会出现在下方预览表格中

### 第三步：筛选与下载

1. 用「筛选」下拉框按合集过滤作品
2. 勾选「全选」或手动勾选，右键可「全选此合集」
3. 选择附加内容：封面 / 音乐 / 头像 / JSON 元数据 / 增量（跳过已下载）
4. 点击右下角「开始下载」，底部进度条实时显示进度
5. 下载完成后右下角弹出通知，可在「📋 下载记录」中查看历史

## 📥 安装与运行

### 方式一：直接运行 EXE（推荐）

从 [Releases](../../releases) 下载最新版 `DouyinDownloader.exe`，双击运行即可，无需安装 Python。

### 方式二：源码运行

```bash
# 环境要求：Python 3.9+
git clone https://github.com/Mochasu123/douyin-downloader-gui.git
cd douyin-downloader-gui

# 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt    # Windows

# 启动图形界面
.venv\Scripts\python desktop_app.py
```

### 打包为 EXE（可选）

```powershell
powershell -File build_desktop_app.ps1
```

打包完成后产物位于 `dist\DouyinDownloader\DouyinDownloader.exe`。

## ⚙️ 配置说明

首次运行自动从 `config.example.yml` 生成 `config.yml`。Cookie 独立存储在 `.cookies.json`，不会提交到 Git。

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `path` | 下载目录 | `./Downloaded/` |
| `thread` | 并发数（固定 3） | 3 |
| `cover` | 下载封面图片 | true |
| `music` | 额外下载 MP3 音频 | false |
| `avatar` | 下载作者头像 | true |
| `json` | 保存作品元数据 JSON | true |
| `increase` | 增量下载（跳过已下载） | false |

## ❓ 常见问题

**Q：解析或下载失败，提示需要登录？**
A：抖音 Cookie 会过期。打开「⚙️ 设置」→ 点「✏️ 修改」→ 粘贴新的 Cookie → 保存配置。

**Q：为什么有些作品显示"已存在"？**
A：开启了增量下载，该作品之前已下载过，自动跳过。

**Q：如何打开下载的文件？**
A：设置页「打开下载目录」直接打开资源管理器；下载记录页右键 →「打开文件所在目录」。

**Q：下载速度慢？**
A：软件固定 3 线程并发（官方接口限制，过高容易触发风控），请勿修改 `thread` 配置。

## 🧑‍💻 开发

```bash
pip install -e ".[dev]"
python -m pytest tests/
ruff check .
```

## 许可

MIT License，基于 [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader)（MIT License）。
