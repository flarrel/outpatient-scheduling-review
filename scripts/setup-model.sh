#!/bin/sh
set -eu

if [ "$(uname -s):$(uname -m)" != "Darwin:arm64" ]; then
    printf '%s\n' 'This setup command targets Apple Silicon macOS.' >&2
    exit 1
fi

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cache="$project_root/cache"
runner="$cache/llama/llama-b12803"
archive="$cache/llama/macos-arm64.tar.gz"
model="$cache/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"
mkdir -p "$cache/llama" "$cache/models"

download() {
    url=$1
    file=$2
    digest=$3
    if [ ! -f "$file" ]; then
        curl -fLSs --retry 2 -o "$file.partial" "$url"
        printf '%s  %s\n' "$digest" "$file.partial" | LC_ALL=C shasum -a 256 -c -
        mv "$file.partial" "$file"
    fi
    printf '%s  %s\n' "$digest" "$file" | LC_ALL=C shasum -a 256 -c -
}

download 'https://github.com/ggml-org/llama.cpp/releases/download/b12803/llama-b12803-bin-macos-arm64.tar.gz' \
    "$archive" 'a052d3f315ccc1ebd4a04f73c2e9c0ac1809dc878dcf26a979f43823feef5fa2'
download 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/9217f5db79a29953eb74d5343926648285ec7e67/qwen2.5-0.5b-instruct-q4_k_m.gguf' \
    "$model" '74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db'

if [ ! -x "$runner/llama-server" ]; then
    LC_ALL=C tar -xzf "$archive" -C "$cache/llama"
fi
printf 'Model files ready in %s\n' "$cache"
