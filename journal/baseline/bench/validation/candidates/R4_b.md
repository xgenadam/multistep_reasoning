{", ": "File-Based Ticketing Systems: An Overview\n\nA file-based ticketing system is a lightweight issue-tracking solution that stores support tickets as individual text files in a shared directory. Unlike complex database-driven platforms, these systems rely on basic file operations, offering an accessible entry point for small teams. However, while their architectural simplicity offers distinct advantages, it also introduces significant operational limitations as demand grows.\n\nKey Advantages\n\nThe primary appeal of file-based ticketing lies in its simplicity and low cost. By eliminating the need for proprietary software licenses, dedicated servers, or complex installations, organizations can implement the system almost instantly using existing network drives. This architecture ensures transparency and portability; tickets are human-readable files (such as Markdown or plain text) that are easily backed up, version-controlled via Git, and migrated without data conversion issues. Furthermore, the barrier to entry is minimal, as team members require no specialized training to manage files using standard tools like text editors or file explorers.\n\nMain Drawbacks\n\nDespite these benefits, file-based systems face critical scalability and functionality challenges. Performance degrades as ticket volume increases, with directory scanning and file management becoming prohibitively slow. This model lacks native automation capabilities, forcing administrators to manually route tickets, update statuses, and track deadlines, which increases workload and error rates. Additionally, searchability is poor; unlike indexed databases, finding specific tickets often requires scanning file contents, making complex filtering and reporting inefficient.\n\nConclusion\n\nFile-based ticketing systems are an excellent, cost-effective solution for small organizations or low-volume environments where simplicity is paramount. However, due to severe scalability constraints and a lack of automation, they become impractical for growing enterprises that require robust reporting, workflow efficiency, and high-volume performance."}

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

## Operational Migration Plan

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

## Integrate migration section into report

The section "Operational Migration Plan: Step-by-Step Execution" has been successfully placed in the report. It follows the "Migration Mapping" section, ensuring a logical flow from schema design to execution. The section provides a detailed, three-step migration plan (Extraction, Transformation, Verification/Cutover) for moving tickets from external trackers to the file-based system, with no duplication of the schema mapping content found in the previous section.
