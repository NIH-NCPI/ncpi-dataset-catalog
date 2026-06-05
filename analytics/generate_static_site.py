#!/usr/bin/env python3
"""
Generate static analytics site from Google Analytics data.

This script fetches analytics data from GA4 and exports it as JSON files
for the static site.

Usage:
    cd analytics
    source ./venv/bin/activate
    python generate_static_site.py

The script will:
1. Authenticate with Google Analytics via OAuth (browser login)
2. Fetch monthly traffic, pageviews, outbound links, filter selections, and chat submissions
3. Export JSON files to site/data/
"""

import os
import json
import re
from datetime import datetime

import pandas as pd

from constants import (
    CURRENT_MONTH,
    NCPI_CATALOG_ID,
    SECRET_NAME,
    ANALYTICS_START,
    HISTORIC_UA_DATA_PATH,
    OAUTH_PORT,
)


def authenticate():
    """Authenticate using OAuth (interactive browser login)."""
    creds_path = os.environ.get(
        "NCPI_ANALYTICS_REPORTING_CLIENT_SECRET_PATH", "../.env/ga4_credentials.json"
    )
    os.environ["NCPI_ANALYTICS_REPORTING_CLIENT_SECRET_PATH"] = creds_path

    import analytics.api as ga

    print("Authenticating with Google Analytics via OAuth...")
    print("(A browser window will open for you to log in)")

    ga_authentication, _, _ = ga.authenticate(
        SECRET_NAME,
        ga.ga4_service_params,
        ga.drive_service_params,
        ga.sheets_service_params,
        port=OAUTH_PORT,
    )
    return ga_authentication


def get_chat_submitted_change(params_current, params_prior):
    """Fetch chat_submitted event count with month-over-month change."""
    from analytics.sheets_elements import get_data_df_from_fields
    from analytics.entities import METRIC_EVENT_COUNT, DIMENSION_EVENT_NAME

    chat_current = get_data_df_from_fields(
        [METRIC_EVENT_COUNT],
        [DIMENSION_EVENT_NAME],
        dimension_filter="eventName==chat_submitted",
        **params_current,
    )
    current_count = (
        int(chat_current[METRIC_EVENT_COUNT["alias"]].sum())
        if len(chat_current) > 0
        else 0
    )

    chat_prior = get_data_df_from_fields(
        [METRIC_EVENT_COUNT],
        [DIMENSION_EVENT_NAME],
        dimension_filter="eventName==chat_submitted",
        **params_prior,
    )
    prior_count = (
        int(chat_prior[METRIC_EVENT_COUNT["alias"]].sum()) if len(chat_prior) > 0 else 0
    )

    change = None
    if prior_count > 0:
        change = (current_count - prior_count) / prior_count

    return {"current": current_count, "prior": prior_count, "change": change}


METRIC_ENGAGEMENT_RATE = {
    "id": "engagementRate",
    "alias": "Engagement Rate",
}



# Regex matching page paths that are clearly not real pages (bot probes,
# broken markdown links, asset requests, etc.).
SUSPICIOUS_PAGE_PATH_RE = re.compile(
    r"("
    r"^/?\].*"             # broken markdown links e.g. /](https://...)
    r"|.*https?://.*"      # concatenated URLs e.g. /overview/securityhttps://...
    r"|^/[^/]*@[^/]*"     # email-as-path e.g. /help@lists...
    r"|^//.*"              # double-slash probes e.g. //checkout/
    r"|^/[^/]*\.[^/]+$"   # file extensions at root e.g. /robots.txt, /favicon-32x32.png
    r"|^/feed$"            # RSS probes
    r"|^/\).*"             # broken parens e.g. /), /).
    r"|^/[^/]*\).*"       # broken parens e.g. /events)
    r"|^/docs(-\w+)?/"     # CMS probes e.g. /docs/, /docs-EN/
    r")"
)


