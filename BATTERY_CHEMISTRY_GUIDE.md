# Battery Chemistry Guide

## Overview
The system automatically handles battery SOC (State of Charge) limits based on battery chemistry. Users don't need to know technical details - just specify the battery type and the system configures safe operating limits.

---

## Supported Battery Chemistries

### 1. **Lithium-ion** (Default)
```json
{
  "battery_chemistry": "lithium_ion"
}
```

**Characteristics:**
- **SOC Range:** 10% - 95%
- **Why:** Most common chemistry, balanced performance
- **Use Case:** Residential and commercial energy storage systems
- **Lifespan:** Optimal when kept within 10-95% range
- **Depth of Discharge (DoD):** 85%

**Examples:**
- Tesla Powerwall
- LG Chem RESU
- Sonnen Batterie
- Most modern home batteries

---

### 2. **Lead-acid**
```json
{
  "battery_chemistry": "lead_acid"
}
```

**Characteristics:**
- **SOC Range:** 20% - 90%
- **Why:** Traditional chemistry, requires shallow discharge
- **Use Case:** Older installations, off-grid systems, backup power
- **Lifespan:** Deeper discharges damage lead plates
- **Depth of Discharge (DoD):** 70%

**Examples:**
- Trojan batteries
- Crown batteries
- Surrette/Rolls batteries
- Older backup systems

**Warning:** Deep discharge (below 20%) significantly reduces lifespan!

---

### 3. **LiFePO4** (Lithium Iron Phosphate)
```json
{
  "battery_chemistry": "lifepo4"
}
```

**Characteristics:**
- **SOC Range:** 5% - 100%
- **Why:** Most tolerant chemistry, very safe
- **Use Case:** High-cycle applications, long-term storage
- **Lifespan:** Can be fully discharged without damage
- **Depth of Discharge (DoD):** 95%

**Examples:**
- BYD Battery-Box
- SimpliPhi Power
- Blue Planet Energy
- Battle Born batteries

**Benefits:** Longest cycle life, safest chemistry, no thermal runaway risk

---

## Configuration Examples

### Example 1: Simple (Auto-detect SOC limits)
```json
{
  "member_id": "user_001",
  "assets": {
    "battery_capacity_kwh": 10.0,
    "battery_chemistry": "lithium_ion"
    // SOC limits auto-set: min=10%, max=95%
  }
}
```

### Example 2: Override SOC Limits (Advanced)
```json
{
  "member_id": "user_002",
  "assets": {
    "battery_capacity_kwh": 15.0,
    "battery_chemistry": "lithium_ion",
    "battery_min_soc": 0.15,  // Override: 15% min (more conservative)
    "battery_max_soc": 0.90   // Override: 90% max (extend lifespan)
  }
}
```

### Example 3: Mixed Chemistries in One Community
```json
{
  "members": [
    {
      "member_id": "user_001",
      "assets": {
        "battery_capacity_kwh": 10.0,
        "battery_chemistry": "lithium_ion"  // 10-95%
      }
    },
    {
      "member_id": "user_002",
      "assets": {
        "battery_capacity_kwh": 20.0,
        "battery_chemistry": "lifepo4"      // 5-100%
      }
    },
    {
      "member_id": "user_003",
      "assets": {
        "battery_capacity_kwh": 50.0,
        "battery_chemistry": "lead_acid"    // 20-90%
      }
    }
  ]
}
```

---

## How It Works

### 1. **Automatic SOC Limits**
When you specify `battery_chemistry`, the system automatically sets appropriate SOC limits:

```python
# User specifies:
"battery_chemistry": "lithium_ion"

# System automatically sets:
"battery_min_soc": 0.10  # 10%
"battery_max_soc": 0.95  # 95%
```

### 2. **Safety Enforcement**
During simulation, the system enforces these limits:

```python
# Simulation tick:
if new_soc < battery_min_soc:
    # Prevent over-discharge
    battery_power_kw = limit_discharge()
    new_soc = battery_min_soc

if new_soc > battery_max_soc:
    # Prevent overcharge
    battery_power_kw = limit_charge()
    new_soc = battery_max_soc
```

### 3. **Per-Member Configuration**
Each member can have different battery chemistry:

```
Community:
├─ User 1: Lithium-ion (10-95%)
├─ User 2: LiFePO4 (5-100%)
└─ User 3: Lead-acid (20-90%)
```

---

## Comparison Table

