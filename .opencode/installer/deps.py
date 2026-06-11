"""依赖安装模块。纯标准库，通过子进程调用 pip。"""
import subprocess
import sys
from pathlib import Path

from installer.ui import info, warn, error, spinner

FEATURE_GROUPS = {
    "dashboard": {
        "label": "Dashboard — Web 管理面板",
        "desc": "fastapi/uvicorn (~15MB)",
        "req": ".opencode/dashboard/requirements.txt",
        "default": True,
    },
    "export": {
        "label": "导出 — MD/TXT/EPUB/HTML/DOCX/PDF",
        "desc": "mistune/python-docx/ebooklib (~8MB)",
        "req": ".opencode/scripts/requirements-export.txt",
        "default": True,
    },
    "publish": {
        "label": "发布 — 小说平台自动发布",
        "desc": "playwright + Chromium (~150MB)",
        "req": None,
        "default": False,
    },
    "dev": {
        "label": "开发工具 — 测试套件",
        "desc": "pytest/pytest-cov (~10MB)",
        "req": ".opencode/scripts/requirements-dev.txt",
        "default": False,
    },
}

CORE_REQ = ".opencode/scripts/requirements.txt"


def check_pip_available() -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, check=True, timeout=10
        )
        return True
    except Exception:
        return False


def create_venv(path: Path) -> bool:
    if path.exists():
        warn(f"虚拟环境已存在: {path}")
        return False
    info(f"创建虚拟环境: {path}")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(path)],
            check=True, timeout=60
        )
        return True
    except subprocess.CalledProcessError as e:
        warn(f"创建虚拟环境失败: {e}")
        return False


def _get_pip_path(venv_path: Path = None) -> list:
    if venv_path:
        if sys.platform == "win32":
            pip = [str(venv_path / "Scripts" / "python"), "-m", "pip"]
        else:
            pip = [str(venv_path / "bin" / "python"), "-m", "pip"]
    else:
        pip = [sys.executable, "-m", "pip"]
    return pip


def install_pip_requirements(req_files: list, venv_path: Path = None) -> bool:
    pip = _get_pip_path(venv_path)

    for rf in req_files:
        if not Path(rf).exists():
            warn(f"依赖文件未找到: {rf}")
            continue
        info(f"安装依赖: {Path(rf).name}")
        try:
            result = subprocess.run(
                pip + ["install", "-r", str(rf), "--quiet", "--progress-bar", "off"],
                capture_output=True, text=True, timeout=300
            )
            # 只在 pip 有实质性输出时显示（表明有新安装/升级，而非"已满足"）
            stderr = result.stderr.strip()
            if stderr:
                for line in stderr.splitlines():
                    if not line.startswith("WARNING: ") and "already satisfied" not in line.lower():
                        print(f"    {line}")
        except subprocess.CalledProcessError as e:
            if e.stderr:
                print(e.stderr.strip(), file=sys.stderr)
            warn(f"pip 安装失败 ({Path(rf).name})")
            return False
    return True


def install_playwright_browser(venv_path: Path = None) -> bool:
    pip = _get_pip_path(venv_path)
    try:
        subprocess.run(pip + ["install", "playwright", "--quiet"], check=True, timeout=60)
    except subprocess.CalledProcessError:
        warn("playwright pip 包安装失败")
        return False

    with spinner("安装 Chromium 浏览器 (~150MB，可能需要几分钟)..."):
        try:
            subprocess.run(
                [pip[0], "-m", "playwright", "install", "chromium"],
                check=True, timeout=600
            )
            return True
        except subprocess.CalledProcessError:
            warn("Chromium 浏览器安装失败")
            return False


def _resolve_features(args, *, skip_playwright: bool = False) -> dict:
    """从 args 或默认值解析要安装的可选功能模块。"""
    features = {}
    with_any = getattr(args, 'with_features', None) or []
    for key in FEATURE_GROUPS:
        if key == "publish" and skip_playwright:
            features[key] = False
        elif key in with_any:
            features[key] = True
        elif hasattr(args, f'no_{key}') and getattr(args, f'no_{key}'):
            features[key] = False
        else:
            features[key] = FEATURE_GROUPS[key]["default"]
    return features


def install_core_deps(venv_path: Path = None, skip_playwright: bool = False,
                      features: dict = None):
    """安装核心 + 选定的可选依赖。"""
    # 核心依赖始终安装
    req_files = [CORE_REQ]

    # 解析可选功能
    if features is None:
        features = {k: v["default"] for k, v in FEATURE_GROUPS.items()}
        if skip_playwright:
            features["publish"] = False

    # 收集可选依赖文件
    for key, cfg in FEATURE_GROUPS.items():
        if features.get(key) and cfg["req"]:
            req_files.append(cfg["req"])

    # 显示安装计划
    labels = ["core"]
    for key, cfg in FEATURE_GROUPS.items():
        labels.append(f"{key}={'Y' if features.get(key) else 'N'}")
    info(f"模块选择: {', '.join(labels)}")

    print(f"    💡 下载慢？可用国内镜像: pip install -r xxx -i https://pypi.tuna.tsinghua.edu.cn/simple")

    if not install_pip_requirements(req_files, venv_path):
        error("核心依赖安装失败")

    # Playwright 特殊处理：先 pip install 再安装浏览器
    if features.get("publish") and not skip_playwright:
        install_playwright_browser(venv_path)
