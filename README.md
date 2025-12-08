# Skiliket IoT System — Gateway & Machine Learning Pipeline

This repository provides the gateway, data processing, simulation engine, and machine learning components for the Skiliket IoT System. It is designed as a central part of an end-to-end environmental IoT + AI architecture deployed in the Metropolitan Zone of Guadalajara (ZMG). Its role is to ingest, clean, store, simulate, and model sensor data for later analysis and dashboarding (see [`Skiliket-Dashboard`](https://github.com/andresaugom/Skiliket-Dashboard) for the visualization interface).

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation & Setup](#installation--setup)
- [Usage Examples](#usage-examples)
- [Dataset & Schema](#dataset--schema)
- [Model Performance](#model-performance)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

This repository implements the following components for the Skiliket IoT System:

- **Raspberry Pi Gateway:** Collects MQTT sensor data, preprocesses it, and uploads to Supabase (PostgreSQL).
- **Simulation Engine:** Generates massive synthetic datasets for ML training.
- **Machine Learning Pipeline:** Trains and evaluates Random Forest regressors on simulated data.
- **Utility Module:** Shared functions for data processing.
- **Hardware Test Scripts:** Prototype-stage integration tests for key peripherals.

---

## Architecture

**The system implements the following data and ML workflows:**

1. **Sensor Data Collection (Gateway)**
    - Raspberry Pi receives MQTT messages from ESP32 environmental sensor nodes every 15 seconds.
    - Incoming data includes: CO₂, UV, noise, temperature, humidity.
    - Data is aggregated via a 5-min moving average and uploaded to Supabase (PostgreSQL).
    - All ingestion, cleaning, and uploading is handled by [`firmware/main.py`](firmware/main.py).

2. **Simulation Engine**
    - [`generate_simulation.py`](generate_simulation.py) generates massive, realistic time series by modeling complex environmental patterns.
    - Simulated data is written to a parallel schema in Supabase for use in model training.

3. **Machine Learning Pipeline**
    - [`model.py`](model.py) trains individual Random Forest regressors to predict each variable using the simulated dataset.
    - Evaluation and prediction are supported in [`test_models.py`](test_models.py).

**Data Flow Overview:**
```
ESP32 Sensor Nodes
        │
    (MQTT)
        ▼
Raspberry Pi Gateway (preprocessing)
        │
(Supabase/PostgreSQL: real & synthetic schemas)
        │
Simulation ⟶ ML Training → Model Evaluation
```

---

## Installation & Setup

**Requirements:**
- Python 3.10+
- Hardware: Raspberry Pi 4 (gateway role)

**Setup Steps:**
1. **Clone the repository**
    ```sh
    git clone https://github.com/andresaugom/Skiliket-RPI4.git
    cd Skiliket-RPI4
    ```

2. **Install dependencies**
    ```sh
    pip install -r requirements.txt
    ```

3. **Environment Variables**

    Set up these environment variables to configure Supabase access (e.g., in a `.env` file or system environment):

    - `SUPABASE_URL`
    - `SUPABASE_KEY`
    - `SUPABASE_SCHEMA` (for simulated data: use `synthetic`)
    - Other project-specific variables as needed

4. **Configuration**

    - Adapt MQTT broker and Supabase details in [`firmware/main.py`](firmware/main.py) or initialize with your own credentials.

---

## Usage Examples

**Run the Gateway (Raspberry Pi):**
```sh
python3 firmware/main.py
```
- Receives and preprocesses sensor data, uploads to Supabase every 5 minutes.

**Generate a Large Synthetic Dataset:**
```sh
python3 generate_simulation.py
```
- Stores simulation data in the `synthetic` schema in Supabase.

**Train Machine Learning Models:**
```sh
python3 model.py
```
- Trains a Random Forest for each variable using simulated data.

**Test Trained Models:**
```sh
python3 test_models.py
```
- Loads trained models and generates evaluation metrics.

**Run Hardware Tests (prototyping):**
```sh
python3 tests/test.py
python3 tests/test_LCD.py
python3 tests/test_buzzer.py
```

---

## Dataset & Schema

**Variables:**
- **Measured/Simulated:** `CO₂`, `UV`, `noise`, `temperature`, `humidity`.
- **Aggregation:** 5-minute moving average for each variable before upload.

**Schemas:**
- **Real data:** Primary schema used for live sensor readings.
- **Synthetic data:** Parallel schema (`synthetic`) populated by simulation engine for ML pipeline.

**5-Minute Moving Average:**
- For each variable, the gateway aggregates readings over a 5-minute sliding window.
- Example: Every 15-second reading is buffered; every 5 minutes, the average is computed and uploaded to the database.

---

## Model Performance

*Mean Absolute Error (MAE) for each variable (Random Forest, simulation-trained):*

- **UV:** MAE ≈ 0.04
- **CO₂:** MAE ≈ 36.4
- **Temperature:** MAE ≈ 0.64
- **Noise:** MAE ≈ 2.31
- **Humidity:** MAE ≈ 2.66

---

## Contributing

- Contributions are welcome—please open issues or pull requests.
- For major changes, discuss first via issue.
- Code should be linted and documented.
- For hardware-related code, specify your device setup when possible.

---

## License

This project is licensed under the MIT License.
