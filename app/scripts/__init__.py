"""
Energy Square Data Pipeline

Modular data processing pipeline for energy community data:
1. Data Ingestion - Load raw Mesa Del Sol CSV files
2. Data Transformation - Aggregate to 1-minute intervals
3. Feature Engineering - Calculate derived metrics
4. Data Generation - Generate coherent community and user profiles
"""

from .data_ingestion import MesaDataIngestion
from .data_transformation import DataTransformation
from .feature_engineering import FeatureEngineering
from .profile_generation import CommunityProfileGenerator, UserProfileGenerator
from .main import DataPipelineRunner

__all__ = [
    'MesaDataIngestion',
    'DataTransformation',
    'FeatureEngineering',
    'CommunityProfileGenerator',
    'UserProfileGenerator',
    'DataPipelineRunner',
]

