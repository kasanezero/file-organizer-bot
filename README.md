# File Organizer Bot

A  cross‑platform bot that tidies a folder automatically using rules (by extension,
name patterns, size, and creation date). You can run it as a one‑shot command or as a
background watcher that keeps your download folder organised in real time. The project is
fully configurable via a YAML file so you can customise it to suit your workflow.

## Features

* **Rule‑based organisation** – Define rules in `config.yaml` to sort files into
  subfolders such as `Images/`, `Docs/`, `Archives/`, `Audio/`, `Video/`, `Code/`, or a
  default `Other/` folder. Rules can match by extension lists, regular expressions on
  filenames, minimum/maximum size, or simply force a category.
* **Date bucketing** – Optionally organise files into `year/` or `year/month/` folders
  based on their modification date.
* **Deduplication** – If a file with the same name exists at the destination, the bot
  appends a numeric suffix to avoid clobbering existing files.
* **Dry‑run mode** – Preview what will happen without moving any files.
* **Undo support** – Undo the last one‑shot run via a move log file (`.moves.log`).
* **Watch mode** – Monitor the source directory in real time (requires the
  [watchdog](https://pypi.org/project/watchdog/) package).
* **Clean, coloured console output** – Uses [rich](https://pypi.org/project/rich/) for
  nicely formatted logs (optional).

## Folder layout

```
file-organizer-bot/
├─ organizer.py        # CLI script
├─ config.yaml         # Example configuration
├─ .gitignore          # Ignore logs, virtual environments, etc.
└─ .moves.log          # Auto-created: stores last run moves for undo
```

## Requirements

Python 3.7+ is required. Install optional dependencies as needed:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install pyyaml rich watchdog
```

Only `PyYAML` is mandatory to parse the configuration. The `rich` and `watchdog`
packages provide enhanced output and watch mode, respectively.

## Configuration (`config.yaml`)

The example `config.yaml` illustrates how to customise the bot. Key fields include:

* **source_dir** – Path to the directory you want to organise.
* **target_dir** – Destination root where sorted files will be placed.
* **bucket_mode** – Set to `none`, `year`, or `year_month` to organise by date.
* **unknown_category** – Default folder for files that don’t match any rules.
* **extensions** – Map of categories to lists of file extensions.
* **rules** – A list of advanced rules evaluated in order. Each rule can match by
  filename regex (`if_name_regex`), extension list (`if_ext_in`), and minimum or
  maximum file size in MB (`min_size_mb`/`max_size_mb`). The first matching rule wins.
* **exclude_regex** – List of regular expressions; if a file name matches any, it’s skipped.

See the provided `config.yaml` for a working example with common categories and three
advanced rules:

```yaml
source_dir: "/path/to/Downloads"
target_dir: "/path/to/Sorted"
bucket_mode: year_month
unknown_category: "Other"
extensions:
  Images: [jpg, jpeg, png, gif, webp, bmp, tiff, heic]
  Docs:   [pdf, doc, docx, xls, xlsx, ppt, pptx, csv, txt, md]
  Archives: [zip, rar, 7z, tar, gz, bz2]
  Audio:  [mp3, wav, flac, m4a, aac, ogg]
  Video:  [mp4, mkv, avi, mov, webm]
  Code:   [py, js, ts, java, kt, cs, cpp, c, go, rs, sql, html, css, json, yaml, yml]
rules:
  - name: "Screenshots by prefix"
    if_name_regex: "(?i)^screenshot[_\\-].*"
    to_category: "Images"
  - name: "Big videos"
    if_ext_in: [mp4, mkv, mov]
    min_size_mb: 200
    to_category: "Video"
  - name: "Design exports"
    if_name_regex: "(?i)^(export|final).*"
    to_category: "Images"
exclude_regex: ["(?i)^~\\$.*", "(?i)^\\.~lock\\.", "(?i)\\.part$", "(?i)\\.crdownload$"]
```

## Usage

Run the script with your configuration file:

```bash
python organizer.py --config config.yaml          # one-shot organise
python organizer.py --config config.yaml --dry    # preview without moving files
python organizer.py --config config.yaml --undo   # undo the last one-shot run
python organizer.py --config config.yaml --watch  # keep watching in real time
```

## Autostart (optional)

To run the bot continuously, you can set it up as a systemd user service on Linux or
create a Task Scheduler entry on Windows. See the comments in the project description
for example unit files and Task Scheduler instructions.
---
