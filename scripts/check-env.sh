#!/usr/bin/env bash
# =============================================================
# 环境自检脚本  —— 每台开发电脑各跑一次，版本对上即视为环境一致
# 基准环境见：《技术方案与架构.md》第九章
# 用法（在项目根目录，Git Bash 下）：  bash scripts/check-env.sh
# =============================================================
set -u

green() { printf "\033[32m%s\033[0m" "$1"; }
red()   { printf "\033[31m%s\033[0m" "$1"; }
yellow(){ printf "\033[33m%s\033[0m" "$1"; }

# 检查函数： 参数 = 命令名, 期望包含的版本子串, 显示名
check() {
  local cmd="$1" want="$2" name="$3"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    printf "  [%s] %-10s 未安装%s\n" "$(red FAIL)" "$name" "${want:+  (期望 $want)}"
    return
  fi
  local out
  out="$("$cmd" --version 2>&1 | head -1 | tr -d '\r')"
  if [ -z "$want" ] || printf '%s' "$out" | grep -q "$want"; then
    printf "  [%s] %-10s %s\n" "$(green OK)" "$name" "$out"
  else
    printf "  [%s] %-10s %s  (期望含 %s)\n" "$(yellow WARN)" "$name" "$out" "$want"
  fi
}

echo "==== 本项目环境自检（基准见 技术方案与架构.md 第九章）===="
echo
echo "--- 语言运行时 ---"
check python "3.13" "Python"
check node   "24"   "Node.js"
check npm    "11"   "npm"
echo
echo "--- 构建工具 / 版本控制 ---"
check git    "2.5"  "Git"
check cmake  "4"    "CMake"
check g++    "16"   "g++"
check make   "4"    "Make"
echo
echo "--- 基础设施 / 依赖管理（本机可能尚未安装）---"
check docker ""     "Docker"
check uv     ""     "uv"
check pnpm   ""     "pnpm"
echo
echo "==== 完成：FAIL = 必须安装后才能开发；WARN = 版本与基准不一致，请对齐 ===="
