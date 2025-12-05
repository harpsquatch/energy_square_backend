"""
Device Management Router
API endpoints for managing user devices/assets (PV, battery, grid connections).
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging

from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine
from app.services.infrastructure.background_service import get_background_service
from app.models.community_model import MemberAssets

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy service initialization
_model_service = None
_simulation_engine = None


def get_model_service():
    """Get or create model service (lazy initialization)."""
    global _model_service
    if _model_service is None:
        _model_service = CommunityModelService(watch_for_changes=True)
    return _model_service


def get_simulation_engine():
    """Get or create simulation engine (lazy initialization)."""
    global _simulation_engine
    if _simulation_engine is None:
        from app.services.infrastructure.model_service import CommunityModelService
        model_service = get_model_service()
        _simulation_engine = CommunitySimulationEngine(model_service)
    return _simulation_engine


class DeviceInfo(BaseModel):
    """Device information for frontend display."""
    id: str
    name: str
    type: str  # "solar" | "battery" | "grid"
    status: str  # "active" | "inactive"
    capacity: float  # in W (for display)
    current: float  # in W (current output/input)
    efficiency: float  # percentage
    lastUpdated: str
    metadata: Optional[Dict[str, Any]] = None


class UpdateDeviceRequest(BaseModel):
    """Request to update device configuration."""
    device_id: str
    capacity: Optional[float] = None  # in W (will be converted to kW/kWh)
    status: Optional[str] = None  # "active" | "inactive"
    metadata: Optional[Dict[str, Any]] = None


@router.get("/devices/{member_id}", response_model=List[DeviceInfo])
async def get_member_devices(member_id: str):
    """
    Get all devices/assets for a member.
    
    Returns devices based on member's assets from MongoDB:
    - Solar array (if pv_capacity_kw > 0)
    - Battery pack (if battery_capacity_kwh > 0)
    - Grid connection (always present)
    """
    try:
        model_service = get_model_service()
        model = model_service.get_model()
        
        if model is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Community model not loaded"
            )
        
        member = model.get_member(member_id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member {member_id} not found"
            )
        
        # Get current simulation data for real-time values
        simulation_engine = get_simulation_engine()
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        now = datetime.now(ZoneInfo(model.community.timezone))
        member_result = simulation_engine.simulate_member(member, now)
        
        devices: List[DeviceInfo] = []
        
        # 1. Solar Array (if PV capacity > 0)
        if member.assets.pv_capacity_kw > 0:
            current_solar = member_result.get('solar_generation_kw', 0.0) * 1000  # Convert to W
            efficiency = (current_solar / (member.assets.pv_capacity_kw * 1000) * 100) if member.assets.pv_capacity_kw > 0 else 0
            devices.append(DeviceInfo(
                id="solar",
                name="Solar Array - Roof",
                type="solar",
                status="active" if member.assets.pv_capacity_kw > 0 else "inactive",
                capacity=member.assets.pv_capacity_kw * 1000,  # Convert to W
                current=current_solar,
                efficiency=min(100, max(0, efficiency)),
                lastUpdated="Just now",
                metadata={
                    "pv_capacity_kw": member.assets.pv_capacity_kw,
                    "inverter_efficiency": member.assets.inverter_efficiency
                }
            ))
        
        # 2. Battery Pack (if battery capacity > 0)
        if member.assets.battery_capacity_kwh > 0:
            battery_soc = member_result.get('battery_soc', 0.0)
            battery_power = member_result.get('battery_power_kw', 0.0) * 1000  # Convert to W
            battery_capacity_w = member.assets.battery_capacity_kwh * 1000  # Convert to W
            current_charge = battery_capacity_w * battery_soc
            
            # Efficiency based on round-trip efficiency
            efficiency = member.assets.round_trip_efficiency * 100
            
            devices.append(DeviceInfo(
                id="battery",
                name="Battery Pack - Main",
                type="battery",
                status="active" if member.assets.battery_capacity_kwh > 0 else "inactive",
                capacity=battery_capacity_w,
                current=current_charge,
                efficiency=efficiency,
                lastUpdated="Just now",
                metadata={
                    "battery_capacity_kwh": member.assets.battery_capacity_kwh,
                    "battery_chemistry": member.assets.battery_chemistry.value,
                    "round_trip_efficiency": member.assets.round_trip_efficiency,
                    "soc": battery_soc * 100,
                    "battery_power_kw": member_result.get('battery_power_kw', 0.0)
                }
            ))
        
        # 3. Grid Connection (always present)
        grid_import = member_result.get('grid_import_kw', 0.0) * 1000  # Convert to W
        grid_export = member_result.get('grid_export_kw', 0.0) * 1000  # Convert to W
        grid_capacity = max(member.assets.grid_import_limit_kw, member.assets.grid_export_limit_kw) * 1000
        
        devices.append(DeviceInfo(
            id="grid",
            name="Grid Connection",
            type="grid",
            status="active",
            capacity=grid_capacity,
            current=grid_import if grid_import > 0 else grid_export,
            efficiency=98.0,  # Grid connection efficiency
            lastUpdated="Just now",
            metadata={
                "grid_import_limit_kw": member.assets.grid_import_limit_kw,
                "grid_export_limit_kw": member.assets.grid_export_limit_kw,
                "current_import_kw": member_result.get('grid_import_kw', 0.0),
                "current_export_kw": member_result.get('grid_export_kw', 0.0)
            }
        ))
        
        return devices
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting devices for {member_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get devices: {str(e)}"
        )


@router.put("/devices/{member_id}/{device_id}")
async def update_device(member_id: str, device_id: str, request: UpdateDeviceRequest):
    """
    Update a device configuration.
    
    Supported devices:
    - "solar": Update PV capacity
    - "battery": Update battery capacity
    - "grid": Update grid import/export limits
    
    Note: "status" updates are not yet supported (would require more complex logic).
    """
    try:
        model_service = get_model_service()
        model = model_service.get_model()
        
        if model is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Community model not loaded"
            )
        
        member = model.get_member(member_id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member {member_id} not found"
            )
        
        # Build update dict based on device type
        asset_updates: Dict[str, Any] = {}
        
        if device_id == "solar":
            if request.capacity is not None:
                # Convert W to kW
                asset_updates["pv_capacity_kw"] = request.capacity / 1000.0
            if request.status == "inactive":
                # Set PV capacity to 0 to deactivate
                asset_updates["pv_capacity_kw"] = 0.0
        
        elif device_id == "battery":
            if request.capacity is not None:
                # Convert W to kWh (assuming 1 hour discharge rate)
                # Actually, capacity is in kWh, so we need to convert W*h to kWh
                # For simplicity, if capacity is given in W, we'll treat it as kWh*1000
                asset_updates["battery_capacity_kwh"] = request.capacity / 1000.0
            if request.status == "inactive":
                # Set battery capacity to 0 to deactivate
                asset_updates["battery_capacity_kwh"] = 0.0
        
        elif device_id == "grid":
            if request.capacity is not None:
                # For grid, capacity represents the max of import/export limits
                # We'll update both to the same value
                capacity_kw = request.capacity / 1000.0
                asset_updates["grid_import_limit_kw"] = capacity_kw
                asset_updates["grid_export_limit_kw"] = capacity_kw
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown device type: {device_id}"
            )
        
        if not asset_updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid updates provided"
            )
        
        # Update member assets
        success = model_service.update_member(member_id, {"assets": asset_updates})
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update device"
            )
        
        # Trigger immediate simulation update
        try:
            background_service = get_background_service()
            background_service.trigger_immediate_update("Device configuration updated")
        except Exception as e:
            logger.warning(f"Could not trigger immediate update: {e}")
        
        return {
            "status": "success",
            "message": f"Device {device_id} updated successfully",
            "updates": asset_updates
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating device {device_id} for {member_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update device: {str(e)}"
        )

