import pytest

from src.services.variant_service import VariantSelector


class _Node:
    def __init__(self, text: str, cls: str = "selected") -> None:
        self._text = text
        self._class = cls
        self.clicked = False

    async def inner_text(self):
        return self._text

    async def get_attribute(self, key: str):
        if key == "disabled":
            return None
        if key == "aria-selected":
            return "true" if self.clicked else "false"
        if key == "class":
            return self._class
        return None

    async def click(self):
        self.clicked = True


class _Select:
    async def select_option(self, label: str):
        self.label = label

    async def input_value(self):
        return "M"


class _Page:
    def __init__(self):
        self.node = _Node("M")

    async def query_selector_all(self, selector: str):
        if selector.startswith("button"):
            return [self.node]
        if selector == "select":
            return [_Select()]
        return []


@pytest.mark.asyncio
async def test_button_group_variant_selected():
    selector = VariantSelector()
    page = _Page()
    ok = await selector.select_variant(page, {"Size": "M"})
    assert ok is True


def test_parse_variants_from_upo():
    selector = VariantSelector()
    parsed = selector.parse_variants_from_upo({"variants": [{"option_name": "Size", "selected_value": "L"}]})
    assert parsed == {"Size": "L"}
