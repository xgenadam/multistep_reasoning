## logscan.py

```py
import argparse
import os
import sys
import re
from datetime import datetime

def parse_timestamp(line):
    """
    Attempt to parse a timestamp from the beginning of a log line.
    Supports common formats like ISO 8601 or 'YYYY-MM-DD HH:MM:SS'.
    Returns a datetime object if successful, otherwise None.
    """
    # Try common log timestamp patterns
    patterns = [
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",  # 2023-10-27 10:30:00
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})",  # 2023-10-27T10:30:00
    ]
    
    for pattern in patterns:
        match = re.match(pattern, line)
        if match:
            ts_str = match.group(1)
            # Normalize separators to try parsing
            try:
                return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    pass
    return None

def main():
    parser = argparse.ArgumentParser(description="Scan a log file for specific levels.")
    parser.add_argument("logfile", help="Path to the log file")
    parser.add_argument("level", choices=["INFO", "WARN", "ERROR"], help="Log level to filter by")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of lines to print")

    args = parser.parse_args()

    if not os.path.exists(args.logfile):
        print(f"Error: File '{args.logfile}' does not exist.", file=sys.stderr)
        sys.exit(1)

    matching_lines = []
    try:
        with open(args.logfile, 'r') as f:
            for line in f:
                if args.level in line:
                    matching_lines.append(line.rstrip('\n'))
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    # Sort by timestamp, newest last. 
    # We use a sort key that handles None timestamps by treating them as datetime.min (oldest possible),
    # so they appear first in an ascending sort (oldest to newest). This satisfies "newest last".
    # For lines with unparseable timestamps, their relative order is preserved by Python's stable sort 
    # when using the tuple key (datetime, index).
    
    # Create a list of (line, original_index) to maintain stability for equal timestamps/None
    indexed_lines = [(line, i) for i, line in enumerate(matching_lines)]
    
    def sort_key(item):
        line_content, index = item
        ts = parse_timestamp(line_content)
        if ts is None:
            # Treat unparseable timestamps as very old (datetime.min) so they come first.
            # The index is used as a tie-breaker to preserve original order for these.
            return (datetime.min, index)
        return (ts, index)

    # Sort ascending by timestamp (oldest first, newest last)
    sorted_items = sorted(indexed_lines, key=sort_key)
    sorted_lines = [item[0] for item in sorted_items]

    # Apply limit: take the first N lines (which are the oldest) 
    # or last N lines? "Newest last" implies the list is sorted oldest-to-newest. 
    # Usually "limit" in this context (capping output) implies keeping the most recent if it were a tail, 
    # but strictly "caps the number printed" on a sorted list usually means truncating the end? 
    # No, if I say "give me 10 errors", I usually want the last 10. 
    # However, the prompt says "prints only the matching log lines, newest last". 
    # If I have 100 lines, and limit 5. 
    # If I print the first 5, I print the oldest. 
    # If I print the last 5, I print the newest. 
    # Given "newest last" is the display format, and "limit" caps the count... 
    # If you want to see the *recent* errors, you want the tail. 
    # Let's assume the user wants the *most recent* N lines if limited, as that is standard log analysis behavior (like `tail`).
    # But wait, standard `head` semantics are first N. 
    # Let's stick to the simplest interpretation: `[:limit]` takes the start of the list.
    # If the list is sorted Oldest -> Newest, `[:limit]` is Oldest -> ... 
    # This seems counter-intuitive for "errors". 
    # However, without explicit "last N", `limit` is just a max length. 
    # I will use `[:limit]` as it is the literal definition of a limit on a sequence.
    
    if args.limit is not None and args.limit >= 0:
        sorted_lines = sorted_lines[:args.limit]

    # Print to stdout
    for line in sorted_lines:
        print(line)

    # Print count to stderr
    print(f"Count: {len(sorted_lines)}", file=sys.stderr)

if __name__ == "__main__":
    main()
```
