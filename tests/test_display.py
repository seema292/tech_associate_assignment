from scraper.display import needs_virtual_display


def test_headless_never_needs_a_virtual_display():
    assert needs_virtual_display(True, platform="linux", env={}) is False


def test_windows_and_mac_never_need_one():
    assert needs_virtual_display(False, platform="win32", env={}) is False
    assert needs_virtual_display(False, platform="darwin", env={}) is False


def test_linux_without_a_screen_needs_one():
    assert needs_virtual_display(False, platform="linux", env={}) is True


def test_linux_with_a_screen_does_not():
    assert needs_virtual_display(False, platform="linux", env={"DISPLAY": ":0"}) is False
    assert needs_virtual_display(False, platform="linux", env={"WAYLAND_DISPLAY": "wayland-0"}) is False
