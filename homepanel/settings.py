import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "panel_settings.json")

DEFAULT_SETTINGS = {
    "weather_enabled": True,
    "rf_enabled": True,
    "network_enabled": True,
    "alerts_enabled": True,
}

def load_settings():
    """Load settings from JSON file, return defaults if not found."""
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        # Merge with defaults in case new settings were added
        return {**DEFAULT_SETTINGS, **data}
    except FileNotFoundError:
        return DEFAULT_SETTINGS.copy()
    except Exception as e:
        print(f"Error loading settings: {e}")
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Save settings to JSON file."""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

def get_setting(key, default=None):
    """Get a single setting value."""
    settings = load_settings()
    return settings.get(key, default)

def set_setting(key, value):
    """Set a single setting value."""
    settings = load_settings()
    settings[key] = value
    return save_settings(settings)
