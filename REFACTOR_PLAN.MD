Status: I’ll propose 4 refactor options, pick the most pragmatic one for now, and provide ready-to-drop files (config, tests, CI, linting) to implement it without breaking your current demos.

### Refactor options (3–5)

- Option A: Adopt a src/ layout + cohesive modules
  - Approach: Create `src/smartpay/` with subpackages: `config/`, `services/`, `transports/`, `consensus/`, `utils/`. Keep existing `mn_wifi` code, add shims later.
  - Pros: Clear boundaries; easier discoverability; safe to introduce alongside current code.
  - Cons: Temporary duplication until migration; requires import hygiene.

- Option B: Define stable interfaces + adapters (ports and adapters)
  - Approach: Introduce abstract protocols for `BlockchainClient`, `NetworkTransport`, `AuthorityRepository`. Existing code implements adapters.
  - Pros: Decouples components; easy to swap transports/blockchain.
  - Cons: Initial interface design effort; requires incremental refactors.

- Option C: Observability and reliability layer
  - Approach: Unified logging (JSON), metrics hooks, error taxonomy, context IDs across messages.
  - Pros: Debuggable simulations; ready for experiments and papers.
  - Cons: Doesn’t reduce structural complexity by itself.

- Option D: Full test + CI modernization
  - Approach: Pytest structure, smoke/integration tests, Ruff, mypy optional, GitHub Actions/uv.
  - Pros: Prevent regressions; onboarding-friendly.
  - Cons: Fails at first until code meets standards; some churn.

Decision
- Choose Option A + D as Phase 1 (structure + config + tests/CI). It delivers immediate clarity with minimal risk and enables later Option B/C refactors smoothly.

Applied changes (add these files)

- pyproject.toml (Ruff, pytest, uv; no build-system change to avoid breaking `setup.py`)
```toml
[project]
name = "smart-pay-offline"
version = "0.1.0"
description = "Offline mobile payment over mesh – dev tooling"
requires-python = ">=3.8"

[tool.ruff]
line-length = 100
target-version = "py38"
select = ["E", "F", "I", "UP", "B", "W", "PL"]
ignore = ["E501"]

[tool.pytest.ini_options]
minversion = "7.0"
addopts = "-q"
testpaths = ["tests"]

[tool.uv.sources]
smart-pay-offline = { path = "." }

[tool.uv.pip]
upgrade = false
```

- .env.example
```bash
# Blockchain/RPC
RPC_URL=http://127.0.0.1:8545
CHAIN_ID=1337
CHAIN_NAME=LocalDev
MESHPAY_CONTRACT_ADDRESS=0x0000000000000000000000000000000000000000

# Backend signer (dev only)
BACKEND_PRIVATE_KEY=0x0000000000000000000000000000000000000000000000000000000000000001

# Sync interval (seconds)
BLOCKCHAIN_SYNC_INTERVAL=60
```

- src/smartpay/config/settings.py
```python
from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChainConfig(BaseModel):
	"""Static blockchain chain metadata."""
	chain_id: int
	chain_name: str


class Settings(BaseSettings):
	"""Application settings loaded from environment variables."""
	rpc_url: str = "http://127.0.0.1:8545"
	meshpay_contract_address: Optional[str] = None
	backend_private_key: Optional[str] = None

	blockchain_sync_interval: int = 60

	chain_id: int = 1337
	chain_name: str = "LocalDev"

	model_config = SettingsConfigDict(env_prefix="", env_file=".env", case_sensitive=False)

	@property
	def chain(self) -> ChainConfig:
		"""Return resolved chain configuration."""
		return ChainConfig(chain_id=self.chain_id, chain_name=self.chain_name)

	def require_contract(self) -> str:
		"""Return the configured MeshPay contract address or raise a descriptive error."""
		if not self.meshpay_contract_address:
			raise ValueError(
				"MESHPAY_CONTRACT_ADDRESS not configured. Set it in .env or environment."
			)
		return self.meshpay_contract_address


# Singleton-style accessor
settings = Settings()
```

- src/smartpay/utils/logging.py
```python
from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
	"""Structured JSON log formatter."""

	def format(self, record: logging.LogRecord) -> str:  # noqa: D401
		payload: Dict[str, Any] = {
			"level": record.levelname,
			"logger": record.name,
			"message": record.getMessage(),
		}
		if record.exc_info:
			payload["exc_info"] = self.formatException(record.exc_info)
		return json.dumps(payload)


def configure_json_logging(level: int = logging.INFO) -> None:
	"""Configure root logger with JSON console handler."""
	handler = logging.StreamHandler(sys.stdout)
	handler.setFormatter(JsonFormatter())
	logging.basicConfig(level=level, handlers=[handler])
```

