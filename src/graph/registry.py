from typing import Any, Dict, Callable

from src.graph import tracetx, tracegrouptx
from src.state.graph_state import Subgraph
from src.state import tracetx_state, tracegrouptx_state

SUBGRAPH_MAP: Dict[Subgraph, Any] = {
    "tracetx": tracetx.create_graph(),
    "tracegrouptx": tracegrouptx.create_graph()
}

STATE_INIT_MAP: Dict[Subgraph, Callable] = {
    "tracetx": tracetx_state.initialize_state,
    "tracegrouptx": tracegrouptx_state.initialize_state
}
