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