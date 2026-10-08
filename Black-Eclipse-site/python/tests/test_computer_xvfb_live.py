"""Opt-in live test for the Xvfb provisioner on a Linux host.

Skipped by default. When `BLACK_ECLIPSE_CUA_XVFB=1` on Linux with Xvfb installed,
this provisions a REAL headless desktop, starts the real `LinuxX11Driver` against
it, captures a frame, and tears it down — proving the full create→attach→teardown
lifecycle end to end (not just via injected probes).

An environment without Xvfb is reported skipped, never faked.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("BLACK_ECLIPSE_CUA_XVFB") != "1" or not sys.platform.startswith("linux"),
    reason="live Xvfb verification is opt-in: set BLACK_ECLIPSE_CUA_XVFB=1 on Linux with Xvfb",
)


@pytest.mark.asyncio
async def test_live_xvfb_provision_capture_teardown():
    from harness.computer.config import ComputerConfig
    from harness.computer.desktop import X11HeadlessProvisioner

    provisioner = X11HeadlessProvisioner()
    if not provisioner.available:
        pytest.skip(provisioner.reason)

    instance = await provisioner.create(config=ComputerConfig())
    try:
        assert instance.isolated is True and instance.headless is True
        assert instance.display and instance.display.startswith(":")
        driver = instance.driver
        caps = driver.capabilities()
        assert caps.screen_capture is True
        frame = await driver.capture()
        # An Xvfb root window is a real, capturable surface.
        assert frame.width > 0 and frame.height > 0
        assert frame.png_bytes is not None
    finally:
        await provisioner.destroy(instance)
