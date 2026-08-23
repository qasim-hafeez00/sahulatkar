from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from playwright.async_api import FrameLocator
from src.services.checkout.form_filler import CheckoutFormFiller


@pytest.mark.asyncio
async def test_human_type_uses_locator_api_for_frame_locator():
    """_human_type must use .locator().type() when target is a FrameLocator."""
    # Build mock FrameLocator with the locator-based API
    mock_locator = MagicMock()
    mock_locator.wait_for = AsyncMock()
    mock_locator.type = AsyncMock()
    mock_locator.first = mock_locator  # .first returns itself for simplicity

    mock_frame_locator = MagicMock(spec=FrameLocator)
    mock_frame_locator.locator = MagicMock(return_value=mock_locator)

    # Instantiate FormFiller directly to test its method
    redis_mock = MagicMock()
    filler = CheckoutFormFiller(redis_mock)
    filler._page = None # Mock page not needed for FrameLocator path

    await filler._human_type(mock_frame_locator, "input[name='cardnumber']", "4111")

    # Verify locator API was used (not selector-based .type directly on the frame locator)
    mock_frame_locator.locator.assert_called_once_with("input[name='cardnumber']")
    # Each character must be typed via the locator
    assert mock_locator.type.call_count == len("4111"), (
        "_human_type must type each character individually via locator.type(char)"
    )


@pytest.mark.asyncio
async def test_human_type_frame_locator_skips_missing_field():
    """_human_type with FrameLocator must silently skip when wait_for times out."""
    mock_locator = MagicMock()
    mock_locator.wait_for = AsyncMock(side_effect=Exception("Timeout"))
    mock_locator.type = AsyncMock()
    mock_locator.first = mock_locator

    mock_frame_locator = MagicMock(spec=FrameLocator)
    mock_frame_locator.locator = MagicMock(return_value=mock_locator)

    redis_mock = MagicMock()
    filler = CheckoutFormFiller(redis_mock)
    filler._page = None

    # Should not raise — non-fatal for optional iframe fields
    await filler._human_type(mock_frame_locator, "input[name='cvv']", "123")

    # Nothing typed if field not found
    mock_locator.type.assert_not_called()


@pytest.mark.asyncio
async def test_human_type_uses_locator_api_for_page_target():
    """_human_type must use page.locator().type() for regular page targets too."""
    mock_locator = MagicMock()
    mock_locator.wait_for = AsyncMock()
    mock_locator.type = AsyncMock()
    mock_locator.first = mock_locator

    mock_page = MagicMock()
    mock_page.locator = MagicMock(return_value=mock_locator)

    redis_mock = MagicMock()
    filler = CheckoutFormFiller(redis_mock)
    filler._page = mock_page

    await filler._human_type(mock_page, "input[name='email']", "ab")

    mock_page.locator.assert_called_once_with("input[name='email']")
    assert mock_locator.type.call_count == 2
