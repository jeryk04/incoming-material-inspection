"""
watcher.py — continuous server process for incoming material inspection.

Watches data/incomings/ for new PDFs and processes them automatically.
On startup it also processes any PDFs that were dropped in while the
watcher was not running (backlog).

Usage (from the project root):
    python src/watcher.py
"""

import os
import sys
import time
import logging

# Make the other src/ modules importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Project root = the directory that contains src/, data/, reports/.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Change to project root so the relative paths in main.py resolve correctly.
os.chdir(BASE_DIR)

import pandas as pd
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import main as inspector  # noqa: E402  (import after chdir is intentional)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(BASE_DIR, "watcher.log"), encoding="utf-8"
        ),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Absolute paths (watchdog needs an absolute folder to watch)
# ---------------------------------------------------------------------------

INCOMING_FOLDER = os.path.join(BASE_DIR, inspector.INCOMING_FOLDER)
PROCESSED_FOLDER = os.path.join(BASE_DIR, inspector.PROCESSED_FOLDER)
REPORTS_FOLDER = os.path.join(BASE_DIR, inspector.REPORTS_FOLDER)
BATCH_SUMMARY_PATH = os.path.join(PROCESSED_FOLDER, "batch_summary.csv")

# How long to wait (in seconds) between file-size checks when waiting for a
# large PDF to finish copying.  Up to MAX_RETRIES × INTERVAL = 30 s total.
_STABLE_INTERVAL = 2
_STABLE_MAX_RETRIES = 15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_processed(pdf_path: str) -> bool:
    """Return True if an analysis JSON already exists for this PDF."""
    stem = inspector.safe_filename(
        os.path.splitext(os.path.basename(pdf_path))[0]
    )
    return os.path.exists(os.path.join(PROCESSED_FOLDER, f"{stem}_analysis.json"))


def _wait_stable(pdf_path: str) -> bool:
    """
    Block until the file stops growing (copy/write finished).
    Returns True when the file is ready, False if it disappears or times out.
    """
    prev = -1
    for _ in range(_STABLE_MAX_RETRIES):
        try:
            size = os.path.getsize(pdf_path)
        except OSError:
            return False
        if size == prev and size > 0:
            return True
        prev = size
        time.sleep(_STABLE_INTERVAL)
    return False


def _update_summary(new_row: dict) -> None:
    """
    Append or replace the row for this item+PO in the batch summary CSV.
    """
    if os.path.exists(BATCH_SUMMARY_PATH):
        try:
            existing = pd.read_csv(BATCH_SUMMARY_PATH, dtype=str)
        except Exception:
            existing = pd.DataFrame()
    else:
        existing = pd.DataFrame()

    if not existing.empty:
        drop = pd.Series(False, index=existing.index)
        # Remove any row that came from the same source PDF.
        if "source_pdf" in existing.columns and new_row.get("source_pdf"):
            drop |= existing["source_pdf"] == str(new_row["source_pdf"])
        # Also remove by item+PO in case the source_pdf column is absent (old rows).
        if "item_number" in existing.columns and "po_number" in existing.columns:
            drop |= (
                (existing["item_number"] == str(new_row.get("item_number", "")))
                & (existing["po_number"] == str(new_row.get("po_number", "")))
            )
        existing = existing[~drop]

    combined = pd.concat([existing, pd.DataFrame([new_row])], ignore_index=True)
    combined.to_csv(BATCH_SUMMARY_PATH, index=False)


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def _process(pdf_path: str) -> None:
    """Wait for the file to stabilise, then run it through the pipeline."""
    name = os.path.basename(pdf_path)
    log.info(f"Detected: {name}")

    if not _wait_stable(pdf_path):
        log.warning(f"File not ready (disappeared or timed out): {name}")
        return

    try:
        summary_row = inspector.process_single_pdf(pdf_path)
        _update_summary(summary_row)
        log.info(f"Completed: {name}  →  {summary_row.get('final_result', '?')}")
    except Exception:
        log.exception(f"Failed to process: {name}")


# ---------------------------------------------------------------------------
# Watchdog event handler
# ---------------------------------------------------------------------------

class _PDFHandler(FileSystemEventHandler):
    """React to PDFs being created or moved into the watch folder."""

    def _handle(self, path: str) -> None:
        if os.path.splitext(path)[1].lower() == ".pdf":
            _process(os.path.abspath(path))

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path)


# ---------------------------------------------------------------------------
# Startup backlog sweep
# ---------------------------------------------------------------------------

def _process_backlog() -> None:
    """Process any PDFs that arrived while the watcher was not running."""
    all_pdfs = inspector.get_all_incoming_pdfs()
    pending = [p for p in all_pdfs if not _is_processed(p)]

    if not pending:
        log.info("No backlogged PDFs.")
        return

    log.info(f"Backlog: processing {len(pending)} PDF(s).")
    for pdf_path in pending:
        _process(pdf_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--process-backlog", action="store_true",
                        help="Also process any existing unprocessed PDFs on startup.")
    args = parser.parse_args()

    log.info("=" * 44)
    log.info("  INCOMING MATERIAL INSPECTION WATCHER")
    log.info("=" * 44)

    for folder in (INCOMING_FOLDER, PROCESSED_FOLDER, REPORTS_FOLDER):
        os.makedirs(folder, exist_ok=True)

    if args.process_backlog:
        _process_backlog()
    else:
        log.info("Watching for new files only. Use --process-backlog to also process existing PDFs.")

    handler = _PDFHandler()
    observer = Observer()
    observer.schedule(handler, INCOMING_FOLDER, recursive=True)
    observer.start()

    log.info(f"Watching: {INCOMING_FOLDER}")
    log.info(f"Reports:  {REPORTS_FOLDER}")
    log.info(f"Drop a PDF into {INCOMING_FOLDER} to trigger processing.")
    log.info("Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    log.info("Shutting down...")
    observer.stop()
    observer.join()
    log.info("Watcher stopped.")


if __name__ == "__main__":
    main()
