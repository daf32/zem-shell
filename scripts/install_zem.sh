#!/bin/bash
set -e

echo "🚀 Installing Zem CLI..."

# Get the project root (parent directory of scripts/)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Ensure uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ Error: 'uv' is not installed."
    exit 1
fi

echo "📦 Installing 'zem' command globally using uv tool..."
uv tool install "$PROJECT_ROOT" --force --reinstall

echo ""
echo "✅ Success!"
echo "You can now type 'zem' in any terminal to start the shell."
echo "If it doesn't work, try running: uv tool update-shell"
