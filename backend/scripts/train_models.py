#!/usr/bin/env python3
"""Train all three ML models on 2 years of historical data."""
import sys
import os

# Ensure the backend app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from app.ml.trainer import ModelTrainer

trainer = ModelTrainer()
print(f"Model dir: {trainer.model_dir}")
print(f"DB:        {trainer.db_url}")
print()

metrics = trainer.train_all()

print("\n=== Training complete ===\n")
for model_name, m in metrics.items():
    if isinstance(m, dict) and "error" not in m:
        print(f"[{model_name}]")
        for k, v in m.items():
            if isinstance(v, float):
                print(f"  {k}: {v:.4f}")
            else:
                print(f"  {k}: {v}")
        print()
    elif isinstance(m, dict) and "error" in m:
        print(f"[{model_name}] ERROR: {m['error']}\n")
