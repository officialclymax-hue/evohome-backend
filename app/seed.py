import os
import json

# This script can be used to validate or process seed data if needed.
# For this setup, main.py directly reads the JSON files.

SEED_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'seed_data')

def validate_seed_data():
    print("Validating seed data...")
    for root, _, files in os.walk(SEED_DATA_DIR):
        for file in files:
            if file.endswith('.json'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r') as f:
                        json.load(f)
                    print(f"  ✅ {file} is valid JSON.")
                except json.JSONDecodeError:
                    print(f"  ❌ {file} is NOT valid JSON.")
                except Exception as e:
                    print(f"  ⚠️ Error processing {file}: {e}")
    print("Seed data validation complete.")

if __name__ == '__main__':
    validate_seed_data()
