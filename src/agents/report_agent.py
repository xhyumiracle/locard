"""
Report Agent - Generates natural language reports from trace results.

Uses gpt-4o-mini for cost efficiency.
"""

from typing import Any, Dict

from langchain_core.messages import SystemMessage, HumanMessage

import config
from src.node.tracetx.score import ScoringTable
from src.agents.prompts import load_prompt
from src.utils.llm import create_chat_openai_with_retry


class ReportAgent:
    """Report Agent that generates natural language reports from trace results."""

    def __init__(self):
        self.llm = create_chat_openai_with_retry(
            model=config.get_agent_model("report"),
            temperature=0.3,
            max_tokens=2048
        )

    def generate_report(
        self,
        result: Dict[str, Any],
        user_query: str = ""
    ) -> str:
        """
        Generate a natural language report from trace result.

        Args:
            result: The result dict from subgraph, structure:
                    - success case: {"success": True, "data": <scoring_table>}
                    - failure case: {"success": False, "reason": <str>}
            user_query: Original user query for context

        Returns:
            Natural language report string
        """
        # Handle failure case
        if not result.get("success"):
            reason = result.get("reason", "Unknown error")
            return f"Trace failed: {reason}"

        # Success case - format scoring table
        scoring_table = result["data"]
        messages = self._build_messages(scoring_table, user_query)
        response = self.llm.invoke(messages)
        return response.content

    def _build_messages(
        self,
        scoring_table: ScoringTable,
        user_query: str
    ):
        """Build messages for LLM."""
        messages = [SystemMessage(content=load_prompt("report_agent"))]

        # Format scoring table as structured input
        table_str = self._format_scoring_table(scoring_table)

        content = f"User Query: {user_query}\n\n" if user_query else ""
        content += f"Scoring Results:\n{table_str}"

        messages.append(HumanMessage(content=content))
        return messages

    def _format_scoring_table(self, table: ScoringTable) -> str:
        """Format scoring table for LLM consumption.

        Filters out large Transfer objects, only keeping essential fields.
        """
        lines = [
            f"Status: {table['status']}",
            f"Summary: {table['summary']}",
            "",
            "Scoring Parameters:",
            f"  - tau_time: {table['params']['tau_time']}s",
            f"  - max_fee_rate: {table['params']['max_fee_rate']:.2%}",
            f"  - max_deviation_rate: {table['params']['max_deviation_rate']:.2%}",
            f"  - w_time: {table['params']['w_time']}",
            f"  - w_amount: {table['params']['w_amount']}",
            "",
        ]

        if table['best_match']:
            lines.append(f"Best Match: {table['best_match']}")
            lines.append("")

        lines.append("Candidates (sorted by confidence):")
        for i, link in enumerate(table['candidates'], 1):
            # Determine if we should show op_id based on transfer type
            show_src_op = link.src_transfer.type == "utxo"
            show_dst_op = link.dst_transfer.type == "utxo"

            if link.excluded:
                lines.append(f"  {i}. [EXCLUDED] {link.src_chain}:{link.src_transfer.txid}")
                lines.append(f"     Reason: {link.exclude_reason}")
            else:
                # Get operations directly via op_id
                src_op = link.src_transfer.operations[link.src_op_id]
                dst_op = link.dst_transfer.operations[link.dst_op_id]

                # Get amounts
                src_amount = src_op.amount if src_op.amount is not None else "N/A"
                dst_amount = dst_op.amount if dst_op.amount is not None else "N/A"

                # Get timestamps
                src_timestamp = link.src_transfer.block_time if link.src_transfer.block_time else "N/A"
                dst_timestamp = link.dst_transfer.block_time if link.dst_transfer.block_time else "N/A"

                # Format source line with amount and timestamp
                src_op_str = f" (op: {src_op.op_id})" if show_src_op else ""
                lines.append(f"  {i}. {link.src_chain}:{link.src_transfer.txid}{src_op_str}")
                lines.append(f"     Source: {src_amount} {link.src_chain}, timestamp: {src_timestamp}")

                # Format destination line with amount and timestamp
                dst_op_str = f" (op: {dst_op.op_id})" if show_dst_op else ""
                lines.append(f"     → {link.dst_chain}:{link.dst_transfer.txid}{dst_op_str}")
                lines.append(f"     Destination: {dst_amount} {link.dst_chain}, timestamp: {dst_timestamp}")

                # Time difference and fee rate
                time_diff_str = f"{link.time_diff}s" if link.time_diff is not None else "N/A"
                fee_rate_str = f"[{link.fee_rate_min:.2%}, {link.fee_rate_max:.2%}]" if link.fee_rate_min is not None else "N/A"
                lines.append(f"     Time diff: {time_diff_str}, Fee rate range: {fee_rate_str}")
                lines.append(f"     Confidence: F_time={link.f_time:.4f}, F_amount={link.f_amount:.4f}, Final={link.confidence:.4f}")

        return "\n".join(lines)
