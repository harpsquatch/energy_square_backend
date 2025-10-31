"""
Data Transformation Service for Energy Square Platform

This module transforms raw Italian market data and solar plant data
into structured formats suitable for the energy trading platform.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class ItalianMarketDataTransformer:
    """Transforms Italian electricity market data for energy trading platform"""
    
    def __init__(self, data_path: str = "artifacts/data_ingestion/"):
        self.data_path = Path(data_path)
        self.transformed_data = {}
    
    def load_pun_data(self) -> pd.DataFrame:
        """Load and transform PUN (National Electricity Price) data"""
        try:
            df = pd.read_excel(self.data_path / "20251027_20251027_PUN.xlsx")
            
            # Clean column names
            df.columns = ['date', 'hour', 'period', 'price_eur_mwh']
            
            # Convert date to datetime
            df['datetime'] = pd.to_datetime(df['date'], format='%d/%m/%Y') + pd.to_timedelta(df['hour'] - 1, unit='h')
            
            # Add period offset (15-minute intervals)
            df['datetime'] += pd.to_timedelta((df['period'] - 1) * 15, unit='m')
            
            # Clean price data
            df['price_eur_mwh'] = pd.to_numeric(df['price_eur_mwh'], errors='coerce')
            
            # Add derived fields
            df['price_eur_kwh'] = df['price_eur_mwh'] / 1000  # Convert to €/kWh
            df['day_of_week'] = df['datetime'].dt.day_name()
            df['is_weekend'] = df['datetime'].dt.weekday >= 5
            df['is_peak_hour'] = df['hour'].between(8, 20)  # Peak hours 8 AM to 8 PM
            
            # Add price categories
            df['price_category'] = pd.cut(
                df['price_eur_mwh'], 
                bins=[0, 50, 70, 100, float('inf')], 
                labels=['Low', 'Medium', 'High', 'Very High']
            )
            
            logger.info(f"PUN data loaded: {len(df)} records")
            return df
            
        except Exception as e:
            logger.error(f"Error loading PUN data: {e}")
            return pd.DataFrame()
    
    def load_zonal_prices(self) -> pd.DataFrame:
        """Load and transform zonal electricity prices"""
        try:
            df = pd.read_excel(self.data_path / "20251027_20251027_MGP_PrezziZonali.xlsx")
            
            # Clean column names
            df.columns = ['date', 'hour', 'period'] + [col for col in df.columns[3:]]
            
            # Convert date to datetime
            df['datetime'] = pd.to_datetime(df['date'], format='%d/%m/%Y') + pd.to_timedelta(df['hour'] - 1, unit='h')
            df['datetime'] += pd.to_timedelta((df['period'] - 1) * 15, unit='m')
            
            # Convert price columns to numeric
            price_columns = [col for col in df.columns if col not in ['date', 'hour', 'period', 'datetime']]
            for col in price_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Add Italian regions only
            italian_regions = [
                'Italia', 'Calabria', 'Central-northern Italy', 'Centeral-southern Italy',
                'North', 'Sardegna', 'Sicilia', 'Southern-Italy'
            ]
            
            # Filter for Italian regions
            italian_cols = ['datetime'] + [col for col in italian_regions if col in df.columns]
            df_italian = df[italian_cols].copy()
            
            # Calculate price spreads for arbitrage opportunities
            if 'Italia' in df_italian.columns:
                for region in italian_regions[1:]:  # Skip 'Italia' itself
                    if region in df_italian.columns:
                        df_italian[f'{region}_spread_vs_national'] = (
                            df_italian[region] - df_italian['Italia']
                        )
            
            logger.info(f"Zonal prices loaded: {len(df_italian)} records, {len(italian_cols)-1} regions")
            return df_italian
            
        except Exception as e:
            logger.error(f"Error loading zonal prices: {e}")
            return pd.DataFrame()
    
    def load_demand_data(self) -> pd.DataFrame:
        """Load and transform energy demand data"""
        try:
            df = pd.read_excel(self.data_path / "20251027_20251027_MGP_Fabbisogno.xlsx")
            
            # Clean column names
            df.columns = ['date', 'hour', 'period'] + [col for col in df.columns[3:]]
            
            # Convert date to datetime
            df['datetime'] = pd.to_datetime(df['date'], format='%d/%m/%Y') + pd.to_timedelta(df['hour'] - 1, unit='h')
            df['datetime'] += pd.to_timedelta((df['period'] - 1) * 15, unit='m')
            
            # Convert demand columns to numeric
            demand_columns = [col for col in df.columns if col not in ['date', 'hour', 'period', 'datetime']]
            for col in demand_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Add demand categories
            if 'Total Italy' in df.columns:
                df['demand_category'] = pd.cut(
                    df['Total Italy'], 
                    bins=[0, 20000, 25000, 30000, float('inf')], 
                    labels=['Low', 'Medium', 'High', 'Very High']
                )
            
            logger.info(f"Demand data loaded: {len(df)} records")
            return df
            
        except Exception as e:
            logger.error(f"Error loading demand data: {e}")
            return pd.DataFrame()
    
    def load_solar_plant_data(self, plant_id: str) -> Dict[str, pd.DataFrame]:
        """Load and transform solar plant data"""
        try:
            # Load generation data
            gen_df = pd.read_csv(self.data_path / f"Plant_{plant_id}_Generation_Data.csv")
            # Handle different date formats
            try:
                gen_df['datetime'] = pd.to_datetime(gen_df['DATE_TIME'], format='%d-%m-%Y %H:%M')
            except:
                gen_df['datetime'] = pd.to_datetime(gen_df['DATE_TIME'])
            
            # Load weather data
            weather_df = pd.read_csv(self.data_path / f"Plant_{plant_id}_Weather_Sensor_Data.csv")
            weather_df['datetime'] = pd.to_datetime(weather_df['DATE_TIME'])
            
            # Merge generation and weather data
            merged_df = pd.merge(
                gen_df, 
                weather_df[['datetime', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'IRRADIATION']], 
                on='datetime', 
                how='left'
            )
            
            # Add derived fields
            merged_df['efficiency'] = (merged_df['AC_POWER'] / merged_df['DC_POWER']).fillna(0)
            merged_df['plant_id'] = plant_id
            merged_df['hour'] = merged_df['datetime'].dt.hour
            merged_df['day_of_week'] = merged_df['datetime'].dt.day_name()
            merged_df['is_producing'] = merged_df['AC_POWER'] > 0
            
            # Calculate daily aggregates
            daily_agg = merged_df.groupby(merged_df['datetime'].dt.date).agg({
                'AC_POWER': 'sum',
                'DC_POWER': 'sum',
                'DAILY_YIELD': 'max',
                'IRRADIATION': 'mean',
                'AMBIENT_TEMPERATURE': 'mean',
                'MODULE_TEMPERATURE': 'mean',
                'efficiency': 'mean'
            }).reset_index()
            daily_agg['datetime'] = pd.to_datetime(daily_agg['datetime'])
            
            logger.info(f"Solar plant {plant_id} data loaded: {len(merged_df)} records")
            return {
                'hourly': merged_df,
                'daily': daily_agg
            }
            
        except Exception as e:
            logger.error(f"Error loading solar plant {plant_id} data: {e}")
            return {'hourly': pd.DataFrame(), 'daily': pd.DataFrame()}
    
    def create_trading_opportunities(self, pun_data: pd.DataFrame, zonal_data: pd.DataFrame) -> pd.DataFrame:
        """Create trading opportunities based on price differences"""
        try:
            # Merge PUN and zonal data
            trading_df = pd.merge(pun_data[['datetime', 'price_eur_mwh']], zonal_data, on='datetime')
            
            # Calculate arbitrage opportunities
            arbitrage_opportunities = []
            
            for region in ['Calabria', 'Sicilia', 'Sardegna', 'North', 'Southern-Italy']:
                if region in trading_df.columns:
                    trading_df[f'{region}_arbitrage'] = trading_df[region] - trading_df['price_eur_mwh']
                    trading_df[f'{region}_arbitrage_pct'] = (
                        (trading_df[region] - trading_df['price_eur_mwh']) / trading_df['price_eur_mwh'] * 100
                    )
            
            # Identify best trading opportunities
            trading_df['best_arbitrage_region'] = trading_df[[
                col for col in trading_df.columns if col.endswith('_arbitrage')
            ]].idxmax(axis=1).str.replace('_arbitrage', '')
            
            trading_df['best_arbitrage_value'] = trading_df[[
                col for col in trading_df.columns if col.endswith('_arbitrage')
            ]].max(axis=1)
            
            logger.info(f"Trading opportunities calculated: {len(trading_df)} records")
            return trading_df
            
        except Exception as e:
            logger.error(f"Error creating trading opportunities: {e}")
            return pd.DataFrame()
    
    def create_energy_analytics(self, pun_data: pd.DataFrame, demand_data: pd.DataFrame, 
                              solar_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Create comprehensive energy analytics"""
        try:
            analytics = {}
            
            # Price analytics
            analytics['price_stats'] = {
                'min_price': pun_data['price_eur_mwh'].min(),
                'max_price': pun_data['price_eur_mwh'].max(),
                'avg_price': pun_data['price_eur_mwh'].mean(),
                'price_volatility': pun_data['price_eur_mwh'].std(),
                'peak_hour_avg': pun_data[pun_data['is_peak_hour']]['price_eur_mwh'].mean(),
                'off_peak_avg': pun_data[~pun_data['is_peak_hour']]['price_eur_mwh'].mean()
            }
            
            # Demand analytics
            if 'Total Italy' in demand_data.columns:
                analytics['demand_stats'] = {
                    'min_demand': demand_data['Total Italy'].min(),
                    'max_demand': demand_data['Total Italy'].max(),
                    'avg_demand': demand_data['Total Italy'].mean(),
                    'peak_hour_avg': demand_data[demand_data['datetime'].dt.hour.between(8, 20)]['Total Italy'].mean(),
                    'off_peak_avg': demand_data[~demand_data['datetime'].dt.hour.between(8, 20)]['Total Italy'].mean()
                }
            
            # Solar production analytics
            for plant_id, plant_data in solar_data.items():
                if not plant_data['hourly'].empty:
                    hourly = plant_data['hourly']
                    analytics[f'plant_{plant_id}_stats'] = {
                        'total_production_kwh': hourly['AC_POWER'].sum() * 0.25,  # 15-min intervals
                        'max_power_kw': hourly['AC_POWER'].max(),
                        'avg_efficiency': hourly['efficiency'].mean(),
                        'production_hours': hourly['is_producing'].sum() * 0.25,
                        'avg_irradiation': hourly['IRRADIATION'].mean(),
                        'temperature_coefficient': self._calculate_temp_coefficient(hourly)
                    }
            
            # Market correlation
            if not pun_data.empty and 'Total Italy' in demand_data.columns:
                merged = pd.merge(pun_data[['datetime', 'price_eur_mwh']], 
                                demand_data[['datetime', 'Total Italy']], on='datetime')
                analytics['price_demand_correlation'] = merged['price_eur_mwh'].corr(merged['Total Italy'])
            
            logger.info("Energy analytics created successfully")
            return analytics
            
        except Exception as e:
            logger.error(f"Error creating energy analytics: {e}")
            return {}
    
    def _calculate_temp_coefficient(self, solar_data: pd.DataFrame) -> float:
        """Calculate temperature coefficient for solar panels"""
        try:
            if 'MODULE_TEMPERATURE' in solar_data.columns and 'AC_POWER' in solar_data.columns:
                # Filter for daylight hours and positive power
                daylight_data = solar_data[
                    (solar_data['AC_POWER'] > 0) & 
                    (solar_data['IRRADIATION'] > 0)
                ]
                
                if len(daylight_data) > 10:
                    correlation = daylight_data['MODULE_TEMPERATURE'].corr(daylight_data['AC_POWER'])
                    return correlation
            return 0.0
        except:
            return 0.0
    
    def transform_all_data(self) -> Dict[str, Any]:
        """Transform all data and return structured format"""
        try:
            logger.info("Starting data transformation...")
            
            # Load market data
            pun_data = self.load_pun_data()
            zonal_data = self.load_zonal_prices()
            demand_data = self.load_demand_data()
            
            # Load solar data
            solar_plant_1 = self.load_solar_plant_data("1")
            solar_plant_2 = self.load_solar_plant_data("2")
            
            # Create trading opportunities
            trading_opportunities = self.create_trading_opportunities(pun_data, zonal_data)
            
            # Create analytics
            analytics = self.create_energy_analytics(
                pun_data, demand_data, 
                {"1": solar_plant_1, "2": solar_plant_2}
            )
            
            # Structure the transformed data
            transformed_data = {
                'market_data': {
                    'pun_prices': pun_data.to_dict('records'),
                    'zonal_prices': zonal_data.to_dict('records'),
                    'demand_data': demand_data.to_dict('records'),
                    'trading_opportunities': trading_opportunities.to_dict('records')
                },
                'solar_data': {
                    'plant_1': {
                        'hourly': solar_plant_1['hourly'].to_dict('records'),
                        'daily': solar_plant_1['daily'].to_dict('records')
                    },
                    'plant_2': {
                        'hourly': solar_plant_2['hourly'].to_dict('records'),
                        'daily': solar_plant_2['daily'].to_dict('records')
                    }
                },
                'analytics': analytics,
                'metadata': {
                    'transformation_date': datetime.now().isoformat(),
                    'data_period': {
                        'start': pun_data['datetime'].min().isoformat() if not pun_data.empty else None,
                        'end': pun_data['datetime'].max().isoformat() if not pun_data.empty else None
                    },
                    'total_records': {
                        'pun_prices': len(pun_data),
                        'zonal_prices': len(zonal_data),
                        'demand_data': len(demand_data),
                        'solar_plant_1': len(solar_plant_1['hourly']),
                        'solar_plant_2': len(solar_plant_2['hourly'])
                    }
                }
            }
            
            self.transformed_data = transformed_data
            logger.info("Data transformation completed successfully")
            return transformed_data
            
        except Exception as e:
            logger.error(f"Error in data transformation: {e}")
            return {}
    
    def save_transformed_data(self, output_path: str = "artifacts/transformed_data.json"):
        """Save transformed data to JSON file"""
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w') as f:
                json.dump(self.transformed_data, f, indent=2, default=str)
            
            logger.info(f"Transformed data saved to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving transformed data: {e}")
            return False


def main():
    """Main function to run data transformation"""
    transformer = ItalianMarketDataTransformer()
    transformed_data = transformer.transform_all_data()
    
    if transformed_data:
        transformer.save_transformed_data()
        print("✅ Data transformation completed successfully!")
        print(f"📊 Market data records: {len(transformed_data['market_data']['pun_prices'])}")
        print(f"☀️ Solar plant 1 records: {len(transformed_data['solar_data']['plant_1']['hourly'])}")
        print(f"☀️ Solar plant 2 records: {len(transformed_data['solar_data']['plant_2']['hourly'])}")
    else:
        print("❌ Data transformation failed!")


if __name__ == "__main__":
    main()
