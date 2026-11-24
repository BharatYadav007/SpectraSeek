"""Run with streamlit run dashboard.py."""

import json

import pandas as pd
import streamlit as st

from spectraseek.dataset import load_csv, simulate
from spectraseek.experiment import RECOMMENDATION_STRATEGIES, evaluate, recommend

st.set_page_config(page_title='SpectraSeek', layout='wide')
st.title('SpectraSeek')
st.caption('AI-Based Target Discovery and Search Optimization in Wireless Networks')
st.sidebar.header('Survey configuration')

file = st.sidebar.file_uploader('Complete survey CSV (optional)', type='csv')
try:
    df = load_csv(file) if file is not None else simulate()
except (ValueError, UnicodeError) as exc:
    st.error(str(exc))
    st.stop()

if df.source.iloc[0] == 'synthetic':
    st.info('Synthetic demonstration')
else:
    st.info('Measured survey data supplied by the user')

site_count = df.site.nunique()
if site_count == 1:
    budget = 1
    st.sidebar.caption('Site budget is 1 for this survey.')
else:
    budget = st.sidebar.slider('Site budget', 1, site_count, min(3, site_count))
max_windows = (df.session.nunique() + 1) // 2
windows = st.sidebar.number_input(
    'Evaluation windows', min_value=1, max_value=max_windows, value=1, step=1,
    help='One window holds out the last quarter. More windows test the later half in chronological batches.',
)


@st.cache_data
def run(data, budget, windows):
    return evaluate(data, budget, windows=windows)


try:
    result = run(df, budget, windows)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

records, sites, targets, sessions = st.columns(4)
records.metric('Survey records', len(df))
sites.metric('Sites', result['sites'])
targets.metric('Targets', result['targets'])
sessions.metric('Held-out sessions', len(result['test_sessions']))

search_tab, models_tab, data_tab = st.tabs(['Search performance', 'ML evaluation', 'Survey data'])
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
    st.dataframe(df.head(100))
    st.download_button('Download survey CSV', df.to_csv(index=False), 'survey.csv', 'text/csv')

st.download_button(
    'Download evaluation JSON', json.dumps(result, indent=2, allow_nan=False),
    'evaluation.json', 'application/json',
)

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
