# Skiliket-RPI4 Repository — File Documentation

This document provides detailed descriptions for each file and directory in the Skiliket-RPI4 repository, which implements the gateway, simulation, and machine learning pipeline for the Skiliket IoT System.

---

## Table of Contents

- [1. Top-Level Files](#1-top-level-files)
- [2. Directories and Contents](#2-directories-and-contents)
  - [2.1 docs/](#21-docs)
  - [2.2 firmware/](#22-firmware)
  - [2.3 skiliket/](#23-skiliket)
  - [2.4 tests/](#24-tests)

---

## 1. Top-Level Files

### `README.md`
- **Description:** Repository overview. Explains architecture, usage, dataset, and ML performance.

### `DOCS.md`
- **Description:** This documentation file. Describes each repository file and directory.

### `requirements.txt`
- **Description:** Python dependency list for all scripts and modules.
- **Contents:** Packages for MQTT communication, Supabase client, data processing, scikit-learn (ML), and hardware support.

### `generate_simulation.py`
- **Description:** Synthetic dataset generator.
- **Details:** Models realistic patterns of environmental sensor values (CO₂, UV, noise, temperature, humidity). Designed to populate a separate Supabase schema for ML training. Highly configurable for experiment reproducibility.

### `model.py`
- **Description:** Machine learning pipeline.
- **Details:** Trains Random Forest regressors for each environmental variable using simulated data. Supports hyperparameter tuning and model serialization.

### `test_models.py`
- **Description:** Model evaluation script.
- **Details:** Loads trained models from `model.py`. Computes and displays performance metrics (e.g., MAE) for each variable.

---

## 2. Directories and Contents

### 2.1 `docs/`
- **Description:** Project documentation assets.
- **Contents:** May include architecture diagrams, protocol descriptions, configuration guidelines, and detailed user/developer guides.

---

### 2.2 `firmware/`
- **Description:** Raspberry Pi gateway implementation.
- **Files:**
  - `main.py`
    - **Description:** Main entry point for real-time sensor data acquisition, MQTT ingestion, preprocessing, and Supabase upload. Implements moving average calculation, error handling, and hardware-specific routines.
    - **Details:** Handles buffering of 15-second readings, computes 5-min averages, and manages connection to database and broker.

---

### 2.3 `skiliket/`
- **Description:** Internal Python utility module.
- **Files:**
  - `__init__.py`
    - **Description:** Module initializer (enables imports).
    - **Details:** Usually minimal or empty.
  - `func.py`
    - **Description:** Shared helper functions for use across simulation, ML, and gateway code.
    - **Contents:** Data transformation, statistical calculations, and utility routines.

---

### 2.4 `tests/`
- **Description:** Hardware integration test scripts (used in prototyping).
- **Files:**
  - `test.py`
    - **Description:** General test script for Raspberry Pi setup.
    - **Details:** Verifies sensor connectivity, database access, and system initialization.
  - `test_LCD.py`
    - **Description:** Tests LCD display functionality.
    - **Details:** Sends sample messages/data to LCD for validation.
  - `test_buzzer.py`
    - **Description:** Tests buzzer component operation.
    - **Details:** Triggers buzzer events to confirm working state and timing.

---

## Summary Table

| Path                        | Type        | Description                                          |
|-----------------------------|-------------|------------------------------------------------------|
| `README.md`                 | Markdown    | Project overview and user guide                      |
| `DOCS.md`                   | Markdown    | File-by-file documentation (this file)               |
| `requirements.txt`          | Text        | Python dependencies                                  |
| `generate_simulation.py`    | Python      | Synthetic data generator                             |
| `model.py`                  | Python      | ML training pipeline                                 |
| `test_models.py`            | Python      | ML model evaluation                                  |
| `docs/`                     | Directory   | Additional documentation                             |
| `firmware/main.py`          | Python      | Raspberry Pi gateway                                 |
| `skiliket/__init__.py`      | Python      | Package initializer                                  |
| `skiliket/func.py`          | Python      | Utility functions                                    |
| `tests/test.py`             | Python      | General hardware test                                |
| `tests/test_LCD.py`         | Python      | LCD hardware test                                    |
| `tests/test_buzzer.py`      | Python      | Buzzer hardware test                                 |

---

## Notes

- **Supabase credentials and configuration** should be handled via environment variables (see `README.md`).
- **Hardware tests** were critical for validating sensor interfaces and peripherals during development.
- All code is organized to facilitate extension for new sensors, additional simulation complexity, or ML model types.

---
