#!/usr/bin/env python3
"""
Generate static analytics site from Google Analytics data.

This script fetches analytics data from GA4 and exports it as JSON files
for the static site.

Authentication modes:
- OAuth (interactive): For local development, opens browser for login
- Service Account (non-interactive): For CI/CD, uses service account key

Usage:
    # Local development (OAuth):
    cd analytics
    source ./venv/bin/activate
    python generate_static_site.py

    # CI/CD (Service Account):
    GA_SERVICE_ACCOUNT_KEY=/path/to/key.json python generate_static_site.py

The script will:
1. Authenticate with Google Analytics
2. Fetch monthly traffic, pageviews, and outbound links from GA4
3. Export JSON files to site/data/
"""

import os
import sys
import json
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

from constants import (
    CURRENT_MONTH,
    NCPI_CATALOG_ID,
    SECRET_NAME,
    ANALYTICS_START,
    HISTORIC_UA_DATA_PATH,
    OAUTH_PORT,
)

# GA4 API scopes
SCOPES = ['https://www.googleapis.com/auth/analytics.readonly']


def authenticate_service_account(key_path_or_json):
    """Authenticate using a service account key file or JSON content.

    Args:
        key_path_or_json: Either a file path to the JSON key, or the JSON content directly.
    """
    # Check if it's JSON content (starts with '{') or a file path
    if key_path_or_json.strip().startswith('{'):
        print("Authenticating with service account (from JSON content)")
        key_info = json.loads(key_path_or_json)
        credentials = service_account.Credentials.from_service_account_info(
            key_info, scopes=SCOPES
        )
    else:
        print(f"Authenticating with service account: {key_path_or_json}")
        credentials = service_account.Credentials.from_service_account_file(
            key_path_or_json, scopes=SCOPES
        )
    service = build('analyticsdata', 'v1beta', credentials=credentials)
    return service, credentials


def authenticate_oauth():
    """Authenticate using OAuth (interactive browser login)."""
    # Set the credentials path before importing analytics modules
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


def get_auth_mode():
    """Determine which authentication mode to use."""
    service_account_key = os.environ.get('GA_SERVICE_ACCOUNT_KEY')
    if service_account_key:
        # Support both file path and raw JSON content
        if service_account_key.strip().startswith('{') or os.path.exists(service_account_key):
            return 'service_account', service_account_key
    return 'oauth', None


def fetch_data_service_account(service, property_id, start_date, end_date):
    """Fetch data using the GA4 Data API directly (for service account auth)."""
    property_name = f"properties/{property_id}"

    # Fetch monthly data
    print("Fetching monthly traffic data...")
    response = service.properties().runReport(
        property=property_name,
        body={
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": "yearMonth"}],
            "metrics": [
                {"name": "totalUsers"},
                {"name": "screenPageViews"}
            ],
            "orderBys": [{"dimension": {"dimensionName": "yearMonth"}, "desc": True}]
        }
    ).execute()

    monthly_data = []
    for row in response.get('rows', []):
        year_month = row['dimensionValues'][0]['value']
        month_str = f"{year_month[:4]}-{year_month[4:]}"
        monthly_data.append({
            'Month': month_str,
            'Users': int(row['metricValues'][0]['value']),
            'Total Pageviews': int(row['metricValues'][1]['value'])
        })

    df_monthly = pd.DataFrame(monthly_data)

    # Fetch page views
    print("Fetching pageviews data...")
    response = service.properties().runReport(
        property=property_name,
        body={
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [
                {"name": "screenPageViews"},
                {"name": "totalUsers"}
            ],
            "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
            "limit": 200
        }
    ).execute()

    pageviews_data = []
    for row in response.get('rows', []):
        pageviews_data.append({
            'Page Path': row['dimensionValues'][0]['value'],
            'Total Pageviews': int(row['metricValues'][0]['value']),
            'Total Users Change': None  # Can't calculate change with single query
        })

    df_pageviews = pd.DataFrame(pageviews_data)

    # Fetch outbound links
    print("Fetching outbound links data...")
    response = service.properties().runReport(
        property=property_name,
        body={
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": "linkUrl"}],
            "metrics": [{"name": "eventCount"}],
            "dimensionFilter": {
                "filter": {
                    "fieldName": "eventName",
                    "stringFilter": {"value": "click", "matchType": "EXACT"}
                }
            },
            "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}],
            "limit": 100
        }
    ).execute()

    # First-party hostnames to exclude from outbound links
    first_party_hosts = {'ncpi-data.org', 'www.ncpi-data.org', 'ncpi-data.dev.clevercanary.com'}

    outbound_data = []
    for row in response.get('rows', []):
        link = row['dimensionValues'][0]['value']
        # Filter to only external links (exclude first-party hosts)
        if link.startswith('http'):
            hostname = urlparse(link).hostname or ''
            if hostname not in first_party_hosts:
                outbound_data.append({
                    'Outbound Link': link,
                    'Total Clicks': int(row['metricValues'][0]['value']),
                    'Total Users Change': None
                })

    df_outbound = pd.DataFrame(outbound_data) if outbound_data else pd.DataFrame(
        columns=['Outbound Link', 'Total Clicks', 'Total Users Change']
    )

    # Fetch filter selections
    print("Fetching filter selections data...")
    response = service.properties().runReport(
        property=property_name,
        body={
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [
                {"name": "customEvent:filter_name"},
                {"name": "customEvent:filter_value"}
            ],
            "metrics": [{"name": "eventCount"}, {"name": "totalUsers"}],
            "dimensionFilter": {
                "filter": {
                    "fieldName": "eventName",
                    "stringFilter": {"value": "filter_selected", "matchType": "EXACT"}
                }
            },
            "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}],
            "limit": 200
        }
    ).execute()

    filter_data = []
    for row in response.get('rows', []):
        filter_data.append({
            'Filter Name': row['dimensionValues'][0]['value'],
            'Filter Value': row['dimensionValues'][1]['value'],
            'Total Events': int(row['metricValues'][0]['value']),
            'Total Users': int(row['metricValues'][1]['value']),
            'Total Events Change': None
        })

    df_filter_selected = pd.DataFrame(filter_data) if filter_data else pd.DataFrame(
        columns=['Filter Name', 'Filter Value', 'Total Events', 'Total Users', 'Total Events Change']
    )

    return df_monthly, df_pageviews, df_outbound, df_filter_selected


