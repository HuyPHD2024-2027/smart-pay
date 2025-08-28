"""
ABI (Application Binary Interface) definitions for smart contracts.
"""
import json
from pathlib import Path
from typing import List, Dict, Any
import importlib.resources as pkg_resources

_ABI_DIR: Path = Path(__file__).resolve().parent

def _load_abi(filename: str) -> List[Dict[str, Any]]:
    """Return ABI list from the given JSON file.

    The JSON may either be a raw list (standard Hardhat export) or an object
    with an ``abi`` field (solidity-coverage & Foundry style). The helper
    normalises both cases and always returns the ABI array.
    """
    with open(_ABI_DIR / filename, "r", encoding="utf-8") as fp:
        data = json.load(fp)

    if isinstance(data, list):  # Hardhat style export
        return data

    # Object export: { "abi": [...] }
    if "abi" in data and isinstance(data["abi"], list):
        return data["abi"]

    raise ValueError(f"Unsupported ABI format in {_ABI_DIR / filename}")

# Load and expose ABIs as module-level constants
try:
    MeshPayABI: List[Dict[str, Any]] = _load_abi("MeshPayMVP.json")
    MeshPayAuthoritiesABI: List[Dict[str, Any]] = _load_abi("MeshPayAuthorities.json")
    ERC20ABI: List[Dict[str, Any]] = _load_abi("ERC20.json")
except FileNotFoundError as e:
    # Provide empty ABIs if files don't exist (for development)
    print(f"Warning: ABI file not found: {e}")
    MeshPayABI: List[Dict[str, Any]] = []
    MeshPayAuthoritiesABI: List[Dict[str, Any]] = []
    ERC20ABI: List[Dict[str, Any]] = []

__all__ = ["MeshPayABI", "MeshPayAuthoritiesABI", "ERC20ABI"] 