from __future__ import annotations

from dataclasses import dataclass

from src.models.core import DstInfo, SrcInfo


@dataclass(frozen=True)
class TraceQueryContext:
    src_info: SrcInfo
    dst_info: DstInfo
    dst_address: str