- tests/__init__.py
```python
# empty to mark as package
```

- tests/test_settings.py
```python
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from src.smartpay.config.settings import Settings

if TYPE_CHECKING:
	from _pytest.capture import CaptureFixture
	from _pytest.fixtures import FixtureRequest
	from _pytest.logging import LogCaptureFixture
	from _pytest.monkeypatch import MonkeyPatch
	from pytest_mock.plugin import MockerFixture


def test_settings_defaults(monkeypatch: "MonkeyPatch") -> None:
	"""Settings should populate sensible defaults when env is missing."""
	monkeypatch.delenv("RPC_URL", raising=False)
	s = Settings()
	assert s.rpc_url.startswith("http")
	assert s.blockchain_sync_interval > 0
	assert s.chain.chain_id == s.chain_id


def test_settings_env(monkeypatch: "MonkeyPatch") -> None:
	"""Settings should read values from environment."""
	monkeypatch.setenv("RPC_URL", "http://localhost:9000")
	monkeypatch.setenv("CHAIN_ID", "999")
	monkeypatch.setenv("CHAIN_NAME", "TestNet")
	s = Settings()
	assert s.rpc_url == "http://localhost:9000"
	assert s.chain.chain_id == 999
	assert s.chain.chain_name == "TestNet"


def test_require_contract_raises_without_value(monkeypatch: "MonkeyPatch") -> None:
	"""require_contract should raise when MESHPAY_CONTRACT_ADDRESS is not set."""
	monkeypatch.delenv("MESHPAY_CONTRACT_ADDRESS", raising=False)
	s = Settings()
	with pytest.raises(ValueError):
		_ = s.require_contract()
```

- .github/workflows/ci.yml
```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install tools
        run: |
          uv pip install --system ruff pytest pydantic pydantic-settings
      - name: Lint
        run: |
          ruff check .
      - name: Tests
        run: |
          pytest -q
```

- README-DEV.md (snippet)
```markdown
### Dev quickstart
- Copy `.env.example` to `.env` and set RPC_URL etc.
- Lint: `ruff check .`
- Test: `pytest -q`
- Settings: see `src/smartpay/config/settings.py`
```

Optional, non-breaking code guard (authority thread)
- If you later re-enable a blockchain sync thread, add a safe guard to avoid None starts:
```python
# in WiFiAuthority.start_fastpay_services
# ...
# only start if created
# if self._blockchain_sync_thread is None:
#     self._blockchain_sync_thread = threading.Thread(target=self._blockchain_sync_loop, daemon=True)
# self._blockchain_sync_thread.start()
```

Where to use new settings now
- You can progressively replace imports of `mn_wifi.services.core.config.settings` with `from src.smartpay.config.settings import settings`. To avoid breakage, keep both in parallel for a while.

Progress report

```json
{
  "timestamp": "2025-08-13T00:00:00Z",
  "chosen_solution": "Phase 1: src/ layout + config + tests/CI (Options A + D)",
  "rationale": "Safest path to clarity and maintainability without breaking existing demos; enables future decoupling (interfaces) and observability.",
  "changes": [
    "Added pyproject.toml with Ruff/pytest/uv config",
    "Added src/smartpay/config/settings.py (Pydantic Settings)",
    "Added src/smartpay/utils/logging.py (JSON logs)",
    "Added .env.example",
    "Added tests (settings) and package marker",
    "Added GitHub Actions CI (lint + tests)",
    "Added README-DEV.md"
  ],
  "status": "success",
  "next_steps": [
    "Gradually move configuration usage to src.smartpay.config.settings",
    "Define abstract ports for BlockchainClient and NetworkTransport; adapt existing implementations",
    "Add structured logging to authority/client paths; integrate metrics hooks",
    "Add integration tests for mesh demo + ping paths; smoke tests for CLI"
  ]
}
```

Summary
- Proposed 4 refactor options, selected structure + CI as Phase 1.
- Provided ready-to-use files for config, logging, tests, linting, CI with minimal risk and no changes to existing imports.
- Next steps outline how to continue the migration cleanly.