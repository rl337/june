# june_agent/prompts.py

# For now, prompts are stored in a Python dictionary.
# In the future, these could be loaded from YAML files, a database, etc.

# Placeholders like {task_description} will be filled in dynamically.
from typing import Optional # Added for type hinting

PROMPT_TEMPLATES = {
    "assess_task_v1": {
        "id": "assess_task_v1",
        "description": "A prompt to assess a given task and determine the best course of action.",
        "template": """
You are an AI assistant helping to process tasks. Your goal is to assess the following task and determine the best way to handle it.

Task Description:
---
{task_description}
---

Please analyze this task and respond in JSON format with the following structure:
{
  "assessment_outcome": "string (either 'direct_completion', 'subtask_breakdown', or 'cannot_complete')",
  "result_payload": "string or list of strings (details below)",
  "reasoning": "string (your brief reasoning for the outcome)",
  "confidence_score": "float (0.0 to 1.0, optional)"
}

Details for "result_payload":
- If "assessment_outcome" is "direct_completion": "result_payload" should be a string containing the direct result of completing the task.
- If "assessment_outcome" is "subtask_breakdown": "result_payload" should be a list of strings, where each string is a description for a proposed subtask. Aim for 2-5 subtasks if a breakdown is needed.
- If "assessment_outcome" is "cannot_complete": "result_payload" should be a string explaining why the task cannot be completed.

Example 1 (Direct Completion):
Task Description: "What is the capital of France?"
Your JSON Response:
{
  "assessment_outcome": "direct_completion",
  "result_payload": "Paris",
  "reasoning": "This is a simple factual question that can be answered directly.",
  "confidence_score": 0.99
}

Example 2 (Subtask Breakdown):
Task Description: "Write a short story about a robot learning to paint."
Your JSON Response:
{
  "assessment_outcome": "subtask_breakdown",
  "result_payload": [
    "Outline the main plot points for the story.",
    "Develop the main character of the robot, including its motivations.",
    "Write the first draft of the story.",
    "Review and revise the story for clarity and engagement."
  ],
  "reasoning": "Writing a story involves multiple steps, making subtasks appropriate.",
  "confidence_score": 0.90
}

Example 3 (Cannot Complete):
Task Description: "Predict tomorrow's exact stock market closing price for AAPL."
Your JSON Response:
{
  "assessment_outcome": "cannot_complete",
  "result_payload": "Predicting exact stock market prices with certainty is not possible due to market volatility and numerous unpredictable factors.",
  "reasoning": "This task requires predicting a highly unpredictable future event.",
  "confidence_score": 0.95
}

Now, please provide your JSON response for the task described above.
"""
    },
    # Add more prompt templates here as needed, e.g., for specific types of tasks or models.
}

def get_prompt(prompt_id: str, **kwargs) -> Optional[str]:
    """
    Retrieves a prompt template by its ID and formats it with provided arguments.

    Args:
        prompt_id: The unique identifier for the prompt template.
        **kwargs: Keyword arguments to fill in placeholders in the prompt template.

    Returns:
        The formatted prompt string if the prompt_id exists, otherwise None.
    """
    template_info = PROMPT_TEMPLATES.get(prompt_id)
    if template_info:
        try:
            return template_info["template"].format(**kwargs)
        except KeyError as e:
            # Handle missing keys in kwargs if a placeholder is not provided
            # Or, ensure all placeholders are always provided by the caller.
            print(f"Error formatting prompt '{prompt_id}': Missing key {e}") # Or log this
            return None # Or raise an error
    return None

if __name__ == '__main__':
    # Example usage:
    task_desc_example = "Plan a three-day trip to a nearby city, including finding accommodation, transport, and three activities per day."

    formatted_prompt = get_prompt("assess_task_v1", task_description=task_desc_example)

    if formatted_prompt:
        print("--- Formatted Prompt (assess_task_v1) ---")
        print(formatted_prompt)
    else:
        print("Prompt 'assess_task_v1' not found or formatting error.")

    # Example with a non-existent prompt ID
    non_existent_prompt = get_prompt("non_existent_v1", task_description="Test")
    if not non_existent_prompt:
        print("\n--- Test for non-existent prompt ID ---")
        print("Prompt 'non_existent_v1' correctly not found or error during formatting.")

    # Example with missing placeholder
    error_prompt = get_prompt("assess_task_v1") # Missing task_description
    if not error_prompt:
        print("\n--- Test for missing placeholder ---")
        print("Prompt 'assess_task_v1' formatting error due to missing placeholder handled correctly.")
