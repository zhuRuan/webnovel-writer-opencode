#!/bin/bash
# Webnovel Writer for OpenCode Installer v1.3.0
# Usage: curl -sL https://raw.githubusercontent.com/lujih/webnovel-writer-opencode/master/init.sh | bash

# Cleanup accidental nul file (Windows special device name)
rm -f "nul" 2>/dev/null
rm -f "./nul" 2>/dev/null

REPO="lujih/webnovel-writer-opencode"
BRANCH="master"
ARCHIVE_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"

echo ""
echo "========================================"
echo "  Webnovel Writer for OpenCode"
echo "  Installer v1.3.0"
echo "========================================"
echo ""

# ========================================
# [0/5] Dependency Check
# ========================================
echo "[0/5] Checking dependencies..."

# Check Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "ERROR: Python is not installed"
    echo ""
    echo "Please install Python 3.9 or higher:"
    echo "  macOS: brew install python3"
    echo "  Linux: sudo apt install python3 python3-pip (Debian/Ubuntu)"
    echo "         sudo dnf install python3 python3-pip (Fedora)"
    echo "  Windows: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_CMD="python3"
$PYTHON_CMD --version &> /dev/null || PYTHON_CMD="python"

PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
PYTHON_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info[0])')
PYTHON_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info[1])')

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    echo "ERROR: Python $PYTHON_VERSION is too old. Requires Python 3.9+"
    echo "Please upgrade Python: https://www.python.org/downloads/"
    exit 1
fi
echo "      Python: $PYTHON_VERSION OK"

# Check pip
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo "ERROR: pip is not installed"
    echo ""
    echo "Please install pip:"
    echo "  macOS: brew install python3"
    echo "  Linux: sudo apt install python3-pip (Debian/Ubuntu)"
    echo "  Windows: python -m ensurepip --upgrade"
    exit 1
fi
echo "      pip: OK"

# Check curl
if ! command -v curl &> /dev/null; then
    echo "ERROR: curl is not installed"
    echo "Please install curl:"
    echo "  macOS: brew install curl"
    echo "  Linux: sudo apt install curl (Debian/Ubuntu)"
    echo "  Windows: Already included in Windows 10+"
    exit 1
fi
echo "      curl: OK"

# Check unzip
if ! command -v unzip &> /dev/null; then
    echo "ERROR: unzip is not installed"
    echo "Please install unzip:"
    echo "  macOS: brew install unzip"
    echo "  Linux: sudo apt install unzip (Debian/Ubuntu)"
    exit 1
fi
echo "      unzip: OK"

echo ""

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    PROJECT_DIR="$(pwd -W)"
else
    PROJECT_DIR="$(pwd)"
fi

echo "Project: $PROJECT_DIR"

# [1/5] Clean existing .opencode
if [ -d ".opencode" ]; then
    echo "[1/5] Cleaning existing .opencode..."
    rm -rf ".opencode"
fi

# Download with retry and fallback
MAX_RETRIES=3
RETRY_COUNT=0
SUCCESS=0

# Try GitHub master first
while [ $RETRY_COUNT -lt $MAX_RETRIES ] && [ $SUCCESS -eq 0 ]; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "[2/5] Downloading from GitHub (attempt $RETRY_COUNT/$MAX_RETRIES)..."
    
    if curl -sL --max-time 120 "$ARCHIVE_URL" -o "repo.zip" 2>/dev/null; then
        if [ -s "repo.zip" ]; then
            SUCCESS=1
        fi
    fi
    
    if [ $SUCCESS -eq 0 ]; then
        echo "      Download failed, retrying in 3 seconds..."
        sleep 3
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

echo "[3/5] Extracting..."
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

echo "[4/5] Installing to .opencode..."
mkdir -p "${PROJECT_DIR}/.opencode"

# Copy .opencode directory (includes agents/, skills/, scripts/, references/, genres/, templates/)
if [ -d "$SOURCE_DIR/.opencode" ]; then
    cp -r "$SOURCE_DIR/.opencode/"* "${PROJECT_DIR}/.opencode/" 2>/dev/null
    echo "      .opencode/: OK"
fi

# Install Python dependencies with retry
echo "[5/5] Installing Python dependencies..."
if [ -f "$SOURCE_DIR/requirements.txt" ]; then
    PIP_RETRIES=0
    PIP_SUCCESS=0
    while [ $PIP_RETRIES -lt 2 ] && [ $PIP_SUCCESS -eq 0 ]; do
        PIP_RETRIES=$((PIP_RETRIES + 1))
        if $PYTHON_CMD -m pip install -r "$SOURCE_DIR/requirements.txt" --quiet 2>/dev/null; then
            PIP_SUCCESS=1
        else
            if [ $PIP_RETRIES -lt 2 ]; then
                echo "      Retrying pip install..."
                sleep 2
            fi
        fi
    done
    
    if [ $PIP_SUCCESS -eq 1 ]; then
        echo "      Python deps: OK"
    else
        echo "      Python deps: SKIPPED (already installed or error)"
    fi
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

echo ""
echo "========================================"
echo "  Webnovel Writer for OpenCode"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your API Key"
echo "     - Get API keys from:"
echo "       * ModelScope: https://modelscope.cn/my/settings"
echo "       * Jina AI: https://jina.ai/"
echo "  2. Restart OpenCode and run /webnovel-init"
echo "  3. Enjoy writing your novel!"
echo ""
