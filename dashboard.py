"""Run with streamlit run dashboard.py."""
import streamlit as st
import pandas as pd
from spectraseek.dataset import simulate, validate
from spectraseek.experiment import evaluate, recommend
import json

st.set_page_config(page_title='SpectraSeek',layout='wide')
st.title('SpectraSeek')
st.caption('AI-Based Target Discovery and Search Optimization in Wireless Networks')
st.sidebar.header('Survey configuration')
file=st.sidebar.file_uploader('Complete survey CSV (optional)',type='csv')
try:
    df=validate(pd.read_csv(file,dtype={'session':str})) if file else simulate()
except ValueError as e:
    st.error(str(e)); st.stop()
st.info('SYNTHETIC DEMONSTRATION — not measured wireless data' if df.source.iloc[0]=='synthetic' else 'Measured survey data (user supplied; provenance not independently verified)')
budget=st.sidebar.slider('Site budget',1,int(df.site.nunique()),min(3,int(df.site.nunique())))
@st.cache_data
def run(data,budget):
    return evaluate(data,budget)
try:
    result=run(df,budget)
except ValueError as e:
    st.error(str(e)); st.stop()
a,b,c,d=st.columns(4)
a.metric('Survey records',len(df)); b.metric('Sites',result['sites']); c.metric('Targets',result['targets']); d.metric('Held-out sessions',len(result['test_sessions']))
coverage,models,data=st.tabs(['Search performance','ML evaluation','Survey data'])
with coverage:
    table=pd.DataFrame(result['strategies']).set_index('strategy'); st.bar_chart(table['mean_found']); st.dataframe(table); st.caption('Offline oracle is a hindsight upper bound, not a live strategy. Random is averaged over 30 trials per session.'); st.subheader('Recommended sites'); st.json(result['recommendations'])
with models:
    table=pd.DataFrame(result['models']).T.drop(columns='confusion_matrix'); st.dataframe(table); st.bar_chart(table[['accuracy','precision','recall','f1']].astype(float)); st.subheader('Confusion matrices'); st.json({k:v['confusion_matrix'] for k,v in result['models'].items()})
with data:
    st.dataframe(df.head(100)); st.download_button('Download survey CSV',df.to_csv(index=False),'survey.csv','text/csv')
st.download_button('Download evaluation JSON',json.dumps(result,indent=2),'evaluation.json','application/json')

with st.expander('Plan the next authorized survey location'):
    visited=st.multiselect('Already visited sites', sorted(df.site.unique()))
    found=st.multiselect('Already discovered targets', sorted(df.target.unique()))
    strategy=st.selectbox('Planning strategy',['random_forest','logistic','empirical_greedy'])
    if st.button('Recommend next site'):
        try:
            st.json(recommend(df,visited,found,strategy))
        except ValueError as exc:
            st.error(str(exc))
