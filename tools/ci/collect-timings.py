#!/usr/bin/env python3
"""Read completed GitHub run/job timings; never execute artifacts from that run."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import urllib.request
from common import RESULTS, write_json


def timestamp(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True, type=int)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', 'jl-casella/OrbisDesk'))
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', args.repository):
        parser.error('Invalid repository')
    headers = {'User-Agent': 'OrbisDesk-CI', 'Accept': 'application/vnd.github+json'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']

    def read(suffix):
        url = 'https://api.github.com/repos/' + args.repository + '/actions/runs/' + str(args.run_id) + suffix
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            return json.load(response)

    run = read('')
    if run['status'] != 'completed':
        raise SystemExit('Run has not completed; final timings are unavailable')
    jobs = []
    page = 1
    while True:
        batch = read('/jobs?per_page=100&page=' + str(page))['jobs']
        jobs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    for job in jobs:
        job['duration_seconds'] = ((timestamp(job['completed_at']) - timestamp(job['started_at'])).total_seconds()
                                   if job.get('started_at') and job.get('completed_at') else None)
        for step in job.get('steps', []):
            step['duration_seconds'] = ((timestamp(step['completed_at']) - timestamp(step['started_at'])).total_seconds()
                                        if step.get('started_at') and step.get('completed_at') else None)
    ends = [timestamp(job['completed_at']) for job in jobs if job.get('completed_at')]
    report = {'run_id': args.run_id, 'run_attempt': run['run_attempt'], 'source_sha': run['head_sha'],
              'run_url': run['html_url'], 'conclusion': run['conclusion'], 'event': run['event'],
              'wall_seconds': (max(ends) - timestamp(run['run_started_at'])).total_seconds() if ends else None,
              'wall_basis': 'run_started_at to last completed job',
              'queue_seconds': (timestamp(run['run_started_at']) - timestamp(run['created_at'])).total_seconds(),
              'summed_job_seconds': sum(job['duration_seconds'] or 0 for job in jobs), 'jobs': jobs}
    write_json(RESULTS / 'timings.json', report)
    summary = '# Manual matrix timing\n\n' + run['html_url'] + '\n\n'
    summary += f"Source: `{run['head_sha']}`; outcome: **{run['conclusion']}**.\n\n"
    summary += f"Wall: **{report['wall_seconds']} s**; sum of jobs: **{report['summed_job_seconds']} s**.\n\n"
    summary += '| Job | Result | Seconds |\n| --- | --- | --- |\n'
    summary += '\n'.join(f"| {j['name']} | {j['conclusion']} | {j['duration_seconds']} |" for j in jobs) + '\n'
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(summary)
    print(summary)


if __name__ == '__main__':
    main()
