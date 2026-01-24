#!/usr/bin/env python3
import sys
sys.path.insert(0, r'c:\Users\opera\Downloads\weather-station-server')

# Import Flask app
from backend.app import local_data, weather_ai, get_label_distribution
from datetime import datetime, timezone, timedelta

# Seed demo data (50 per class, 150 total) dengan noise dan overlap yang realistis
import random
import numpy as np

count_each = 50
base = datetime.now(timezone.utc) - timedelta(seconds=count_each * 3 // 2)
random.seed(42)
np.random.seed(42)

added = 0
for i in range(count_each * 3):
    cls = i % 3
    
    # Tambah noise yang lebih besar + overlap untuk simulasi real-world
    if cls == 0:
        # Very Hot: temp 30-40, hum 20-50, aq 60-100
        temp = np.random.normal(36, 3)    # Larger std dev
        hum = np.random.normal(35, 8)     # More variation
        aq = np.random.normal(80, 8)
    elif cls == 1:
        # Normal: temp 18-30, hum 35-65, aq 25-55 (more overlap!)
        temp = np.random.normal(24, 4)
        hum = np.random.normal(50, 9)
        aq = np.random.normal(40, 10)
    else:
        # Cold: temp 5-20, hum 25-55, aq 15-50 (more overlap!)
        temp = np.random.normal(10, 3.5)
        hum = np.random.normal(40, 8)
        aq = np.random.normal(30, 7)
    
    # Clamp values to realistic ranges
    temp = max(0, min(50, temp))
    hum = max(15, min(100, hum))
    aq = max(10, min(500, aq))
    light = np.random.uniform(100, 1300)  
    
    ts = (base + timedelta(seconds=i)).isoformat()
    local_data.append({
        'temperature': float(temp),
        'humidity': float(hum),
        'air_quality': float(aq),
        'light_intensity': float(light),
        'battery_voltage': 3.7 + np.random.uniform(0, 0.3),
        'timestamp': ts,
        'synthetic_demo': True
    })
    added += 1

print(f"✓ Seeded {added} synthetic samples")
print(f"✓ Total data points: {len(local_data)}")
dist = get_label_distribution(local_data)
print(f"✓ Label distribution: {dist}")

# Train model
print("\n⏳ Starting training...")
success = weather_ai.train_model(force_single_class=False)

if success:
    print(f"✓ Training completed successfully!")
    print(f"✓ Model trained: {weather_ai.trained}")
    eval_mode = weather_ai.last_metrics.get('evaluation_mode', 'UNKNOWN')
    print(f"✓ Evaluation mode: {eval_mode}")
    metrics_trusted = weather_ai.last_metrics.get('metrics_trusted', False)
    print(f"✓ Metrics trusted: {metrics_trusted}")
    if eval_mode == 'VALID':
        val_acc = weather_ai.last_metrics.get('validation_accuracy')
        test_acc = weather_ai.last_metrics.get('test_accuracy')
        val_macro_f1 = weather_ai.last_metrics.get('validation_macro_f1')
        test_macro_f1 = weather_ai.last_metrics.get('test_macro_f1')
        print(f"✓ Validation accuracy: {val_acc:.4f if val_acc else 'N/A'}")
        print(f"✓ Test accuracy: {test_acc:.4f if test_acc else 'N/A'}")
        print(f"✓ Validation Macro F1: {val_macro_f1:.4f if val_macro_f1 else 'N/A'}")
        print(f"✓ Test Macro F1: {test_macro_f1:.4f if test_macro_f1 else 'N/A'}")
        print(f"\n✅ TRAINING SUCCESSFUL - Model is VALID!")
    else:
        print(f"\n⚠️  WARNING: Training completed but evaluation is NON_VALID")
        print(f"   Warnings: {weather_ai.last_metrics.get('warnings', [])}")
else:
    print("✗ Training failed!")
