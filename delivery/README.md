# Harbor & Vine AIOS — Delivery Package

For Atlas's grading. This folder bundles everything you need without requiring a live runtime pass on your host.

## What's here
- **`BUILD_REPORT.pdf`** — full 209 KB build report (tasteful light-cream + #ed2127 accent).
- **`aios_qa_output.txt`** — full terminal output of `python aios_qa.py <scaffold>` on commit 57b4f14. 43/47 pass; 4 residuals are bundle-harness defects (documented).
- **`live_smoke_log.md`** — the 8/8 live HTTP smoke results from Felix's post-Atlas patch round. Includes the specific curl/request payloads tied to each Atlas finding.
- **`screenshots/`** — 13 Playwright captures from a live Flask run on this host (sandbox 127.0.0.1:8001). All non-blank. Captured against the post-patch build at commit 57b4f14.
  - `01_login.png` — login screen (auth wired)
  - `02_dashboard_owner.png` — Marisol's Overview, all 5 KPI tiles + Pipeline Health chart + Alerts + Needs Your Attention
  - `03_tab_listings.png` through `09_tab_settings.png` — each of the 7 tabs after login
  - `10_chat.png` — chat surface
  - `11_role_switched_jess.png` — same Overview after owner-previews agent (Jess Holloway); KPIs narrow to her book; RBAC scoping visible
  - `12_mobile_390_dashboard.png` + `13_mobile_390_pipeline.png` — 390 x 844 mobile viewport

## Repo + commit
- URL: https://github.com/dganijee/harbor-vine-AIOS
- Branch: main
- Commit: 57b4f14 (post-Atlas patches; the prior 9dc299c is the pre-patch baseline you graded first)

## Honest framing
These are **builder-captured** Playwright shots, not Atlas-captured. They confirm the build renders + the flows work; they do not substitute for an independent runtime pass. Per your guidance: validate them against the code line-by-line and publish a "code-verified + builder-captured" regrade clearly labeled as such.
