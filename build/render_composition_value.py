#!/usr/bin/env python3
"""Render the composition- and exposure-value tables from the frozen JSON."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'results/composition_value_n10000.json'
SOURCE_LATE = ROOT / 'results/composition_value_1970_n10000.json'
FIG = ROOT / 'paper/new_paper/figures/erc'
EXPOSURE = 175

LATE_NOTE = (' The last column draws returns from 1970 to 2025, after the 1968 separation of the free London gold '
             'market from the official price.')


def table(path, caption, label, header, body, note, size=r'\small'):
    cols = 'l' + 'r' * (len(header) - 1)
    text = (r'\begin{table}[p]\centering' + '\n'
            + '\\caption{' + caption + '}\\label{' + label + '}\n'
            + r'\begin{minipage}{\linewidth}\small ' + note + r'\end{minipage}' + '\n\\medskip\n\n'
            + '{\\setlength{\\tabcolsep}{4pt}' + size + '\n'
            + '\\begin{tabular}{' + cols + '}\\toprule\n'
            + ' & '.join(header) + r' \\ \midrule' + '\n'
            + '\n'.join(body)
            + '\n' + r'\bottomrule\end{tabular}}' + '\n'
            + r'\end{table}' + '\n')
    path.write_text(text)


def pp(value):
    return f'{100 * value:+.1f}'.replace('-', '$-$')


def group(text, columns):
    return r'\multicolumn{' + str(columns) + r'}{c}{' + text + r'} \\'


def local_cells(record, scale_pp):
    """Local decomposition per 10 pp reallocated, total local and exact values."""
    per = 10.0 / scale_pp
    local = record['local_saving_change']
    exact = record['exact_saving_change']
    agree = r'\checkmark' if local * exact > 0 else r'$\times$'
    return (f'{pp(local * per)} & {pp(record["local_mean_component"] * per)} & '
            f'{pp(record["local_covariance_component"] * per)} & '
            f'{pp(local)} & {pp(exact)} & {agree}')


def composition_row(name, record, record_late):
    return (f'{name} & {100 * record["reallocation"]:.1f} & '
            f'{pp(record["exact_saving_change"])} & '
            f'{pp(record_late["exact_saving_change"])} \\\\')


def composition_local_row(name, record):
    return (f'{name} & {100 * record["reallocation"]:.1f} & '
            + local_cells(record, 100 * record['reallocation']) + r' \\')


def optimal_row(name, record, record_late):
    return (f'{name} & {100 * record["reallocation"]:.1f} & '
            f'{pp(record["saving_change_vs_aco175"])} & '
            f'{pp(record_late["saving_change_vs_aco175"])} \\\\')


def weight_string(record):
    weights = record['weights']
    parts = [f'{100 * weights["equity"]:.0f}\\% stocks']
    for key, label in (('bonds', 'global bonds'), ('gold', 'gold'), ('mf', 'managed futures')):
        if weights.get(key, 0.0) >= 0.005:
            parts.append(f'{100 * weights[key]:.0f}\\% {label}')
    return ', '.join(parts)


def weights_sentence(payload):
    text = weight_string(payload['optimal_composition'])
    stressed = '; '.join(
        f'{weight_string(entry)} with a {entry["haircut_bp"] / 100:.0f}\\% haircut'
        for entry in payload.get('optimal_composition_stressed', []))
    return text + (f'; {stressed}' if stressed else '')


def exposure_row(step, record, record_late):
    return (f'{step} & {pp(record["exact_saving_change"])} & '
            f'{pp(record_late["exact_saving_change"])} \\\\')


def exposure_local_row(step, record):
    return f'{step} & ' + local_cells(record, 100 * record['delta_g']) + r' \\'


SLEEVE_LABELS = {'bonds': 'Global bonds', 'gold': 'Gold',
                 'managed futures': 'Managed futures',
                 'remove bonds': 'Global bonds', 'remove gold': 'Gold',
                 'remove mf': 'Managed futures',
                 'remove bonds and gold': 'Bonds and gold',
                 'proportional package': 'All three asset classes',
                 'remove package': 'All three asset classes'}


def main():
    payload = json.loads(SOURCE.read_text())
    payload_late = json.loads(SOURCE_LATE.read_text())
    by_label = {entry['label']: entry for entry in payload['experiments']}
    by_label_late = {entry['label']: entry for entry in payload_late['experiments']}

    def transfer(labels, experiment_label, transfer_label):
        entry = labels[experiment_label]
        return next(r for r in entry['transfers'] if r['label'] == transfer_label)

    blocks = [
        (f'Panel A: Add one asset class to the all-equity strategy at {EXPOSURE}\\%', '$+$ ',
         f'Four-sleeve composition at {EXPOSURE}% exposure',
         ('bonds', 'gold', 'managed futures', 'proportional package')),
        (f'Panel B: Remove one asset class from the proportional strategy at {EXPOSURE}\\%', '$-$ ',
         f'Four-sleeve composition at {EXPOSURE}% exposure (proportional)',
         ('remove bonds', 'remove gold', 'remove mf', 'remove bonds and gold', 'remove package')),
        (f'Panel C: Remove one asset class from the risk parity strategy at {EXPOSURE}\\%', '$-$ ',
         f'Four-sleeve composition at {EXPOSURE}% exposure (ERC)',
         ('remove bonds', 'remove gold', 'remove mf', 'remove bonds and gold', 'remove package')),
    ]
    body, local_body = [], []
    for title, sign, experiment, keys in blocks:
        body.append(group(title, 4))
        local_body.append(group(title, 8))
        for key in keys:
            record = transfer(by_label, experiment, key)
            body.append(composition_row(sign + SLEEVE_LABELS[key], record,
                                        transfer(by_label_late, experiment, key)))
            local_body.append(composition_local_row(sign + SLEEVE_LABELS[key], record))
        body.append(r'\midrule')
        local_body.append(r'\midrule')
    local_body.pop()
    body.append(group(f'Panel D: Utility-maximizing weights at {EXPOSURE}\\% exposure', 4))
    body.append(optimal_row('Optimal mix', payload['optimal_composition'],
                            payload_late['optimal_composition']))
    late_stressed = {entry['haircut_bp']: entry
                     for entry in payload_late.get('optimal_composition_stressed', [])}
    for entry in payload.get('optimal_composition_stressed', []):
        body.append(optimal_row(f'Optimal mix, MF $-${entry["haircut_bp"]}bp', entry,
                                late_stressed[entry['haircut_bp']]))

    note = ('The table reports the change in the equivalent savings rate, in percentage points, from changing '
            f'the asset class weights of a strategy at {EXPOSURE}\\% gross exposure. A negative change means that the '
            'household needs to save less to attain the expected utility of the all-equity strategy at 100\\% '
            'exposure and a 10\\% savings rate. Panel A adds global bonds, gold, managed futures, or all three to the '
            'levered all-equity strategy at their proportional-strategy weights, financed by reducing stocks. Panels '
            'B and C remove one asset class from the proportional or risk parity strategy and reallocate its weight '
            'to stocks. Reallocation is the weight moved, as a percentage of wealth. Panel D reports the weights that '
            'maximize expected utility at 175\\% exposure in each sample, measured relative to the all-equity strategy '
            'at 175\\%; the last two rows reoptimize after subtracting 3\\% and 6\\% per year from managed-futures '
            'returns. Each comparison is based on 10,000 bootstrap simulations.')
    note += LATE_NOTE
    note += f' In the full sample, the optimal weights are {weights_sentence(payload)}.'
    note += f' In the post-1970 sample, they are {weights_sentence(payload_late)}.'
    table(FIG / 'composition_value.tex',
          'Sources of the gains from levered diversification',
          'tab:composition-value',
          ['Change in weights', 'Reallocation', r'\shortstack{Full sample\\ (1927--2025)}',
           r'\shortstack{Post-1970 sample\\ (1970--2025)}'],
          body, note)
    print(f"wrote {FIG.relative_to(ROOT) / 'composition_value.tex'}")

    local_note = (
        'The table decomposes the changes in Panels A to C of Table~\\ref{tab:composition-value} using the '
        'first-order approximation in Section~\\ref{app:framework}. Local is the derivative of the equivalent '
        'savings rate with respect to the change in weights, evaluated at the initial weights. The first three '
        'columns scale it to a reallocation of 10\\% of wealth and split it into a mean term, '
        '$E[M_t]\\,E[\\Delta R_t]$, and a covariance term, $\\mathrm{Cov}(M_t,\\Delta R_t)$. The next two columns '
        'report the local value for the full reallocation and the exact change from Table~\\ref{tab:composition-value}. '
        'Sign indicates whether the two agree in sign. The sample is 1927 to 2025, and entries are in percentage '
        'points.')
    table(FIG / 'composition_local.tex',
          f'First-order decomposition of changes in asset class weights',
          'tab:composition-local',
          ['Change in weights', 'Realloc.', r'\shortstack{Local\\ per 10 pp}', r'\shortstack{of which\\ mean}',
           r'\shortstack{of which\\ cov.}', r'\shortstack{Local,\\ full move}', 'Exact', 'Sign'],
          local_body, local_note, size=r'\footnotesize')
    print(f"wrote {FIG.relative_to(ROOT) / 'composition_local.tex'}")

    def exposure_record(labels, experiment_label, delta):
        entry = labels[experiment_label]
        return next(r for r in entry['exposure'] if abs(r['delta_g'] - delta) < 1e-9)

    exposure_blocks = [('Panel A: All-equity strategy', 'equity benchmark'),
                       ('Panel B: Proportional strategy', 'proportional portfolio'),
                       ('Panel C: Risk parity strategy', 'ERC portfolio')]
    steps = [('100$\\to$125', '', 0.25), ('100$\\to$175', '', 0.75), ('175$\\to$200', ' at 175%', 0.25)]
    exposure_body, exposure_local_body = [], []
    for title, name in exposure_blocks:
        exposure_body.append(group(title, 3))
        exposure_local_body.append(group(title, 7))
        for step, suffix, delta in steps:
            label = f'Leverage of the {name}{suffix}'
            record = exposure_record(by_label, label, delta)
            exposure_body.append(exposure_row(step, record, exposure_record(by_label_late, label, delta)))
            exposure_local_body.append(exposure_local_row(step, record))
        exposure_body.append(r'\midrule')
        exposure_local_body.append(r'\midrule')
    exposure_body.pop()
    exposure_local_body.pop()

    exposure_note = (
        'The table reports the change in the equivalent savings rate, in percentage points, from raising the '
        'gross exposure of each strategy. A negative change means that the household needs to save less. Each '
        'comparison is based on 10,000 bootstrap simulations.') + LATE_NOTE
    table(FIG / 'exposure_value.tex',
          'Changes in the equivalent savings rate from additional leverage',
          'tab:exposure-value',
          ['Gross exposure', r'\shortstack{Full sample\\ (1927--2025)}',
           r'\shortstack{Post-1970 sample\\ (1970--2025)}'],
          exposure_body, exposure_note)
    print(f"wrote {FIG.relative_to(ROOT) / 'exposure_value.tex'}")

    exposure_local_note = (
        'The table decomposes the changes in Table~\\ref{tab:exposure-value} using the first-order approximation '
        'in Section~\\ref{app:framework}. Local is the derivative of the equivalent savings rate with respect to '
        'gross exposure, evaluated at the initial exposure and scaled to an increase of 10\\% of wealth. The mean '
        'column is the average excess-return term, and the covariance column is the utility cost of the added '
        'volatility. The last three columns report the local value for the full step, the exact change, and '
        'whether the two agree in sign. The sample is 1927 to 2025, and entries are in percentage points.')
    table(FIG / 'exposure_local.tex',
          'First-order decomposition of changes in gross exposure',
          'tab:exposure-local',
          ['Gross exposure', r'\shortstack{Local\\ per 10 pp}', r'\shortstack{of which\\ mean}',
           r'\shortstack{of which\\ cov.}', r'\shortstack{Local,\\ full step}', 'Exact', 'Sign'],
          exposure_local_body, exposure_local_note)
    print(f"wrote {FIG.relative_to(ROOT) / 'exposure_local.tex'}")


if __name__ == '__main__':
    main()
