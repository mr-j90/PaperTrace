"""Register and run the daily delta schedule (SPEC §4).

A long-lived Prefect serve process: registers the papertrace-delta deployment
with a daily cron against the Prefect server (PREFECT_API_URL) and executes its
runs. Ships as the `scheduler` compose service.
"""

from ingest.delta import ingest_delta

DAILY_AT_06_UTC = "0 6 * * *"

if __name__ == "__main__":
    ingest_delta.serve(name="daily-delta", cron=DAILY_AT_06_UTC)
