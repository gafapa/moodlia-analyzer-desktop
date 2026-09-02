# Architecture

## Entry Point

- `main.py` starts the CustomTkinter application and loads `MoodleAnalyzerApp`.

## Core Modules

- `src/ui_app.py`: application shell and top-level navigation.
- `src/ui_connection.py`: connection, profile, and token-generation workflow.
- `src/ui_dashboard.py`: course selection and course dashboard UI.
- `src/ui_student.py`: student detail UI.
- `src/charts_course.py`: course-level and cross-course visualizations.
- `src/charts_student.py`: student-level visualizations.
- `src/ui.py`: backward-compatible import shim for `MoodleAnalyzerApp`.
- `src/moodle_client.py`: Moodle REST client, token-based access, and token generation from credentials.
- `src/data_collector.py`: gathers course, user, submission, forum, quiz, and completion data from Moodle.
- `src/analyzer.py`: computes course and student metrics, passing-threshold-aware predictions, and risk indicators.
- `src/report_agent.py`: generates AI-assisted narrative reports.
- `src/profiles.py`: persists local connection profiles.
- `src/i18n.py`: runtime translation layer, language persistence, and UI/chart text translation.
- `website/`: static HTML/CSS page that presents the project, its purpose, and its workflow.
- `prepare_web_release.bat`: creates `deploy/webserver/` with the website assets and the standalone executable under `downloads/` for server upload.

## Authentication Flow

1. User enters Moodle URL.
2. User either:
   - provides an existing token, or
   - provides username and password.
   The token generation action is shown only when the token field is empty.
3. If the token is missing, the UI asks `MoodleClient.from_credentials(...)` to request a token from:
   - `/login/token.php`
   - `service=moodle_mobile_app`
4. The returned token is reused for the active session and can be stored in the local profile.
5. Passwords are cleared after successful token generation or connection.
6. Remote service URLs must use HTTPS; loopback HTTP is allowed only for local development.
7. Credential-bearing requests reject HTTP redirects.

## Session Flow

1. The first screen collects the UI language, Moodle URL, and authentication method.
2. After a successful connection, the user reaches course selection.
3. Course selection also exposes the configurable passing threshold, which defaults to `50%`.
4. The selected threshold is stored in the app session and passed into the analysis pipeline.
5. Dashboard, student detail views, charts, and reports consume the same analysis object so pass/fail logic stays consistent across the UI.
6. Asynchronous course-list loads are request-scoped so stale responses do not overwrite the currently selected mode or analysis tab.

## Local Persistence

- Profiles are stored in `~/.moodle_analyzer/profiles.json`.
- AI settings are stored in `~/.moodle_analyzer/ai_settings.json`.
- UI language settings are stored in `~/.moodle_analyzer/ui_settings.json`.
- Profile and settings files are restricted to the current user on platforms that support POSIX file permissions.

## Web Distribution

- The public website links to `./downloads/MoodleAnalyzer.exe` as the stable download path for the standalone Windows build.
- `prepare_web_release.bat` assembles a deployable bundle that mirrors that structure so the web root can be uploaded without manual rearrangement.

## Internationalization

- The desktop app supports Spanish, Galician, English, French, German, Catalan, and Basque.
- The static website uses client-side translations for the same languages.
- Report prompts adapt the requested report language to the active UI language.
- AI report payloads use internal identifiers and aggregate metrics instead of student names or email addresses.
- UI and website strings are stored as UTF-8 source text in `src/i18n.py` and `website/app.js` to avoid encoding artifacts in labels and messages.
- The desktop translation runtime resolves icon-prefixed labels and dynamic status lines used in loading states, charts, and reports.
- Student detail sections, including alert/recommendation panels and AI-report controls, use the same runtime translation layer instead of local hardcoded labels.
- Analyzer-generated recommendation sentences and risk-factor messages are covered through pattern-based runtime translations, so student alert cards remain localized too.
- The desktop language is selected from the initial connection screen; the main shell does not expose an in-session language switcher.

## Adaptive Analysis

- Student and course metrics are availability-aware: forums, assignments, quizzes, and completion metrics are only evaluated when that component exists in the course.
- Aggregated course metrics expose component availability flags so the UI can suppress unsupported summary rows and chart tabs.
- Course and student chart builders also drop unavailable dimensions to avoid presenting zero-valued placeholders as real behavior.
- The analysis pipeline also carries a configurable passing grade threshold, selected on the course selection screen and defaulted to `50%`.
- That threshold is propagated into the analyzer, chart builders, student detail indicators, and AI-report context so grade-based interpretations stay consistent.
- Risk scoring uses conservative cutoffs so students with grades comfortably above the passing threshold are not escalated to medium risk by only mild warning signals.
- Loading and progress messages shown during course retrieval and analysis are translated through the same runtime language layer used by the rest of the UI.

## Website And Distribution

- `website/index.html` provides the public landing page for the project.
- `website/app.js` contains the website translation dictionaries and current product description.
- The website text now reflects:
  - configurable pass threshold selection before analysis
  - adaptive omission of metrics that do not apply to the selected course
  - conservative risk interpretation for students whose grades are clearly above the pass threshold
- `prepare_web_release.bat` rebuilds `deploy/webserver/` so the upload bundle always contains the latest website assets and download link target.

## Testing

- Unit tests live in `tests/`.
- Authentication coverage includes token generation and profile persistence without storing passwords.
- Regression coverage includes threshold-aware risk behavior and adaptive analysis for courses without specific Moodle components.
