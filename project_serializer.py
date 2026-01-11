import argparse
import os


def build_tree_from_paths(rel_paths):
    tree = {}
    for rel in rel_paths:
        parts = rel.split(os.sep)
        current = tree
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        if parts:
            current[parts[-1]] = "file"
    return tree


def build_tree_string(node, indent=""):
    lines = []
    # Separate dirs and files, sort them
    dirs = sorted([k for k, v in node.items() if isinstance(v, dict)])
    files = sorted([k for k, v in node.items() if not isinstance(v, dict)])
    items = dirs + files
    for i, key in enumerate(items):
        is_dir = key in dirs
        line = indent + "- " + key
        if is_dir:
            line += "/"
        lines.append(line)
        if is_dir:
            extension = build_tree_string(node[key], indent + "  ")
            lines.extend(extension)
    return lines


def generate_structure(root_dir, suffix, exclude=None):
    rel_paths = []
    for root, dirs, files in os.walk(root_dir):
        if exclude:
            dirs[:] = [d for d in dirs if d != exclude]
        for f in files:
            if f.endswith(suffix):
                rel_path = os.path.relpath(os.path.join(root, f), root_dir)
                rel_paths.append(rel_path)

    rel_paths.sort()

    output = []
    output.append("Directory Structure:")
    if rel_paths:
        tree = build_tree_from_paths(rel_paths)
        output.extend(build_tree_string(tree))
    else:
        output.append("No files found with the given suffix.")

    output.append("\nFile Contents:\n")
    for rel in rel_paths:
        full_path = os.path.join(root_dir, rel)
        output.append(f"Path: {rel}")
        try:
            with open(full_path, "r", encoding="utf-8") as file:
                content = file.read()
            output.append("```python")
            output.append(content)
            output.append("```")
        except UnicodeDecodeError:
            output.append("Error: File contains binary data or invalid UTF-8 encoding.")
        except Exception as e:
            output.append(f"Error reading file: {str(e)}")
        output.append("\n---\n")

    return "\n".join(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate directory structure and file contents for files with a given suffix."
    )
    parser.add_argument(
        "--directory", required=True, help="The root directory to traverse."
    )
    parser.add_argument(
        "--suffix", required=True, help="The file suffix to filter by (e.g., .txt)."
    )
    parser.add_argument(
        "--exclude",
        default=None,
        help="The directory name to exclude from traversal (e.g., .git).",
    )
    args = parser.parse_args()

    result = generate_structure(args.directory, args.suffix, args.exclude)
    print(result)
