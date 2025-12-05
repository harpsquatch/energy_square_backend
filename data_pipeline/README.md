# Energy Square Data Pipeline

Modular data processing pipeline for generating coherent community dashboard and user profile data from Mesa Del Sol raw CSV files.

**Note**: This pipeline generates time-series data (community dashboard and user profiles) that serves as simulated real-time data. Marketplace, Demand Response, and Leaderboard data are generated dynamically by backend services in production, not pre-generated here.

## Pipeline Architecture

The pipeline is organized into 4 distinct stages:

### 1. Data Ingestion (`data_ingestion.py`)
**Purpose**: Load and validate raw Mesa Del Sol CSV files

**Responsibilities**:
- Load raw CSV files
- Parse timestamps
- Validate data quality
- Clean sentinel values (-999999)
- Filter data by month range

**Key Class**: `MesaDataIngestion`

### 2. Data Transformation (`data_transformation.py`)
**Purpose**: Transform raw data into hourly interval aggregated data

**Responsibilities**:
- Add time-based features (hour, minute, day_of_week, is_weekend)
- Aggregate raw 10-second data to hourly intervals
- Preserve original Mesa Del Sol data integrity

**Key Class**: `DataTransformation`

### 3. Feature Engineering (`feature_engineering.py`)
**Purpose**: Calculate derived metrics and features for dashboard

**Responsibilities**:
- Calculate power metrics (generation, consumption, net balance)
- Calculate energy metrics (kWh from kW)
- Calculate grid metrics (voltage, frequency, stability index)
- Calculate renewable percentage and grid load
- Calculate carbon offset metrics
- Generate cumulative metrics

**Key Class**: `FeatureEngineering`

### 4. Profile Generation (`profile_generation.py`)
**Purpose**: Generate coherent community and user profiles

**Responsibilities**:
- Generate community dashboard CSV files
- Generate user profile CSV files with bottom-up approach
- Ensure user totals aggregate to match community totals (100% coherence)
- Apply normalization to maintain exact matching

**Key Classes**: `CommunityProfileGenerator`, `UserProfileGenerator`

### 5. Pipeline Runner (`main.py`)
**Purpose**: Orchestrate the complete pipeline

**Responsibilities**:
- Coordinate all pipeline stages
- Process multiple months
- Generate combined summaries
- Maintain user profile consistency across months

**Key Class**: `DataPipelineRunner`

## What This Pipeline Generates vs. Dynamic Services

**Generated (Static CSV Data - Used as Simulated Real-Time)**:
- Community Dashboard data (time-series at 1-minute resolution)
- User Profiles data (time-series at 1-minute resolution)
  - These are read by backend services with time-shifting to simulate real-time data streams

**Generated Dynamically by Backend Services (Production)**:
- Marketplace transactions and activity (real-time processing)
- Demand Response events and participation (event-driven)
- Leaderboard rankings and gamification (calculated on-demand)

The pipeline only generates the foundational time-series data (community/user profiles). All transactional and calculated data is handled by production backend services.

## Usage

### Running the Pipeline

```python
from be.data_pipeline.main import DataPipelineRunner
from pathlib import Path

runner = DataPipelineRunner()

monthly_files = [
    ("Oct_2022.csv", "October 2022"),
    # ... more months
]

data_dir = Path("data/artifacts/data_ingestion")
output_dir = Path("data/artifacts")

runner.run_pipeline(data_dir, output_dir, monthly_files)
```

### Running from Command Line

**Option 1: Run as a module (recommended)**
```bash
cd be
python -m data_pipeline.main
```

**Option 2: Run directly**
```bash
cd be/data_pipeline
python main.py
```

Both methods work - the script handles imports automatically.

## Pipeline Flow

```
Raw CSV Files (10-second resolution)
    ↓
[1] Data Ingestion
    ↓ (cleaned DataFrame)
[2] Data Transformation  
    ↓ (1-minute intervals - aggregates 6 records per minute)
[3] Feature Engineering
    ↓ (derived metrics)
[4] Profile Generation
    ├─→ Community Dashboard CSV
    └─→ User Profiles CSV (coherent)
```

## Key Features

- **Bottom-up Approach**: User profiles aggregate to match community totals exactly
- **Modular Design**: Each stage is independent and testable
- **Data Integrity**: Preserves original Mesa Del Sol data without modification
- **Coherence Validation**: Ensures 100% match between user sums and community totals
- **Normalization**: Automatically normalizes user data to match community totals after variations

## Output Structure

```
output_dir/
├── community_dashboard/
│   ├── community_dashboard_October_2022.csv
│   └── ...
└── user_profiles/
    ├── user_profiles_October_2022.csv
    └── ...
```

