SOIL_MATCH_DEFAULTS = {
    "oc_min": 0.50,
    "oc_max": 0.75,
    "ec_min": 0.0,
    "ec_max": 1.2,
}

CROP_SOIL_MATCH_OVERRIDES = {
    "Banana": {"oc_min": 0.75, "oc_max": 1.20, "ec_min": 0.0, "ec_max": 1.0},
    "Citrus": {"oc_min": 0.60, "oc_max": 1.00, "ec_min": 0.0, "ec_max": 1.0},
    "Date Palm": {"oc_min": 0.35, "oc_max": 0.80, "ec_min": 0.0, "ec_max": 3.0},
    "Dragon Fruit": {"oc_min": 0.50, "oc_max": 1.00, "ec_min": 0.0, "ec_max": 1.5},
    "Makhana": {"oc_min": 0.70, "oc_max": 1.30, "ec_min": 0.0, "ec_max": 1.2},
    "Pomegranate": {"oc_min": 0.50, "oc_max": 0.90, "ec_min": 0.0, "ec_max": 2.0},
}

CROP_DATABASE = {
    "Wheat": {
        "family": "Poaceae", "is_nitrogen_fixer": False, "season": "Rabi", "type": "seasonal",
        "water_intensive": False, "sowing_window": ["November", "December"], "harvest_window": ["March", "April"],
        "ideal": {"N": 120, "P": 60, "K": 40, "pH_min": 6.0, "pH_max": 7.5, "gdd_min": 1500, "gdd_max": 2000, "rain_min": 400, "rain_max": 700},
        "survival": {"pH_min": 5.0, "pH_max": 8.5, "gdd_min": 1000, "gdd_max": 2500}
    },
    "Paddy(Dhan)(Common)": { 
        "family": "Poaceae", "is_nitrogen_fixer": False, "season": "Kharif", "type": "seasonal",
        "water_intensive": True, "sowing_window": ["June", "July"], "harvest_window": ["October", "November"],
        "ideal": {"N": 100, "P": 50, "K": 50, "pH_min": 5.5, "pH_max": 7.0, "gdd_min": 2000, "gdd_max": 3000, "rain_min": 1000, "rain_max": 2000},
        "survival": {"pH_min": 4.5, "pH_max": 8.0, "gdd_min": 1500, "gdd_max": 4000}
    },
    "Soyabean": {
        "family": "Fabaceae", "is_nitrogen_fixer": True, "season": "Kharif", "type": "seasonal",
        "water_intensive": False, "sowing_window": ["June", "July"], "harvest_window": ["September", "October"],
        "ideal": {"N": 20, "P": 60, "K": 40, "pH_min": 6.0, "pH_max": 7.5, "gdd_min": 1500, "gdd_max": 2200, "rain_min": 600, "rain_max": 1000},
        "survival": {"pH_min": 5.5, "pH_max": 8.0, "gdd_min": 1200, "gdd_max": 2800}
    },
    "Cotton": {
        "family": "Malvaceae", "is_nitrogen_fixer": False, "season": "Kharif", "type": "seasonal",
        "water_intensive": False, "sowing_window": ["June", "July"], "harvest_window": ["November", "January"],
        "ideal": {"N": 80, "P": 40, "K": 80, "pH_min": 6.0, "pH_max": 8.0, "gdd_min": 1800, "gdd_max": 2600, "rain_min": 500, "rain_max": 900},
        "survival": {"pH_min": 5.5, "pH_max": 8.5, "gdd_min": 1500, "gdd_max": 3200}
    },
    "Mustard": {
        "family": "Brassicaceae", "is_nitrogen_fixer": False, "season": "Rabi", "type": "seasonal",
        "water_intensive": False, "sowing_window": ["October", "November"], "harvest_window": ["February", "March"],
        "ideal": {"N": 80, "P": 40, "K": 40, "pH_min": 6.0, "pH_max": 7.5, "gdd_min": 1200, "gdd_max": 1800, "rain_min": 300, "rain_max": 500},
        "survival": {"pH_min": 5.5, "pH_max": 8.5, "gdd_min": 900, "gdd_max": 2200}
    },
    "Gram": {
        "family": "Fabaceae", "is_nitrogen_fixer": True, "season": "Rabi", "type": "seasonal",
        "water_intensive": False, "sowing_window": ["October", "November"], "harvest_window": ["March", "April"],
        "ideal": {"N": 20, "P": 40, "K": 20, "pH_min": 6.0, "pH_max": 7.5, "gdd_min": 1300, "gdd_max": 1800, "rain_min": 250, "rain_max": 500},
        "survival": {"pH_min": 5.5, "pH_max": 8.0, "gdd_min": 1000, "gdd_max": 2200}
    },
    "Garlic": {
        "family": "Amaryllidaceae", "is_nitrogen_fixer": False, "season": "Rabi", "type": "seasonal",
        "water_intensive": True, "sowing_window": ["September", "October"], "harvest_window": ["February", "March"],
        "ideal": {"N": 100, "P": 50, "K": 50, "pH_min": 6.5, "pH_max": 7.5, "gdd_min": 1400, "gdd_max": 1900, "rain_min": 400, "rain_max": 800},
        "survival": {"pH_min": 5.5, "pH_max": 8.0, "gdd_min": 1100, "gdd_max": 2300}
    },
    "Onion": {
        "family": "Amaryllidaceae", "is_nitrogen_fixer": False, "season": "Rabi", "type": "seasonal",
        "water_intensive": True, "sowing_window": ["October", "November"], "harvest_window": ["March", "April"],
        "ideal": {"N": 100, "P": 50, "K": 50, "pH_min": 6.5, "pH_max": 7.5, "gdd_min": 1500, "gdd_max": 2000, "rain_min": 500, "rain_max": 800},
        "survival": {"pH_min": 5.8, "pH_max": 8.0, "gdd_min": 1200, "gdd_max": 2500}
    },
    "Moong": {
        "family": "Fabaceae", "is_nitrogen_fixer": True, "season": "Kharif", "type": "seasonal",
        "water_intensive": False, "sowing_window": ["June", "July"], "harvest_window": ["August", "September"],
        "ideal": {"N": 20, "P": 40, "K": 20, "pH_min": 6.5, "pH_max": 7.5, "gdd_min": 1000, "gdd_max": 1500, "rain_min": 400, "rain_max": 700},
        "survival": {"pH_min": 5.5, "pH_max": 8.2, "gdd_min": 800, "gdd_max": 2000}
    },
    "Pomegranate": {
        "family": "Lythraceae", "is_nitrogen_fixer": False, "season": "All", "type": "horticulture",
        "gestation_period": 36, "investment_lifespan": 20,
        "water_intensive": False, "sowing_window": ["July", "August"], "harvest_window": ["Year-round after gestation"],
        "ideal": {"N": 150, "P": 50, "K": 50, "pH_min": 6.5, "pH_max": 7.5, "gdd_min": 2000, "gdd_max": 4000, "rain_min": 500, "rain_max": 800},
        "survival": {"pH_min": 5.5, "pH_max": 8.5, "gdd_min": 1500, "gdd_max": 5000}
    },
    "Dragon Fruit": {
        "family": "Cactaceae", "is_nitrogen_fixer": False, "season": "All", "type": "horticulture",
        "gestation_period": 18, "investment_lifespan": 15,
        "water_intensive": False, "sowing_window": ["June", "July"], "harvest_window": ["June", "November"],
        "ideal": {"N": 100, "P": 50, "K": 100, "pH_min": 5.5, "pH_max": 6.5, "gdd_min": 2500, "gdd_max": 4500, "rain_min": 500, "rain_max": 1500},
        "survival": {"pH_min": 5.0, "pH_max": 8.5, "gdd_min": 2000, "gdd_max": 6000}
    },
    "Date Palm": {
        "family": "Arecaceae", "is_nitrogen_fixer": False, "season": "All", "type": "horticulture",
        "gestation_period": 48, "investment_lifespan": 30,
        "water_intensive": False, "sowing_window": ["July", "August"], "harvest_window": ["August", "September"],
        "ideal": {"N": 120, "P": 35, "K": 160, "pH_min": 7.0, "pH_max": 8.5, "gdd_min": 3000, "gdd_max": 6000, "rain_min": 100, "rain_max": 350},
        "survival": {"pH_min": 6.5, "pH_max": 9.0, "gdd_min": 2500, "gdd_max": 7000}
    },
    "Citrus": {
        "family": "Rutaceae", "is_nitrogen_fixer": False, "season": "All", "type": "horticulture",
        "gestation_period": 48, "investment_lifespan": 25,
        "water_intensive": True, "sowing_window": ["July", "August"], "harvest_window": ["Year-round after gestation"],
        "ideal": {"N": 200, "P": 50, "K": 100, "pH_min": 5.5, "pH_max": 6.5, "gdd_min": 2500, "gdd_max": 3500, "rain_min": 700, "rain_max": 1200},
        "survival": {"pH_min": 5.0, "pH_max": 8.5, "gdd_min": 2000, "gdd_max": 5000}
    },
    "Banana": {
        "family": "Musaceae", "is_nitrogen_fixer": False, "season": "All", "type": "horticulture",
        "gestation_period": 12, "investment_lifespan": 5,
        "water_intensive": True, "sowing_window": ["June", "July"], "harvest_window": ["Year-round after gestation"],
        "ideal": {"N": 250, "P": 60, "K": 300, "pH_min": 6.0, "pH_max": 7.5, "gdd_min": 2500, "gdd_max": 4500, "rain_min": 1000, "rain_max": 2500},
        "survival": {"pH_min": 5.5, "pH_max": 8.0, "gdd_min": 2000, "gdd_max": 5500}
    },
    "Makhana": {
        "family": "Nymphaeaceae", "is_nitrogen_fixer": False, "season": "All", "type": "horticulture",
        "gestation_period": 8, "investment_lifespan": 3,
        "water_intensive": True, "sowing_window": ["February", "March"], "harvest_window": ["August", "September"],
        "ideal": {"N": 220, "P": 45, "K": 180, "pH_min": 6.0, "pH_max": 7.5, "gdd_min": 2200, "gdd_max": 4200, "rain_min": 1000, "rain_max": 2200},
        "survival": {"pH_min": 5.5, "pH_max": 8.2, "gdd_min": 1800, "gdd_max": 5200}
    },
    "Potato": {
        "family": "Solanaceae", "is_nitrogen_fixer": False, "season": "Rabi", "type": "seasonal",
        "water_intensive": True, "sowing_window": ["October", "November"], "harvest_window": ["February", "March"],
        "ideal": {"N": 150, "P": 60, "K": 100, "pH_min": 5.5, "pH_max": 6.5, "gdd_min": 1200, "gdd_max": 1800, "rain_min": 500, "rain_max": 800},
        "survival": {"pH_min": 4.8, "pH_max": 7.5, "gdd_min": 900, "gdd_max": 2200}
    },
    "Tomato": {
        "family": "Solanaceae", "is_nitrogen_fixer": False, "season": "All", "type": "seasonal",
        "water_intensive": True, "sowing_window": ["June", "July"], "harvest_window": ["September", "November"],
        "ideal": {"N": 120, "P": 60, "K": 80, "pH_min": 6.0, "pH_max": 7.0, "gdd_min": 1500, "gdd_max": 2500, "rain_min": 500, "rain_max": 1000},
        "survival": {"pH_min": 5.0, "pH_max": 8.0, "gdd_min": 1200, "gdd_max": 3000}
    },
}
