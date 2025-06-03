import configparser
import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Global dictionary to cache loaded prompt templates.
_PROMPT_TEMPLATES: Dict[str, Dict[str, Any]] = {}
# Define the path to the default prompts properties file, relative to this script.
_PROMPTS_FILE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'default_prompts.properties')

def _load_prompts_from_file(file_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Loads prompt templates from a specified .properties file.

    The .properties file is expected to have a [Prompts] section.
    Each prompt is defined by three keys using a common prefix:
    - `<prefix>_id`: The unique identifier for the prompt (e.g., "assess_task_v1").
    - `<prefix>_description`: A human-readable description of the prompt.
    - `<prefix>_template`: The actual prompt template string, which may contain
                           placeholders like {placeholder_name}.

    Example:
        assess_task_v1_id = assess_task_v1
        assess_task_v1_description = Describes what this prompt does.
        assess_task_v1_template = Your prompt text with {variable}.

    Args:
        file_path: The absolute or relative path to the .properties file.

    Returns:
        A dictionary where keys are prompt IDs and values are dictionaries
        containing "id", "description", and "template" for each prompt.
        Returns an empty dictionary if the file is not found, cannot be parsed,
        or contains no valid prompts.
    """
    parser = configparser.ConfigParser()
    # Ensure file is read with UTF-8 encoding to support various characters in prompts.
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            parser.read_file(f)
    except FileNotFoundError:
        logger.error(f"Prompts file not found: {file_path}")
        return {}
    except Exception as e:
        logger.error(f"Error reading prompts file {file_path}: {e}", exc_info=True)
        return {}

    loaded_prompts: Dict[str, Dict[str, Any]] = {}
    if 'Prompts' in parser:
        prompt_section = parser['Prompts']
        # Group keys by prompt ID prefix (e.g., "assess_task_v1_")
        keys_by_id: Dict[str, Dict[str, str]] = {}
        for key in prompt_section:
            if key.count('_') >= 2: # Expecting at least two underscores (e.g., prefix_id_field)
                parts = key.rsplit('_', 1)
                prompt_key_prefix = parts[0] # e.g., "assess_task_v1"
                field_name = parts[1]        # e.g., "id", "description", "template"

                if prompt_key_prefix not in keys_by_id:
                    keys_by_id[prompt_key_prefix] = {}
                keys_by_id[prompt_key_prefix][field_name] = prompt_section[key]

        for prompt_key_prefix, fields in keys_by_id.items():
            # The 'actual_prompt_id' is the value from the '<prefix>_id' key in the properties file.
            # This becomes the key in our _PROMPT_TEMPLATES dictionary.
            actual_prompt_id = fields.get('id')
            if not actual_prompt_id:
                logger.warning(f"Prompt definition for key group '{prompt_key_prefix}' is missing an '_id' field (e.g., '{prompt_key_prefix}_id') in {file_path}. Skipping this group.")
                continue
            if 'template' not in fields:
                logger.warning(f"Prompt definition for '{actual_prompt_id}' (from group '{prompt_key_prefix}') is missing a '_template' field in {file_path}. Skipping.")
                continue

            # Store the prompt details, ensuring the template text is stripped of leading/trailing whitespace.
            loaded_prompts[actual_prompt_id] = {
                "id": actual_prompt_id, # Store the ID for consistency, though it's also the key.
                "description": fields.get("description", ""), # Optional description.
                "template": fields["template"].strip()
            }
            logger.info(f"Successfully loaded prompt '{actual_prompt_id}' from {file_path}")
    else:
        logger.warning(f"No [Prompts] section found in {file_path}")

    return loaded_prompts

def _initialize_prompts():
    """Initializes the global _PROMPT_TEMPLATES dictionary by loading from file."""
    global _PROMPT_TEMPLATES
    if not _PROMPT_TEMPLATES: # Load only once
        _PROMPT_TEMPLATES = _load_prompts_from_file(_PROMPTS_FILE_PATH)
        if not _PROMPT_TEMPLATES:
            logger.error("No prompts were loaded. Prompt system may not function correctly.")

# Call initialization when the module is loaded.
_initialize_prompts()

def get_prompt(prompt_id: str, **kwargs) -> Optional[str]:
    """
    Retrieves a prompt template by its ID and formats it with provided arguments.
    Prompts are loaded from the properties file on first call or module import.

    Args:
        prompt_id: The unique identifier for the prompt template (e.g., "assess_task_v1").
        **kwargs: Keyword arguments to fill in placeholders in the prompt template.

    Returns:
        The formatted prompt string if the prompt_id exists and formatting is successful,
        otherwise None.
    """
    if not _PROMPT_TEMPLATES: # Ensure prompts are loaded if _initialize_prompts failed silently or was deferred
            _initialize_prompts() # Attempt to load again if empty (e.g. for tests that might clear it)

    template_info = _PROMPT_TEMPLATES.get(prompt_id)
    if template_info:
        try:
            return template_info["template"].format(**kwargs)
        except KeyError as e:
            logger.error(f"Error formatting prompt '{prompt_id}': Missing placeholder key '{e}' in provided arguments. Template expected: {template_info['template']}", exc_info=False)
            return None
        except Exception as e_fmt:
            logger.error(f"Unexpected error formatting prompt '{prompt_id}': {e_fmt}", exc_info=True)
            return None
    else:
        logger.warning(f"Prompt template with ID '{prompt_id}' not found.")
        return None

# The if __name__ == '__main__' block for testing get_prompt will be moved to a dedicated test file.
