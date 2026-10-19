# Real pairs R1–R5: the user's labels (Q-01 design note § 4)

Source: `20261019T051008Z_rebaseline-0-16_s1_cli_code-s1b_csv2json_cli-s1c_logscan_cli-s2_report-s3_followup-s4_anchors.json`, run 0 (candidate A) against run 1 (candidate B), harness output both sides.
For each pair, fill the `label:` line with `A`, `B` or `tie`. Your label is the standard the judge is scored against (Q-1); the judge later sees both orders.

## R1 — s1_cli_code, turn 0

label: 

**Task:**

Write a small CLI tool in Python called "wordcount" that, given one or more file paths, prints for each file: line count, word count, and character count, in a simple table. It should exit non-zero if a path does not exist. Provide the code.

### R1 candidate A (run 0)

### wordcount.py

#!/usr/bin/env python3
"""
wordcount - A simple CLI tool to count lines, words, and characters in files.
Usage: wordcount file1.txt file2.txt ...
"""

import sys
import os

def main():
    # Check if file arguments were provided
    if len(sys.argv) < 2:
        print("Usage: wordcount <file1> [file2 ...]")
        sys.exit(1)

    # List to store results
    results = []
    error_occurred = False

    for filepath in sys.argv[1:]:
        if not os.path.isfile(filepath):
            print(f"Error: '{filepath}' does not exist or is not a regular file.", file=sys.stderr)
            error_occurred = True
            continue

        try:
            # Read file content
            with open(filepath, 'r', errors='ignore') as f:
                content = f.read()

            # Calculate counts
            # Splitlines() handles different line endings properly
            lines = len(content.splitlines())
            # split() without args splits by any whitespace and removes empty strings
            words = len(content.split())
            chars = len(content)

            results.append({
                'filename': filepath,
                'lines': lines,
                'words': words,
                'chars': chars
            })
        except Exception as e:
            print(f"Error reading '{filepath}': {e}", file=sys.stderr)
            error_occurred = True

    # If no valid files were processed, exit with error
    if not results:
        if error_occurred:
            sys.exit(1)
        else:
            sys.exit(0)

    # Determine column widths for table formatting
    # Headers
    headers = ["Filename", "Lines", "Words", "Chars"]
    
    # Max widths
    col_filename = max(len(headers[0]), max(len(r['filename']) for r in results))
    col_lines = max(len(headers[1]), max(len(str(r['lines'])) for r in results))
    col_words = max(len(headers[2]), max(len(str(r['words'])) for r in results))
    col_chars = max(len(headers[3]), max(len(str(r['chars'])) for r in results))

    # Define format string
    # Left align filename, right align numbers
    fmt_str = f"{{:<{col_filename}}} {{:>{col_lines}}} {{:>{col_words}}} {{:>{col_chars}}}"

    # Print Header
    print(fmt_str.format(headers[0], headers[1], headers[2], headers[3]))
    print("-" * (col_filename + col_lines + col_words + col_chars + 3)) # separator line

    # Print Rows
    for r in results:
        print(fmt_str.format(r['filename'], r['lines'], r['words'], r['chars']))

    # Exit with non-zero status if any error occurred during processing
    if error_occurred:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()

### R1 candidate B (run 1)

### Argument Parsing and Path Validation

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

### File Counting Logic

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

### Table Formatting and Output

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

### wordcount.py

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

## R2 — s1b_csv2json_cli, turn 0

label: 

**Task:**

Write a small CLI tool in Python called "csv2json" that, given a path to a CSV file, prints the rows as a JSON array of objects (header row = keys) to stdout. Flag "--indent" for pretty-printing. Exit non-zero if the file is missing or empty. Provide the code.

### R2 candidate A (run 0)

### csv2json.py

```python
import sys
import argparse
import csv
import json
import os

def main():
    parser = argparse.ArgumentParser(description='Convert CSV to JSON.')
    parser.add_argument('file', help='Path to the CSV file')
    parser.add_argument('--indent', type=int, nargs='?', const=2, help='Indentation level for pretty-printing JSON (default: 2 if flag is present)')
    
    args = parser.parse_args()
    
    # Check if file exists
    if not os.path.exists(args.file):
        sys.stderr.write(f"Error: File '{args.file}' not found.\n")
        sys.exit(1)
        
    # Check if file is empty
    if os.path.getsize(args.file) == 0:
        sys.stderr.write(f"Error: File '{args.file}' is empty.\n")
        sys.exit(1)

    # Convert CSV data to JSON structure
    try:
        with open(args.file, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = list(reader)
            
        # Output JSON with indentation support
        indent = args.indent
        print(json.dumps(data, indent=indent))
    except Exception as e:
        sys.stderr.write(f"Error processing file: {e}\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

### Output JSON with indentation support

```python
        # Output JSON with indentation support
        indent = args.indent
        print(json.dumps(data, indent=indent))
```

### Finalize script with shebang and execution block

```python
#!/usr/bin/env python3
import sys
import argparse
import csv
import json
import os

