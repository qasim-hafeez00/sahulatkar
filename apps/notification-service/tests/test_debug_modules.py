import pytest
from src.core.event_listeners import listener_state as ls1
import src.core.event_listeners as mod1

@pytest.mark.asyncio
async def test_module_paths():
    import src.core.event_listeners as mod2
    from src.api.v1.health import listener_state as ls2
    
    print(f"DEBUG: mod1 file: {mod1.__file__}")
    print(f"DEBUG: mod2 file: {mod2.__file__}")
    print(f"DEBUG: ls1 id: {id(ls1)}")
    print(f"DEBUG: ls2 id: {id(ls2)}")
    assert id(ls1) == id(ls2)
