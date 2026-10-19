## Argument Parsing and Path Validation

Here is the Python code snippet handling user input and validating file paths with non-zero exit on error:

```python
import sys
import argparse
import os

def parse_args():
    parser = argparse.ArgumentParser(description="Count lines, words, and characters in files.")
    parser.add_argument("files", nargs="+", help="One or more file paths")
    return parser.parse_args()

def validate_files(file_paths):
    """
    Validates that all provided paths exist.
    Exits with non-zero status if any file is missing.
    """
    for path in file_paths:
        if not os.path.exists(path):
            print(f"Error: File '{path}' does not exist.", file=sys.stderr)
            sys.exit(1)

# Main execution flow for this component
def main():
    args = parse_args()
    validate_files(args.files)
    
    # Proceed to counting logic (to be implemented in subsequent steps)
    # e.g., process_files(args.files)

if __name__ == "__main__":
    main()
```

## File Counting Logic

```python
import os

def count_metrics(filepath: str) -> dict:
    """
    Reads a file and returns its line, word, and character counts.
    
    Args:
        filepath (str): The path to the file to be processed.
        
    Returns:
        dict: A dictionary containing 'lines', 'words', and 'chars' counts.
        
    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be read due to permissions or other OS errors.
    """
    try:
        # Use 'r' mode with default encoding (usually utf-8) for text files.
        # 'ignore' errors might be safer for robustness, but strict utf-8 is standard.
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except FileNotFoundError:
        # Re-raise or let caller handle if not already checked
        raise
    except OSError:
        raise

    # Count characters: total length of the string
    char_count = len(content)
    
    # Count words: split by whitespace and filter non-empty parts
    # Using split() without arguments splits by any whitespace and handles multiple spaces/newlines
    word_count = len(content.split())
    
    # Count lines: split by newline characters
    # Note: This matches the behavior of 'wc -l' for standard files.
    # If the file ends with a newline, split('\n') might create an extra empty string at the end
    # if we are not careful, but 'wc -l' counts newlines.
    # Let's use splitlines() which handles various line endings and doesn't include trailing empty lines
    # as separate lines unless they contain content? No, splitlines splits at line boundaries.
    # 'wc -l' counts the number of newline characters.
    # To be most consistent with typical 'wc -l' behavior:
    line_count = content.count('\n')
    
    # If the file is not empty and does not end with a newline, 'wc -l' still counts the last line.
    # Actually, standard wc -l counts newlines. If there is text but no newline at the end, it counts that line.
    # A common way to match `wc -l` is:
    # lines = content.splitlines()
    # count = len(lines)
    # But let's stick to a simple robust definition often used in such tools:
    # Number of lines is number of newlines + 1 if there is content not ending in newline.
    # However, `content.count('\n')` is the direct definition of lines in POSIX terms often.
    # Let's use splitlines() as it is generally more robust for counting "visible" lines.
    line_count = len(content.splitlines())

    return {
        'lines': line_count,
        'words': word_count,
        'chars': char_count
    }
```

## Table Formatting and Output

### Table Formatting and Main Execution

To meet the requirement of printing results in a simple table, we define a `print_table` function that calculates the maximum width for each column based on the content and then prints the rows using Python's standard string formatting. This avoids external dependencies like `tabulate`.

```python
def print_table(results):
    """
    Prints a formatted table of file counts.
    
    Args:
        results: A list of tuples (filename, line_count, word_count, char_count)
    """
    if not results:
        return

    # Define headers
    headers = ["File", "Lines", "Words", "Chars"]
    
    # Determine column widths
    # Start with header widths
    widths = [len(h) for h in headers]
    
    # Update widths based on data
    for row in results:
        widths[0] = max(widths[0], len(row[0]))       # File
        widths[1] = max(widths[1], len(str(row[1])))  # Lines
        widths[2] = max(widths[2], len(str(row[2])))  # Words
        widths[3] = max(widths[3], len(str(row[3])))  # Chars
        
    # Create format string
    # e.g., "%-10s %5s %5s %5s"
    fmt_string = "  ".join(f"%-{w}s" for w in widths)
    separator = "  ".join("-" * w for w in widths)
    
    # Print header
    print(fmt_string % tuple(headers))
    print(separator)
    
    # Print rows
    for file_name, lines, words, chars in results:
        print(fmt_string % (file_name, lines, words, chars))

def main():
    args = parse_args()
    valid_files = validate_files(args.files)
    
    if not valid_files:
        # Handle case where no valid files exist if needed, though validate_files likely exits on error
        return

    results = []
    for file_path in valid_files:
        try:
            metrics = count_metrics(file_path)
            results.append((
                file_path, 
                metrics['lines'], 
                metrics['words'], 
                metrics['chars']
            ))
        except Exception as e:
            # If a file fails during reading (e.g. permission error after validation),
            # we might want to handle it gracefully or let it crash depending on strictness.
            # For this simple tool, we assume validation caught most issues or let it propagate.
            raise e

    print_table(results)

if __name__ == "__main__":
    main()
```

