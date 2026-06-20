# Changelog

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
