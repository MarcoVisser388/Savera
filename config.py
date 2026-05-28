import os

# Algemene instellingen
APP_NAME = "Savera"
DEBUG = True
SECRET_KEY = "savera-secret-2026"

# Database
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "database", "savera.db")

# Water prijs per kubieke meter
WATER_PRIJS_PER_M3 = 1.45

# Energie prijs per kWh
ENERGIE_PRIJS_PER_KWH = 0.32

# MQTT
MQTT_BROKER = '192.168.1.90'  # jouw Pi IP
MQTT_PORT = 1883

# HomeWizard P1
P1_IP = "192.168.1.95"
P1_API_URL = f"http://{P1_IP}/api/v1/data"

# Elektra prijzen
STROOM_PRIJS_PER_KWH = 0.32
TERUGLEVER_PRIJS_PER_KWH = 0.08