This code completes the tool by aggregating the metrics from `count_metrics` for all valid files and presenting them in a clean, aligned table structure as requested.

## wordcount.py

```py
#!/usr/bin/env python3
"""
wordcount: A simple CLI tool to count lines, words, and characters in files.

Usage:
    ./wordcount.py file1.txt file2.py ...
"""

import argparse
import os
import sys


def parse_args():
    """Parse command-line arguments to extract file paths."""
    parser = argparse.ArgumentParser(
        description="Count lines, words, and characters in specified files."
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="One or more file paths to process"
    )
    return parser.parse_args()


def validate_files(paths):
    """
    Validate that all provided file paths exist and are readable.
    Exits with code 1 if any path is invalid.
    
    Args:
        paths: List of file paths (strings).
        
    Returns:
        List of validated file paths.
    """
    valid_paths = []
    for path in paths:
        if not os.path.exists(path):
            print(f"Error: File '{path}' does not exist.", file=sys.stderr)
            sys.exit(1)
        if not os.path.isfile(path):
            print(f"Error: '{path}' is not a file.", file=sys.stderr)
            sys.exit(1)
        valid_paths.append(path)
    return valid_paths


def count_metrics(filepath):
    """
    Count lines, words, and characters in a file.
    
    Args:
        filepath: Path to the file.
        
    Returns:
        Dictionary with keys 'lines', 'words', 'chars'.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except FileNotFoundError:
        # Should be caught by validate_files, but handling here for robustness
        print(f"Error: File '{filepath}' not found during read.", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"Error reading '{filepath}': {e}", file=sys.stderr)
        sys.exit(1)
    
    lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    words = len(content.split())
    chars = len(content)
    
    return {
        "lines": lines,
        "words": words,
        "chars": chars
    }


def print_table(results):
    """
    Print a formatted table of results.
    
    Args:
        results: List of dictionaries, each containing 'file', 'lines', 'words', 'chars'.
    """
    if not results:
        return

    # Define headers
    headers = ["File", "Lines", "Words", "Chars"]
    
    # Prepare data rows
    rows = []
    for res in results:
        rows.append([
            res["file"],
            str(res["lines"]),
            str(res["words"]),
            str(res["chars"])
        ])
    
    # Calculate column widths
    col_widths = [0, 0, 0, 0]
    for h in headers:
        if len(h) > col_widths[headers.index(h)]:
            col_widths[headers.index(h)] = len(h)
            
    for row in rows:
        for i, val in enumerate(row):
            if len(val) > col_widths[i]:
                col_widths[i] = len(val)
                
    # Construct format string
    # Left-align file, right-align numbers for better readability
    fmt_row = f"{col_widths[0]}s  {col_widths[1]}s  {col_widths[2]}s  {col_widths[3]}s"
    fmt_num = f"{{:<{col_widths[0]}}}  {{:>{col_widths[1]}}}  {{:>{col_widths[2]}}}  {{:>{col_widths[3]}}}"
    
    # Print header
    print(f"{'File':<{col_widths[0]}}  {'Lines':>{col_widths[1]}}  {'Words':>{col_widths[2]}}  {'Chars':>{col_widths[3]}}")
    print("-" * (col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3] + 6)) # 2 spaces * 3 separators + separators
    
    # Print rows
    for row in rows:
        print(fmt_num.format(row[0], row[1], row[2], row[3]))


def main():
    """Main entry point for the wordcount CLI."""
    args = parse_args()
    
    # Validate paths
    valid_files = validate_files(args.files)
    
    # Process files
    results = []
    for filepath in valid_files:
        metrics = count_metrics(filepath)
        metrics["file"] = filepath
        results.append(metrics)
    
    # Output
    print_table(results)


if __name__ == "__main__":
    main()
```
