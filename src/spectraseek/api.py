"""Local, read-only demonstration API. Do not expose publicly without authentication."""
from fastapi import FastAPI, Query, HTTPException
from .dataset import simulate
from .experiment import evaluate, recommend

app=FastAPI(title='SpectraSeek',version='0.1.0')

@app.get('/health')
def health():
    return {'status':'ok','name':'SpectraSeek'}

@app.get('/demo/evaluation')
def demo_evaluation(
    budget: int = Query(3, ge=1, le=12),
    seed: int = Query(42, ge=0, le=2**32-1),
    windows: int = Query(1, ge=1, le=20),
):
    try:
        return evaluate(simulate(seed), budget, seed, windows=windows)
    except ValueError as e:
        raise HTTPException(status_code=422,detail=str(e)) from e

@app.get('/demo/recommend')
def demo_recommend(visited: list[str]=Query(default=[]), found: list[str]=Query(default=[])):
    try:
        return recommend(simulate(),visited,found)
    except ValueError as e:
        raise HTTPException(status_code=422,detail=str(e)) from e
