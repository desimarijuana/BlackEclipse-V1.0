"""Visual teaching reaches the model as REAL image parts.

The caption is not the lesson: a shape is. These tests prove the image survives
validation, becomes an `image_url` content block on the human turn, and rides
along on a scheduled agent run built by the automation dispatcher.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from harness.automation.dispatcher import Dispatcher
from harness.graph import _user_content
from harness.schemas import ModelSettings, RunImage, RunInput, RunRequest

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _request(images=None) -> RunRequest:
    return RunRequest(
        runId="run_1",
        input=RunInput(query="teach me the setup", images=images),
        modelSettings=ModelSettings(provider="openai", model="gpt-4o"),
        callbackBaseUrl="http://127.0.0.1:3000",
    )


def _image(caption="enter after the retest") -> dict:
    return {"dataUrl": PNG, "caption": caption, "mime": "image/png"}


def test_run_input_accepts_a_raster_data_url():
    request = _request([_image()])
    assert request.input.images is not None
    assert request.input.images[0].data_url.startswith("data:image/png;base64,")
    assert request.input.images[0].caption == "enter after the retest"


def test_run_input_refuses_a_remote_url():
    with pytest.raises(ValidationError):
        RunImage(dataUrl="https://example.com/setup.png")


def test_run_input_refuses_more_than_four_images():
    with pytest.raises(ValidationError):
        RunInput(query="x", images=[_image() for _ in range(5)])


def test_the_human_turn_carries_image_parts():
    content = _user_content(_request([_image()]))
    assert isinstance(content, list)
    kinds = [part["type"] for part in content]
    assert kinds.count("image_url") == 1
    assert kinds[0] == "text"
    image = next(part for part in content if part["type"] == "image_url")
    assert image["image_url"]["url"].startswith("data:image/png;base64,")
    assert any("enter after the retest" in part.get("text", "") for part in content)
    assert any("not live market data" in part.get("text", "") for part in content)


def test_without_images_the_turn_stays_a_string():
    assert _user_content(_request()) == "teach me the setup"


def test_a_scheduled_agent_run_carries_the_bot_images():
    definition = SimpleNamespace(
        id="aut_1",
        name="Trend bot",
        trigger=SimpleNamespace(type="manual"),
        action=SimpleNamespace(
            type="run_agent",
            config={
                "visuals": [
                    {"dataUrl": PNG, "caption": "failed breakout to avoid", "mime": "image/png"},
                    {"dataUrl": "https://example.com/x.png", "caption": "remote is dropped"},
                ],
            },
            workspace_root=None,
            autonomy=None,
            agent_id=None,
        ),
        permissions=SimpleNamespace(),
    )
    dispatcher = Dispatcher(SimpleNamespace())
    request = dispatcher._run_request(definition, "run_1", "review the setup")
    assert request.input.images is not None
    assert len(request.input.images) == 1
    assert request.input.images[0].caption == "failed breakout to avoid"
    assert "failed breakout to avoid" in request.input.query
    assert "not live market data" in request.input.query
