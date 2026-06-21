# Changelog

## 0.0.5

- Added Iron-themed HTML reports for scans, manual job analyses, and resume optimizations.
- Updated the reports tab to open HTML reports in the browser and backfill missing HTML for older reports.
- Added a 30-day repeated-job blocklist using title, company, source, and full location.
- Reduced Serper usage by limiting queries and stopping collection once enough new jobs are found.
- Improved monitoring logs with clearer next-attempt guidance and stop/close instructions.
- Increased desktop and configuration window sizes by 50px in width and height.

## 0.0.4

- Redesigned the **Otimizar curriculo** tab with a stable full-width layout for both normal and maximized windows.
- Added a direct **Otimizar esta vaga** action after manual job analysis.
- Added a **Relatorios** tab with local history for scans, manual analyses, and resume optimizations.
- Added quick configuration tests for IA, Serper, and Gmail.
- Improved the v0.0.4 workflow between analysis, optimization, and saved reports.

## 0.0.3

- Added the **Otimizar curriculo** desktop tab.
- Added AI guidance for targeted resume positioning from a pasted job description.
- Generates suggested headline, professional summary, priority skills, priority experiences, suggested bullets, items to reduce, missing evidence, and honesty warnings.
- Resume optimization reports are saved as JSON and Markdown in `reports/`.
- The optimizer does not export DOCX/PDF and must not invent experience, technologies, certifications, jobs, or projects.

## 0.0.2

- Added a desktop tab to analyze one pasted job description at a time.
- The manual analysis compares the configured resume/profile against only that job.
- Added professional guidance focused on strengths, gaps, resume improvements, less relevant items, and next action.
- Kept resume generation out of this flow; the feature only recommends what to improve or emphasize.
- Manual job analyses are saved as JSON and Markdown reports in `reports/`.

## 0.0.1

Initial public release.

- Desktop app for Windows.
- User-owned Groq, Serper, and Gmail configuration.
- Persistent local settings.
- DPAPI protection for sensitive fields on Windows.
- TXT profile plus PDF resume parsing.
- AI job matching and resume guidance.
- Email digest for best matches.
- Local job cache to reduce repeated results.
- Markdown and JSON scan reports.
