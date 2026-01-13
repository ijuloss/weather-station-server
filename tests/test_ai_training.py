import os
import time
from backend import app as server


def make_sample(point_count=60, temp=30, hum=60, aq=50):
    now = time.time()
    samples = []
    for i in range(point_count):
        samples.append({
            'temperature': float(temp),
            'humidity': float(hum),
            'air_quality': float(aq),
            'light_intensity': 500,
            'battery_voltage': 3.9,
            'timestamp': server.iso_now()
        })
    return samples


def test_prepare_training_data_labels():
    model = server.WeatherAIModel()
    data = [
        {'temperature': 10, 'humidity': 40, 'air_quality': 20, 'timestamp': server.iso_now()},
        {'temperature': 36, 'humidity': 20, 'air_quality': 30, 'timestamp': server.iso_now()},
        {'temperature': 26, 'humidity': 85, 'air_quality': 20, 'timestamp': server.iso_now()},
    ]
    X, y, ts = model.prepare_training_data(data)
    assert X.shape[0] == 3
    assert len(y) == 3
    assert 'Cold' in y or 'Very Hot' in y or 'Hot Humid' in y


def test_train_single_class_force_creates_model(tmp_path):
    # Backup original local_data
    orig_data = server.local_data
    try:
        server.local_data = make_sample(point_count=60, temp=26, hum=85, aq=30)
        # Make sure model files go to a tmp dir and update config before instantiation
        server.PROJECT_DATA_DIR = tmp_path
        server.config.set('DATA_DIR', str(tmp_path))
        # Create a fresh model instance so it picks up the new DATA_DIR
        model = server.WeatherAIModel()
        ok = model.train_model(force_single_class=True)
        assert ok is True
        assert model.trained is True
        assert isinstance(model.last_metrics, dict)
        # Synthetic should be noted in metrics for single-class forced runs
        assert model.last_metrics.get('synthetic_used') in (True, False)
        # model file exists
        assert model.model_file.exists()
    finally:
        server.local_data = orig_data
