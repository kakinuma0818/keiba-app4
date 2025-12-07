import pandas as pd

def load_dummy_data():
    return pd.DataFrame({
        "馬名": ["サンプルホースA", "サンプルホースB"],
        "脚質": ["先行", "差し"],
        "適性": ["ダート1800", "芝2400"],
        "前走着順": [1, 3]
    })
