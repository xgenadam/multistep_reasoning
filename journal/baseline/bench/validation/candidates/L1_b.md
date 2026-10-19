## Cost and Hosting

## Cost and Hosting

Adopting a file-based ticketing system using markdown files in Git offers significant financial and operational advantages over traditional external issue trackers. First and foremost, this approach eliminates recurring subscription fees. Popular external issue trackers often charge per user per month, creating a direct financial scaling penalty as the team grows or when contractors are added. By contrast, storing tickets as markdown files incurs zero incremental licensing costs, regardless of the number of engineers accessing the system.

Secondly, this model requires no separate infrastructure management. External SaaS platforms, while managed, still require administrative overhead for permission management, integration maintenance, and sometimes data export compliance. A git-based system leverages the existing Git hosting infrastructure (such as GitHub, GitLab, or Bitbucket) that the engineering team already utilizes for code. There is no need to spin up or maintain a separate database or web application for ticketing. This reduces the "surface area" of third-party dependencies we must vet, monitor, and integrate.

Finally, because the tickets live in the same repository as the code, the hosting workflow is unified. Engineers do not need to switch contexts to different web portals to update ticket status. Commits that resolve tickets automatically link to the markdown files, providing built-in traceability without complex API integrations. This synergy not only reduces hosting complexity but also streamlines the developer experience, keeping the ticketing system as lightweight and accessible as the codebase itself.

## Searchability and Review Culture

### Searchability and Review Culture

One of the most underrated advantages of storing tickets as Markdown files is native searchability. In a traditional issue tracker, finding an old discussion often requires navigating a UI with limited filtering options, relying on specific tags or IDs that may be inconsistent or forgotten. In a file-based system, every ticket is just text in the repository. This means you can use your existing developer tools—`grep`, IDE project-wide search, or command-line utilities like `ripgrep`—to find any mention of a keyword, error code, or API endpoint instantly. There is no separate search index to learn or latency to endure; the search is local, fast, and integrated directly into your workflow.

This accessibility directly strengthens our review culture. Because tickets live in Git, they can be referenced and linked to Pull Requests naturally. For instance, a developer can include `Refs: #tickets/login-flow.md` in a commit message or PR description, creating a bidirectional link between the problem definition and the solution. This integration encourages engineers to treat ticket updates with the same rigor as code changes. If a scope change occurs, it should be documented in the Markdown file within the PR, ensuring that the "why" behind the code is preserved alongside the "what." This makes code reviews more meaningful, as reviewers can immediately see the historical context and decision-making recorded in the ticket files, rather than relying on fragmented comments in external platforms.

## Further Considerations

Before closing, it is worth stepping back to consider the broader picture that the sections above describe. Cost and hosting matter: as noted, a file-based system removes per-seat subscription fees and runs on the Git hosting the team already uses, so there is no separate database or web application to maintain. This keeps the toolchain small and the budget predictable for a team of four.

Searchability is the second consideration. Because every ticket is plain text in the repository, the team can find anything with the tools it already knows, such as grep, ripgrep or an IDE's project search, without learning a separate search interface. In practice this means old discussions are as easy to find as old code.

Review culture is the third. Tickets that live in Git can be changed through pull requests, linked from commits and reviewed like code, which keeps the reasoning behind a change next to the change itself. Reviewers see the history of a decision rather than scattered comments in another tool.

Finally, the drawback deserves restating: people who do not use Git day to day will find a file-based tracker harder to use than a graphical one, and dashboards such as burndown charts need extra work. Weighing these considerations together, the team should keep all four in mind when deciding.

## Drawback and Conclusion

## Drawback

The most significant limitation of a file-based ticketing system is its lack of accessibility for non-developers. External issue trackers like Jira or Linear provide graphical user interfaces that allow product managers, designers, and stakeholders to interact with tickets—assigning owners, changing statuses, or adding comments—without needing to understand Git workflows or Markdown syntax. By requiring tickets to exist as files in a repository, we effectively gatekeep issue management to those comfortable with version control tools. For a four-person engineering team where non-technical stakeholders might need visibility or input, this friction can be a major hurdle. Additionally, there is the initial UI overhead; without a dedicated dashboard, tracking high-level metrics like burndown charts or sprint velocity requires manual effort or custom scripting, whereas external tools provide these views out of the box.

## Conclusion

For our four-person team, a file-based ticketing system offers a compelling balance of cost efficiency and developer-centric workflow integration. By eliminating SaaS subscription costs and leveraging our existing Git infrastructure, we simplify our budget. Furthermore, embedding tickets directly into our codebase enhances searchability and integrates issue resolution seamlessly into our code review culture. However, we must be honest about the trade-off: this approach assumes all relevant parties are developers comfortable with Git. If we anticipate needing significant input from non-technical stakeholders or require robust reporting dashboards immediately, the friction introduced by Markdown and Git workflows may outweigh the benefits. Ultimately, if our current team composition remains strictly technical and we prioritize low overhead and tight integration over rich UI features, this model is a strong, pragmatic choice.
