"""
Community Control Service
External interfaces for demand response, member management, and asset updates.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine
from app.models.community_model import Member, MemberAssets

logger = logging.getLogger(__name__)


class CommunityControlService:
    """Service for external control of community simulation."""
    
    def __init__(
        self,
        model_service: CommunityModelService,
        simulation_engine: CommunitySimulationEngine
    ):
        """
        Initialize control service.
        
        Args:
            model_service: Community model service
            simulation_engine: Simulation engine instance
        """
        self.model_service = model_service
        self.simulation_engine = simulation_engine
    
    # === Member Management ===
    
    def add_member(self, member_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new member to the community.
        
        Args:
            member_config: Member configuration dictionary
            
        Returns:
            Result dictionary
        """
        try:
            # Create member from config
            member = Member.model_validate(member_config)
            
            # Add to model
            success = self.model_service.add_member(member)
            
            if success:
                # Initialize member state in simulation engine
                self.simulation_engine._initialize_member_states()
                
                return {
                    "success": True,
                    "member_id": member.member_id,
                    "message": f"Member {member.member_id} added successfully"
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to add member {member_config.get('member_id')}"
                }
        except Exception as e:
            logger.error(f"Error adding member: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def remove_member(self, member_id: str) -> Dict[str, Any]:
        """
        Remove a member from the community.
        
        Args:
            member_id: Member ID to remove
            
        Returns:
            Result dictionary
        """
        success = self.model_service.remove_member(member_id)
        
        if success:
            # Remove from simulation engine state
            if member_id in self.simulation_engine._member_states:
                del self.simulation_engine._member_states[member_id]
            
            return {
                "success": True,
                "member_id": member_id,
                "message": f"Member {member_id} removed successfully"
            }
        else:
            return {
                "success": False,
                "error": f"Failed to remove member {member_id}"
            }
    
    def update_member_assets(
        self,
        member_id: str,
        asset_updates: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Update a member's asset configuration.
        
        Args:
            member_id: Member ID
            asset_updates: Dictionary of asset fields to update
            
        Returns:
            Result dictionary
        """
        success = self.simulation_engine.update_member_asset(member_id, asset_updates)
        
        if success:
            return {
                "success": True,
                "member_id": member_id,
                "updates": asset_updates,
                "message": f"Assets updated for member {member_id}"
            }
        else:
            return {
                "success": False,
                "error": f"Failed to update assets for member {member_id}"
            }
    
    def scale_member_asset(
        self,
        member_id: str,
        asset_name: str,
        scale_factor: float
    ) -> Dict[str, Any]:
        """
        Scale a member's asset by a factor.
        
        Args:
            member_id: Member ID
            asset_name: Asset field name (e.g., "pv_capacity_kw")
            scale_factor: Scaling factor (e.g., 1.2 for 20% increase)
            
        Returns:
            Result dictionary
        """
        member = self.model_service.get_member(member_id)
        if not member:
            return {
                "success": False,
                "error": f"Member {member_id} not found"
            }
        
        # Get current value
        current_assets = member.assets.model_dump()
        if asset_name not in current_assets:
            return {
                "success": False,
                "error": f"Asset {asset_name} not found"
            }
        
        # Calculate new value
        new_value = current_assets[asset_name] * scale_factor
        asset_updates = {asset_name: new_value}
        
        return self.update_member_assets(member_id, asset_updates)
    
    # === Community Control ===
    
    def update_community_limits(
        self,
        grid_import_limit_kw: Optional[float] = None,
        grid_export_limit_kw: Optional[float] = None,
        battery_min_soc: Optional[float] = None,
        battery_max_soc: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Update community-level control limits.
        
        Args:
            grid_import_limit_kw: New grid import limit
            grid_export_limit_kw: New grid export limit
            battery_min_soc: New minimum battery SOC
            battery_max_soc: New maximum battery SOC
            
        Returns:
            Result dictionary
        """
        model = self.model_service.get_model()
        if not model:
            return {
                "success": False,
                "error": "Model not loaded"
            }
        
        updates = {}
        if grid_import_limit_kw is not None:
            updates["grid_import_limit_kw"] = grid_import_limit_kw
        if grid_export_limit_kw is not None:
            updates["grid_export_limit_kw"] = grid_export_limit_kw
        if battery_min_soc is not None:
            updates["battery_min_soc"] = battery_min_soc
        if battery_max_soc is not None:
            updates["battery_max_soc"] = battery_max_soc
        
        try:
            # Update community control
            control_dict = model.community_control.model_dump()
            control_dict.update(updates)
            model.community_control = type(model.community_control).model_validate(control_dict)
            
            # Save model
            self.model_service._save_model(model)
            
            return {
                "success": True,
                "updates": updates,
                "message": "Community limits updated successfully"
            }
        except Exception as e:
            logger.error(f"Error updating community limits: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # === Member Status ===
    
    def get_member_status(self, member_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a member."""
        member = self.model_service.get_member(member_id)
        if not member:
            return None
        
        # Get current state
        state = self.simulation_engine._member_states.get(member_id, {})
        
        return {
            "member_id": member_id,
            "member_type": member.member_type.value,
            "assets": member.assets.model_dump(),
            # Use battery state from simulation or default to middle of min/max range from model
            "battery_soc": state.get("battery_soc", self._get_default_battery_soc()),
            "last_update": state.get("last_update")
        }
    
    def get_community_status(self) -> Dict[str, Any]:
        """Get current status of the community."""
        model = self.model_service.get_model()
        if not model:
            return {
                "error": "Model not loaded"
            }
        
        # Get all member statuses
        member_statuses = []
        for member in model.members:
            status = self.get_member_status(member.member_id)
            if status:
                member_statuses.append(status)
        
        return {
            "community_id": model.community.community_id,
            "total_members": len(model.members),
            "prosumers": len([m for m in model.members if m.member_type.value == "prosumer"]),
            "consumers": len([m for m in model.members if m.member_type.value == "consumer"]),
            "community_control": model.community_control.model_dump(),
            "members": member_statuses
        }

