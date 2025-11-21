"""
Command to process user interaction task queue and create todorama tasks.

This command reads from the user_interaction_tasks.jsonl queue file (created by
Telegram/Discord services) and creates actual todorama tasks via MCP.
"""
import argparse
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any

from essence.command import Command

logger = logging.getLogger(__name__)


class ProcessUserInteractionQueueCommand(Command):
    """
    Command to process user interaction task queue and create todorama tasks.
    """

    @classmethod
    def get_name(cls) -> str:
        """Get the command name."""
        return "process-user-interaction-queue"

    @classmethod
    def get_description(cls) -> str:
        """Get the command description."""
        return "Process user interaction task queue and create todorama tasks"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        """Add command-line arguments."""
        parser.add_argument(
            "--queue-file",
            type=str,
            help="Path to queue file (default: auto-detect)",
        )
        parser.add_argument(
            "--max-tasks",
            type=int,
            default=10,
            help="Maximum number of tasks to process in one run (default: 10)",
        )
        parser.add_argument(
            "--project-id",
            type=int,
            default=int(os.getenv("TODORAMA_PROJECT_ID", "1")),
            help="Todorama project ID (default: 1)",
        )

    def run(self) -> None:
        """Run the command to process the queue."""
        args = self.args
        
        # Determine queue file path
        if args.queue_file:
            queue_file = Path(args.queue_file)
        else:
            data_dir = os.getenv("JUNE_DATA_DIR", "/home/rlee/june_data")
            queue_file = Path(f"{data_dir}/var-data/user_interaction_tasks.jsonl")
        
        if not queue_file.exists():
            logger.info(f"Queue file does not exist: {queue_file}")
            print(f"No tasks to process (queue file not found: {queue_file})")
            return
        
        # Read tasks from queue
        tasks = []
        try:
            with open(queue_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            task_data = json.loads(line)
                            tasks.append(task_data)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse queue line: {e}")
                            continue
        except Exception as e:
            logger.error(f"Failed to read queue file: {e}", exc_info=True)
            print(f"ERROR: Failed to read queue file: {e}")
            return
        
        if not tasks:
            logger.info("No tasks in queue")
            print("No tasks to process")
            return
        
        # Limit number of tasks to process
        tasks_to_process = tasks[:args.max_tasks]
        logger.info(f"Processing {len(tasks_to_process)} tasks from queue")
        
        # Process each task
        agent_id = os.getenv("TODORAMA_AGENT_ID", "cursor-agent")
        created_tasks = []
        failed_tasks = []
        
        for task_data in tasks_to_process:
            try:
                # Create todorama task via MCP
                # Note: This requires MCP todorama service to be available
                # We'll use subprocess to call cursor-agent MCP todorama service
                # For now, we'll use a workaround: write to a file that the agent loop will process
                # The agent loop has direct access to MCP todorama
                
                # Store task metadata for agent loop to process
                task_metadata = {
                    "task_data": task_data,
                    "agent_id": agent_id,
                    "project_id": args.project_id,
                }
                
                # Write to a processing file that the agent loop will read
                processing_file = queue_file.parent / "user_interaction_tasks_pending.jsonl"
                with open(processing_file, "a") as f:
                    f.write(json.dumps(task_metadata) + "\n")
                
                # For now, mark as created (agent loop will actually create the task)
                created_tasks.append((task_data, None))
                logger.info(f"Queued task for agent loop to create: {task_data['title']}")
                print(f"✓ Queued task for creation: {task_data['title']}")
                    
            except Exception as e:
                failed_tasks.append((task_data, str(e)))
                logger.error(f"Error processing task: {e}", exc_info=True)
                print(f"✗ Error processing task: {e}")
        
        # Remove processed tasks from queue
        if created_tasks or failed_tasks:
            remaining_tasks = tasks[len(tasks_to_process):]
            
            # Write remaining tasks back to queue
            try:
                with open(queue_file, "w") as f:
                    for task in remaining_tasks:
                        f.write(json.dumps(task) + "\n")
                
                logger.info(f"Updated queue file: {len(remaining_tasks)} tasks remaining")
            except Exception as e:
                logger.error(f"Failed to update queue file: {e}", exc_info=True)
                print(f"WARNING: Failed to update queue file: {e}")
        
        # Summary
        remaining_count = len(remaining_tasks) if created_tasks or failed_tasks else len(tasks)
        print(f"\nSummary:")
        print(f"  Queued for creation: {len(created_tasks)} tasks")
        print(f"  Failed: {len(failed_tasks)} tasks")
        print(f"  Remaining in queue: {remaining_count} tasks")
        print(f"\nNote: Tasks are queued for the agent loop to create via MCP todorama.")
