## Core CSV-to-JSON Logic

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

## CLI Implementation

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

## Error Handling

The `csv2json` CLI implementation includes the necessary validation checks to handle missing or empty files. 

1. **File Existence Check**: The code wraps the call to `csv_to_json_records(args.file_path)` in a `try...except` block. If a `FileNotFoundError` is raised, it prints an error message to `stderr` and exits with a non-zero status code (`sys.exit(1)`).

2. **Empty File/Data Check**: After retrieving the records, it checks if the returned list is empty (`if not records:`). This handles cases where the file is empty or contains only headers (resulting in no data rows). If empty, it prints an error to `stderr` and exits with `sys.exit(1)`.

Both checks ensure the tool fails gracefully with appropriate error messages and non-zero exit codes, satisfying the requirement to exit non-zero if the file is missing or empty.

## csv2json.py

```py
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
```