def fetch_data_oauth(ga_authentication):
    """Fetch analytics data using the analytics package (OAuth auth)."""
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

    print("Data fetching complete!")

    return {
        "monthly_traffic": df_monthly_traffic,
        "pageviews": df_pageviews,
        "outbound": df_outbound,
        "filter_selected": df_filter_selected,
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
        link_col = 'Outbound Link' if 'Outbound Link' in df_outbound.columns else 'Link URL'
        clicks_col = 'Total Clicks' if 'Total Clicks' in df_outbound.columns else 'Event Count'
        change_col = 'Total Users Change' if 'Total Users Change' in df_outbound.columns else 'Total Clicks Change'

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
        # Handle column names from both OAuth and service account paths
        filter_name_col = 'Filter Name' if 'Filter Name' in df_filter_selected.columns else 'filter_name'
        filter_value_col = 'Filter Value' if 'Filter Value' in df_filter_selected.columns else 'filter_value'
        events_col = 'Total Events' if 'Total Events' in df_filter_selected.columns else 'Event Count'
        change_col = 'Total Events Change' if 'Total Events Change' in df_filter_selected.columns else 'Event Count Change'

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

    # Determine authentication mode
    auth_mode, service_account_key = get_auth_mode()

    if auth_mode == 'service_account':
        print("Using Service Account authentication (CI mode)")
        service, credentials = authenticate_service_account(service_account_key)

        # Calculate date range
        import analytics.sheets_elements as elements
        report_dates = elements.get_bounds_for_month_and_prev(CURRENT_MONTH)
        start_date = ANALYTICS_START
        end_date = report_dates["end_current"]

        print(f"Fetching data from {start_date} to {end_date}")

        df_monthly, df_pageviews, df_outbound, df_filter_selected = fetch_data_service_account(
            service, NCPI_CATALOG_ID, start_date, end_date
        )

        data = {
            "monthly_traffic": df_monthly,
            "pageviews": df_pageviews,
            "outbound": df_outbound,
            "filter_selected": df_filter_selected,
            "dates": {
                "start_current": report_dates["start_current"],
                "end_current": report_dates["end_current"],
                "start_prior": report_dates["start_previous"],
                "end_prior": report_dates["end_previous"],
            }
        }
    else:
        print("Using OAuth authentication (interactive mode)")
        ga_authentication = authenticate_oauth()
        data = fetch_data_oauth(ga_authentication)

    # Export data
    export_data(data)


if __name__ == "__main__":
    main()
