#!/bin/bash
# Webnovel Writer for OpenCode Installer v1.2.0
# Usage: curl -sL https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/init.sh | bash

REPO="lujih/webnovel-writer-opencode"
BRANCH="master"
ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"

echo ""
echo "========================================"
echo "  Webnovel Writer for OpenCode"
echo "  Installer v1.2.0"
echo "========================================"
echo ""

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    PROJECT_DIR="$(pwd -W)"
else
    PROJECT_DIR="$(pwd)"
fi

echo "Project: $PROJECT_DIR"

# [0/4] Clean existing .opencode
if [ -d ".opencode" ]; then
    echo "[0/4] Cleaning existing .opencode..."
    rm -rf ".opencode"
fi

# Download with retry and fallback
MAX_RETRIES=3
RETRY_COUNT=0
SUCCESS=0

# Try GitHub master first
while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ $SUCCESS -eq 0 ]; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "[1/4] Downloading from GitHub (attempt $RETRY_COUNT/$MAX_RETRIES)..."
    
    if curl -sL --max-time 120 "$ARCHIVE_URL" -o "repo.zip" 2>/dev/null; then
        if [ -s "repo.zip" ]; then
            SUCCESS=1
        fi
    fi
    
    if [ $SUCCESS -eq 0 ]; then
        sleep 2
    fi
done

# Try China mirror as fallback
if [ $SUCCESS -eq 0 ]; then
    echo "       Trying China mirror (github.akams.cn)..."
    if curl -sL --max-time 120 "https://github.akams.cn/${REPO}/archive/refs/heads/${BRANCH}.zip" -o "repo.zip" 2>/dev/null; then
        if [ -s "repo.zip" ]; then
            SUCCESS=1
        fi
    fi
fi

if [ $SUCCESS -eq 0 ]; then
    echo ""
    echo "ERROR: Download failed after all attempts"
    echo "Possible solutions:"
    echo "  1. Check your internet connection"
    echo "  2. Use a VPN if you're in a restricted region"
    echo "  3. Manually download from: https://github.com/$REPO/archive/$BRANCH.zip"
    exit 1
fi

echo "[2/4] Extracting..."
unzip -q "repo.zip"
rm -f "repo.zip"

# Find extracted directory
SOURCE_DIR=""
for d in "$PROJECT_DIR"/webnovel-writer-opencode-*; do
    if [ -d "$d" ]; then
        SOURCE_DIR="$d"
        break
    fi
done

if [ -z "$SOURCE_DIR" ]; then
    echo "ERROR: Could not find extracted directory"
    exit 1
fi

echo "[3/4] Installing to .opencode..."
mkdir -p "${PROJECT_DIR}/.opencode"

# Copy .opencode directory (includes agents/, skills/, scripts/, references/, genres/, templates/)
if [ -d "$SOURCE_DIR/.opencode" ]; then
    cp -r "$SOURCE_DIR/.opencode/"* "${PROJECT_DIR}/.opencode/" 2>/dev/null
    echo "      .opencode/: OK"
fi

# Install Python dependencies
echo "[4/4] Installing Python dependencies..."
if [ -f "$SOURCE_DIR/requirements.txt" ]; then
    pip install -r "$SOURCE_DIR/requirements.txt" 2>/dev/null && echo "      Python deps: OK" || echo "      Python deps: SKIPPED"
fi

# Create .env
echo "      Creating .env..."
if [ ! -f ".env" ]; then
    cat > "${PROJECT_DIR}/.env" << 'EOF'
# Webnovel Writer for OpenCode Config
# Fill in your API Key

EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EMBED_API_KEY=your_api_key

RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=jina-reranker-v3
RERANK_API_KEY=your_api_key
EOF
    echo "      .env: CREATED"
else
    echo "      .env: Already exists, skipped"
fi

# Cleanup source directory
rm -rf "$SOURCE_DIR"

# Cleanup accidental nul file (created by bash 2>nul redirect)
rm -f "nul"

echo ""
echo "========================================"
echo "  Webnovel Writer for OpenCode"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your API Key"
echo "  2. Restart OpenCode and enjoy writing!"
echo ""
