import pandas as pd
from pathlib import Path

# Directories:
OUTPUT_DIR = Path("data/cleaned_data")
FLAGGED_DIR = Path("data/flagged")

# Expected Categories:
EXPECTED_RIDEABLE_TYPE = ["classic_bike", "electric_bike", "electric_scooter"]
EXPECTED_MEMBER_CASUAL = ["member", "casual"]

pd.set_option("display.max_columns", None)

def load_data(path):
    df = pd.read_pickle(path)
    cols = ["ride_id",
            "rideable_type",
            "started_at",
            "ended_at",
            "start_lat",
            "start_lng",
            "end_lat",
            "end_lng",
            "member_casual"]
    return df[cols].copy()


def main():
    df = load_data("data/intermediate_data/rides_2025.pkl")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FLAGGED_DIR.mkdir(parents=True, exist_ok=True)
    clean_rides(df)

def remove_na_id(df, flagged_dir):
    null_mask = ((df["ride_id"].isna()) | (df["ride_id"].str.strip() == ""))
    null_ride_id = df[null_mask]
    if not null_ride_id.empty:
        print(f"""Missing ride_id found: {null_ride_id.shape[0]}
        Missing values exported to: {flagged_dir}""")
        null_ride_id.to_pickle(flagged_dir/"missing_id_rows.pkl")
        df = df.loc[~null_mask].copy()
    return df

# Let's trim the relevant data before checking for duplicates:
def trim_cols(df):
    df = df.copy()
    cols_to_strip = ["ride_id", "rideable_type", "member_casual"]
    for col in cols_to_strip:
        df[col] = df[col].astype("string").str.strip() # Use .astype("string") instead of .astype(str)
    print(f"Following Columns Stripped: {cols_to_strip}")
    return df


def drop_duplicates(df, flagged_dir):
    duplicate_ids = df.duplicated(keep="first", subset="ride_id")
    duplicate_id_rows = df[duplicate_ids]
    if not duplicate_id_rows.empty:
        print(f"""Duplicates dropped: {duplicate_id_rows.shape[0]}
                  Duplicates exported to {flagged_dir}""")
        duplicate_id_rows.to_pickle(flagged_dir/"duplicate_id_rows.pkl")
        df=df.drop_duplicates(subset="ride_id", keep="first")
    else:
        print(f"No duplicates found")
    return df

# If any unexpected categorical values detected, ValueError will be raised and the script stopped
def check_unique_values(df):
    categorical_columns = ["rideable_type", "member_casual"]

    # Because NOT in python is designed for a single bool value, using it on a boolean Series will return a ValueError:
    # We use .all() to collapse the boolean series returned from .isin() into a single boolean value:
        # True - if all values in boolean Series are true
        # False - If there is at least 1 false value in the boolean Series
    if not df["rideable_type"].isin(EXPECTED_RIDEABLE_TYPE).all():
        unexpected_ride_type = df.loc[~df["rideable_type"].isin(EXPECTED_RIDEABLE_TYPE), "rideable_type"].unique().tolist()
        raise ValueError(f"Unexpected value(s) in rideable_type detected: {unexpected_ride_type}."
                         f"If valid for your data, add them to EXPECTED_RIDEABLE_TYPE")

    if not df["member_casual"].isin(EXPECTED_MEMBER_CASUAL).all():
        unexpected_member_casual = df.loc[~df["member_casual"].isin(EXPECTED_MEMBER_CASUAL), "member_casual"].unique().tolist()
        raise ValueError(f"Unexpected value(s) in member_casual detected: {unexpected_member_casual}"
                         f"If valid for your data, add them to EXPECTED_MEMBER_CASUAL")

    for col in categorical_columns:
        unique_values = df[col].unique()
        print(f"Unique in {col}: {unique_values}")


