# AGENTS.md

本项目为「青海旅游 + 农产品平台」。以下是**开发环境要求与配置指令**，请在动手前照此执行；详细说明见 `开发环境.md`。

## 一、环境硬要求

只要求**大版本一致**，补丁号可不同。目标：让每个人的代码都能跑通。

| 组件 | 要求版本 | 安装位置 |
|---|---|---|
| Python | 3.13.x | python.org 安装包（**不要用 Microsoft Store 版**） |
| uv | 0.13.x | `D:\ruanjian\uv` |
| Node.js | 24.x | `D:\ruanjian\nodejs` |
| npm | 11.x | 随 Node |
| pnpm | 12.x | 随 Node（`D:\ruanjian\nodejs\pnpm.cmd`） |
| Git | 2.55+ | `D:\ruanjian\PortableGit` |
| w64devkit（GCC 16.x / CMake 4.x / Make 4.x） | 2.10.x | `D:\ruanjian\w64devkit` |
| Docker Desktop | 全员同一版本 | `C:\Program Files\Docker\Docker` |

- 所有开发软件统一安装到 **`D:\ruanjian\`**。
- `D:\ruanjian\w64devkit` 仅在**编译 C++ 核心**时需要，纯 Python / 前端开发可忽略。

## 二、执行约定（重要）

- **Shell**：以下命令除特别标注外，一律在 **Git Bash** 下执行。
- **唯一例外**：安装 uv 用 **PowerShell**：
  ```powershell
  $env:UV_INSTALL_DIR='D:\ruanjian\uv'
  irm https://astral.sh/uv/install.ps1 | iex
  ```
- **需要管理员权限的步骤，不要尝试自动执行**，停下来告知用户手动完成：
  1. `wsl --install`（管理员 PowerShell，之后需**重启电脑**）
  2. 安装 Docker Desktop
  3. 修改 Docker 数据目录（*Settings → Resources → Disk image location* → `D:\ruanjian\Docker`）
- PATH 修改后需**新开终端**才生效，不要在当前会话里反复重试。
- 装 pnpm 时，npm 11 会拦截安装脚本；若提示 `not yet covered by allowScripts`，执行：
  ```bash
  npm install -g --allow-scripts=pnpm pnpm
  ```

## 三、拉下代码后，先跑这三步

```bash
docker compose up -d     # 起 PostgreSQL/Redis/MinIO（版本已在 docker-compose.yml 写死）
uv sync                  # 还原 Python 依赖（读 uv.lock）
pnpm install             # 还原前端依赖（读 pnpm-lock.yaml）
```

> **禁止**绕过锁文件手装依赖（如直接 `pip install` 某个包），否则会导致其他人代码跑不通。

## 四、环境自检

```bash
bash scripts/check-env.sh
```

- `OK` = 已达标；`FAIL` = 该组件未安装，需安装；`WARN` = 版本与基准不同，**只要大版本一致可忽略**。

## 五、其他约定

- **动手做具体任务前，先读 `docs/AI任务手册.md`**：每张任务卡含改动范围、步骤、自测命令与完成判据。
  当前进度与未完成项见 `docs/任务清单.md`。
- 接口以仓库内的 OpenAPI 契约文档为准，契约变更先改契约再改代码。
- `.env` 不提交，仓库只提供 `.env.example` 模板。
- 换行符由 `.gitattributes` 统一为 LF，不要手动修改。

---

详细环境说明（含各组件安装地址与验证方法）见 **`开发环境.md`**。
