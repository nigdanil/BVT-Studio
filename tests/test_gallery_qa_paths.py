"""The read-only gallery checker must not depend on a developer's drive."""
from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_gallery_v021_outputs.py'


class GalleryQAPathTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / 'relocated repo'
        script = self.root / 'scripts' / SCRIPT.name
        script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, script)
        spec = importlib.util.spec_from_file_location('gallery_qa_path_test', script)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.cwd = Path(temp.name).resolve() / 'unrelated cwd'
        self.cwd.mkdir()
        old_cwd = Path.cwd()
        self.addCleanup(os.chdir, old_cwd)
        os.chdir(self.cwd)

    def check_argument(self, args, expected):
        with patch.object(sys, 'argv', [str(SCRIPT), *args]), \
                patch.object(self.module, 'inspect', return_value=[]) as inspect, \
                redirect_stdout(io.StringIO()):
            self.module.main()
        inspect.assert_called_once_with(expected)
        self.assertFalse((self.root / 'qa_renders').exists())

    def test_default_is_relative_to_relocated_repository(self):
        self.check_argument([], self.root / 'qa_renders/effects_gallery_v021')

    def test_explicit_absolute_override(self):
        target = self.cwd / 'custom gallery'
        self.check_argument(['--output', str(target)], target)

    def test_explicit_relative_override_preserves_cwd_semantics(self):
        self.check_argument(['--output', 'custom/gallery'], Path('custom/gallery'))
