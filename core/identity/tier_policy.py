"""Declarative tier permission matrix for APCOS identity access control."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

PERMISSIONS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "OWNER": frozenset({"CREATE", "COMPLETE", "ARCHIVE", "STRATEGY"}),
        "FAMILY": frozenset({"COMPLETE", "STRATEGY"}),
        "GUEST": frozenset({"STRATEGY"}),
    }
)

