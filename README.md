# Cyclistic Data Cleaning

> A Python script that runs a standard cleaning pass over raw Cyclistic (Divvy) bike-share trip data and flags anomalies for review.

## Highlights

- Cleans raw trip data into a single, analysis-ready dataset (`.pkl` and `.csv`).
- Flags anomalies for review — missing IDs, duplicate IDs, unparsable dates, DST-ambiguous times, and out-of-range durations each export to their own file in `data/flagged/`.
- Handles Chicago daylight-saving fall-back correctly: ambiguous local times are set to `NaT` via `tz_localize(..., ambiguous="NaT")` rather than producing wrong durations.
- Derives analysis fields from the timestamps: trip duration in minutes, month, and day of week.

## Overview

Cyclistic is a fictional Chicago bike-share company used as the case study for the Google Data Analytics capstone. The marketing team wants to understand how casual riders and annual members use the bikes differently, in order to design a campaign that converts casual riders into annual members. The guiding question is:

> How do annual members and casual riders use Cyclistic bikes differently?

This script is the cleaning step: it takes the raw 2025 trip data, produces a clean dataset for the analysis, and leaves an audit trail of everything it removed. It is a personal portfolio project and is still in progress.

**Note on columns:**

- The station columns (`start_station_name`, `start_station_id`, `end_station_name`, `end_station_id`) aren't included — `load_data` keeps only the columns in `cols`, so they're dropped at load. If you want them for station-level analysis, add them to `cols`.
- The coordinate columns (`start_lat`, `start_lng`, `end_lat`, `end_lng`) are kept, but missing values in them aren't handled — rows with missing coordinates pass through untouched, since whether you need them depends on your analysis.

### Author

Samer El-Feghali — [GitHub](https://github.com/feghali1994)


## Datasets

The data is real Divvy trip data, made available publicly by Motivate International Inc. under the [Divvy Data License Agreement](https://divvybikes.com/data-license-agreement). "Cyclistic" is a fictional name used for the case study.

The `data/` directory is gitignored, so you supply your own copy — download the raw trip data from the link above.

## Requirements & Setup

- Python 3.11 *(set this to the version you actually built on)*
- pandas — the only third-party dependency (`pathlib` is part of the standard library)

```bash
# 1. Clone the repo and enter it
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

Generate `requirements.txt` from a clean environment with `pip freeze > requirements.txt` so it's reproducible.

### Input & paths

The script expects a single pickle at `data/intermediate_data/rides_2025.pkl` containing the concatenated raw trip data. Assembling that pickle from the monthly raw CSVs is a step done outside this script.

You don't have to use a pickle, though. You can run the script on the individual monthly or concatenated CSVs (or any other format) — just change the reader in `load_data()` to match, e.g. `pd.read_csv(...)` or `pd.read_parquet(...)`.

The only requirement is that the file has the columns selected in `cols` inside `load_data()`. You can extend that list to keep extra columns, but the cleaning steps reference the existing ones by name, so don't drop or rename them.

Before running, check the paths for your setup:

- the input path in `main()`
- the `OUTPUT_DIR` and `FLAGGED_DIR` constants at the top of the file

## Usage

```bash
python clean_rides.py
```

This loads the input pickle, runs the full cleaning pass, writes the cleaned dataset to `data/cleaned_data/`, and writes any flagged rows to `data/flagged/`. Progress is printed to the console as it goes (counts of dropped IDs, duplicates, unparsable dates, and so on).

## Output

**Cleaned dataset** → `data/cleaned_data/`

- `rides_2025_clean.pkl`
- `rides_2025_clean.csv` (written with `index=False`)

| Column | Type |
|------------------|--------------------------|
| `ride_id` | string |
| `rideable_type` | category |
| `started_at` | datetime (America/Chicago) |
| `ended_at` | datetime (America/Chicago) |
| `start_lat` / `start_lng` | float32 |
| `end_lat` / `end_lng` | float32 |
| `member_casual` | category |
| `month` | category |
| `start_day` / `end_day` | category |
| `trip_duration_min` | float |

**Flagged rows** → `data/flagged/` (each category gets its own file)

| File | Contents |
|---------------------------|----------|
| `missing_id_rows.pkl` | rows with a missing or blank `ride_id` |
| `duplicate_id_rows.pkl` | duplicate `ride_id` rows (the first occurrence is kept) |
| `unparsed_dates.pkl` | rows whose `started_at` / `ended_at` could not be parsed — `ride_id` plus the original values |
| `ambiguous_dates.pkl` | rows nulled at DST localisation (ambiguous or non-existent Chicago times) — `ride_id` plus originals |
| `negative_durations.pkl` | rows with a negative trip duration (see below) |
| `outlier_durations.pkl` | rides under 1 minute or over 24 hours |

## How it works

The pipeline runs as a sequence of single-purpose functions, orchestrated by `clean_rides()`:

1. **`trim_cols`** — strips whitespace from the text columns (`ride_id`, `rideable_type`, `member_casual`).
2. **`remove_na_id`** — flags and removes rows with a missing or blank `ride_id`.
3. **`drop_duplicates`** — flags and removes duplicate `ride_id` rows, keeping the first.
4. **`check_unique_values`** — checks `rideable_type` and `member_casual` against the expected categories and raises a `ValueError` if it finds anything unexpected, so unknown values stop the run rather than passing through quietly. It prints the unique values it sees; it doesn't modify the data.
5. **`convert_dtypes`** — casts the columns to their target types and parses the datetime columns. Dates are parsed with `pd.to_datetime(errors="coerce")` and localised to `America/Chicago` with `ambiguous="NaT"` and `nonexistent="NaT"`. Rows that fail to parse are flagged to `unparsed_dates.pkl`; rows nulled by localisation are flagged to `ambiguous_dates.pkl`. Both groups are removed, so the cleaned output contains only rows with valid, timezone-aware timestamps.
6. **`calculate_trip_duration`** — derives `month`, `start_day`, `end_day`, and `trip_duration_min` from the timestamps.
7. **`clean_trip_durations`** — handles duration anomalies (below).

Finally the cleaned frame is written to `data/cleaned_data/` as both pickle and CSV.

### A note on negative durations

The negative-duration check is a diagnostic check, not routine cleaning. Chicago observes daylight saving time, and on the autumn fall-back the 1 AM hour repeats, making local timestamps in that window ambiguous. Subtracting two such naive timestamps can run backwards and produce a negative duration. Because `convert_dtypes` already nulls those ambiguous rows via `ambiguous="NaT"` and removes them, durations are computed from clean, timezone-aware timestamps — so this check should report **zero**. If you do find some negative durations, something upstream has changed and is worth investigating. The separate out-of-range filter (`< 1 min` or `> 24 h`) is the routine bulk cleaning step and is also dependent on your analysis. Feel free to change the boundaries to suit your needs.

## Feedback

This is a personal portfolio project. If you spot a bug or have a suggestion, feel free to open an issue on the repo.





