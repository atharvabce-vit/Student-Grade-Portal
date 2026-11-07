"""Snapshot the live database and report files into a dated folder.

Run it from the CLI (``py main.py report``) or from any scheduler (cron,
Windows Task Scheduler) to keep periodic copies of the data.
"""

import datetime
import os

import database
from export import export_to_csv


def timestamp(when=None):
    moment = when or datetime.datetime.now()
    return moment.strftime("%Y%m%d-%H%M%S")


def run_backup(directory="backups", when=None):
    """Copy the database and write a CSV report into `directory`."""
    stamp = timestamp(when)
    os.makedirs(directory, exist_ok=True)

    database_path = os.path.join(directory, f"students-{stamp}.db")
    csv_path = os.path.join(directory, f"students-{stamp}.csv")

    database.backup_to(database_path)
    export_to_csv(csv_path)

    return {"database": database_path, "csv": csv_path}