# .astype() does not work with datetime - so we need to convert the start/end_at columns separately using pd.to_datetime()
def convert_dtypes(df, flagged_dir):
    dtype_map = {
        "ride_id": "string",
        "rideable_type": "category",
        "start_lat": "float32",
        "start_lng": "float32",
        "end_lat": "float32",
        "end_lng": "float32",
        "member_casual": "category"
    }
    df = df.astype(dtype_map)

    # Convert datetime columns:
    datetime_cols = ["started_at", "ended_at"]
    original_df = df.copy()
    unparsed_dates = pd.DataFrame()

    ambiguous_dates = pd.DataFrame()

    for col in datetime_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")
        null_mask=df[col].isna()
        if null_mask.any():
            print(f"{col} unparsed dates: {null_mask.sum()}")
            # We concat the output to the empty Df to prevent overwriting on the second run
            # Any started_at na values will get concatenated to the unparsed_dates df
            # Instead of getting overwritten by the unparsed dates in ended_at column
            unparsed_dates = pd.concat([unparsed_dates, original_df.loc[null_mask, ["ride_id", "started_at", "ended_at"]]])
            df = df.loc[~null_mask].copy()
            original_df = original_df.loc[~null_mask].copy()

        df[col] = df[col].dt.tz_localize("America/Chicago", ambiguous="NaT", nonexistent="NaT")
        null_mask_dst = df[col].isna()
        if null_mask_dst.any():
            print(f"{col} ambiguous dates: {null_mask_dst.sum()}")
            ambiguous_dates = pd.concat([ambiguous_dates, original_df.loc[null_mask_dst, ["ride_id", "started_at", "ended_at"]]])
            df = df.loc[~null_mask_dst].copy()
            original_df = original_df.loc[~null_mask_dst].copy()
    # Move the export outside the for loop to avoid being overwritten after each iteration
    if not unparsed_dates.empty:
        unparsed_dates.to_pickle(flagged_dir / "unparsed_dates.pkl")

    if not ambiguous_dates.empty:
        ambiguous_dates.to_pickle(flagged_dir / "ambiguous_dates.pkl")

    print("Updated dtypes:")
    print(df.dtypes)
    return df


# Create Day, Month and Duration columns from Datetime Columns:
def calculate_trip_duration(df):
    # Make sure to convert the new column datatype to a less memory intensive datatype - category
    # Since Day and Month are categorical values (Monday-Sunday), (January - December)
    df["month"] = df["started_at"].dt.month_name().astype("category")
    df["start_day"] = df["started_at"].dt.day_name().astype("category")
    df["end_day"] = df["ended_at"].dt.day_name().astype("category")
    # When we assign operators to datetime columns - the output datatype becomes Pandas.Timedelta (when dealing with pandas)
    # We can then apply certain methods to extract the duration in min/sec/hours/days etc. by using mathematical operation:
    df["trip_duration_min"] = ((df["ended_at"] - df["started_at"]).dt.total_seconds() / 60)
    return df


def clean_trip_durations(df, flagged_dir):
    intermediate_df = df[["ride_id", "started_at", "ended_at", "trip_duration_min"]].copy()

    # Check for any negative durations
    negative_mask = df["trip_duration_min"] < 0
    if negative_mask.any():
        total_negative_durations = negative_mask.sum()
        print(f"Negative Durations: {total_negative_durations} - Negative durations exported to {flagged_dir}")
        negative_durations = intermediate_df.loc[negative_mask]
        negative_durations.to_pickle(flagged_dir / "negative_durations.pkl")
        df = df.loc[~negative_mask].copy()
        intermediate_df = intermediate_df.loc[~negative_mask]

    # Divvy have removed any rides under 60s, we will check and filter against those
    # Assumption: Any rides longer than 24 hours could be lost or stolen bikes - we will filter against those
    outlier_duration_mask = ((df["trip_duration_min"] < 1) | (df["trip_duration_min"] > 1440))
    if outlier_duration_mask.any():
        total_outlier_durations = outlier_duration_mask.sum()
        print(f"Outlier Durations: {total_outlier_durations} - exported to {flagged_dir}")
        bad_durations = intermediate_df.loc[outlier_duration_mask]
        bad_durations.to_pickle(flagged_dir/"outlier_durations.pkl")
        df = df.loc[~outlier_duration_mask].copy()
    return df


def clean_rides(df):
    # We need to reassign the trimmed/cleaned df to the df variable,
    # Take the cleaned DF and overwrite file with it:
    df = trim_cols(df)
    df = remove_na_id(df, FLAGGED_DIR)
    df = drop_duplicates(df, FLAGGED_DIR)

    # We don't need to assign a variable to the function - as it is acting as a validation step - it will print the unique values
    check_unique_values(df)

    df = convert_dtypes(df, FLAGGED_DIR)
    df = calculate_trip_duration(df)
    df = clean_trip_durations(df, FLAGGED_DIR)
    df.to_pickle(OUTPUT_DIR / "rides_2025_clean.pkl")
    df.to_csv(OUTPUT_DIR / "rides_2025_clean.csv", index=False)
    return df


if __name__ == "__main__":
    main()