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
        'NCPI_ANALYTICS_REPORTING_CLIENT_SECRET_PATH',
        '../.env/ga4_credentials.json'
    )
    os.environ['NCPI_ANALYTICS_REPORTING_CLIENT_SECRET_PATH'] = creds_path

    import analytics.api as ga

    print("Authenticating with Google Analytics via OAuth...")
    print("(A browser window will open for you to log in)")

    ga_authentication, _, _ = ga.authenticate(
        SECRET_NAME,
        ga.ga4_service_params,
        ga.drive_service_params,
        ga.sheets_service_params,
        port=OAUTH_PORT
    )
    return ga_authentication


def fetch_chat_submitted(params_current, params_prior):
    """Fetch chat_submitted event count with month-over-month change."""
    print("Fetching chat submissions data...")
    from analytics._sheets_utils import get_data_df_from_fields
    from analytics.entities import METRIC_EVENT_COUNT, DIMENSION_EVENT_NAME

    chat_current = get_data_df_from_fields(
        [METRIC_EVENT_COUNT],
        [DIMENSION_EVENT_NAME],
        dimension_filter="eventName==chat_submitted",
        **params_current,
    )
    current_count = int(chat_current[METRIC_EVENT_COUNT["alias"]].sum()) if len(chat_current) > 0 else 0

    chat_prior = get_data_df_from_fields(
        [METRIC_EVENT_COUNT],
        [DIMENSION_EVENT_NAME],
        dimension_filter="eventName==chat_submitted",
        **params_prior,
    )
    prior_count = int(chat_prior[METRIC_EVENT_COUNT["alias"]].sum()) if len(chat_prior) > 0 else 0

    change = None
    if prior_count > 0:
        change = (current_count - prior_count) / prior_count

    return {"current": current_count, "prior": prior_count, "change": change}


def fetch_data(ga_authentication):
    """Fetch analytics data using the analytics package."""
    import analytics.sheets_elements as elements

    # Calculate date ranges
    report_dates = elements.get_bounds_for_month_and_prev(CURRENT_MONTH)
    start_date_current = report_dates["start_current"]
    end_date_current = report_dates["end_current"]
    start_date_prior = report_dates["start_previous"]
    end_date_prior = report_dates["end_previous"]

    print(f"Current month: {start_date_current} to {end_date_current}")
    print(f"Prior month: {start_date_prior} to {end_date_prior}")

    # Set up query parameters
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

    # Fetch data
    print("Fetching monthly traffic data...")
    df_monthly_traffic = elements.get_page_views_over_time_df(
        ncpi_catalog_params_all_time,
        additional_data_path=HISTORIC_UA_DATA_PATH,
        additional_data_behavior=elements.ADDITIONAL_DATA_BEHAVIOR.ADD
    )

    print("Fetching pageviews data...")
    df_pageviews = elements.get_page_views_change(
        ncpi_catalog_params,
        start_date_current,
        end_date_current,
        start_date_prior,
        end_date_prior
    )

    print("Fetching outbound links data...")
    df_outbound = elements.get_outbound_links_change(
        ncpi_catalog_params,
        start_date_current,
        end_date_current,
        start_date_prior,
        end_date_prior
    )

    print("Fetching filter selections data...")
    df_filter_selected = elements.get_index_filter_selected_change(
        ncpi_catalog_params,
        start_date_current,
        end_date_current,
        start_date_prior,
        end_date_prior
    )

    ncpi_catalog_params_prior = {**ncpi_catalog_params, "start_date": start_date_prior, "end_date": end_date_prior}
    chat_submitted_stats = fetch_chat_submitted(ncpi_catalog_params, ncpi_catalog_params_prior)

    print("Data fetching complete!")

    return {
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
        }
    }


