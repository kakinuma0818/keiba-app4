import pandas as pd

def simple_rank(df: pd.DataFrame):
    df = df.copy()
    df["評価"] = df["前走着順"].rank(ascending=True)
    return df
