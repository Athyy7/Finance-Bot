import asyncio
import json
import os
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import Depends

from backend.app.models.domain.error import Error

# from backend.app.models.schemas.agent_request_schema import AgentRequestSchema
# from backend.app.prompts.supabase_testing_agent_prompt import (
#     SYSTEM_PROMPT,
#     USER_PROMPT,
# )

from backend.app.repositories.error_repository import ErrorRepo
from backend.app.repositories.llm_usage_repository import LLMUsageRepository
from backend.app.services.llm_service import LLMProvider, LLMService

# from backend.app.services.memory_service import AgentMemory
from backend.app.tools.registry.tool_registry import ToolRegistry


class AgentService:
    """
    Simplified Agent Service for handling user requests with tool calling.

    Features:
    - Clean tool calling loop with maximum iteration limits
    - Proper conversation handling with memory service
    - Intermediate output logging for debugging
    - Clear error handling and recovery
    - Progress tracking with print statements
    - Comprehensive tool call statistics tracking
    """

    def __init__(
        self,
        llm_service: LLMService = Depends(),
        tool_registry: ToolRegistry = Depends(),
        error_repo: ErrorRepo = Depends(),
        llm_usage_repo: LLMUsageRepository = Depends(),
        max_tool_calls: int = 100,
        enable_parallel_execution: bool = True,
        max_parallel_tools: int = 10,
    ):
        self.llm_service = llm_service
        self.tool_registry = tool_registry
        self.error_repo = error_repo
        self.llm_usage_repo = llm_usage_repo
        self.max_tool_calls = max_tool_calls
        self.enable_parallel_execution = enable_parallel_execution
        self.max_parallel_tools = max_parallel_tools

        # Initialize memory and session
        # self.memory = AgentMemory(
        #     llm_usage_repository=llm_usage_repo, llm_service=llm_service
        # )
        self.session_id = str(uuid.uuid4())

        # Create intermediate outputs directory for this session
        self.intermediate_dir = f"intermediate_outputs/{self.session_id}"
        os.makedirs(self.intermediate_dir, exist_ok=True)

        # Initialize tool call statistics tracking
        self._init_tool_stats()

        print(f"🤖 Agent Service initialized with session: {self.session_id}")
        print(
            f"📁 Intermediate outputs will be saved to: {self.intermediate_dir}"
        )
        print(
            f"⚡ Parallel execution: {'enabled' if enable_parallel_execution else 'disabled'}"
        )
        if enable_parallel_execution:
            print(f"🔧 Max parallel tools: {max_parallel_tools}")

    def _init_tool_stats(self):
        """Initialize tool call statistics tracking."""
        self.tool_stats = {
            "session_id": self.session_id,
            "start_time": datetime.utcnow().isoformat(),
            "tool_counts": Counter(),  # Count by tool name
            "tool_sequence": [],  # Ordered list of tool calls
            "tool_details": [],  # Detailed info for each tool call
            "parallel_execution_stats": {
                "total_parallel_batches": 0,
                "total_sequential_batches": 0,
                "parallel_tools_executed": 0,
                "sequential_tools_executed": 0,
                "parallel_time_saved": 0.0,  # Estimated time saved by parallel execution
            },
            "file_operations": {
                "files_read": set(),
                "files_written": set(),
                "files_deleted": set(),
                "files_searched": set(),
            },
            "terminal_commands": [],
            "errors": [],
            "success_rate": {},
            "total_execution_time": 0,
        }

    def _track_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_id: str,
        result: str,
        success: bool,
        execution_time: float,
        error_msg: str = None,
    ):
        """Track detailed information about a tool call."""
        call_timestamp = datetime.utcnow().isoformat()

        # Update counts and sequence
        self.tool_stats["tool_counts"][tool_name] += 1
        self.tool_stats["tool_sequence"].append(
            {
                "position": len(self.tool_stats["tool_sequence"]) + 1,
                "tool_name": tool_name,
                "timestamp": call_timestamp,
                "success": success,
            }
        )

        # Extract file operations
        file_ops = self._extract_file_operations(tool_name, tool_input, result)

        # Extract terminal commands
        terminal_cmd = self._extract_terminal_command(
            tool_name, tool_input, result
        )
        if terminal_cmd:
            self.tool_stats["terminal_commands"].append(terminal_cmd)

        # Store detailed information
        tool_detail = {
            "call_id": tool_id,
            "position": len(self.tool_stats["tool_details"]) + 1,
            "tool_name": tool_name,
            "timestamp": call_timestamp,
            "input_parameters": tool_input,
            "success": success,
            "execution_time_seconds": execution_time,
            "result_length": len(str(result)),
            "file_operations": file_ops,
            "error_message": error_msg if not success else None,
        }

        self.tool_stats["tool_details"].append(tool_detail)

        # Track errors
        if not success and error_msg:
            self.tool_stats["errors"].append(
                {
                    "tool_name": tool_name,
                    "error_message": error_msg,
                    "timestamp": call_timestamp,
                    "input_parameters": tool_input,
                }
            )

        # Update total execution time
        self.tool_stats["total_execution_time"] += execution_time

    def _extract_file_operations(
        self, tool_name: str, tool_input: Dict[str, Any], result: str
    ) -> Dict[str, Any]:
        """Extract file operations from tool calls."""
        file_ops = {"files_affected": [], "operation_type": None, "details": {}}

        # Handle different tool types
        if tool_name == "read_file":
            file_path = tool_input.get("absolute_path", "")
            if file_path:
                self.tool_stats["file_operations"]["files_read"].add(file_path)
                file_ops["files_affected"] = [file_path]
                file_ops["operation_type"] = "read"
                file_ops["details"] = {
                    "start_line": tool_input.get("start_line", 0),
                    "end_line": tool_input.get("end_line", 300),
                    "file_path": file_path,
                }

        elif tool_name == "edit_file":
            file_path = tool_input.get("absolute_path", "")
            if file_path:
                self.tool_stats["file_operations"]["files_written"].add(
                    file_path
                )
                file_ops["files_affected"] = [file_path]
                file_ops["operation_type"] = "write/edit"
                file_ops["details"] = {
                    "file_path": file_path,
                    "code_snippet_length": len(
                        tool_input.get("code_snippet", "")
                    ),
                }

        elif tool_name == "file_deletion":
            file_path = tool_input.get("absolute_path", "")
            if file_path:
                self.tool_stats["file_operations"]["files_deleted"].add(
                    file_path
                )
                file_ops["files_affected"] = [file_path]
                file_ops["operation_type"] = "delete"
                file_ops["details"] = {"file_path": file_path}

        elif tool_name in ["grep_search", "file_search"]:
            search_path = tool_input.get("absolute_path", "")
            if search_path:
                self.tool_stats["file_operations"]["files_searched"].add(
                    search_path
                )
                file_ops["files_affected"] = [search_path]
                file_ops["operation_type"] = "search"
                file_ops["details"] = {
                    "search_path": search_path,
                    "query": tool_input.get("query", ""),
                    "case_sensitive": tool_input.get("case_sensitive", False),
                    "include_pattern": tool_input.get("include_pattern", "*"),
                    "exclude_pattern": tool_input.get("exclude_pattern", ""),
                }

        elif tool_name == "search_and_replace":
            file_path = tool_input.get("absolute_path", "")
            if file_path:
                self.tool_stats["file_operations"]["files_written"].add(
                    file_path
                )
                file_ops["files_affected"] = [file_path]
                file_ops["operation_type"] = "search_and_replace"
                file_ops["details"] = {
                    "file_path": file_path,
                    "search_query": tool_input.get("query", ""),
                    "replacement": tool_input.get("replacement", ""),
                }

        elif tool_name == "list_directory":
            dir_path = tool_input.get("absolute_path", "")
            if dir_path:
                file_ops["files_affected"] = [dir_path]
                file_ops["operation_type"] = "list_directory"
                file_ops["details"] = {"directory_path": dir_path}

        return file_ops

    def _extract_terminal_command(
        self, tool_name: str, tool_input: Dict[str, Any], result: str
    ) -> Dict[str, Any]:
        """Extract terminal command information."""
        if tool_name != "run_terminal_cmd":
            return None

        command = tool_input.get("command", "")
        working_dir = tool_input.get("absolute_path", "")

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "command": command,
            "working_directory": working_dir,
            "result_length": len(str(result)),
            "command_type": self._classify_command(command),
        }

    def _classify_command(self, command: str) -> str:
        """Classify the type of terminal command."""
        command = command.lower().strip()

        if command.startswith(("ls", "dir")):
            return "directory_listing"
        elif command.startswith(("cd")):
            return "directory_change"
        elif command.startswith(("git")):
            return "git_operation"
        elif command.startswith(("npm", "yarn", "pip", "poetry")):
            return "package_management"
        elif command.startswith(("python", "node", "java")):
            return "code_execution"
        elif command.startswith(("cat", "head", "tail", "grep")):
            return "file_viewing"
        elif command.startswith(("mkdir", "rmdir", "rm", "cp", "mv")):
            return "file_system_operation"
        elif command.startswith(("chmod", "chown")):
            return "permission_change"
        else:
            return "other"

    def tools_call_stats(self) -> str:
        """Generate comprehensive tool call statistics report."""
        try:
            # Finalize stats
            self.tool_stats["end_time"] = datetime.utcnow().isoformat()

            # Calculate success rates
            total_calls = len(self.tool_stats["tool_details"])
            successful_calls = sum(
                1 for call in self.tool_stats["tool_details"] if call["success"]
            )
            overall_success_rate = (
                (successful_calls / total_calls * 100) if total_calls > 0 else 0
            )

            # Calculate success rate by tool
            tool_success_rates = {}
            for tool_name in self.tool_stats["tool_counts"]:
                tool_calls = [
                    call
                    for call in self.tool_stats["tool_details"]
                    if call["tool_name"] == tool_name
                ]
                successful = sum(1 for call in tool_calls if call["success"])
                total = len(tool_calls)
                tool_success_rates[tool_name] = (
                    (successful / total * 100) if total > 0 else 0
                )

            self.tool_stats["success_rate"] = {
                "overall": round(overall_success_rate, 2),
                "by_tool": {
                    k: round(v, 2) for k, v in tool_success_rates.items()
                },
            }

            # Generate markdown report
            report = self._generate_markdown_report()

            # Save to file
            stats_file = f"{self.intermediate_dir}/tool_stats.md"
            with open(stats_file, "w", encoding="utf-8") as f:
                f.write(report)

            # Also save raw JSON data for programmatic access
            json_stats_file = f"{self.intermediate_dir}/tool_stats.json"
            json_compatible_stats = self._convert_sets_to_lists(self.tool_stats)
            with open(json_stats_file, "w", encoding="utf-8") as f:
                json.dump(json_compatible_stats, f, indent=2, default=str)

            print(f"📊 Tool statistics saved to: {stats_file}")
            print(f"📊 Raw tool data saved to: {json_stats_file}")
            return report

        except Exception as e:
            error_msg = f"Failed to generate tool stats: {str(e)}"
            print(f"⚠️  {error_msg}")
            return error_msg

    def _convert_sets_to_lists(self, data: Any) -> Any:
        """Recursively convert sets to lists for JSON serialization."""
        if isinstance(data, set):
            return sorted(list(data))
        elif isinstance(data, dict):
            return {
                key: self._convert_sets_to_lists(value)
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return [self._convert_sets_to_lists(item) for item in data]
        else:
            return data

    def _generate_markdown_report(self) -> str:
        """Generate detailed markdown report of tool usage statistics."""
        report_lines = [
            "# 🛠️ Tool Call Statistics Report",
            "",
            f"**Session ID:** `{self.tool_stats['session_id']}`",
            f"**Start Time:** {self.tool_stats['start_time']}",
            f"**End Time:** {self.tool_stats.get('end_time', 'In Progress')}",
            f"**Total Execution Time:** {self.tool_stats['total_execution_time']:.2f} seconds",
            "",
            "## 📈 Summary Statistics",
            "",
            f"- **Total Tool Calls:** {len(self.tool_stats['tool_details'])}",
            f"- **Unique Tools Used:** {len(self.tool_stats['tool_counts'])}",
            f"- **Overall Success Rate:** {self.tool_stats['success_rate']['overall']}%",
            f"- **Total Errors:** {len(self.tool_stats['errors'])}",
            "",
            "## ⚡ Parallel Execution Statistics",
            "",
            f"- **Parallel Execution:** {'Enabled' if self.enable_parallel_execution else 'Disabled'}",
            f"- **Max Parallel Tools:** {self.max_parallel_tools}",
            f"- **Parallel Batches:** {self.tool_stats['parallel_execution_stats']['total_parallel_batches']}",
            f"- **Sequential Batches:** {self.tool_stats['parallel_execution_stats']['total_sequential_batches']}",
            f"- **Tools Executed in Parallel:** {self.tool_stats['parallel_execution_stats']['parallel_tools_executed']}",
            f"- **Tools Executed Sequentially:** {self.tool_stats['parallel_execution_stats']['sequential_tools_executed']}",
            f"- **Estimated Time Saved:** {self.tool_stats['parallel_execution_stats']['parallel_time_saved']:.2f} seconds",
            "",
            "## 🔧 Tool Usage Counts",
            "",
            "| Tool Name | Count | Success Rate |",
            "|-----------|-------|--------------|",
        ]

        # Add tool counts table
        for tool_name, count in self.tool_stats["tool_counts"].most_common():
            success_rate = self.tool_stats["success_rate"]["by_tool"].get(
                tool_name, 0
            )
            report_lines.append(f"| {tool_name} | {count} | {success_rate}% |")

        report_lines.extend(
            [
                "",
                "## 📅 Tool Call Sequence",
                "",
                "| # | Tool Name | Timestamp | Status |",
                "|---|-----------|-----------|--------|",
            ]
        )

        # Add sequence table
        for seq in self.tool_stats["tool_sequence"]:
            status = "✅ Success" if seq["success"] else "❌ Failed"
            timestamp = seq["timestamp"].split("T")[1][:8]  # Just time part
            report_lines.append(
                f"| {seq['position']} | {seq['tool_name']} | {timestamp} | {status} |"
            )

        # File operations section
        report_lines.extend(
            [
                "",
                "## 📁 File Operations Summary",
                "",
                f"- **Files Read:** {len(self.tool_stats['file_operations']['files_read'])}",
                f"- **Files Written/Edited:** {len(self.tool_stats['file_operations']['files_written'])}",
                f"- **Files Deleted:** {len(self.tool_stats['file_operations']['files_deleted'])}",
                f"- **Paths Searched:** {len(self.tool_stats['file_operations']['files_searched'])}",
            ]
        )

        # Files read details
        if self.tool_stats["file_operations"]["files_read"]:
            report_lines.extend(["", "### 📖 Files Read", ""])
            for file_path in sorted(
                self.tool_stats["file_operations"]["files_read"]
            ):
                report_lines.append(f"- `{file_path}`")

        # Files written details
        if self.tool_stats["file_operations"]["files_written"]:
            report_lines.extend(["", "### ✏️ Files Written/Edited", ""])
            for file_path in sorted(
                self.tool_stats["file_operations"]["files_written"]
            ):
                report_lines.append(f"- `{file_path}`")

        # Files deleted details
        if self.tool_stats["file_operations"]["files_deleted"]:
            report_lines.extend(["", "### 🗑️ Files Deleted", ""])
            for file_path in sorted(
                self.tool_stats["file_operations"]["files_deleted"]
            ):
                report_lines.append(f"- `{file_path}`")

        # Terminal commands section
        if self.tool_stats["terminal_commands"]:
            report_lines.extend(
                [
                    "",
                    "## 💻 Terminal Commands Executed",
                    "",
                    "| Command | Type | Working Directory | Result Size |",
                    "|---------|------|------------------|-------------|",
                ]
            )

            for cmd in self.tool_stats["terminal_commands"]:
                command_short = (
                    (cmd["command"][:50] + "...")
                    if len(cmd["command"]) > 50
                    else cmd["command"]
                )
                report_lines.append(
                    f"| `{command_short}` | {cmd['command_type']} | `{cmd['working_directory']}` | {cmd['result_length']} chars |"
                )

        # Detailed tool calls section
        report_lines.extend(["", "## 🔍 Detailed Tool Call Log", ""])

        for detail in self.tool_stats["tool_details"]:
            status_icon = "✅" if detail["success"] else "❌"
            report_lines.extend(
                [
                    f"### {status_icon} Call #{detail['position']}: {detail['tool_name']}",
                    "",
                    f"- **Timestamp:** {detail['timestamp']}",
                    f"- **Execution Time:** {detail['execution_time_seconds']:.3f}s",
                    f"- **Result Size:** {detail['result_length']} characters",
                    f"- **Success:** {detail['success']}",
                ]
            )

            if detail.get("error_message"):
                report_lines.append(f"- **Error:** {detail['error_message']}")

            # Add file operation details
            if detail["file_operations"]["operation_type"]:
                op_details = detail["file_operations"]["details"]
                report_lines.extend(
                    [
                        f"- **Operation:** {detail['file_operations']['operation_type']}",
                        f"- **Files Affected:** {', '.join(f'`{f}`' for f in detail['file_operations']['files_affected'])}",
                    ]
                )

                # Add specific operation details
                if detail["file_operations"]["operation_type"] == "read":
                    report_lines.append(
                        f"- **Lines:** {op_details.get('start_line', 0)}-{op_details.get('end_line', 'end')}"
                    )
                elif detail["file_operations"]["operation_type"] in [
                    "write/edit"
                ]:
                    report_lines.append(
                        f"- **Code Snippet Length:** {op_details.get('code_snippet_length', 0)} chars"
                    )
                elif detail["file_operations"]["operation_type"] == "search":
                    report_lines.append(
                        f"- **Search Query:** `{op_details.get('query', '')}`"
                    )

            # Add input parameters (truncated)
            if detail["input_parameters"]:
                params_str = json.dumps(detail["input_parameters"], indent=2)
                if len(params_str) > 300:
                    params_str = params_str[:300] + "... [truncated]"
                report_lines.extend(
                    ["- **Parameters:**", "```json", params_str, "```"]
                )

            report_lines.append("")

        # Errors section
        if self.tool_stats["errors"]:
            report_lines.extend(["## ❌ Errors Encountered", ""])

            for i, error in enumerate(self.tool_stats["errors"], 1):
                report_lines.extend(
                    [
                        f"### Error #{i}: {error['tool_name']}",
                        "",
                        f"- **Timestamp:** {error['timestamp']}",
                        f"- **Error Message:** {error['error_message']}",
                        f"- **Input Parameters:** `{json.dumps(error['input_parameters'])}`",
                        "",
                    ]
                )

        # Performance insights
        report_lines.extend(
            [
                "## ⚡ Performance Insights",
                "",
                f"- **Average Tool Execution Time:** {(self.tool_stats['total_execution_time'] / len(self.tool_stats['tool_details'])):.3f}s",
                f"- **Fastest Tool Call:** {min((d['execution_time_seconds'] for d in self.tool_stats['tool_details']), default=0):.3f}s",
                f"- **Slowest Tool Call:** {max((d['execution_time_seconds'] for d in self.tool_stats['tool_details']), default=0):.3f}s",
                "",
            ]
        )

        # Most used tools
        if self.tool_stats["tool_counts"]:
            most_used = self.tool_stats["tool_counts"].most_common(3)
            report_lines.extend(["### 🏆 Most Used Tools", ""])
            for tool_name, count in most_used:
                percentage = count / len(self.tool_stats["tool_details"]) * 100
                report_lines.append(
                    f"1. **{tool_name}** - {count} calls ({percentage:.1f}%)"
                )

        report_lines.extend(
            [
                "",
                "---",
                f"*Report generated on {datetime.utcnow().isoformat()}*",
            ]
        )

        return "\n".join(report_lines)

    def _log_intermediate_step(
        self, step_type: str, content: Dict[str, Any]
    ) -> None:
        """Log intermediate steps for debugging."""
        try:
            timestamp = datetime.utcnow().isoformat()
            log_entry = {
                "timestamp": timestamp,
                "session_id": self.session_id,
                "step_type": step_type,
                "content": content,
            }

            # Write to file
            log_file = f"{self.intermediate_dir}/steps_log.jsonl"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")

        except Exception as e:
            print(f"⚠️  Failed to log intermediate step: {str(e)}")

    def _save_conversation_state(self, filename: str) -> None:
        """Save current conversation state to file."""
        try:
            state = {
                "session_id": self.session_id,
                "timestamp": datetime.utcnow().isoformat(),
                "messages": self.memory.get_conversation_messages(),
                "tool_usage_summary": self.memory.get_tool_usage_summary(),
                "memory_stats": self.memory.get_session_info(),
            }

            filepath = f"{self.intermediate_dir}/{filename}"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)

        except Exception as e:
            print(f"⚠️  Failed to save conversation state: {str(e)}")

    def _extract_text_content(self, response: Dict[str, Any]) -> str:
        """Extract text content from LLM response (handles both Anthropic and OpenAI formats)."""
        # Check if this is an OpenAI response
        if response.get("llm_responded") == "openai" or response.get("llm_provider") == "openai":
            print("📄 Extracting text content from OpenAI format")
            # OpenAI format: content is directly in choices[0].message.content
            if "choices" in response and len(response["choices"]) > 0:
                message = response["choices"][0].get("message", {})
                content = message.get("content")
                return str(content) if content is not None else ""
            return ""
        
        # Anthropic format: content blocks
        content_blocks = response.get("content", [])
        text_parts = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        return "".join(text_parts)

    def _extract_tool_calls(
        self, response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract tool calls from LLM response (handles both Anthropic and OpenAI formats)."""
        # Check if this is an OpenAI response
        if response.get("llm_responded") == "openai" or response.get("llm_provider") == "openai":
            print("🔧 Extracting tool calls from OpenAI format")
            # OpenAI format: tool_calls array in choices[0].message.tool_calls
            tool_calls = []
            if "choices" in response and len(response["choices"]) > 0:
                message = response["choices"][0].get("message", {})
                openai_tool_calls = message.get("tool_calls", [])
                
                for openai_tool_call in openai_tool_calls:
                    function = openai_tool_call.get("function", {})
                    arguments = function.get("arguments", "{}")
                    
                    # Parse arguments if it's a string
                    try:
                        if isinstance(arguments, str):
                            parsed_input = json.loads(arguments)
                        else:
                            parsed_input = arguments
                    except json.JSONDecodeError:
                        print(f"⚠️  Failed to parse tool arguments: {arguments}")
                        parsed_input = {}
                    
                    # Convert to Anthropic format
                    tool_calls.append({
                        "id": openai_tool_call.get("id"),
                        "name": function.get("name"),
                        "input": parsed_input,
                    })
            
            return tool_calls
        
        # Anthropic format: content blocks with tool_use type
        content_blocks = response.get("content", [])
        tool_calls = []

        for block in content_blocks:
            if block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": block.get("input", {}),
                    }
                )

        return tool_calls

    async def _execute_tool_call(self, tool_call: Dict[str, Any]) -> str:
        """Execute a single tool call and return the result."""
        tool_name = tool_call["name"]
        tool_input = tool_call["input"]
        tool_id = tool_call["id"]
        start_time = time.time()
        success = False
        error_msg = None

        print(f"  🔧 Executing tool: {tool_name}")
        print(f"     Parameters: {json.dumps(tool_input, indent=2)}")

        try:
            # Get tool from registry
            tool_instance = self.tool_registry.get_tool(tool_name)
            if not tool_instance:
                error_msg = f"Tool '{tool_name}' not found in registry"
                print(f"     ❌ {error_msg}")
                execution_time = time.time() - start_time

                # Track the failed tool call
                self._track_tool_call(
                    tool_name,
                    tool_input,
                    tool_id,
                    error_msg,
                    success=False,
                    execution_time=execution_time,
                    error_msg=error_msg,
                )

                return error_msg

            # Execute tool
            result = await tool_instance.execute(tool_input)

            # Convert result to string if needed
            if not isinstance(result, str):
                result = json.dumps(result, default=str, indent=2)

            success = True
            execution_time = time.time() - start_time

            # Log the tool execution
            self._log_intermediate_step(
                "tool_execution",
                {
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "tool_id": tool_id,
                    "result_length": len(result),
                    "success": True,
                    "execution_time": execution_time,
                },
            )

            # Track the successful tool call
            self._track_tool_call(
                tool_name,
                tool_input,
                tool_id,
                result,
                success=True,
                execution_time=execution_time,
            )

            print(f"     ✅ Result: {result}")

            return result

        except Exception as e:
            error_msg = f"Error executing tool {tool_name}: {str(e)}"
            execution_time = time.time() - start_time
            print(f"     ❌ Tool execution failed: {str(e)}")

            # Log the error
            self._log_intermediate_step(
                "tool_error",
                {
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "tool_id": tool_id,
                    "error": str(e),
                    "success": False,
                    "execution_time": execution_time,
                },
            )

            # Track the failed tool call
            self._track_tool_call(
                tool_name,
                tool_input,
                tool_id,
                error_msg,
                success=False,
                execution_time=execution_time,
                error_msg=str(e),
            )

            return error_msg

    async def _execute_tool_call_with_metadata(
        self, tool_call: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single tool call and return result with metadata for parallel execution."""
        tool_name = tool_call["name"]
        tool_id = tool_call["id"]

        try:
            print(
                f"  🔧 [Parallel] Executing tool: {tool_name} (ID: {tool_id})"
            )
            result = await self._execute_tool_call(tool_call)

            return {
                "tool_call": tool_call,
                "result": result,
                "success": True,
                "error": None,
            }

        except Exception as e:
            error_msg = f"Error executing tool {tool_name}: {str(e)}"
            print(f"     ❌ [Parallel] Tool {tool_name} failed: {str(e)}")

            return {
                "tool_call": tool_call,
                "result": error_msg,
                "success": False,
                "error": str(e),
            }

    async def _execute_tool_calls_parallel(
        self, tool_calls: List[Dict[str, Any]], tool_call_count: int
    ) -> tuple[List[Dict[str, Any]], int]:
        """Execute multiple tool calls in parallel and return results with updated count."""

        # Check if we have enough room for all tool calls
        remaining_calls = self.max_tool_calls - tool_call_count
        if len(tool_calls) > remaining_calls:
            print(
                f"⚠️  Can only execute {remaining_calls} more tool calls (limit: {self.max_tool_calls})"
            )
            tool_calls = tool_calls[:remaining_calls]

        if not tool_calls:
            return [], tool_call_count

        # Limit parallel execution to max_parallel_tools
        if len(tool_calls) > self.max_parallel_tools:
            print(
                f"⚠️  Limiting parallel execution to {self.max_parallel_tools} tools (requested: {len(tool_calls)})"
            )
            tool_calls = tool_calls[: self.max_parallel_tools]

        print(f"🚀 Executing {len(tool_calls)} tool calls in PARALLEL...")

        # Create tasks for parallel execution
        tasks = [
            self._execute_tool_call_with_metadata(tool_call)
            for tool_call in tool_calls
        ]

        # Execute all tasks in parallel using asyncio.gather
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        parallel_execution_time = time.time() - start_time

        # Update parallel execution statistics
        self.tool_stats["parallel_execution_stats"][
            "total_parallel_batches"
        ] += 1
        self.tool_stats["parallel_execution_stats"][
            "parallel_tools_executed"
        ] += len(tool_calls)

        # Estimate time saved (assume sequential would take sum of individual times)
        estimated_sequential_time = sum(
            detail.get("execution_time_seconds", 0)
            for detail in self.tool_stats["tool_details"][-len(tool_calls) :]
        )
        if estimated_sequential_time > parallel_execution_time:
            time_saved = estimated_sequential_time - parallel_execution_time
            self.tool_stats["parallel_execution_stats"][
                "parallel_time_saved"
            ] += time_saved
            print(
                f"⚡ Parallel execution completed in {parallel_execution_time:.2f}s (estimated time saved: {time_saved:.2f}s)"
            )
        else:
            print(
                f"⚡ Parallel execution completed in {parallel_execution_time:.2f} seconds"
            )

        # Process results and handle any exceptions
        processed_results = []
        successful_count = 0
        failed_count = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Handle exceptions from asyncio.gather
                tool_call = tool_calls[i]
                error_result = {
                    "tool_call": tool_call,
                    "result": f"Exception during parallel execution: {str(result)}",
                    "success": False,
                    "error": str(result),
                }
                processed_results.append(error_result)
                failed_count += 1
                print(
                    f"     ❌ Tool {tool_call['name']} failed with exception: {str(result)}"
                )
            else:
                processed_results.append(result)
                if result["success"]:
                    successful_count += 1
                    print(
                        f"     ✅ Tool {result['tool_call']['name']} completed successfully"
                    )
                else:
                    failed_count += 1
                    print(f"     ❌ Tool {result['tool_call']['name']} failed")

        updated_tool_call_count = tool_call_count + len(tool_calls)

        print(
            f"📊 Parallel execution summary: {successful_count} successful, {failed_count} failed"
        )

        return processed_results, updated_tool_call_count

    async def _execute_tool_calls_sequential(
        self, tool_calls: List[Dict[str, Any]], tool_call_count: int
    ) -> tuple[List[Dict[str, Any]], int]:
        """Execute tool calls sequentially (original behavior) and return results with updated count."""
        results = []
        current_count = tool_call_count

        print(f"🔄 Executing {len(tool_calls)} tool calls SEQUENTIALLY...")

        # Update sequential execution statistics
        self.tool_stats["parallel_execution_stats"][
            "total_sequential_batches"
        ] += 1

        for tool_call in tool_calls:
            if current_count >= self.max_tool_calls:
                print(
                    f"⚠️  Maximum tool calls ({self.max_tool_calls}) reached during sequential execution"
                )
                break

            current_count += 1
            self.tool_stats["parallel_execution_stats"][
                "sequential_tools_executed"
            ] += 1

            try:
                tool_result = await self._execute_tool_call(tool_call)
                results.append(
                    {
                        "tool_call": tool_call,
                        "result": tool_result,
                        "success": True,
                        "error": None,
                    }
                )
            except Exception as e:
                error_msg = (
                    f"Error executing tool {tool_call['name']}: {str(e)}"
                )
                results.append(
                    {
                        "tool_call": tool_call,
                        "result": error_msg,
                        "success": False,
                        "error": str(e),
                    }
                )

        return results, current_count

    def _should_execute_parallel(
        self, tool_calls: List[Dict[str, Any]]
    ) -> bool:
        """
        Determine if tool calls should be executed in parallel based on tool types and dependencies.

        Some tools that are safe to run in parallel:
        - read_file (multiple file reads)
        - grep_search (multiple searches)
        - file_search (multiple file searches)
        - list_directory (multiple directory listings)
        - schema_analysis (if multiple projects)

        Tools that should NOT be run in parallel:
        - edit_file (file modifications can conflict)
        - search_and_replace (file modifications)
        - file_deletion (can conflict with other operations)
        - run_terminal_cmd (commands might depend on each other)
        """

        # Check if parallel execution is enabled
        if not self.enable_parallel_execution:
            print(f"🔄 Parallel execution disabled by configuration")
            return False

        if len(tool_calls) <= 1:
            return False

        # Tools that are safe for parallel execution
        parallel_safe_tools = {
            "read_file",
            "grep_search",
            "file_search",
            "list_directory",
            "schema_analysis",
        }

        # Tools that should not be run in parallel
        sequential_only_tools = {
            "edit_file",
            "search_and_replace",
            "file_deletion",
            "run_terminal_cmd",
        }

        tool_names = [tool_call["name"] for tool_call in tool_calls]

        # If any tool requires sequential execution, run all sequentially
        if any(tool_name in sequential_only_tools for tool_name in tool_names):
            print(
                f"🔄 Sequential execution required due to tools: {[t for t in tool_names if t in sequential_only_tools]}"
            )
            return False

        # If all tools are parallel-safe, execute in parallel
        if all(tool_name in parallel_safe_tools for tool_name in tool_names):
            print(f"🚀 All tools are parallel-safe: {tool_names}")
            return True

        # For mixed or unknown tools, default to sequential for safety
        unknown_tools = [
            t
            for t in tool_names
            if t not in parallel_safe_tools and t not in sequential_only_tools
        ]
        if unknown_tools:
            print(
                f"🔄 Sequential execution due to unknown tools: {unknown_tools}"
            )

        return False

    async def _get_schema(
        self, project_reference: str, personalized_access_token: str
    ) -> str:
        """
        Get the schema for a project.
        """
        try:
            tool_instance = self.tool_registry.get_tool("schema_analysis")
            if not tool_instance:
                error_msg = f"Tool 'schema_analysis' not found in registry"
                print(f"     ❌ {error_msg}")
                return error_msg

            result = await tool_instance.execute(
                {
                    "project_reference": project_reference,
                    "access_token": personalized_access_token,
                }
            )

            markdown_report = result.get("markdown_report", "")
            print(f"✅ Markdown report of supabase project: {markdown_report}")

            return result

        except Exception as e:
            error_msg = f"Error getting schema: {str(e)}"
            print(f"     ❌ {error_msg}")
            return error_msg




    # async def execute(self, request: AgentRequestSchema) -> Dict[str, Any]:
    #     """
    #     Execute agent processing with tool calling loop.

    #     Args:
    #         user_query: The user's request
    #         working_directory: Current working directory (optional)

    #     Returns:
    #         Dict with success status, response, and metadata
    #     """
    #     start_time = time.time()
    #     tool_call_count = 0
    #     final_message = ""
    #     completion_reason = "completed"

    #     try:
    #         # Get schema
    #         # schema_context = await self._get_schema(
    #         #     request.project_ref, request.personalized_access_token
    #         # )

    #         schema_context = {"status": "success", "markdown_report": "No schema analysis found"}

    #         markdown_report = ""
    #         if (
    #             isinstance(schema_context, dict)
    #             and schema_context.get("status") == "success"
    #         ):
    #             markdown_report = schema_context.get("markdown_report", "")

    #         if markdown_report == "":
    #             markdown_report = "No schema analysis found"

    #         # Format user prompt
    #         formatted_system_prompt = SYSTEM_PROMPT.format(
    #             current_supabase_context=markdown_report
    #         )

    #         # Get file structure content
    #         file_structure_content = self._get_file_structure_content(
    #             request.codebase_path
    #         )

    #         # Format user prompt
    #         formatted_user_prompt = USER_PROMPT.format(
    #             file_structure_content=file_structure_content,
    #             codebase_path=request.codebase_path,
    #         )

    #         with open(
    #             f"{self.intermediate_dir}/formatted_system_prompt.txt", "w"
    #         ) as f:
    #             f.write(formatted_system_prompt)

    #         # Add user message to memory
    #         await self.memory.add_user_message(formatted_user_prompt)

    #         # Get available tools
    #         available_tools = self.tool_registry.get_tools_for_provider(
    #             LLMProvider.ANTHROPIC
    #         )
    #         # Log initial state
    #         self._log_intermediate_step(
    #             "agent_start",
    #             {
    #                 "user_query": USER_PROMPT,
    #                 "working_directory": request.codebase_path,
    #                 "available_tools_count": len(available_tools),
    #                 "max_tool_calls": self.max_tool_calls,
    #             },
    #         )

    #         # Save initial conversation state
    #         self._save_conversation_state("conversation_start.json")

    #         # Tool calling loop
    #         while tool_call_count < self.max_tool_calls:
    #             print(
    #                 f"\n💭 Making LLM request (iteration {tool_call_count + 1})..."
    #             )

    #             # Get current conversation messages
    #             messages = self.memory.get_conversation_messages()

    #             # Make LLM request
    #             try:
    #                 llm_response = await self.llm_service.create_completion(
    #                     messages=messages,
    #                     system=formatted_system_prompt,
    #                     tools=available_tools,
    #                     max_tokens=7000,
    #                     temperature=0.25,
    #                 )

    #                 # Log LLM response (handle both OpenAI and Anthropic formats)
    #                 response_content = llm_response.get("content", [])
    #                 if llm_response.get("llm_responded") == "openai" and "choices" in llm_response:
    #                     # For OpenAI, extract content from choices structure
    #                     choices = llm_response.get("choices", [])
    #                     if choices:
    #                         message = choices[0].get("message", {})
    #                         response_content = {
    #                             "text_content": message.get("content"),
    #                             "tool_calls": message.get("tool_calls", [])
    #                         }
                    
    #                 self._log_intermediate_step(
    #                     "llm_response",
    #                     {
    #                         "iteration": tool_call_count + 1,
    #                         "response_content": response_content,
    #                         "response_tokens": llm_response.get("usage", {}),
    #                         "llm_provider": llm_response.get("llm_provider"),
    #                         "llm_responded": llm_response.get("llm_responded"),
    #                     },
    #                 )

    #             except Exception as e:
    #                 error_msg = f"LLM request failed: {str(e)}"
    #                 print(f"❌ {error_msg}")
    #                 await self._log_error(error_msg)

    #                 return {
    #                     "success": False,
    #                     "message": "Failed to get response from language model",
    #                     "error": str(e),
    #                     "tool_calls_used": tool_call_count,
    #                     "completion_reason": "llm_error",
    #                     "session_id": self.session_id,
    #                     "duration": time.time() - start_time,
    #                 }

    #             # Normalize response to Anthropic format before adding to memory
    #             normalized_response = self._normalize_llm_response_to_anthropic_format(llm_response)
                
    #             # Add assistant response to memory
    #             await self.memory.add_assistant_message(normalized_response)

    #             # Extract content and tool calls
    #             text_content = self._extract_text_content(llm_response)
    #             tool_calls = self._extract_tool_calls(llm_response)

    #             # Display agent response
    #             if text_content and text_content.strip():
    #                 final_message = text_content
    #                 print(f"🤖 Agent says: {text_content}")

    #             # If no tool calls, we're done
    #             if not tool_calls:
    #                 print("✅ Agent completed - no more tool calls needed")
    #                 completion_reason = "natural_completion"
    #                 break

    #             print(f"🔧 Processing {len(tool_calls)} tool call(s)...")

    #             # Decide execution strategy: parallel or sequential
    #             execute_parallel = self._should_execute_parallel(tool_calls)

    #             # Execute tool calls (parallel or sequential)
    #             if execute_parallel:
    #                 execution_results, tool_call_count = (
    #                     await self._execute_tool_calls_parallel(
    #                         tool_calls, tool_call_count
    #                     )
    #                 )
    #             else:
    #                 execution_results, tool_call_count = (
    #                     await self._execute_tool_calls_sequential(
    #                         tool_calls, tool_call_count
    #                     )
    #                 )

    #             # Process results and add to memory
    #             for result_data in execution_results:
    #                 tool_call = result_data["tool_call"]
    #                 tool_result = result_data["result"]
    #                 success = result_data["success"]

    #                 # Truncate tool result if it exceeds 20000 words
    #                 tool_result_str = str(tool_result)
    #                 words = tool_result_str.split()
    #                 if len(words) > 20000:
    #                     print(
    #                         f"⚠️ Tool result exceeds 20000 words, truncating..."
    #                     )

    #                     # If it's a dictionary with content field, truncate that field
    #                     if (
    #                         isinstance(tool_result, dict)
    #                         and "content" in tool_result
    #                         and isinstance(tool_result["content"], str)
    #                     ):
    #                         tool_result["content"] = (
    #                             " ".join(tool_result["content"].split()[:20000])
    #                             + "... [RESULT TRUNCATED]"
    #                         )
    #                     # Otherwise, if it's a string, truncate the string
    #                     elif isinstance(tool_result, str):
    #                         tool_result = (
    #                             " ".join(words[:20000])
    #                             + "... [RESULT TRUNCATED]"
    #                         )
    #                     # For other types, we keep the original but log the truncation
    #                     else:
    #                         print(
    #                             f"⚠️ Could not truncate tool result of type {type(tool_result)}"
    #                         )

    #                 # Add tool result to memory
    #                 await self.memory.add_tool_result(
    #                     tool_call["id"], tool_result
    #                 )
    #                 self.memory.add_tool_call(
    #                     tool_call["name"], tool_call["input"], tool_call["id"]
    #                 )

    #             # Check if we hit the limit
    #             if tool_call_count >= self.max_tool_calls:
    #                 print(
    #                     f"⚠️  Maximum tool calls ({self.max_tool_calls}) reached - stopping execution"
    #                 )
    #                 completion_reason = "max_tool_calls"
    #                 break

    #         # Handle final response based on completion reason
    #         if completion_reason == "max_tool_calls":
    #             print("📝 Generating final summary due to tool limit...")

    #             # Add a request for summary
    #             await self.memory.add_user_message(
    #                 "Please provide a summary of what has been accomplished and any remaining tasks."
    #             )

    #             try:
    #                 final_response = await self.llm_service.create_completion(
    #                     messages=self.memory.get_conversation_messages(),
    #                     system=SYSTEM_PROMPT,
    #                     tools=[],  # No tools for final summary
    #                     max_tokens=7000,
    #                     temperature=0.25,
    #                 )

    #                 summary_content = self._extract_text_content(final_response)
    #                 if summary_content:
    #                     final_message = summary_content
    #                     print(
    #                         f"📋 Summary: {summary_content[:400]}{'...' if len(summary_content) > 400 else ''}"
    #                     )

    #             except Exception as e:
    #                 print(f"⚠️  Failed to generate final summary: {str(e)}")

    #         # Ensure we have a final message
    #         if not final_message:
    #             final_message = "Agent completed successfully."

    #         duration = time.time() - start_time

    #         print(f"\n🎯 Agent execution completed!")
    #         print(f"   ⏱️  Duration: {duration:.2f} seconds")
    #         print(f"   🔧 Tool calls used: {tool_call_count}")
    #         print(f"   📊 Completion reason: {completion_reason}")

    #         # Generate and save tool call statistics
    #         print(f"\n📊 Generating tool call statistics...")
    #         try:
    #             self.tools_call_stats()
    #         except Exception as e:
    #             print(f"⚠️  Failed to generate tool statistics: {str(e)}")

    #         # Save final conversation state
    #         self._save_conversation_state("conversation_final.json")

    #         # Log completion
    #         self._log_intermediate_step(
    #             "agent_completion",
    #             {
    #                 "tool_calls_used": tool_call_count,
    #                 "completion_reason": completion_reason,
    #                 "duration": duration,
    #                 "final_message_length": len(final_message),
    #             },
    #         )

    #         return {
    #             "success": True,
    #             "message": final_message,
    #             "tool_calls_used": tool_call_count,
    #             "completion_reason": completion_reason,
    #             "session_id": self.session_id,
    #             "duration": duration,
    #             "memory_stats": self.memory.get_tool_usage_summary(),
    #             "intermediate_outputs_path": self.intermediate_dir,
    #             "error": None,
    #         }

    #     except Exception as e:
    #         duration = time.time() - start_time
    #         error_msg = f"Agent execution failed: {str(e)}"
    #         print(f"❌ {error_msg}")

    #         await self._log_error(error_msg)

    #         # Save error state
    #         self._save_conversation_state("conversation_error.json")

    #         return {
    #             "success": False,
    #             "message": "Agent encountered an unexpected error during execution",
    #             "error": str(e),
    #             "tool_calls_used": tool_call_count,
    #             "completion_reason": "error",
    #             "session_id": self.session_id,
    #             "duration": duration,
    #             "intermediate_outputs_path": self.intermediate_dir,
    #         }







    async def _log_error(self, error_message: str) -> None:
        """Log error to the error repository."""
        try:
            error_data = {
                "tool_name": "agent_service",
                "error_message": error_message,
                "session_id": self.session_id,
            }
            error = Error(**error_data)
            await self.error_repo.insert_error(error)
        except Exception:
            # Silent fail for error logging to prevent cascading failures
            pass

    def configure_parallel_execution(
        self, enabled: bool = True, max_parallel_tools: int = 10
    ) -> Dict[str, Any]:
        """
        Configure parallel execution settings at runtime.

        Args:
            enabled: Whether to enable parallel execution
            max_parallel_tools: Maximum number of tools to execute in parallel

        Returns:
            Dict with current configuration
        """
        old_enabled = self.enable_parallel_execution
        old_max = self.max_parallel_tools

        self.enable_parallel_execution = enabled
        self.max_parallel_tools = max_parallel_tools

        print(f"🔧 Parallel execution configuration updated:")
        print(f"   Enabled: {old_enabled} → {enabled}")
        print(f"   Max parallel tools: {old_max} → {max_parallel_tools}")

        # Log the configuration change
        self._log_intermediate_step(
            "parallel_config_changed",
            {
                "old_config": {"enabled": old_enabled, "max_tools": old_max},
                "new_config": {
                    "enabled": enabled,
                    "max_tools": max_parallel_tools,
                },
                "changed_by": "runtime_configuration",
            },
        )

        return {
            "parallel_execution_enabled": self.enable_parallel_execution,
            "max_parallel_tools": self.max_parallel_tools,
            "previous_config": {"enabled": old_enabled, "max_tools": old_max},
        }

    def get_parallel_execution_config(self) -> Dict[str, Any]:
        """Get current parallel execution configuration."""
        return {
            "parallel_execution_enabled": self.enable_parallel_execution,
            "max_parallel_tools": self.max_parallel_tools,
            "parallel_safe_tools": [
                "read_file",
                "grep_search",
                "file_search",
                "list_directory",
                "schema_analysis",
            ],
            "sequential_only_tools": [
                "edit_file",
                "search_and_replace",
                "file_deletion",
                "run_terminal_cmd",
            ],
        }

    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information."""
        # Calculate current tool stats summary
        total_calls = len(self.tool_stats["tool_details"])
        successful_calls = sum(
            1 for call in self.tool_stats["tool_details"] if call["success"]
        )
        success_rate = (
            (successful_calls / total_calls * 100) if total_calls > 0 else 0
        )

        return {
            "session_id": self.session_id,
            "intermediate_outputs_path": self.intermediate_dir,
            "memory_stats": self.memory.get_tool_usage_summary(),
            "session_info": self.memory.get_session_info(),
            "available_tools": self.tool_registry.list_tool_names(),
            "max_tool_calls": self.max_tool_calls,
            "parallel_execution_config": self.get_parallel_execution_config(),
            "tool_stats_summary": {
                "total_tool_calls": total_calls,
                "successful_calls": successful_calls,
                "failed_calls": total_calls - successful_calls,
                "success_rate": round(success_rate, 2),
                "unique_tools_used": len(self.tool_stats["tool_counts"]),
                "most_used_tool": (
                    self.tool_stats["tool_counts"].most_common(1)[0]
                    if self.tool_stats["tool_counts"]
                    else None
                ),
                "total_execution_time": round(
                    self.tool_stats["total_execution_time"], 2
                ),
                "files_read_count": len(
                    self.tool_stats["file_operations"]["files_read"]
                ),
                "files_written_count": len(
                    self.tool_stats["file_operations"]["files_written"]
                ),
                "terminal_commands_count": len(
                    self.tool_stats["terminal_commands"]
                ),
                "parallel_execution_summary": {
                    "parallel_batches": self.tool_stats[
                        "parallel_execution_stats"
                    ]["total_parallel_batches"],
                    "sequential_batches": self.tool_stats[
                        "parallel_execution_stats"
                    ]["total_sequential_batches"],
                    "parallel_tools": self.tool_stats[
                        "parallel_execution_stats"
                    ]["parallel_tools_executed"],
                    "sequential_tools": self.tool_stats[
                        "parallel_execution_stats"
                    ]["sequential_tools_executed"],
                    "time_saved": round(
                        self.tool_stats["parallel_execution_stats"][
                            "parallel_time_saved"
                        ],
                        2,
                    ),
                },
            },
        }

    def get_current_tool_stats(self) -> Dict[str, Any]:
        """Get current tool statistics (JSON-compatible format)."""
        return self._convert_sets_to_lists(self.tool_stats)

    def clear_conversation(self) -> None:
        """Clear the conversation history and reset tool statistics."""
        print(
            f"🗑️  Clearing conversation history for session: {self.session_id}"
        )
        self.memory.clear_conversation()

        # Reset tool statistics
        self._init_tool_stats()
        print(f"📊 Tool statistics reset for session: {self.session_id}")

        self._log_intermediate_step(
            "conversation_cleared",
            {"cleared_at": datetime.utcnow().isoformat()},
        )

    def _get_file_structure_content(self, codebase_path: str) -> str:
        """
        Generate a tree-like file structure representation of the codebase.

        Args:
            codebase_path: Path to the codebase directory

        Returns:
            String representation of the file tree structure
        """

        if not os.path.exists(codebase_path):
            return f"Error: Path '{codebase_path}' does not exist"

        if not os.path.isdir(codebase_path):
            return f"Error: Path '{codebase_path}' is not a directory"

        def generate_tree(
            directory: Path, prefix: str = "", is_last: bool = True
        ) -> List[str]:
            """Recursively generate tree structure for a directory."""
            lines = []

            try:
                # Get all items in the directory, sorted
                items = sorted(
                    directory.iterdir(),
                    key=lambda x: (x.is_file(), x.name.lower()),
                )

                for i, item in enumerate(items):
                    is_last_item = i == len(items) - 1

                    # Choose the appropriate tree characters
                    if is_last_item:
                        current_prefix = "└── "
                        next_prefix = "    "
                    else:
                        current_prefix = "├── "
                        next_prefix = "│   "

                    # Add the current item
                    lines.append(f"{prefix}{current_prefix}{item.name}")

                    # If it's a directory, recursively add its contents
                    if item.is_dir():
                        # Skip hidden directories and common ignore patterns
                        if not item.name.startswith(".") and item.name not in {
                            "__pycache__",
                            "node_modules",
                            ".git",
                            ".vscode",
                            ".idea",
                            "dist",
                            "build",
                            ".next",
                            "coverage",
                            ".dart_tool",
                            "android",
                            "ios",
                            "web",
                            "build",
                        }:
                            subdirectory_lines = generate_tree(
                                item, prefix + next_prefix, is_last_item
                            )
                            lines.extend(subdirectory_lines)

            except PermissionError:
                lines.append(f"{prefix}├── [Permission Denied]")
            except Exception as e:
                lines.append(f"{prefix}├── [Error: {str(e)}]")

            return lines

        try:
            # Start with the root directory name
            root_path = Path(codebase_path)
            result_lines = [f"{root_path.absolute()}/"]

            # Generate the tree structure
            tree_lines = generate_tree(root_path)
            result_lines.extend(tree_lines)

            return "\n".join(result_lines)

        except Exception as e:
            return f"Error generating file structure: {str(e)}"

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the agent service."""
        try:
            memory_stats = self.memory.get_tool_usage_summary()
            available_tools = self.tool_registry.list_tool_names()

            return {
                "status": "healthy",
                "session_id": self.session_id,
                "tools_available": len(available_tools),
                "memory_stats": memory_stats,
                "intermediate_outputs_path": self.intermediate_dir,
                "max_tool_calls": self.max_tool_calls,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "session_id": self.session_id,
            }

    def _normalize_llm_response_to_anthropic_format(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert OpenAI response format to Anthropic format for consistent memory storage.
        If already in Anthropic format, returns the response unchanged.
        """
        # If it's already in Anthropic format, return as-is
        if response.get("llm_responded") != "openai" and response.get("llm_provider") != "openai":
            return response
        
        print("🔄 Converting OpenAI response to Anthropic format for memory consistency")
        
        # Convert OpenAI response to Anthropic format
        if "choices" in response and len(response["choices"]) > 0:
            message = response["choices"][0].get("message", {})
            content_blocks = []
            
            # Add text content if present
            text_content = message.get("content")
            if text_content and text_content.strip():
                content_blocks.append({
                    "type": "text",
                    "text": text_content
                })
            
            # Convert tool calls to Anthropic format
            openai_tool_calls = message.get("tool_calls", [])
            for openai_tool_call in openai_tool_calls:
                function = openai_tool_call.get("function", {})
                arguments = function.get("arguments", "{}")
                
                # Parse arguments if it's a string
                try:
                    if isinstance(arguments, str):
                        parsed_input = json.loads(arguments)
                    else:
                        parsed_input = arguments
                except json.JSONDecodeError:
                    print(f"⚠️  Failed to parse tool arguments for normalization: {arguments}")
                    parsed_input = {}
                
                content_blocks.append({
                    "type": "tool_use",
                    "id": openai_tool_call.get("id"),
                    "name": function.get("name"),
                    "input": parsed_input
                })
            
            # Create normalized response in Anthropic format
            normalized_response = {
                "id": response.get("id", ""),
                "type": "message",
                "role": "assistant",
                "content": content_blocks,
                "model": response.get("model", ""),
                "stop_reason": "end_turn" if message.get("finish_reason") == "stop" else "tool_use",
                "stop_sequence": None,
                "usage": response.get("usage", {}),
                # Preserve the original provider information
                "llm_provider": response.get("llm_provider"),
                "fallback_llm_provider": response.get("fallback_llm_provider"),
                "llm_responded": response.get("llm_responded")
            }
            
            return normalized_response
        
        # Fallback: return original response if conversion fails
        return response