def fetch_data(ga_authentication):
    """Fetch analytics data using the analytics package."""
    import analytics.sheets_elements as elements
    from analytics.sheets_elements import get_data_df_from_fields
    from analytics.entities import METRIC_SESSIONS

    # Calculate date ranges
    report_dates = elements.get_bounds_for_month_and_prev(CURRENT_MONTH)
    start_date_current = report_dates["start_current"]
    end_date_current = report_dates["end_current"]
    start_date_prior = report_dates["start_previous"]
    end_date_prior = report_dates["end_previous"]

    print(f"Current month: {start_date_current} to {end_date_current}")
    print(f"Prior month: {start_date_prior} to {end_date_prior}")

    default_params = {
        "service_system": ga_authentication,
        "start_date": start_date_current,
        "end_date": end_date_current,
    }

    ncpi_catalog_params = {
        **default_params,
        "property": NCPI_CATALOG_ID,
    }

    ncpi_catalog_params_all_time = {
        **ncpi_catalog_params,
        "start_date": ANALYTICS_START,
        "end_date": end_date_current,
    }

    print("Fetching monthly traffic data...")
    df_monthly_traffic = elements.get_page_views_over_time_df(
        ncpi_catalog_params_all_time,
        additional_data_path=HISTORIC_UA_DATA_PATH,
        additional_data_behavior=elements.ADDITIONAL_DATA_BEHAVIOR.ADD,
    )

    print("Fetching pageviews data...")
    df_pageviews = elements.get_page_views_change(
        ncpi_catalog_params,
        start_date_current,
        end_date_current,
        start_date_prior,
        end_date_prior,
    )

    if df_pageviews is not None and len(df_pageviews) > 0:
        page_col = "Page Path"
        suspicious_mask = df_pageviews[page_col].str.match(SUSPICIOUS_PAGE_PATH_RE, na=False)
        n_suspicious = suspicious_mask.sum()
        if n_suspicious > 0:
            df_pageviews = df_pageviews[~suspicious_mask]
            print(f"  Filtered {n_suspicious} suspicious page path(s)")

    print("Fetching outbound links data...")
    df_outbound = elements.get_outbound_links_change(
        ncpi_catalog_params,
        start_date_current,
        end_date_current,
        start_date_prior,
        end_date_prior,
    )

    print("Fetching filter selections data...")
    df_filter_selected = elements.get_index_filter_selected_change(
        ncpi_catalog_params,
        start_date_current,
        end_date_current,
        start_date_prior,
        end_date_prior,
    )

    print("Fetching chat submissions data...")
    ncpi_catalog_params_prior = {
        **ncpi_catalog_params,
        "start_date": start_date_prior,
        "end_date": end_date_prior,
    }
    chat_submitted_stats = get_chat_submitted_change(
        ncpi_catalog_params, ncpi_catalog_params_prior
    )

    print("Fetching sessions and engagement data...")
    df_sessions_current = get_data_df_from_fields(
        [METRIC_SESSIONS, METRIC_ENGAGEMENT_RATE], [], **ncpi_catalog_params,
    )
    df_sessions_prior = get_data_df_from_fields(
        [METRIC_SESSIONS, METRIC_ENGAGEMENT_RATE], [], **ncpi_catalog_params_prior,
    )
    sessions_current = int(df_sessions_current[METRIC_SESSIONS["alias"]].sum()) if len(df_sessions_current) > 0 else 0
    sessions_prior = int(df_sessions_prior[METRIC_SESSIONS["alias"]].sum()) if len(df_sessions_prior) > 0 else 0
    _eng_current = df_sessions_current[METRIC_ENGAGEMENT_RATE["alias"]].mean() if len(df_sessions_current) > 0 else None
    _eng_prior = df_sessions_prior[METRIC_ENGAGEMENT_RATE["alias"]].mean() if len(df_sessions_prior) > 0 else None
    engagement_current = float(_eng_current) if _eng_current is not None and not pd.isna(_eng_current) else None
    engagement_prior = float(_eng_prior) if _eng_prior is not None and not pd.isna(_eng_prior) else None

    print("Data fetching complete!")

    return {
        "sessions": {
            "current": sessions_current,
            "prior": sessions_prior,
        },
        "engagement_rate": {
            "current": engagement_current,
            "prior": engagement_prior,
        },
        "monthly_traffic": df_monthly_traffic,
        "pageviews": df_pageviews,
        "outbound": df_outbound,
        "filter_selected": df_filter_selected,
        "chat_submitted": chat_submitted_stats,
        "dates": {
            "start_current": start_date_current,
            "end_current": end_date_current,
            "start_prior": start_date_prior,
            "end_prior": end_date_prior,
        },
    }