def export_data(data, output_dir="site/data"):
    """Export DataFrames to JSON files."""
    os.makedirs(output_dir, exist_ok=True)

    df_monthly_traffic = data["monthly_traffic"]
    df_pageviews = data["pageviews"]
    df_outbound = data["outbound"]
    dates = data.get("dates", {})

    # Export monthly traffic data
    print("Exporting monthly traffic data...")
    traffic_data = df_monthly_traffic[['Month', 'Users', 'Total Pageviews']].copy()
    traffic_data.columns = ['month', 'users', 'pageviews']
    traffic_data['month'] = traffic_data['month'].astype(str)
    traffic_data['users'] = traffic_data['users'].fillna(0).astype(int)
    traffic_data['pageviews'] = traffic_data['pageviews'].fillna(0).astype(int)

    traffic_records = traffic_data.to_dict(orient='records')
    with open(os.path.join(output_dir, 'monthly_traffic.json'), 'w') as f:
        json.dump(traffic_records, f, indent=2)
    print(f"  Wrote monthly_traffic.json ({len(traffic_records)} records)")

    # Export pageviews data
    print("Exporting pageviews data...")
    pageviews_cols = ['Page Path', 'Total Pageviews']
    if 'Total Users Change' in df_pageviews.columns:
        pageviews_cols.append('Total Users Change')
        pageviews_export = df_pageviews[pageviews_cols].copy()
        pageviews_export.columns = ['page', 'views', 'change']
    else:
        pageviews_export = df_pageviews[pageviews_cols].copy()
        pageviews_export.columns = ['page', 'views']
        pageviews_export['change'] = None

    pageviews_export['views'] = pageviews_export['views'].fillna(0).astype(int)

    pageviews_records = pageviews_export.to_dict(orient='records')
    for record in pageviews_records:
        if pd.isna(record.get('change')):
            record['change'] = None

    with open(os.path.join(output_dir, 'pageviews.json'), 'w') as f:
        json.dump(pageviews_records, f, indent=2)
    print(f"  Wrote pageviews.json ({len(pageviews_records)} records)")

    # Export outbound links data
    print("Exporting outbound links data...")

    if len(df_outbound) > 0:
        link_col = 'Outbound Link'
        clicks_col = 'Total Clicks'
        change_col = 'Total Clicks Change'

        outbound_cols = [link_col, clicks_col]
        if change_col in df_outbound.columns:
            outbound_cols.append(change_col)
            outbound_export = df_outbound[outbound_cols].copy()
            outbound_export.columns = ['link', 'clicks', 'change']
        else:
            outbound_export = df_outbound[outbound_cols].copy()
            outbound_export.columns = ['link', 'clicks']
            outbound_export['change'] = None

        outbound_export['clicks'] = outbound_export['clicks'].fillna(0).astype(int)

        outbound_records = outbound_export.to_dict(orient='records')
        for record in outbound_records:
            if pd.isna(record.get('change')):
                record['change'] = None
    else:
        outbound_records = []

    with open(os.path.join(output_dir, 'outbound_links.json'), 'w') as f:
        json.dump(outbound_records, f, indent=2)
    print(f"  Wrote outbound_links.json ({len(outbound_records)} records)")

    # Export filter selections data
    print("Exporting filter selections data...")
    df_filter_selected = data.get("filter_selected")

    if df_filter_selected is not None and len(df_filter_selected) > 0:
        filter_name_col = 'Filter Name'
        filter_value_col = 'Filter Value'
        events_col = 'Total Events'
        change_col = 'Total Events Change'

        filter_cols = [filter_name_col, filter_value_col, events_col]
        if change_col in df_filter_selected.columns:
            filter_cols.append(change_col)
            filter_export = df_filter_selected[filter_cols].copy()
            filter_export.columns = ['filterName', 'filterValue', 'count', 'change']
        else:
            filter_export = df_filter_selected[filter_cols].copy()
            filter_export.columns = ['filterName', 'filterValue', 'count']
            filter_export['change'] = None

        filter_export['count'] = filter_export['count'].fillna(0).astype(int)

        filter_records = filter_export.to_dict(orient='records')
        for record in filter_records:
            if pd.isna(record.get('change')):
                record['change'] = None
    else:
        filter_records = []

    with open(os.path.join(output_dir, 'filter_selected.json'), 'w') as f:
        json.dump(filter_records, f, indent=2)
    print(f"  Wrote filter_selected.json ({len(filter_records)} records)")

    # Export chat submissions data
    print("Exporting chat submissions data...")
    chat_record = data.get("chat_submitted", {"current": 0, "prior": 0, "change": None})

    with open(os.path.join(output_dir, 'chat_submitted.json'), 'w') as f:
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
    }

    with open(os.path.join(output_dir, 'meta.json'), 'w') as f:
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