| Chemistry | Min SOC | Max SOC | DoD | Cycle Life | Cost | Safety | Best For |
|-----------|---------|---------|-----|------------|------|--------|----------|
| **Lithium-ion** | 10% | 95% | 85% | 3,000-5,000 | $$$ | Good | General use |
| **Lead-acid** | 20% | 90% | 70% | 500-1,500 | $ | Good | Budget, backup |
| **LiFePO4** | 5% | 100% | 95% | 5,000-10,000 | $$$$ | Excellent | Long-term, high-cycle |

**Legend:**
- **DoD:** Depth of Discharge (usable capacity)
- **Cycle Life:** Number of charge/discharge cycles
- **Cost:** $ (cheap) to $$$$ (expensive)

---

## When to Override SOC Limits

### Conservative Operation (Extend Lifespan)
```json
{
  "battery_chemistry": "lithium_ion",
  "battery_min_soc": 0.20,  // 20% instead of 10%
  "battery_max_soc": 0.80   // 80% instead of 95%
}
```
**Result:** Battery lasts longer but less usable capacity

### Aggressive Operation (Maximize Capacity)
```json
{
  "battery_chemistry": "lifepo4",
  "battery_min_soc": 0.00,  // 0% (only for LiFePO4!)
  "battery_max_soc": 1.00   // 100%
}
```
**Result:** Full capacity but shorter lifespan (OK for LiFePO4)

**Warning:** Never set lithium-ion or lead-acid to 0-100%!

---

## Migration Guide

### Old Format (Hardcoded SOC):
```json
{
  "assets": {
    "battery_capacity_kwh": 10.0,
    "battery_min_soc": 0.10,
    "battery_max_soc": 0.95
  }
}
```

### New Format (Chemistry-based):
```json
{
  "assets": {
    "battery_capacity_kwh": 10.0,
    "battery_chemistry": "lithium_ion"
    // SOC limits auto-set
  }
}
```

**Backward Compatible:** Old format still works if you specify both SOC limits explicitly.

---

## API Response

The dashboard API returns battery chemistry information:

```json
{
  "storage_network": {
    "total_capacity": 500.0,
    "aggregate_soc": 67.5,
    "battery_chemistries": {
      "lithium_ion": 3,  // 3 members with lithium-ion
      "lifepo4": 2,      // 2 members with LiFePO4
      "lead_acid": 1     // 1 member with lead-acid
    }
  }
}
```

---

## Validation

### Valid Configuration:
```json
{
  "battery_capacity_kwh": 10.0,
  "battery_chemistry": "lithium_ion"
  // ✅ Valid: SOC limits auto-set to 10-95%
}
```

### Invalid Configuration:
```json
{
  "battery_capacity_kwh": 10.0,
  "battery_chemistry": "lithium_ion",
  "battery_min_soc": 0.05,  // ❌ Too low for lithium-ion
  "battery_max_soc": 1.00   // ❌ Too high for lithium-ion
}
```
**Error:** "For lithium_ion, recommended SOC range is 10-95%"

---

## Real-World Examples

### Residential Home (10 kWh Lithium-ion)
```json
{
  "member_id": "home_001",
  "customer_category": "residential",
  "assets": {
    "pv_capacity_kw": 5.0,
    "battery_capacity_kwh": 10.0,
    "battery_chemistry": "lithium_ion",  // Tesla Powerwall 2
    "load_capacity_kw": 8.0
  }
}
```
**Usable Capacity:** 8.5 kWh (85% DoD)

### Commercial Building (50 kWh LiFePO4)
```json
{
  "member_id": "building_001",
  "customer_category": "commercial",
  "assets": {
    "pv_capacity_kw": 25.0,
    "battery_capacity_kwh": 50.0,
    "battery_chemistry": "lifepo4",  // BYD Battery-Box
    "load_capacity_kw": 40.0
  }
}
```
**Usable Capacity:** 47.5 kWh (95% DoD)

### Off-Grid Cabin (20 kWh Lead-acid)
```json
{
  "member_id": "cabin_001",
  "customer_category": "residential",
  "assets": {
    "pv_capacity_kw": 3.0,
    "battery_capacity_kwh": 20.0,
    "battery_chemistry": "lead_acid",  // Trojan T-105
    "load_capacity_kw": 5.0
  }
}
```
**Usable Capacity:** 14 kWh (70% DoD)

---

## Summary

✅ **Users don't need to know SOC limits** - just specify battery type  
✅ **System auto-configures safe limits** based on chemistry  
✅ **Per-member configuration** - mixed chemistries in one community  
✅ **Override when needed** - for advanced users  
✅ **Prevents damage** - enforces safe operating ranges  
✅ **Extends lifespan** - chemistry-appropriate limits  

Simply set `"battery_chemistry": "lithium_ion"` and the system handles the rest!