def _export_df_as_json(df, col_map, change_col, filename, output_dir):
    """Export a DataFrame to JSON with column renaming and NaN handling.

    Args:
        df: Source DataFrame.
        col_map: Dict mapping source column names to output names.
        change_col: Source column name for the change metric (may be absent).
        filename: Output JSON filename.
        output_dir: Output directory.
    """
    if df is None or len(df) == 0:
        records = []
    else:
        export_cols = list(col_map.keys())
        output_names = list(col_map.values())
        if change_col is not None and change_col in df.columns:
            export_cols.append(change_col)
            output_names.append("change")

        export = df[export_cols]
        export.columns = output_names

        # Fill NaN in numeric columns with 0, cast to int
        for col in output_names:
            if col != "change" and export[col].dtype != object:
                export[col] = export[col].fillna(0).astype(int)

        records = export.to_dict(orient="records")
        for record in records:
            if pd.isna(record.get("change")):
                record["change"] = None

    with open(os.path.join(output_dir, filename), "w") as f:
        json.dump(records, f, indent=2)
    print(f"  Wrote {filename} ({len(records)} records)")


def export_data(data, output_dir="site/data"):
    """Export DataFrames to JSON files."""
    os.makedirs(output_dir, exist_ok=True)

    df_monthly_traffic = data["monthly_traffic"]
    dates = data.get("dates", {})

    # Export monthly traffic data
    print("Exporting monthly traffic data...")
    traffic_data = df_monthly_traffic[["Month", "Users", "Total Pageviews"]].copy()
    traffic_data.columns = ["month", "users", "pageviews"]
    traffic_data["month"] = traffic_data["month"].astype(str)
    traffic_data["users"] = traffic_data["users"].fillna(0).astype(int)
    traffic_data["pageviews"] = traffic_data["pageviews"].fillna(0).astype(int)

    with open(os.path.join(output_dir, "monthly_traffic.json"), "w") as f:
        json.dump(traffic_data.to_dict(orient="records"), f, indent=2)
    print(f"  Wrote monthly_traffic.json ({len(traffic_data)} records)")

    print("Exporting pageviews data...")
    _export_df_as_json(
        data["pageviews"],
        {"Page Path": "page", "Total Pageviews": "views"},
        "Total Pageviews Change",
        "pageviews.json",
        output_dir,
    )

    print("Exporting outbound links data...")
    _export_df_as_json(
        data["outbound"],
        {"Outbound Link": "link", "Total Clicks": "clicks"},
        "Total Clicks Change",
        "outbound_links.json",
        output_dir,
    )

    print("Exporting filter selections data...")
    _export_df_as_json(
        data.get("filter_selected"),
        {"Filter Name": "filterName", "Filter Value": "filterValue", "Event Count": "count"},
        "Event Count Change",
        "filter_selected.json",
        output_dir,
    )

    # Export chat submissions data
    print("Exporting chat submissions data...")
    chat_record = data.get("chat_submitted", {"current": 0, "prior": 0, "change": None})

    with open(os.path.join(output_dir, "chat_submitted.json"), "w") as f:
        json.dump(chat_record, f, indent=2)
    print("  Wrote chat_submitted.json")

    # Export metadata
    print("Exporting metadata...")
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_month": CURRENT_MONTH,
        "current_month_start": dates.get("start_current", ""),
        "current_month_end": dates.get("end_current", ""),
        "prior_month_start": dates.get("start_prior", ""),
        "prior_month_end": dates.get("end_prior", ""),
        "analytics_start": ANALYTICS_START,
        "sessions": data.get("sessions", {}),
        "engagement_rate": data.get("engagement_rate", {}),
    }

    with open(os.path.join(output_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print("  Wrote meta.json")

    print("\n" + "=" * 50)
    print("Static site data generation complete!")
    print(f"Files written to: {os.path.abspath(output_dir)}")
    print("\nTo view the site locally, run:")
    print("  cd site && python -m http.server 8080")
    print("Then open http://localhost:8080 in your browser.")


def main():
    """Main entry point."""
    print("=" * 50)
    print("NCPI Dataset Catalog Analytics - Static Site Generator")
    print("=" * 50)
    print()

    ga_authentication = authenticate()
    data = fetch_data(ga_authentication)
    export_data(data)


if __name__ == "__main__":
    main()
