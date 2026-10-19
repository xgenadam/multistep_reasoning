## wordcount.py

```py
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
```
