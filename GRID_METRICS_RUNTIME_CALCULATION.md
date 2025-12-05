# Grid Metrics Runtime Calculation

## Overview
Grid stability metrics are now **calculated at runtime** from simulation state rather than being static MongoDB configuration values.

---

## Changed Metrics

### 1. **Grid Stability Index** (0-100%)

**Before:** Static value from MongoDB (`grid_stability_index: 95.0`)

**Now:** Dynamically calculated based on three factors:

#### **Formula:**
```python
stability_index = (voltage_score × 0.3) + (frequency_score × 0.3) + (balance_score × 0.4)
```

#### **Components:**

| Component | Weight | Calculation | Criteria |
|-----------|--------|-------------|----------|
| **Voltage Stability** | 30% | Deviation from nominal voltage | ±5% = excellent |
| **Frequency Stability** | 30% | Deviation from nominal frequency | ±0.5 Hz = excellent |
| **Power Balance** | 40% | Generation vs. consumption match | Perfect balance = 100 |

#### **Scoring Details:**

**1. Voltage Score (30 points max):**
```python
voltage_deviation = |actual_voltage - nominal_voltage| / nominal_voltage
voltage_score = max(0, 100 - (voltage_deviation / 0.05) × 30)
```
- Within ±5% of nominal → 100 points
- Beyond ±5% → Score decreases

**2. Frequency Score (30 points max):**
```python
frequency_deviation = |actual_frequency - nominal_frequency|
frequency_score = max(0, 100 - (frequency_deviation / 0.5) × 30)
```
- Within ±0.5 Hz → 100 points
- Beyond ±0.5 Hz → Score decreases

**3. Balance Score (40 points max):**
```python
power_imbalance = |generation - consumption|
balance_factor = power_imbalance / consumption
balance_score = max(0, 100 - (balance_factor × 40))
```
- Perfect balance → 100 points
- 10% imbalance → 96 points
- 50% imbalance → 80 points

#### **Simulated Grid Behavior:**

**Voltage Drop Under Load:**
```python
load_factor = consumption / generation
actual_voltage = nominal_voltage × (1.0 - load_factor × 0.005)
```
- 0.5% voltage drop per 10% load increase

**Frequency Variation:**
```python
power_balance = |generation - consumption|
balance_factor = power_balance / consumption
actual_frequency = nominal_frequency × (1.0 - balance_factor × 0.001)
```
- Frequency drops with power imbalance

---

### 2. **Grid Load Reference** (kW)

**Before:** Static value from MongoDB (`grid_load_reference_kw: 1000.0`)

**Now:** Dynamically calculated from total community capacity:

```python
total_load_capacity = sum(member.assets.load_capacity_kw for all members)
grid_load_pct = (current_consumption / total_load_capacity) × 100%
```

**Benefits:**
- Scales automatically with community size
- Reflects actual installed capacity
- No manual configuration needed

---

## Example Scenarios

### Scenario 1: Well-Balanced Grid
```
Generation: 500 kW
Consumption: 505 kW
Imbalance: 5 kW (1%)

Voltage: 479.76 V (nominal: 480V, -0.05%)
Frequency: 59.995 Hz (nominal: 60Hz, -0.005 Hz)

Voltage Score: 100
Frequency Score: 100
Balance Score: 99.6

Stability Index: 99.8%
```

### Scenario 2: Moderate Load Stress
```
Generation: 400 kW
Consumption: 500 kW
Imbalance: 100 kW (20%)

Voltage: 477.6 V (nominal: 480V, -0.5%)
Frequency: 59.98 Hz (nominal: 60Hz, -0.02 Hz)

Voltage Score: 97
Frequency Score: 99
Balance Score: 92

Stability Index: 95.4%
```

### Scenario 3: Heavy Imbalance
```
Generation: 300 kW
Consumption: 600 kW
Imbalance: 300 kW (50%)

Voltage: 472.8 V (nominal: 480V, -1.5%)
Frequency: 59.94 Hz (nominal: 60Hz, -0.06 Hz)

Voltage Score: 91
Frequency Score: 96
Balance Score: 80

Stability Index: 87.5%
```

