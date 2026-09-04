"""Refresh the paper's matched-leverage comparisons using existing source panels.

Run after rebuild_all.sh's data stage. Each simulation keeps the historical
panel and household conventions of the corresponding published experiment.
"""
from pathlib import Path
import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent.parent

def run(job):
    label, arguments = job
    logs = ROOT / 'results/aco_leverage_logs'
    logs.mkdir(exist_ok=True)
    with (logs / (label + '.log')).open('w') as stream:
        subprocess.run([sys.executable, *arguments], cwd=ROOT,
                       stdout=stream, stderr=subprocess.STDOUT, check=True)
    print('Completed ' + label, flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--methods-only', action='store_true')
    args = parser.parse_args()
    base = ['build/compare_fixed_stacked_utility.py', '--runs', '10000',
            '--seed', '20260827', '--portfolio-set', 'ladders']
    jobs = [('baseline', base + ['--output-json', 'results/main_ladders_n10000.json'])]
    for year in (1950, 1970):
        jobs.append((str(year), base + ['--year-from', str(year), '--output-json',
            f'results/method_review/sample_windows/post{year}_ladders_n10000.json']))
    for label, script in [('source_exclusions', 'source_exclusion_diagnostics'),
                          ('cost', 'central_cost_sensitivity'),
                          ('policy', 'policy_sensitivity'),
                          ('ablation', 'sleeve_ablation'),
                          ('margin', 'margin_call_experiment'),
                          ('gamma', 'gamma_sensitivity')]:
        jobs.append((label, [f'build/{script}.py']))
    jobs.append(('gamma_fixed_theta', ['build/gamma_sensitivity.py', '--fixed-theta',
        '--output-json', 'results/gamma_fixed_theta_n10000.json',
        '--output-tex', 'paper/figures/gamma_fixed_theta.tex']))
    for panel in sorted((ROOT / 'results/method_review/source_loo').glob('panel-*.csv')):
        country = panel.stem[6:]
        jobs.append(('omit_' + country, base + ['--runs', '5000', '--panel', str(panel),
            '--exclude-country', country, '--output-json',
            f'results/method_review/source_loo/{country}.json']))
    variants = {
        'raw_corrected_fixed_notional_aco': [],
        'raw_corrected_fixed_notional_restart': ['--bootstrap-end-treatment', 'restart'],
        'raw_corrected_ideal_aco': ['--hedge-mode', 'ideal'],
        'legacy_return_filter_fixed_notional_aco': ['--panel', 'results/method_review/panel-filtered.csv'],
        'war_screen_fixed_notional_aco': ['--exclude-war-years'],
    }
    if args.methods_only:
        jobs = []
    for label, options in variants.items():
        jobs.append((label, base + options + ['--output-json',
                     f'results/method_review/final/{label}_n10000.json']))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, jobs))
    if args.methods_only:
        return
    run(('source_summary', ['build/source_country_sensitivity.py', '--runs', '5000',
                           '--summarize-existing']))

if __name__ == '__main__':
    main()
