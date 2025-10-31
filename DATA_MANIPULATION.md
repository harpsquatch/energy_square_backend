# Data Manipulation Documentation

## Overview

This document explains how generation and consumption data is manipulated in the Energy Square platform to create realistic energy community scenarios.

## Data Sources

### Generation Data
- **Source**: 2020 solar plant data from Plant 1 and Plant 2
- **File**: `artifacts/transformed_data.json`
- **Fields**: `AC_POWER` values in kW for each hour
- **Period**: Historical data from 2020
- **Frequency**: Hourly intervals

### Consumption Data
- **Source**: Italian electricity market data (MGP - Mercato del Giorno Prima)
- **File**: `artifacts/transformed_data.json`
- **Fields**: Regional demand data for Calabria and Sardegna
- **Period**: October 27, 2025
- **Frequency**: 15-minute intervals

## Community Specifications

### Community Size
- **Population**: 3,000-5,000 people
- **Households**: 1,200-2,000 households
- **Type**: Small town or large neighborhood in Calabria/Sardegna region
- **Representation**: 0.1% of regional demand

### Household Specifications
- **Average household size**: 2-2.5 people
- **Power consumption**: 0.3-2.0 kW average
- **Peak consumption**: 1.5x average during peak hours (6-9 AM, 5-10 PM)
- **Base consumption**: 1.2 kW per household

### Solar Panel Specifications
- **Individual panel capacity**: 300-400 W per panel
- **Total community capacity**: 2,233 kW (with 1.2x scaling factor)
- **Number of panels**: 5,500-7,000 solar panels
- **Installation type**: Community solar farm
- **Peak generation**: Based on real 2020 solar data patterns

## Data Manipulation Process

### Generation Data Processing

#### Step 1: Load Real Solar Data
```python
solar_data = self.data.get('solar_data', {})
plant_1_data = solar_data.get('plant_1', {}).get('hourly', [])
plant_2_data = solar_data.get('plant_2', {}).get('hourly', [])
```

#### Step 2: Filter by Current Hour
```python
plant_1_hour_data = [d for d in plant_1_data if d.get('hour') == current_hour]
plant_2_hour_data = [d for d in plant_2_data if d.get('hour') == current_hour]
```

#### Step 3: Calculate Average Generation
```python
plant_1_avg = sum([d.get('AC_POWER', 0) for d in plant_1_hour_data]) / len(plant_1_hour_data)
plant_2_avg = sum([d.get('AC_POWER', 0) for d in plant_2_hour_data]) / len(plant_2_hour_data)
total_real_generation = plant_1_avg + plant_2_avg
```

#### Step 4: Apply Scaling Factors
- **Community Dashboard**: `live_generation = total_real_generation * self_sufficiency_factor`
- **User Dashboard**: `current_generation = total_real_generation / 1000`

### Consumption Data Processing

#### Step 1: Load Market Demand Data
```python
demand_data = market_data.get('demand_data', [])
current_hour_data = [d for d in demand_data if d.get('hour') == current_hour]
```

#### Step 2: Aggregate Regional Demand
```python
regional_demand = 0
for region in ['Calabria', 'Sardegna', 'Sicilia', 'North', 'Central-northern Italy', 'Centeral-southern Italy', 'Southern-Italy']:
    value = period_data.get(region, 0)
    if value is not None and not (isinstance(value, float) and (value != value)):
        regional_demand += float(value)
```

#### Step 3: Calculate Average Demand
```python
avg_demand_mw = total_demand_mw / valid_periods
```

#### Step 4: Apply Scaling Factors
- **Community Dashboard**: `live_consumption = avg_demand_mw * 1000 * 0.001` (0.1% of regional demand)
- **User Dashboard**: `current_consumption = avg_demand_mw * 1000 / 2000000` (divided by 2M households)

## Scaling Factors

### Self-Sufficiency Factor
- **Default**: 1.2 (120% self-sufficiency)
- **Range**: 0.5 to 2.0
- **Purpose**: Configurable scaling for different energy independence scenarios
- **Effect**: Multiplies base solar generation capacity

### Regional Scaling
- **Calabria + Sardegna population**: ~3.5 million people
- **Community representation**: 0.1% of regional demand
- **Household scaling**: Regional demand divided by 2M households

## Data Quality Considerations

### Generation Data
- **Completeness**: Full 2020 solar plant data available
- **Accuracy**: Real AC_POWER measurements from solar inverters
- **Limitations**: Historical data (2020) may not reflect current conditions
- **Weather impact**: Captured in historical patterns

### Consumption Data
- **Completeness**: Partial data (only Calabria and Sardegna regions)
- **Accuracy**: Real Italian electricity market demand
- **Limitations**: Missing data for other Italian regions
- **Scaling**: Requires assumptions about regional representation

## Current Metrics Example

### Community Dashboard
- **Generation**: 2,233 kW (real solar data × 1.2 scaling factor)
- **Consumption**: 1,467 kW (regional demand × 0.1%)
- **Net Balance**: +766 kW (surplus exported to grid)
- **Grid Export**: 766 kW

### User Dashboard
- **Generation**: 0.3-2.2 kW (real solar data ÷ 1000)
- **Consumption**: 0.3-1.8 kW (regional demand ÷ 2M households)
- **Net Balance**: Variable based on time of day

## Technical Implementation

### Files Modified
- `be/app/services/data_presentation.py`: Main data processing logic
- `be/artifacts/transformed_data.json`: Source data file

### Key Functions
- `get_dashboard_data()`: User dashboard data processing
- `get_community_dashboard_data()`: Community dashboard data processing
- `_load_data()`: Data loading from JSON file

### Configuration
- `self_sufficiency_factor`: Configurable scaling factor for generation
- Regional scaling factors: Hardcoded based on population estimates
- Time-based filtering: Uses current system hour

## Limitations and Assumptions

### Data Limitations
1. **Historical solar data**: 2020 data may not reflect current solar technology
2. **Partial demand data**: Only Calabria and Sardegna regions available
3. **Scaling assumptions**: Regional population estimates may be inaccurate
4. **Time zone**: Uses system time, may not match data timezone

### Modeling Assumptions
1. **Community size**: Estimated based on consumption scaling
2. **Solar capacity**: Estimated based on generation scaling
3. **Demand patterns**: Assumed to follow regional patterns
4. **Self-sufficiency**: Configurable but not validated against real communities

## Future Improvements

### Data Sources
1. **Real-time solar data**: Integrate live solar generation feeds
2. **Complete demand data**: Obtain full Italian regional demand data
3. **Weather data**: Include weather impact on generation
4. **Historical trends**: Analyze multi-year patterns

### Modeling Enhancements
1. **Dynamic scaling**: Adjust scaling factors based on actual community data
2. **Seasonal patterns**: Account for seasonal variations in demand and generation
3. **Load profiles**: Implement detailed household load profiles
4. **Storage modeling**: Include battery storage systems

### Validation
1. **Real community data**: Validate against actual energy community metrics
2. **Benchmarking**: Compare with similar communities in Italy
3. **Sensitivity analysis**: Test impact of scaling factor changes
4. **Accuracy assessment**: Measure prediction accuracy against real data

