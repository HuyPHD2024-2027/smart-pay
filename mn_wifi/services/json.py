import dataclasses
from typing import Any
from uuid import UUID
from enum import Enum

# Recursive JSON-safe serialiser ------------------------------------

class JSONable:
    def _to_jsonable(self, obj: Any) -> Any:  # noqa: ANN401 – generic helper
        """Return *obj* converted into JSON-serialisable structures.

        • dataclasses → dict (recursively processed)
        • set → list (sorted for determinism when items are plain types)  
        • UUID → str  
        • list / tuple / dict processed recursively  
        • everything else returned unchanged.
        """

        if dataclasses.is_dataclass(obj):
            return {k: self._to_jsonable(v) for k, v in dataclasses.asdict(obj).items()}

        if isinstance(obj, dict):
            return {k: self._to_jsonable(v) for k, v in obj.items()}

        if isinstance(obj, (list, tuple)):
            return [self._to_jsonable(v) for v in obj]

        if isinstance(obj, set):
            # Try to return a deterministic ordering when items are simple types
            try:
                return [self._to_jsonable(v) for v in sorted(obj)]
            except Exception:
                return [self._to_jsonable(v) for v in obj]

        if isinstance(obj, UUID):
            return str(obj)

        if isinstance(obj, Enum):
            return obj.value

        return obj