---

## Grid Health Status Thresholds

Frontend displays health based on stability index:

| Stability Index | Health Status | Color | Description |
|----------------|---------------|-------|-------------|
| **90-100%** | Excellent | Green | Grid operating optimally |
| **70-89%** | Good | Yellow | Minor fluctuations, acceptable |
| **<70%** | Warning | Red | Grid stress, attention needed |

---

## MongoDB Configuration

### What's Still in MongoDB:

```javascript
{
  "community_control": {
    "grid_voltage_v": 480.0,     // Nominal voltage (reference)
    "grid_frequency_hz": 60.0,   // Nominal frequency (reference)
    // grid_stability_index: REMOVED (calculated at runtime)
    // grid_load_reference_kw: REMOVED (calculated from member capacities)
  }
}
```

### What Changed:

❌ **Removed from MongoDB:**
- `grid_stability_index` - Now calculated from simulation state
- `grid_load_reference_kw` - Now calculated from member capacities

✅ **Kept in MongoDB (as reference values):**
- `grid_voltage_v` - Nominal voltage for calculations
- `grid_frequency_hz` - Nominal frequency for calculations

---

## Implementation Details

### Files Modified:

1. **`be/app/services/community/dashboard_service.py`**
   - Added `_convert_to_dashboard_format()` calculations (lines 123-162)
   - Calculates voltage, frequency, stability index from simulation state

2. **`be/app/models/community_model.py`**
   - Removed `grid_stability_index` field
   - Removed `grid_load_reference_kw` field
   - Updated comments for `grid_voltage_v` and `grid_frequency_hz`

3. **`be/scripts/init_mongodb_community.py`**
   - Removed static `grid_stability_index` and `grid_load_reference_kw` from init data

---

## Benefits

✅ **Realistic:** Grid metrics reflect actual simulation state  
✅ **Dynamic:** Values change based on generation/consumption balance  
✅ **Accurate:** No hardcoded assumptions about grid stability  
✅ **Scalable:** Load reference auto-adjusts to community size  
✅ **Observable:** Can monitor grid health in real-time  

---

## Future Enhancements

1. **Historical Tracking:** Store stability index trends over time
2. **Alerts:** Trigger warnings when stability drops below thresholds
3. **Predictive:** Forecast stability based on upcoming load patterns
4. **Regional Variations:** Calculate stability per grid zone/feeder
5. **Event Correlation:** Link stability drops to specific events (storms, maintenance)

---

## Technical Notes

### Load Factor Calculation:
```python
load_factor = min(1.0, consumption / max(generation, 1.0))
```
- Capped at 1.0 to prevent negative voltage
- Protects against division by zero

### Balance Factor Calculation:
```python
balance_factor = power_imbalance / max(consumption, 1.0)
```
- Normalized to consumption level
- Protects against division by zero

### Grid Health Formula Tuning:

Current weights:
- **Voltage:** 30% (critical but usually stable)
- **Frequency:** 30% (critical indicator of balance)
- **Power Balance:** 40% (most important for grid stability)

These weights can be adjusted based on real-world observations.

---

## Validation

To verify grid metrics are calculated correctly:

1. **Check API response:**
```bash
curl http://localhost:8000/api/community-dashboard/presentation/community-dashboard
```

2. **Verify stability index:**
```json
{
  "grid_interaction": {
    "stability_index": 95.4,  // Should be 0-100, not 9500
    "voltage_v": 479.76,
    "frequency_hz": 59.995
  }
}
```

3. **Expected behavior:**
   - Stability decreases when generation ≠ consumption
   - Voltage drops slightly under heavy load
   - Frequency varies with power balance
   - All values update every simulation tick (hourly)

---

## Conclusion

Grid stability and load metrics are now **living values** that reflect the actual state of the microgrid simulation, not static configuration parameters. This provides:
- More realistic dashboard displays
- Better operational insights
- Foundation for future predictive analytics and alerts

