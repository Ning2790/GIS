#!/usr/bin/env bash
# 生成本地自签证书（HTTPS 起步用；正式部署请替换为可信证书，如 Let's Encrypt）。
# 用法：bash deploy/gen-self-signed-cert.sh
set -euo pipefail

# pwd -W：Git Bash 下输出 Windows 风格路径（如 D:/...）——配合下面禁用 MSYS 参数转换后，
# openssl（原生程序）才能同时正确处理输出路径与 -subj。
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && { pwd -W 2>/dev/null || pwd; })/nginx/certs"
mkdir -p "$DIR"

if [[ -f "$DIR/server.crt" ]]; then
    echo "证书已存在（$DIR），如需重新生成请先删除。"
    exit 0
fi

# Git Bash（MSYS）会把 -subj 的 "/C=CN/..." 误当路径转换，禁用之（两类环境变量名兼容）
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$DIR/server.key" -out "$DIR/server.crt" \
    -subj "/C=CN/ST=Qinghai/O=QH Platform/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

echo "自签证书已生成：$DIR/server.crt（有效 365 天，CN=localhost）"
