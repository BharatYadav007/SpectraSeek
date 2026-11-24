"""Run with streamlit run dashboard.py."""

import io
import json

import pandas as pd
import streamlit as st

from spectraseek.adaptive import study
from spectraseek.pilot import compare_snapshots, read_pilot
from spectraseek.dataset import load_csv, simulate
from spectraseek.experiment import RECOMMENDATION_STRATEGIES, evaluate, recommend

st.set_page_config(page_title='SpectraSeek', layout='wide')
st.title('SpectraSeek')
st.caption('AI-Based Target Discovery and Search Optimization in Wireless Networks')
@st.cache_data
def run(data, budget, windows):
    return evaluate(data, budget, windows=windows)



@st.cache_data
def replay_study(data, budgets, windows):
    return study(data, budgets, windows=windows, include_temporal=True)


def download_report(result, filename):
    st.download_button(
        'Download evaluation JSON', json.dumps(result, indent=2, allow_nan=False),
        filename, 'application/json',
    )


def coverage_view(report):
    traces = pd.DataFrame(report['per_session'])
    curves = traces.groupby(['budget', 'model', 'policy']).agg(
        coverage_pct=('coverage_pct', 'mean'), mean_found=('found', 'mean'),
    ).reset_index()
    model = st.selectbox('Replay model', curves.model.unique())
    selected = curves[curves.model == model]
    if selected.coverage_pct.notna().any():
        st.line_chart(selected.pivot(index='budget', columns='policy', values='coverage_pct'))
        st.caption('Coverage is the percentage of targets detectable in the held-out session. '
                   'Sessions with no detectable targets have undefined coverage.')
    else:
        st.info('Coverage is undefined because no targets were detected in the held-out sessions.')
    st.dataframe(selected.assign(targets_per_scan=selected.mean_found / selected.budget),
                 hide_index=True)
    traces = traces[traces.model == model]
    window, session, budget = st.selectbox(
        'Held-out replay', list(traces[['window', 'session', 'budget']].drop_duplicates()
                                .itertuples(index=False, name=None)),
        format_func=lambda key: f'Window {key[0]} · Session {key[1]} · Budget {key[2]}',
    )
    selected = traces[(traces.window == window) & (traces.session == session)
                      & (traces.budget == budget)]
    steps = pd.DataFrame([
        {'policy': row.policy, 'step': step, 'site': site, 'unique targets': found}
        for row in selected.itertuples()
        for step, (site, found) in enumerate(zip(row.sites, row.cumulative_found), 1)
    ])
    st.line_chart(steps, x='step', y='unique targets', color='policy')
    st.dataframe(steps, hide_index=True)
    st.download_button('Download replay study', json.dumps(report, allow_nan=False),
                       f"{report['source']}-replay-study.json", 'application/json')


def pilot_view():
    files = [st.sidebar.file_uploader(f'Scanner {position} pilot CSV', type='csv')
             for position in (1, 2)]
    tolerance = st.sidebar.number_input('Maximum alignment gap (seconds)', 0, 300, 30)
    if any(file is None for file in files):
        st.info('Upload two pilot CSVs to validate observations and compare scan timestamps.')
        return
    try:
        with st.spinner('Validating and aligning pilot scans…'):
            left, right = [read_pilot(io.StringIO(file.getvalue().decode('utf-8-sig')))
                           for file in files]
            report = compare_snapshots(left, right, max_gap_seconds=tolerance)
    except (ValueError, UnicodeError, OSError) as exc:
        st.error(str(exc))
        return

    first, second, matched, unmatched = st.columns(4)
    for column, scanner in zip((first, second), report['scanners']):
        column.metric(f"{scanner['site']} scans", scanner['scans'])
        column.caption(scanner['backend'])
    matched.metric('Candidate pairs', report['matched_pairs'])
    unmatched.metric('Unmatched scans', sum(report['unmatched_scans']))
    detection, alignment, methods = st.tabs(['Observations', 'Timestamp alignment', 'Evaluation'])
    with detection:
        rates = pd.DataFrame([
            {'site': scanner['site'], 'backend': scanner['backend'], **target}
            for scanner in report['scanners'] for target in scanner['targets']
        ])
        detection_heatmap(rates, 'detection_rate')
        st.dataframe(rates, hide_index=True)
        for snapshots in (left, right):
            scanner = snapshots[0]
            st.subheader(f"{scanner['site']} · {scanner['backend']}")
            timestamps = pd.DatetimeIndex([scan['timestamp'] for scan in snapshots], name='timestamp')
            quality = pd.DataFrame([scan['targets'] for scan in snapshots], index=timestamps)
            if quality.notna().any().any():
                st.line_chart(quality)
                st.caption('Signal quality is reported by the scanner. Nondetections have no quality reading.')
            else:
                st.info('This scanner recorded no detections.')
    with alignment:
        if report['pairs']:
            pairs = pd.DataFrame(report['pairs'])
            pairs['left_timestamp'] = pd.to_datetime(pairs.left_timestamp, utc=True)
            st.scatter_chart(pairs, x='left_timestamp', y='gap_seconds')
            st.dataframe(pairs, hide_index=True)
        else:
            st.info('No scan pairs fall within the selected tolerance.')
        for scanner, scans in zip(report['scanners'], report['unmatched_observations']):
            st.write(f"{scanner['site']} · {len(scans)} unmatched scans")
            if scans:
                st.dataframe(scans, hide_index=True)
    with methods:
        st.warning(report['model_evaluation']['reason'])
        st.caption('Model scores, search coverage, scan efficiency and location recommendations '
                   'require a verified multi-site survey. See docs/PILOT_ANALYSIS.md for the protocol.')
        for limitation in report['limitations']:
            st.markdown(f'- {limitation}')
    download_report(report, 'pilot.local.json')


