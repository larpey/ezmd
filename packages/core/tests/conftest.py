from __future__ import annotations

import pytest
from core_factories import every_block_document

from intomd.ir import Document


@pytest.fixture
def full_doc() -> Document:
    return every_block_document()
