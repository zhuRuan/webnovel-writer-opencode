import sys, os
sys.path.insert(0, '.opencode/scripts')

from opencode.dashboard.app import create_app

PROJECT_ROOT = "/mnt/d/novels/project_a"
os.environ["WEBNOVEL_PROJECT_ROOT"] = PROJECT_ROOT

app = create_app(PROJECT_ROOT)