def detection_heatmap(rows, value):
    st.subheader('Target detection rate by site')
    matrix = rows.pivot(index='site', columns='target', values=value)
    st.dataframe(matrix.style.map(lambda rate: f'background-color: rgba(52, 132, 237, {rate * 0.65})')
                 .format('{:.0%}'), use_container_width=True)


def survey_view(mode):
    if mode == 'Synthetic':
        file = st.sidebar.file_uploader('Synthetic survey CSV (optional)', type='csv')
    else:
        file = st.sidebar.file_uploader('Verified measured survey CSV', type='csv')
        if file is None:
            st.info('Upload a complete measured survey exported from the survey database.')
            return
    try:
        df = load_csv(file) if file is not None else simulate()
        if df.source.iloc[0] != mode.lower():
            raise ValueError(f'This view requires a {mode.lower()} survey CSV.')
    except (ValueError, UnicodeError) as exc:
        st.error(str(exc))
        return

    st.info('Synthetic demonstration' if mode == 'Synthetic' else 'Measured survey supplied by the user')
    site_count = df.site.nunique()
    budget = st.sidebar.slider('Site budget', 1, site_count, min(3, site_count)) if site_count > 1 else 1
    max_windows = (df.session.nunique() + 1) // 2
    windows = st.sidebar.number_input(
        'Evaluation windows', min_value=1, max_value=max_windows, value=1, step=1,
        help='One window holds out the last quarter. More windows test the later half in chronological batches.',
    )
    try:
        with st.spinner('Evaluating chronological survey windows…'):
            result = run(df, budget, windows)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    records, sites, targets, sessions = st.columns(4)
    records.metric('Survey records', len(df))
    sites.metric('Sites', result['sites'])
    targets.metric('Targets', result['targets'])
    sessions.metric('Held-out sessions', len(result['test_sessions']))

    search_tab, models_tab, data_tab, replay_tab = st.tabs(
        ['Search performance', 'ML evaluation', 'Survey data', 'Adaptive replay'],
    )
    with search_tab:
        strategies = pd.DataFrame(result['strategies']).set_index('strategy')
        st.bar_chart(strategies['mean_found'])
        st.dataframe(strategies)
        st.caption('The offline oracle is a hindsight upper bound. Random uses 30 trials per session.')
        st.subheader('Coverage difference vs empirical greedy')
        comparisons = pd.DataFrame.from_dict(result['coverage_vs_empirical'], orient='index')
        st.dataframe(comparisons.rename(columns={
            'sessions': 'Sessions',
            'mean_delta_pp': 'Mean difference (pp)',
            'bootstrap_95_ci_pp': '95% bootstrap interval (pp)',
        }))
        st.caption('Intervals treat sessions as independent. A small pilot can give unstable estimates.')
        st.subheader('Site plans for the final evaluation window')
        st.json(result['recommendations'])

    with models_tab:
        metrics = {**result['classification_baseline'], **result['models']}
        table = pd.DataFrame(metrics).T.drop(columns='confusion_matrix')
        st.dataframe(table)
        st.bar_chart(table[['accuracy', 'precision', 'recall', 'f1']].astype(float))
        st.subheader('Confusion matrices')
        st.json({name: values['confusion_matrix'] for name, values in metrics.items()})

    with data_tab:
        rates = df.groupby(['site', 'target'], as_index=False).detected.mean()
        detection_heatmap(rates, 'detected')
        st.dataframe(df.head(100))
        st.download_button('Download survey CSV', df.to_csv(index=False),
                           f'{mode.lower()}-survey.csv', 'text/csv')

    with replay_tab:
        try:
            with st.spinner('Replaying fixed and adaptive search plans…'):
                report = replay_study(df, tuple(range(1, site_count + 1)), windows)
        except ValueError as exc:
            st.error(str(exc))
        else:
            coverage_view(report)
            st.subheader('Held-out classification, including temporal predictors')
            scores = pd.DataFrame(report['classification']).T.drop(columns='confusion_matrix')
            st.bar_chart(scores[['accuracy', 'precision', 'recall', 'f1']].astype(float))
            st.dataframe(scores)

    download_report(result, f'{mode.lower()}-evaluation.json')

    with st.expander('Plan the next authorized survey location'):
        visited = st.multiselect('Already visited sites', sorted(df.site.unique()))
        found = st.multiselect('Already discovered targets', sorted(df.target.unique()))
        strategy = st.selectbox(
            'Planning strategy', RECOMMENDATION_STRATEGIES,
            index=RECOMMENDATION_STRATEGIES.index('random_forest'),
        )
        if st.button('Recommend next site'):
            try:
                next_site = recommend(df, visited, found, strategy)
                if next_site['site'] is None:
                    st.info('No remaining sites or targets.')
                else:
                    st.json(next_site)
            except ValueError as exc:
                st.error(str(exc))


st.sidebar.header('Survey configuration')
mode = st.sidebar.radio('Dataset', ['Synthetic', 'Measured pilot', 'Measured survey'])
if mode == 'Measured pilot':
    pilot_view()
else:
    survey_view(mode)
