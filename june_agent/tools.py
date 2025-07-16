import subprocess

def save_file(filename: str, content: str):
    """
    Saves content to a file.

    Args:
        filename (str): The name of the file to save.
        content (str): The content to save to the file.
    """
    with open(filename, "w") as f:
        f.write(content)
    return f"File {filename} saved successfully."

def run_python(code: str):
    """
    Runs a Python script and returns the output.

    Args:
        code (str): The Python code to run.
    """
    result = subprocess.run(['python', '-c', code], capture_output=True, text=True)
    return result.stdout
