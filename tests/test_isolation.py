import pwd
from os import getuid
from pathlib import Path

from garmin_mcp import config, dashboard


def test_tests_cannot_reach_the_owners_home_folder():
    """A build with a temporary data folder still mirrors to ~/Library/Mobile Documents."""
    real = Path(pwd.getpwuid(getuid()).pw_dir)
    assert Path.home() != real
    assert not config.data_dir().is_relative_to(real / ".garmin-mcp")
    _, icloud = dashboard._snapshot_paths()
    assert icloud is None or not icloud.is_relative_to(real)
