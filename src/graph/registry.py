from typing import Any, Dict

from src.graph import tracetx
from src.state.graph_state import Subgraph

SUBGRAPH_MAP: Dict[Subgraph, Any] = {
    "tracetx": tracetx.create_graph()
}
