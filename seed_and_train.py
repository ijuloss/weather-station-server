#!/usr/bin/env python3
import sys
sys.path.insert(0, r'c:\Users\opera\Downloads\weather-station-server')

# Import Flask app
from backend.app import local_data, weather_ai, get_label_distribution
from datetime import datetime, timezone, timedelta

# Seed demo data (50 per class, 150 total)
count_each = 50
base = datetime.now(timezone.utc) - timedelta(seconds=count_each * 3 // 2)

added = 0
for i in range(count_each * 3):
    cls = i % 3
    if cls == 0:
        temp, hum, aq = 36, 35, 80  # Very Hot
    elif cls == 1:
        temp, hum, aq = 24, 50, 40  # Normal
    else:
        temp, hum, aq = 10, 40, 30  # Cold
    
    ts = (base + timedelta(seconds=i)).isoformat()
    local_data.append({
        'temperature': float(temp),
        'humidity': float(hum),
        'air_quality': float(aq),
        'light_intensity': 500,
        'battery_voltage': 3.9,
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
        test_acc = weather_ai.last_metrics.get('test_accuracy')
        macro_f1 = weather_ai.last_metrics.get('macro_f1')
        print(f"✓ Test accuracy: {test_acc:.4f if test_acc else 'N/A'}")
        print(f"✓ Macro F1: {macro_f1:.4f if macro_f1 else 'N/A'}")
        print(f"\n✅ TRAINING SUCCESSFUL - Model is VALID with diverse data!")
    else:
        print(f"\n⚠️  WARNING: Training completed but evaluation is NON_VALID")
        print(f"   Warnings: {weather_ai.last_metrics.get('warnings', [])}")
else:
    print("✗ Training failed!")
