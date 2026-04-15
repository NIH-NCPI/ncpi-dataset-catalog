# Analytics

This directory contains tools for generating analytics reports from Google Analytics 4 data.

## Installing the environment

- Use Python 3.12.4
- Run `python -m venv ./venv` to create a new environment under `./venv`
- Run `source ./venv/bin/activate` to activate the environment
- Run `pip install -r ./requirements.txt` to install requirements

## Deactivating/reactivating

- To deactivate the environment, run `deactivate`
- To activate the environment again, run `source ./venv/bin/activate`

## Generating Google Sheets Reports

- Update `constants.py` to reflect the date ranges and file name you would like for the report
- Open `./generate_sheets_report.ipynb` using your favorite IDE or by running `jupyter notebook`
- Run all cells in the Jupyter notebook. You will be prompted to log in to your Google Account, which must have access to the relevant analytics property
- Check your Google Drive to ensure that the desired spreadsheet is present

## Generating Static Analytics Site

The `generate_static_site.py` script creates a static HTML site with interactive charts, suitable for hosting on GitHub Pages.

### Generate fresh data

1. Update `constants.py` with the current month
2. Activate the venv and run the script:
   ```bash
   source ./venv/bin/activate
   python generate_static_site.py
   ```
3. You'll be prompted to authenticate with Google (browser window opens)
4. JSON files will be written to `site/data/`

### Run locally

```bash
cd site
python -m http.server 8080
```

Then open http://localhost:8080 in your browser.

### Deploy to GitHub Pages

The `site/` directory can be deployed directly to GitHub Pages:

1. Push the `site/` directory to a `gh-pages` branch, or
2. Configure GitHub Pages to serve from `analytics/site/` on main branch

### CI/CD (GitHub Actions)

For automated deployments, the script supports service account authentication:

```bash
GA_SERVICE_ACCOUNT_KEY=/path/to/service-account.json python generate_static_site.py
```

Set `GA_SERVICE_ACCOUNT_KEY` as a GitHub secret containing the service account JSON key.
