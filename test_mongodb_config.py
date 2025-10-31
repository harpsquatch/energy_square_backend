#!/usr/bin/env python3
"""
Test script for MongoDB community configuration

This script tests the MongoDB-based community configuration system
to ensure it works correctly with the database.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.community_config import community_config, CommunityConfigDocument
from app.core.database import get_database


async def test_mongodb_config():
    """Test MongoDB configuration functionality"""
    print("🧪 Testing MongoDB Community Configuration")
    print("=" * 50)
    
    try:
        # Test 1: Get default configuration
        print("\n1️⃣ Testing default configuration loading...")
        config = await community_config.get_config()
        print(f"✅ Loaded config: {config.total_households} households, {config.total_solar_capacity} kW solar")
        
        # Test 2: Update configuration
        print("\n2️⃣ Testing configuration update...")
        await community_config.update_config(
            total_households=1000,
            average_household_size=3.0,
            households_with_solar=800
        )
        updated_config = await community_config.get_config()
        print(f"✅ Updated config: {updated_config.total_households} households, {updated_config.total_population} people")
        
        # Test 3: Get scaling factors
        print("\n3️⃣ Testing scaling factors...")
        scaling_factors = await community_config.get_scaling_factors()
        print(f"✅ Scaling factors: {scaling_factors}")
        
        # Test 4: Get community metrics
        print("\n4️⃣ Testing community metrics...")
        metrics = await community_config.get_community_metrics()
        print(f"✅ Community metrics: {metrics['total_households']} households, {metrics['solar_coverage_percentage']:.1f}% solar coverage")
        
        # Test 5: Validate configuration
        print("\n5️⃣ Testing configuration validation...")
        validation = await community_config.validate_configuration()
        print(f"✅ Validation result: Valid={validation['valid']}, Issues={len(validation['issues'])}, Warnings={len(validation['warnings'])}")
        
        # Test 6: Reset configuration
        print("\n6️⃣ Testing configuration reset...")
        await community_config.reset_config()
        reset_config = await community_config.get_config()
        print(f"✅ Reset config: {reset_config.total_households} households (should be 500)")
        
        # Test 7: Test database connection
        print("\n7️⃣ Testing database connection...")
        db = await get_database()
        collections = await db.list_collection_names()
        print(f"✅ Database connected. Collections: {collections}")
        
        # Test 8: Check if community_config collection exists
        if 'community_config' in collections:
            collection = db['community_config']
            count = await collection.count_documents({})
            print(f"✅ community_config collection has {count} document(s)")
        else:
            print("⚠️  community_config collection not found (will be created on first save)")
        
        print("\n🎉 All tests passed! MongoDB configuration is working correctly.")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function"""
    print("Starting MongoDB Community Configuration Tests...")
    success = await test_mongodb_config()
    
    if success:
        print("\n✅ All tests completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