def main():
    parser = argparse.ArgumentParser(description='Convert CSV to JSON.')
    parser.add_argument('file', help='Path to the CSV file')
    parser.add_argument('--indent', type=int, nargs='?', const=2, help='Indentation level for pretty-printing JSON (default: 2 if flag is present)')
    
    args = parser.parse_args()
    
    # Check if file exists
    if not os.path.exists(args.file):
        sys.stderr.write(f"Error: File '{args.file}' not found.\n")
        sys.exit(1)
        
    # Check if file is empty
    if os.path.getsize(args.file) == 0:
        sys.stderr.write(f"Error: File '{args.file}' is empty.\n")
        sys.exit(1)

    # Convert CSV data to JSON structure
    try:
        with open(args.file, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = list(reader)
            
        # Output JSON with indentation support
        indent = args.indent
        print(json.dumps(data, indent=indent))
    except Exception as e:
        sys.stderr.write(f"Error processing file: {e}\n")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

### R2 candidate B (run 1)

### Core CSV-to-JSON Logic

```python
import csv

def csv_to_json_records(file_path: str) -> list[dict]:
    """
    Reads a CSV file and converts it into a list of dictionaries.
    The first row is treated as the header (keys).
    
    Args:
        file_path (str): Path to the CSV file.
        
    Returns:
        list[dict]: A list where each item is a dictionary mapping
                    header names to the corresponding row values.
    """
    records = []
    try:
        with open(file_path, mode='r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                records.append(row)
    except FileNotFoundError:
        raise FileNotFoundError(f"The file {file_path} does not exist.")
    except Exception as e:
        raise e
        
    return records
```

### CLI Implementation

```python
import argparse
import json
import sys

# Assume csv_to_json_records is defined/imported as per previous section
# from core_logic import csv_to_json_records

def main():
    parser = argparse.ArgumentParser(description="Convert CSV file to JSON array of objects.")
    parser.add_argument("file_path", help="Path to the CSV file")
    parser.add_argument("--indent", type=int, default=None, help="Indent spaces for pretty-printing")

    args = parser.parse_args()

    try:
        records = csv_to_json_records(args.file_path)
    except FileNotFoundError:
        sys.stderr.write(f"Error: The file '{args.file_path}' does not exist.\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error reading file: {e}\n")
        sys.exit(1)

    # Check if records is empty (covers empty file or header-only file depending on interpretation)
    if not records:
        sys.stderr.write(f"Error: The file '{args.file_path}' is empty or contains no data rows.\n")
        sys.exit(1)

    json_output = json.dumps(records, indent=args.indent)
    print(json_output)

if __name__ == "__main__":
    main()
```

### Error Handling

The `csv2json` CLI implementation includes the necessary validation checks to handle missing or empty files. 

1. **File Existence Check**: The code wraps the call to `csv_to_json_records(args.file_path)` in a `try...except` block. If a `FileNotFoundError` is raised, it prints an error message to `stderr` and exits with a non-zero status code (`sys.exit(1)`).

2. **Empty File/Data Check**: After retrieving the records, it checks if the returned list is empty (`if not records:`). This handles cases where the file is empty or contains only headers (resulting in no data rows). If empty, it prints an error to `stderr` and exits with `sys.exit(1)`.

Both checks ensure the tool fails gracefully with appropriate error messages and non-zero exit codes, satisfying the requirement to exit non-zero if the file is missing or empty.

### csv2json.py

```python
#!/usr/bin/env python3
import csv
import json
import argparse
import sys

def csv_to_json_records(file_path: str) -> list[dict]:
    """
    Reads a CSV file and converts it into a list of dictionaries.
    The first row is treated as the header (keys).
    
    Args:
        file_path (str): Path to the CSV file.
        
    Returns:
        list[dict]: A list where each item is a dictionary mapping
                    header names to the corresponding row values.
    """
    records = []
    try:
        with open(file_path, mode='r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                records.append(row)
    except FileNotFoundError:
        raise FileNotFoundError(f"The file {file_path} does not exist.")
    except Exception as e:
        raise e
        
    return records

def main():
    parser = argparse.ArgumentParser(description="Convert CSV file to JSON array of objects.")
    parser.add_argument("file_path", help="Path to the CSV file")
    parser.add_argument("--indent", type=int, default=None, help="Indent spaces for pretty-printing")

    args = parser.parse_args()

    try:
        records = csv_to_json_records(args.file_path)
    except FileNotFoundError:
        sys.stderr.write(f"Error: The file '{args.file_path}' does not exist.\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error reading file: {e}\n")
        sys.exit(1)

    # Check if records is empty (covers empty file or header-only file depending on interpretation)
    if not records:
        sys.stderr.write(f"Error: The file '{args.file_path}' is empty or contains no data rows.\n")
        sys.exit(1)

    json_output = json.dumps(records, indent=args.indent)
    print(json_output)

if __name__ == "__main__":
    main()
```

## R3 — s2_report, turn 0

label: 

**Task:**

Write a short internal report (about 300-500 words total) on why a team of four engineers should adopt a file-based ticketing system (markdown files in git) instead of an external issue tracker. Cover: cost and hosting, searchability, review culture, and one honest drawback. Use clear section headings.

### R3 candidate A (run 0)

### Cost and Hosting

## Cost and Hosting

Adopting a file-based ticketing system using markdown files in Git offers significant financial and operational advantages over traditional external issue trackers. First and foremost, this approach eliminates recurring subscription fees. Popular external issue trackers often charge per user per month, creating a direct financial scaling penalty as the team grows or when contractors are added. By contrast, storing tickets as markdown files incurs zero incremental licensing costs, regardless of the number of engineers accessing the system.

Secondly, this model requires no separate infrastructure management. External SaaS platforms, while managed, still require administrative overhead for permission management, integration maintenance, and sometimes data export compliance. A git-based system leverages the existing Git hosting infrastructure (such as GitHub, GitLab, or Bitbucket) that the engineering team already utilizes for code. There is no need to spin up or maintain a separate database or web application for ticketing. This reduces the "surface area" of third-party dependencies we must vet, monitor, and integrate.

Finally, because the tickets live in the same repository as the code, the hosting workflow is unified. Engineers do not need to switch contexts to different web portals to update ticket status. Commits that resolve tickets automatically link to the markdown files, providing built-in traceability without complex API integrations. This synergy not only reduces hosting complexity but also streamlines the developer experience, keeping the ticketing system as lightweight and accessible as the codebase itself.

### Searchability and Review Culture

### Searchability and Review Culture

One of the most underrated advantages of storing tickets as Markdown files is native searchability. In a traditional issue tracker, finding an old discussion often requires navigating a UI with limited filtering options, relying on specific tags or IDs that may be inconsistent or forgotten. In a file-based system, every ticket is just text in the repository. This means you can use your existing developer tools—`grep`, IDE project-wide search, or command-line utilities like `ripgrep`—to find any mention of a keyword, error code, or API endpoint instantly. There is no separate search index to learn or latency to endure; the search is local, fast, and integrated directly into your workflow.

This accessibility directly strengthens our review culture. Because tickets live in Git, they can be referenced and linked to Pull Requests naturally. For instance, a developer can include `Refs: #tickets/login-flow.md` in a commit message or PR description, creating a bidirectional link between the problem definition and the solution. This integration encourages engineers to treat ticket updates with the same rigor as code changes. If a scope change occurs, it should be documented in the Markdown file within the PR, ensuring that the "why" behind the code is preserved alongside the "what." This makes code reviews more meaningful, as reviewers can immediately see the historical context and decision-making recorded in the ticket files, rather than relying on fragmented comments in external platforms.

### Drawback and Conclusion

## Drawback

The most significant limitation of a file-based ticketing system is its lack of accessibility for non-developers. External issue trackers like Jira or Linear provide graphical user interfaces that allow product managers, designers, and stakeholders to interact with tickets—assigning owners, changing statuses, or adding comments—without needing to understand Git workflows or Markdown syntax. By requiring tickets to exist as files in a repository, we effectively gatekeep issue management to those comfortable with version control tools. For a four-person engineering team where non-technical stakeholders might need visibility or input, this friction can be a major hurdle. Additionally, there is the initial UI overhead; without a dedicated dashboard, tracking high-level metrics like burndown charts or sprint velocity requires manual effort or custom scripting, whereas external tools provide these views out of the box.

## Conclusion

For our four-person team, a file-based ticketing system offers a compelling balance of cost efficiency and developer-centric workflow integration. By eliminating SaaS subscription costs and leveraging our existing Git infrastructure, we simplify our budget. Furthermore, embedding tickets directly into our codebase enhances searchability and integrates issue resolution seamlessly into our code review culture. However, we must be honest about the trade-off: this approach assumes all relevant parties are developers comfortable with Git. If we anticipate needing significant input from non-technical stakeholders or require robust reporting dashboards immediately, the friction introduced by Markdown and Git workflows may outweigh the benefits. Ultimately, if our current team composition remains strictly technical and we prioritize low overhead and tight integration over rich UI features, this model is a strong, pragmatic choice.

### R3 candidate B (run 1)

### report-main

# Why a Team of Four Should Adopt File-Based Ticketing

## Introduction
For a small, high-velocity team of four engineers, the overhead of traditional issue trackers often outweighs their convenience. This report outlines why transitioning to a file-based ticketing system—using markdown files within our existing git repository—is a superior operational strategy. By integrating tickets directly into our codebase, we optimize for speed, cost, and engineering rigor.

## Cost and Hosting
A file-based ticketing system eliminates recurring SaaS subscription fees entirely. Tools like Jira, Linear, or GitHub Issues charge per-user or per-month pricing that compounds for a four-person team—easily $20-50 per seat monthly, plus potential add-ons for integrations or storage. By storing tickets as markdown files inside the existing git repository, we leverage infrastructure we already run and maintain. No separate service to configure, no SSO to integrate, no vendor lock-in to negotiate. Maintenance overhead drops to zero beyond what we already do: git operations we use daily. The marginal cost of adding ticket files is essentially zero, making this the economically smallest-footprint option available for a small engineering team.

## Searchability
Because tickets are plain markdown files, your entire ticket history is indexed locally. Engineers can use `grep`, `rg`, or IDE search to find issues by error codes, function names, or commit hashes in milliseconds, rather than waiting for web-based trackers to render filtered lists. This enables powerful regex searches directly in the terminal, allowing you to query complex relationships between tickets and code. There is no need to context-switch to a browser or navigate through slow UIs. This seamless integration fits naturally into existing developer workflows, making it easy to pull related tickets into code reviews or scripts. When a bug arises, the developer can immediately search the repository for historical context, significantly reducing debugging time.

## Review Culture
Adopting a pull-request-based workflow for tickets fundamentally shifts how we discuss work. Just as code requires review before merging, each ticket—whether a feature spec, bug report, or architectural decision—becomes a file requiring explicit approval. This enforces peer review, ensuring that proposals are scrutinized by at least one other engineer before acceptance. The resulting history is not merely a log of status updates but a clear, immutable record of *why* decisions were made, tied directly to the specific lines of discussion and context. This structure significantly reduces ambiguity; instead of vague comment threads that disappear into the void, every change is versioned and traceable. We gain transparency into the evolution of ideas, preventing scope creep and fostering a shared understanding that persists long after the initial conversation.

## Honest Drawback: Visibility for Non-Technical Stakeholders
The primary limitation of file-based ticketing is the lack of intuitive visual interfaces for non-engineers. Without drag-and-drop Kanban boards or polished dashboards, product managers and stakeholders cannot quickly grasp project status without git access or engineering assistance. This creates a communication barrier that external trackers solve out-of-the-box.

However, for a team of four engineers, the gains in speed, cost savings, and rigorous review culture outweigh this visibility trade-off. We recommend adopting the file-based system, with the explicit understanding that we will maintain a lightweight, manually updated summary file for stakeholder visibility.

## R4 — s3_followup, turn 1

label: 

**Task:**

Extend the report: add a section on how to migrate an existing set of tickets from an external tracker to the file-based system, including a concrete migration plan with three steps. Keep the existing sections accurate and do not repeat their content.

### R4 candidate A (run 0)

### File-Based Ticketing Systems: Overview, Benefits, and Drawbacks

### 1. System Definition

A file-based ticketing system is a lightweight issue-tracking mechanism that stores each support ticket as a discrete file within a local or networked filesystem, rather than in a traditional relational database. This architecture leverages the operating system’s native file management capabilities. Typically, the directory structure reflects the workflow status, with subdirectories such as `open/` and `closed/` indicating the lifecycle stage of each ticket. Within this structure, file metadata plays a crucial role: the filename often acts as a unique identifier, the file content contains the issue description and subsequent comments, and the modification timestamp provides a built-in audit trail of updates. This design prioritizes simplicity, utilizing standard file operations for creation, movement, and deletion.

### 2. Primary Benefits

The most significant advantage of this approach is its architectural simplicity. By eliminating the need for a dedicated database server, installation and maintenance overhead is drastically reduced. This makes the system ideal for small teams, embedded environments, or projects requiring minimal dependency management. Furthermore, data portability and backup are exceptionally straightforward; a ticketing system can be backed up or migrated simply by copying directories or creating a zip archive. Version control systems like Git can also integrate seamlessly, allowing ticket history to be tracked alongside code changes. This transparency and ease of access foster a developer-friendly environment where troubleshooting tickets directly in the file structure is intuitive.

### 3. Key Drawbacks

Despite their utility for small-scale operations, file-based systems face significant scalability challenges. Concurrency control is a primary limitation; simultaneous updates to the same file can lead to data conflicts or loss without sophisticated locking mechanisms, which are difficult to implement reliably in a filesystem. Additionally, search performance degrades as the volume of tickets grows. Unlike databases optimized for indexed queries, searching across thousands of files for specific keywords or metadata requires scanning the filesystem, which is computationally expensive. Finally, enforcing complex validation rules, user permissions, and relational consistency is cumbersome and error-prone, making this model less suitable for large enterprises with strict compliance or high-volume traffic requirements.

### Migrating Existing Tickets

## Migrating Existing Tickets

Transitioning from a traditional external issue tracker (such as Jira, GitHub Issues, or GitLab) to a file-based ticketing system requires a structured approach to ensure data integrity and workflow continuity. The migration process involves moving all existing ticket data into the new directory-based structure while preserving critical metadata. This can be achieved through a three-step process: Extraction, Mapping, and Import/Validation.

### Step 1: Extraction
The first phase involves identifying and exporting all existing tickets from the source tracker. Most external systems provide API endpoints or bulk export features for this purpose. The goal is to retrieve comprehensive data for every ticket, including:
*   Unique ID
*   Title
*   Description
*   Status
*   Priority
*   Assignee
*   Creation and Modification dates
*   Full comment history

The raw extracted data should be stored in a structured intermediate format, such as JSON, CSV, or XML, to serve as the source for the subsequent transformation phase.

### Step 2: Mapping
Once the data is extracted, it must be mapped to the native file system characteristics of the destination system. This step translates database rows into file objects:
*   **Identifier:** Convert the external ticket ID and title into a sanitized, unique file name (e.g., `ticket-1234_short-title.txt`).
*   **Content:** Format the description and comments into the file body. Use a consistent delimiter to separate the main description from the chronological comment log.
*   **Metadata:** Prepare modification timestamps from the external tracker to be used for updating file system timestamps after import. This ensures the original audit trail is preserved.
*   **Status Mapping:** Map external status values to the directory structure of the file-based system (e.g., "Open" maps to `/tickets/open/`, "Closed" to `/tickets/closed/`, and "In Progress" to `/tickets/active/`).

### Step 3: Import/Validation
The final phase involves creating the physical files and verifying their integrity:
1.  **Directory Creation:** Create the necessary directory structure (`/tickets/open/`, `/tickets/closed/`, etc.) to mirror the workflow status as defined in the mapping phase.
2.  **File Writing:** Write the formatted data from the intermediate storage into individual files within their respective status directories.
3.  **Timestamp Application:** Apply the original modification timestamps to each file to replicate the external tracker's audit trail.
4.  **Validation:** Verify that the total count of created files matches the extracted tickets. Perform spot checks to ensure content integrity and correct directory placement.

By following these steps, teams can effectively migrate their existing workflows into a lightweight, file-based system without losing historical context or data fidelity.

### R4 candidate B (run 1)

### final-report

{", ": "File-Based Ticketing Systems: An Overview\n\nA file-based ticketing system is a lightweight issue-tracking solution that stores support tickets as individual text files in a shared directory. Unlike complex database-driven platforms, these systems rely on basic file operations, offering an accessible entry point for small teams. However, while their architectural simplicity offers distinct advantages, it also introduces significant operational limitations as demand grows.\n\nKey Advantages\n\nThe primary appeal of file-based ticketing lies in its simplicity and low cost. By eliminating the need for proprietary software licenses, dedicated servers, or complex installations, organizations can implement the system almost instantly using existing network drives. This architecture ensures transparency and portability; tickets are human-readable files (such as Markdown or plain text) that are easily backed up, version-controlled via Git, and migrated without data conversion issues. Furthermore, the barrier to entry is minimal, as team members require no specialized training to manage files using standard tools like text editors or file explorers.\n\nMain Drawbacks\n\nDespite these benefits, file-based systems face critical scalability and functionality challenges. Performance degrades as ticket volume increases, with directory scanning and file management becoming prohibitively slow. This model lacks native automation capabilities, forcing administrators to manually route tickets, update statuses, and track deadlines, which increases workload and error rates. Additionally, searchability is poor; unlike indexed databases, finding specific tickets often requires scanning file contents, making complex filtering and reporting inefficient.\n\nConclusion\n\nFile-based ticketing systems are an excellent, cost-effective solution for small organizations or low-volume environments where simplicity is paramount. However, due to severe scalability constraints and a lack of automation, they become impractical for growing enterprises that require robust reporting, workflow efficiency, and high-volume performance."}

### migration-mapping-strategy

## Migration Mapping: External Tracker to File-Based System

To ensure data integrity during migration, define a clear mapping between the source tracker's database fields and the target file-based system's attributes. The following schema maps common fields from a typical external tracker (e.g., Jira, GitHub Issues) to the file-based structure, utilizing YAML front matter for metadata and file content for the body.

### Target File Structure
Each ticket is represented as a single Markdown (`.md`) file. Metadata is stored in YAML front matter at the top of the file, while the description and comments are stored in the Markdown body. Files are organized into folders based on status or assignee.

### Field Mapping Table

| Source Field (External Tracker) | Target Attribute | Format / Location | Notes |
| :--- | :--- | :--- | :--- |
| **Unique ID** (e.g., PROJ-123) | `ticket_id` | YAML front matter: `ticket_id: "PROJ-123"` | Used for unique identification and linking. |
| **Title/Summary** | `title` | YAML front matter: `title: "Fix login bug"` <br> Markdown H1: `# Fix login bug` | Duplicated in front matter for machine parsing and as H1 for human readability. |
| **Status** (e.g., Open, Done) | `status` | YAML front matter: `status: "open"` <br> **Folder**: `/tickets/open/` | Status determines both the YAML value and the file's directory location for easy visual scanning. |
| **Priority** (e.g., High, Low) | `priority` | YAML front matter: `priority: 1` | Normalized to integers (1=High, 2=Medium, 3=Low) for consistent sorting. |
| **Assignee** | `assignee` | YAML front matter: `assignee: "jdoe"` | Stored as username. If unassigned, use `assignee: null` or omit. |
| **Reporter** | `reporter` | YAML front matter: `reporter: "asmith"` | Preserves original author information. |
| **Created Date** | `created_at` | YAML front matter: `created_at: "2023-10-27T10:00:00Z"` | Stored in ISO 8601 format for consistent sorting and filtering. |
| **Updated Date** | `updated_at` | YAML front matter: `updated_at: "2023-11-01T14:30:00Z"` | Last modified timestamp from the source system. |
| **Description** | `body` | Markdown body (below front matter) | Cleaned HTML/Markdown converted to standard Markdown. |
| **Labels/Tags** | `labels` | YAML front matter: `labels: ["bug", "ui"]` | Array of strings. Useful for grouping and search. |
| **Comments** | `comments` | Markdown section in body: `## Comments` | Each comment converted to a sub-section with author/timestamp headers. |

### Migration Logic Notes
1. **Normalization**: Convert mixed-case statuses (e.g., "In Progress") to lowercase, space-free slugs (e.g., "in_progress") for consistent YAML values and folder names.
2. **Date Handling**: Ensure all timestamps are converted to UTC ISO 8601 format to prevent timezone ambiguities.
3. **File Naming**: Use a convention of `{ticket_id}-{slugified-title}.md` to ensure uniqueness and readability in file explorers.
4. **Attachments**: Move any file attachments to a dedicated `/attachments/` folder and reference them in the Markdown body or front matter list.

### Operational Migration Plan

## Operational Migration Plan: Step-by-Step Execution

While the previous section defined the *target schema* for file-based tickets, this section outlines the *operational process* required to move live data from an external tracker (e.g., Jira, GitHub Issues, or a legacy SQL database) into that structure. This three-step plan ensures data fidelity and minimizes service interruption.

### Step 1: Data Extraction and Backup

Before any transformation occurs, a complete snapshot of the source data must be secured. This step is critical for rollback capability if the migration fails or corrupts data.

1.  **Full Database/State Export**: Use the external tracker’s native export API or command-line tools to dump all relevant ticket data. For SQL-based trackers, generate a full `.sql` dump or CSV export of the `issues`, `comments`, and `attachments` tables. For SaaS platforms like Jira or GitHub, use their respective CLI tools (e.g., `gh api`, `jira-cli`) to fetch all issues as JSON.
2.  **Attachment Preservation**: Download all linked file attachments to a temporary local directory (e.g., `./migration_workspace/attachments/`). Ensure file integrity by recording checksums (MD5/SHA256) for each attachment.
3.  **Verification of Source**: Spot-check 5–10 random tickets in the export to ensure no fields are truncated and special characters are preserved.
4.  **Immutable Backup**: Copy the raw export and attachments to a secure, read-only backup location (e.g., S3 Glacier, external drive) with a timestamped directory name (e.g., `backup_2023-11-05T12:00Z/`). Do not modify these files.

### Step 2: Transformation and Scripting

Using the mapping schema defined in the previous section, build and execute a conversion script. This step transforms the raw source data into the file-based `.md` structure.

1.  **Script Development**: Write a script (Python, Ruby, or Node.js) that:
    *   Iterates through the exported JSON/CSV rows.
    *   Maps fields to YAML front matter keys (e.g., `status` -> `status: open`, `created_date` -> `created_at: "2023-10-27T10:00:00Z"`).
    *   Converts HTML descriptions to Markdown (using libraries like `html2text` or `turndown`).
    *   Constructs the file body with a `## Comments` section, appending each comment with author/timestamp headers.
    *   Names the file using the `{ticket_id}-{slugified-title}.md` convention.
    *   Moves processed attachments to the `/attachments/` folder and updates references in the Markdown body.
2.  **Dry Run (Staging)**:
    *   Execute the script against a *subset* of data (e.g., 50 tickets) to a temporary output directory.
    *   Manually inspect 5–10 generated files for correctness: check YAML validity, Markdown rendering, and attachment links.
    *   Fix any bugs in the mapping logic (e.g., unescaped YAML characters in titles).
3.  **Full Execution**:
    *   Run the validated script against the full dataset.
    *   Output all generated `.md` files into a staging directory (e.g., `./staging_tickets/`), organized into subfolders by status (e.g., `/open/`, `/closed/`).

### Step 3: Verification and Cutover

Once the file-based system is populated in the staging directory, validate the migration before switching production workflows.

1.  **Automated Validation**:
    *   **Count Check**: Ensure the number of `.md` files in staging exactly matches the number of tickets in the source export.
    *   **YAML Lint**: Run a YAML parser across all files to confirm every front matter block is valid and required fields (`ticket_id`, `title`, `status`) are present.
    *   **Link Check**: Verify that all internal Markdown links and attachment references point to existing files in the `/attachments/` folder.
2.  **Sample Audit**:
    *   Select 20 random tickets across different statuses and priorities.
    *   Compare the content in the `.md` file against the original ticket in the external tracker. Confirm descriptions, comments, and metadata match exactly.
3.  **Cutover Execution**:
    *   **Freeze External Tracker**: Set the external tracker to read-only mode or disable issue creation to prevent new changes during the final sync.
    *   **Incremental Sync (Optional)**: If time has passed between Step 1 and Step 3, run a delta script to capture any tickets created/modified during the migration window and add/update corresponding `.md` files.
    *   **Promote to Production**: Move or rename the staging directory to the live production path (e.g., `./tickets/`).
    *   **Announce Switch**: Inform all team members to begin using the file-based system for new issues. Disable the external tracker’s write access permanently.

### Post-Migration Checklist
- [ ] Confirm all team members can access and edit the file-based system.
- [ ] Monitor for file permission issues or sync conflicts.
- [ ] Archive the external tracker’s read-only instance for historical reference if required by compliance.

### Integrate migration section into report

The section "Operational Migration Plan: Step-by-Step Execution" has been successfully placed in the report. It follows the "Migration Mapping" section, ensuring a logical flow from schema design to execution. The section provides a detailed, three-step migration plan (Extraction, Transformation, Verification/Cutover) for moving tickets from external trackers to the file-based system, with no duplication of the schema mapping content found in the previous section.

## R5 — s4_anchors, turn 0

label: 

**Task:**

Plan a 7-day study schedule for learning the basics of linear algebra (vectors, matrices, systems of equations). Deliverable 1: a day-by-day schedule table. Deliverable 2: a short checklist of 10 concepts that must be solid before moving on to numerical linear algebra.

### R5 candidate A (run 0)

### Core Concepts and Dependencies

Here is the structured list of core linear algebra topics with prerequisite annotations:

1. **Scalar and Vector Arithmetic** (Addition, Scalar Multiplication)  
   - Prerequisites: None (Foundational)

2. **Dot Product and Norms**  
   - Prerequisites: Scalar and Vector Arithmetic

3. **Matrix Definition and Notation**  
   - Prerequisites: Scalar and Vector Arithmetic (specifically understanding columns/rows)

4. **Matrix Addition and Scalar Multiplication**  
   - Prerequisites: Matrix Definition and Notation, Vector Arithmetic

5. **Matrix-Vector Multiplication**  
   - Prerequisites: Dot Product and Norms, Matrix Definition

6. **Matrix-Matrix Multiplication**  
   - Prerequisites: Matrix-Vector Multiplication, Dot Product

7. **Systems of Linear Equations and Augmented Matrices**  
   - Prerequisites: Matrix Definition, Matrix-Vector Multiplication (conceptually related)

8. **Gaussian Elimination and Row Reduction**  
   - Prerequisites: Systems of Linear Equations and Augmented Matrices

9. **Rank and Null Space**  
   - Prerequisites: Gaussian Elimination and Row Reduction, Matrix-Vector Multiplication

10. **Determinants**  
    - Prerequisites: Matrix-Matrix Multiplication (for cofactor expansion intuition), Systems of Linear Equations

11. **Matrix Inversion**  
    - Prerequisites: Determinants, Gaussian Elimination, Matrix-Matrix Multiplication

12. **Vector Spaces and Subspaces**  
    - Prerequisites: Vector Arithmetic, Systems of Linear Equations, Null Space

13. **Linear Independence and Span**  
    - Prerequisites: Vector Spaces and Subspaces, Vector Arithmetic

14. **Basis and Dimension**  
    - Prerequisites: Linear Independence and Span, Rank

15. **Orthogonality and Projection**  
    - Prerequisites: Dot Product and Norms, Vector Spaces

16. **Eigenvalues and Eigenvectors**  
    - Prerequisites: Matrix Inversion, Determinants, Matrix-Vector Multiplication

17. **Diagonalization**  
    - Prerequisites: Eigenvalues and Eigenvectors, Matrix Inversion

### 7-Day Curriculum Outline

### 7-Day Linear Algebra Study Schedule

This schedule progresses from foundational arithmetic to solving systems of equations and analyzing matrix properties. It strictly follows the prerequisite dependencies identified in the core concepts list.

| Day | Focus Area | Specific Topics & Sub-Topics | Learning Objectives |
| :--- | :--- | :--- | :--- |
| **1** | **Foundations of Vectors and Matrices** | 1. Scalar and Vector Arithmetic (Addition, Scalar Multiplication)<br>2. Matrix Definition and Notation (Rows, Columns, Dimensions) | • Perform vector addition and scalar multiplication.<br>• Identify matrix dimensions and specific entries.<br>• Understand that matrices are collections of vectors (columns/rows). |
| **2** | **Vector Metrics & Basic Matrix Ops** | 1. Dot Product and Norms (Euclidean norm, orthogonality)<br>2. Matrix Addition and Scalar Multiplication | • Calculate dot products and vector norms.<br>• Add matrices and multiply by scalars.<br>• Understand geometric interpretations of dot product. |
| **3** | **Matrix Multiplication** | 1. Matrix-Vector Multiplication (Linear combination of columns)<br>2. Matrix-Matrix Multiplication (Composition of linear maps) | • Compute $A\mathbf{x}$ and $AB$.<br>• Understand matrix multiplication as a series of dot products.<br>• Recognize non-commutativity ($AB \neq BA$). |
| **4** | **Systems of Linear Equations** | 1. Systems of Linear Equations and Augmented Matrices<br>2. Consistency and Geometric Interpretation | • Translate systems into matrix form $A\mathbf{x} = \mathbf{b}$.<br>• Construct and interpret augmented matrices.<br>• Visualize solutions as intersecting lines/planes. |
| **5** | **Solving Systems via Elimination** | 1. Gaussian Elimination<br>2. Row Reduction (REF and RREF) | • Apply elementary row operations.<br>• Reduce matrices to Row Echelon Form (REF) and Reduced Row Echelon Form (RREF).<br>• Back-substitute to find solutions. |
| **6** | **Solution Structure and Rank** | 1. Rank and Null Space<br>2. Pivot and Free Variables | • Determine Rank from RREF.<br>• Identify pivot and free variables.<br>• Express the general solution (particular + homogeneous).<br>• Understand the Null Space as the solution to $A\mathbf{x} = \mathbf{0}$. |
| **7** | **Invertibility and Determinants** | 1. Matrix Inversion (Conceptual and via RREF)<br>2. Determinants (Properties and calculation) | • Determine if a matrix is invertible (based on Rank/Det).<br>• Calculate determinants for small matrices.<br>• Compute matrix inverses using row reduction. |

### 10-Point Concept Checklist Before Numerical Linear Algebra

Before moving to numerical linear algebra (which focuses on algorithms, stability, and approximation), ensure you can solidly execute and explain these 10 concepts:

1. [ ] **Vector Arithmetic**: Fluently add vectors and multiply by scalars; understand vector norms.
2. [ ] **Dot Product**: Correctly calculate dot products and use them to test for orthogonality.
3. [ ] **Matrix-Vector Multiplication**: Interpret $A\mathbf{x}$ both as row operations and column linear combinations.
4. [ ] **Matrix-Matrix Multiplication**: Perform products correctly and understand the dimensions rule ($m \times n$ times $n \times p$).
5. [ ] **Augmented Matrices**: Efficiently convert systems of equations into augmented matrix form.
6. [ ] **Row Operations**: Execute row swaps, scaling, and addition without arithmetic errors.
7. [ ] **Gaussian Elimination**: Systematically reduce a matrix to REF and RREF.
8. [ ] **Rank Identification**: Correctly identify the rank of a matrix from its RREF.
9. [ ] **Null Space Analysis**: Parametrize the solution space of a homogeneous system ($A\mathbf{x}=0$) using free variables.
10. [ ] **Invertibility**: Determine invertibility via RREF (no zeros in diagonal) or Determinant, and compute the inverse for small systems.

### 7-Day Study Schedule

| Day | Primary Topics | Key Concepts | Suggested Activities |
| :--- | :--- | :--- | :--- |
| **1** | **Foundations of Vectors and Matrices** | • Scalar and Vector Arithmetic (Addition, Scalar Multiplication)<br>• Matrix Definition and Notation (Rows, Columns, Dimensions) | • Practice vector addition and scalar multiplication.<br>• Identify matrix dimensions and specific entries.<br>• Review how matrices relate to vectors (columns/rows). |
| **2** | **Vector Metrics & Basic Matrix Ops** | • Dot Product and Norms (Euclidean norm, orthogonality)<br>• Matrix Addition and Scalar Multiplication | • Calculate dot products and vector norms.<br>• Add matrices and multiply by scalars.<br>• Explore geometric interpretations of the dot product. |
| **3** | **Matrix Multiplication** | • Matrix-Vector Multiplication (Linear combination of columns)<br>• Matrix-Matrix Multiplication (Composition of linear maps) | • Compute $A\mathbf{x}$ and $AB$.<br>• Analyze matrix multiplication as a series of dot products.<br>• Verify non-commutativity ($AB \neq BA$) with examples. |
| **4** | **Systems of Linear Equations** | • Systems of Linear Equations and Augmented Matrices<br>• Consistency and Geometric Interpretation | • Translate systems of equations into matrix form $A\mathbf{x} = \mathbf{b}$.<br>• Construct and interpret augmented matrices.<br>• Visualize solutions as intersecting lines or planes. |
| **5** | **Solving Systems via Elimination** | • Gaussian Elimination<br>• Row Reduction (REF and RREF) | • Apply elementary row operations (swap, scale, add).<br>• Reduce matrices to Row Echelon Form (REF) and Reduced Row Echelon Form (RREF).<br>• Back-substitute to find solutions. |
| **6** | **Solution Structure and Rank** | • Rank and Null Space<br>• Pivot and Free Variables | • Determine Rank from the RREF of a matrix.<br>• Identify pivot and free variables.<br>• Express the general solution (particular + homogeneous).<br>• Analyze the Null Space as the solution to $A\mathbf{x} = \mathbf{0}$. |
| **7** | **Invertibility and Determinants** | • Matrix Inversion (Conceptual and via RREF)<br>• Determinants (Properties and calculation) | • Determine if a matrix is invertible based on Rank or Determinant.<br>• Calculate determinants for small matrices.<br>• Compute matrix inverses using row reduction. |

### 10-Concept Prerequisite Checklist

1. **Matrix-Vector Multiplication**: Essential for defining linear transformations and implementing iterative solvers like Krylov subspace methods.
2. **Systems of Linear Equations**: The primary problem class in numerical linear algebra, requiring understanding of solution existence and uniqueness.
3. **Gaussian Elimination and Row Reduction**: Foundational for direct solvers and determining matrix rank and invertibility in finite precision arithmetic.
4. **Rank**: Determines the solvability of systems and the structure of least-squares problems, critical for rank-revealing decompositions.
5. **Vector Spaces and Subspaces**: Provides the geometric framework for understanding solution sets and approximations in finite-dimensional spaces.
6. **Linear Independence**: Crucial for determining basis viability and avoiding instability in linear system solutions.
7. **Orthogonality and Projection**: Key to stable algorithms like QR factorization and solving least-squares problems via projections.
8. **Eigenvalues and Eigenvectors**: Fundamental for analyzing matrix behavior in iterative methods and assessing stability via spectral radius.
9. **Matrix Norms** (implied under Dot Product and Norms): Essential for quantifying error, stability, and conditioning in numerical computations.
10. **Matrix Inversion**: While rarely computed directly, understanding it is vital for analyzing system conditioning and formulating inverse problems.

### R5 candidate B (run 1)

### 7-Day Study Schedule

| Day | Topic | Key Concepts | Daily Goal/Exercise |
| :--- | :--- | :--- | :--- |
| Day 1 | Vector Fundamentals | Definition, magnitude, unit vectors, vector addition/subtraction, scalar multiplication | Perform vector arithmetic in 2D and 3D; calculate magnitude and normalize vectors |
| Day 2 | Vector Products & Independence | Dot product, cross product (intuition), linear combinations, linear dependence vs. independence | Compute dot products; determine if a set of 3 vectors is linearly independent |
| Day 3 | Vector Spaces & Subspaces | Definition of a vector space, subspaces, span, basis, dimension | Identify if given sets are subspaces; find a basis for a given span in R3 |
| Day 4 | Matrix Basics & Operations | Matrix representation, dimensions, addition, scalar multiplication, transpose | Construct matrices from vector data; perform matrix addition and transposition |
| Day 5 | Matrix Multiplication & Properties | Dot product interpretation, compatibility, associativity, distributivity, identity matrix | Multiply 2x2 and 3x3 matrices; verify associativity with small examples |
| Day 6 | Linear Systems & Gaussian Elimination | Systems as Ax=b, augmented matrices, row echelon form (REF), reduced row echelon form (RREF) | Solve a 3x3 system using Gaussian elimination; convert to RREF |
| Day 7 | Inverses, Determinants & Applications | Matrix inverse, 2x2/3x3 determinant, singularity, solving systems via inverse | Calculate inverse of a 2x2 matrix; compute determinant; solve a system using A⁻¹ |

### Prerequisite Checklist for Numerical Linear Algebra

- [ ] Can compute the magnitude and normalize a vector in 2D or 3D space.
- [ ] Can compute the dot product of two vectors and interpret the result (e.g., orthogonality check).
- [ ] Can determine if a set of vectors is linearly independent or dependent.
- [ ] Can identify if a given set of vectors forms a subspace of a larger vector space.
- [ ] Can find a basis and state the dimension of a subspace spanned by a set of vectors.
- [ ] Can perform basic matrix operations: addition, scalar multiplication, and transposition.
- [ ] Can multiply two matrices and verify compatibility of dimensions.
- [ ] Can represent a system of linear equations as an augmented matrix.
- [ ] Can perform Gaussian elimination to convert a matrix to Row Echelon Form (REF) and Reduced Row Echelon Form (RREF).
- [ ] Can compute the determinant of a 2x2 or 3x3 matrix and determine if the matrix is invertible (non-singular).

