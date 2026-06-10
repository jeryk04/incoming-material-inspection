import os
from flask import Flask, render_template, jsonify, send_file
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

app = Flask(__name__, template_folder='../templates')

BASE_DIR = Path(__file__).parent.parent
LOG_FILE      = Path(os.getenv("WATCHER_LOG_PATH")     or BASE_DIR / 'watcher.log')
PROCESSED_DIR = Path(os.getenv("PROCESSED_FOLDER_PATH") or BASE_DIR / 'data' / 'processed')
REPORTS_DIR   = Path(os.getenv("REPORTS_FOLDER_PATH")   or BASE_DIR / 'reports')
BATCH_SUMMARY = PROCESSED_DIR / 'batch_summary.csv'


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/results')
def get_results():
    if not BATCH_SUMMARY.exists():
        return jsonify([])
    try:
        df = pd.read_csv(BATCH_SUMMARY)
        df = df.fillna('')
        records = df.iloc[::-1].to_dict('records')
        # Attach report filename if it exists
        for row in records:
            report_name = str(row.get('report_filename', '')).strip()
            row['report'] = report_name if report_name and (REPORTS_DIR / report_name).exists() else ''
        return jsonify(records)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats')
def get_stats():
    if not BATCH_SUMMARY.exists():
        return jsonify({'total': 0, 'accepted': 0, 'rejected': 0})
    try:
        df = pd.read_csv(BATCH_SUMMARY)
        total = len(df)
        accepted = int((df['final_result'] == 'LOT ACCEPTED').sum())
        rejected = int((df['final_result'] == 'LOT REJECTED').sum())
        return jsonify({'total': total, 'accepted': accepted, 'rejected': rejected})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/logs')
def get_logs():
    if not LOG_FILE.exists():
        return jsonify({'lines': []})
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        return jsonify({'lines': lines[-400:]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/reports/<path:filename>')
def serve_report(filename):
    report_path = REPORTS_DIR / filename
    if not report_path.exists():
        return 'Report not found', 404
    return send_file(report_path)


if __name__ == '__main__':
    port = int(os.getenv("DASHBOARD_PORT", 5000))
    print()
    print('  Incoming Inspection Dashboard')
    print(f'  http://0.0.0.0:{port}')
    print()
    app.run(host='0.0.0.0', port=port, debug=False)
