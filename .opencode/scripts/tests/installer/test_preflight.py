"""Tests for installer.preflight — orchestration."""
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from installer.preflight import apply_staging, verify_installation


class TestApplyStaging:
    def test_no_staging_directory(self):
        """apply_staging without .opencode_staging should return False."""
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                result = apply_staging()
                assert result == False
            finally:
                os.chdir(cwd)

    def test_staging_replaces_opencode(self):
        """With staging dir and no existing .opencode, apply succeeds."""
        d = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(d)
        try:
            staging = Path(d) / ".opencode_staging"
            staging.mkdir()
            (staging / "test_file.txt").write_text("new content")
            result = apply_staging()
            assert result == True
            assert (Path(d) / ".opencode").is_dir()
            assert (Path(d) / ".opencode" / "test_file.txt").read_text() == "new content"
            assert not staging.exists()
        finally:
            os.chdir(cwd)


class TestVerifyInstallation:
    @patch("subprocess.run")
    def test_verify_runs_preflight(self, mock_run):
        mock_run.return_value.returncode = 0
        assert verify_installation() == True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_verify_fails_on_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        assert verify_installation() == False
