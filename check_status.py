#!/usr/bin/env python3
import sys
sys.path.insert(0, r'c:\Users\opera\Downloads\weather-station-server')
from backend.app import local_data, weather_ai, get_label_distribution

print("=" * 60)
print("AI MODEL STATUS REPORT")
print("=" * 60)
print(f"Data points: {len(local_data)}")
print(f"Label distribution: {get_label_distribution(local_data)}")
print(f"Model trained: {weather_ai.trained}")
print(f"Evaluation mode: {weather_ai.last_metrics.get('evaluation_mode', 'UNKNOWN')}")
print(f"Metrics trusted: {weather_ai.last_metrics.get('metrics_trusted', False)}")

test_acc = weather_ai.last_metrics.get('test_accuracy')
if test_acc is not None:
    print(f"Test accuracy: {test_acc:.4f}")
else:
    print(f"Test accuracy: NON_VALID (not trustworthy)")

macro_f1 = weather_ai.last_metrics.get('macro_f1')
if macro_f1 is not None:
    print(f"Macro F1: {macro_f1:.4f}")
else:
    print(f"Macro F1: NON_VALID (not trustworthy)")

warnings = weather_ai.last_metrics.get('warnings', [])
print(f"Warnings: {warnings if warnings else 'None'}")
print("=" * 60)

if weather_ai.last_metrics.get('evaluation_mode') == 'VALID' and weather_ai.trained:
    print("\n✅ SUCCESS!")
    print("Model is VALID with diverse training data!")
    print("Auto-prediction will be enabled when training completes on next sensor reading.")
else:
    print("\n⚠️  Model status is not VALID")
