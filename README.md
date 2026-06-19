# Job Matcher

**Version:** `0.0.1`

Job Matcher is a free, bring-your-own-API desktop app that searches for job openings, compares each job with your resume/profile, sends the best matches by email, and suggests honest resume adjustments for each opportunity.

This is an early `0.0.1` release. It already works as a local desktop assistant, but the project will keep improving over time.

## Repository Description

AI-powered desktop job matcher that searches jobs, scores resume fit, emails best matches, and suggests targeted resume improvements using the user's own Groq, Serper, and Gmail credentials.

## Suggested GitHub Topics

`job-search` `resume` `career-tools` `ai` `desktop-app` `python` `customtkinter` `groq` `serper` `gmail` `pyinstaller` `open-source`

## What It Does

- Searches job openings through Google results using Serper.
- Reads and filters job pages.
- Builds a candidate profile from a TXT file and a PDF resume.
- Uses Groq AI to score fit between the candidate and each job.
- Sends the best matches by Gmail.
- Generates resume guidance for each job:
  - suggested resume headline.
  - strengths to highlight.
  - honest improvements to make the resume fit the job better.
- Saves local reports in `reports/`.
- Keeps a local cache to reduce repeated job alerts.

## Download The App

For normal users, download the Windows app from the GitHub release:

```text
Releases -> v0.0.1 -> JobMatcherApp.zip
```

After downloading, extract the zip and run:

```text
JobMatcherApp.exe
```

If you build it locally, the executable is generated at:

```text
dist\JobMatcherApp\JobMatcherApp.exe
```

## Requirements

The user provides their own credentials:

- Groq API key.
- Serper API key.
- Gmail account.
- Gmail app password.
- TXT profile file.
- PDF resume.

No paid account is required by this project itself. External services may have their own free tiers, limits, and terms.

## Quick Start For Users

1. Open `JobMatcherApp.exe`.
2. Click `Configurar`.
3. Add your Groq API key.
4. Add your Serper API key.
5. Add your Gmail address.
6. Add your Gmail app password.
7. Add the destination email for job alerts.
8. Select a `.txt` profile file.
9. Select your resume PDF.
10. Add search terms, one per line.
11. Click `Salvar configuracao`.
12. Click `E-mail teste`.
13. Click `Varredura unica` to test one scan.
14. Click `Iniciar` to keep monitoring.

Full setup instructions are in [GUIA_USUARIO.md](GUIA_USUARIO.md).

## How To Get API Keys

### Groq

1. Go to `https://console.groq.com/keys`.
2. Sign in or create an account.
3. Create an API key.
4. Paste it into `API de IA Groq`.

Default model:

```text
llama-3.3-70b-versatile
```

### Serper

1. Go to `https://serper.dev`.
2. Create an account.
3. Copy your API key.
4. Paste it into `API Serper`.

Serper is the main search provider. Without it, the main job search source will not work.

### Gmail App Password

This is not your normal Gmail password.

1. Go to `https://myaccount.google.com/security`.
2. Enable 2-Step Verification.
3. Search for `App passwords`.
4. Create an app password for Job Matcher.
5. Copy the 16-character password.
6. Paste it into `Senha de app do Gmail`.

## Persistence

Settings are saved outside the executable.

Primary Windows location:

```text
%APPDATA%\JobMatcher\config.json
%APPDATA%\JobMatcher\job_cache.json
%APPDATA%\JobMatcher\documents\
```

Fallback portable location:

```text
user_data\config.json
user_data\job_cache.json
user_data\documents\
```

Selected TXT and PDF files are copied into the app data `documents` folder so the app can keep using them later.

## Security

Sensitive fields are:

- Groq API key.
- Serper API key.
- Gmail app password.

On Windows, these values are protected with DPAPI before being written to disk. That protection is tied to the logged-in Windows user.

Do not publish or share:

- `config.json`
- `job_cache.json`
- `user_data/`
- `%APPDATA%\JobMatcher`
- `job_matcher.log`
- screenshots of the configuration window

If a secret leaks, revoke it in Groq, Serper, or Google and generate a new one.

## Duplicate Jobs And Local Memory

Job Matcher stores analyzed job IDs in `job_cache.json`.

This helps avoid repeated jobs while the cache exists and while job URLs/IDs remain stable.

Current `0.0.1` limitations:

- If `job_cache.json` is deleted, old jobs can appear again.
- If the app is moved to another computer without the data folder, the job memory does not move with it.
- If a job site changes the URL or ID, the same job may look new.
- If the computer sleeps, shuts down, or loses internet, the app does not monitor during that time.
- For continuous monitoring, keep the app open, the computer awake, and the internet connected.

## Build From Source

```powershell
pip install -r requirements.txt
python app_desktop.py
```

Build the Windows executable:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Output:

```text
dist\JobMatcherApp\JobMatcherApp.exe
```

## Project Structure

```text
job-matcher/
|-- app_desktop.py
|-- main.py
|-- config/
|   `-- settings.py
|-- core/
|   |-- cache.py
|   |-- matcher.py
|   |-- report.py
|   |-- resume_parser.py
|   |-- secure_store.py
|   `-- user_config.py
|-- notifier/
|   `-- email_notifier.py
|-- scrapers/
|-- GUIA_USUARIO.md
|-- build_exe.ps1
`-- requirements.txt
```

## Roadmap

Planned improvements after `0.0.1`:

- Better installer experience.
- More search providers.
- Cleaner job deduplication.
- Better resume export options.
- Safer secret storage fallback outside Windows.
- More transparent match explanations.
- Optional background scheduling.

## Disclaimer

Job Matcher does not guarantee interviews, offers, or employment. It is a local assistant that helps users find relevant jobs and improve resume targeting using their own credentials and data.

## License

Add a license before publishing the repository publicly. MIT is a good default for this kind of tool if you want broad reuse.
