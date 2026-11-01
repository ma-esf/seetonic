from app import gemini, jev


def test_jev_judges_the_same_definitions_as_the_flash_router():
    for label, definition in jev.CRITERIA.items():
        assert f"{label}: {definition}" in gemini.ROUTER_INSTRUCTION
