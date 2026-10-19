## csv2json.py

```py
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
```

## Output JSON with indentation support

```python
        # Output JSON with indentation support
        indent = args.indent
        print(json.dumps(data, indent=indent))
```

## Finalize script with shebang and execution block

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
