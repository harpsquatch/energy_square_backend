"""
Data Preprocessor Module
Merges all CSV files, aligns timestamps to continuous 10s index,
creates hourly resolution data, interpolates missing records,
and filters extreme outliers based on physical bounds.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class DataPreprocessor:
    """
    Preprocess Mesa Del Sol microgrid data by merging CSVs,
    aligning timestamps, creating hourly aggregates,
    interpolating missing values, and filtering outliers.
    """
    
    # Physical bounds for outlier filtering based on microgrid specifications
    PHYSICAL_BOUNDS = {
        # Power values (Kilowatts) - reasonable ranges for microgrid components
        'Battery_Active_Power': (-500, 500),  # Battery can charge/discharge
        'Battery_Active_Power_Set_Response': (-500, 500),
        'PVPCS_Active_Power': (0, 1000),  # Solar panels can't generate negative power
        'GE_Body_Active_Power': (0, 1000),  # Consumption should be positive
        'GE_Active_Power': (-1000, 1000),  # Can be negative if exporting
        'GE_Body_Active_Power_Set_Response': (0, 1000),
        'FC_Active_Power_FC_END_Set': (0, 500),  # Fuel cell set points positive
        'FC_Active_Power': (0, 500),  # Fuel cell generation positive
        'FC_Active_Power_FC_end_Set_Response': (0, 500),
        'Island_mode_MCCB_Active_Power': (-1000, 1000),
        
        # Voltage values (Volts) - AC grid voltage ranges
        'MG-LV-MSB_AC_Voltage': (400, 600),  # Typical AC voltage range
        'Receiving_Point_AC_Voltage': (400, 600),
        'Island_mode_MCCB_AC_Voltage': (400, 600),
        
        # Frequency values (Hertz) - Grid frequency stability
        'Island_mode_MCCB_Frequency': (55, 65),  # Normal grid frequency range
        'MG-LV-MSB_Frequency': (55, 65),
        
        # Temperature values (Degree Celsius) - Chilled water plant
        'Inlet_Temperature_of_Chilled_Water': (0, 50),  # Reasonable water temp range
        'Outlet_Temperature': (0, 50),
    }
    
    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize the data preprocessor.
        
        Args:
            data_dir: Directory containing CSV files. If None, uses default path.
        """
        if data_dir is None:
            # Default to be/artifacts/data_ingestion
            script_path = Path(__file__).parent  # be/data_pipeline
            be_path = script_path.parent  # be/
            self.data_dir = be_path / "artifacts" / "data_ingestion"
        else:
            self.data_dir = Path(data_dir)
        
        logger.info(f"DataPreprocessor initialized with data_dir: {self.data_dir}")
    
    def find_all_csv_files(self) -> List[Path]:
        """
        Find all CSV files in the data directory.
        
        Returns:
            List of Path objects to CSV files, sorted by filename
        """
        if not self.data_dir.exists():
            logger.error(f"Data directory does not exist: {self.data_dir}")
            return []
        
        csv_files = sorted(self.data_dir.glob("*.csv"))
        logger.info(f"Found {len(csv_files)} CSV files in {self.data_dir}")
        return csv_files
    
    def load_and_merge_csvs(self, csv_files: Optional[List[Path]] = None) -> pd.DataFrame:
        """
        Load and merge all CSV files into a single DataFrame.
        
        This function reads each CSV file, validates timestamps, and concatenates
        them into one continuous dataset. It handles timestamp parsing and basic
        cleaning (sentinel values).
        
        Args:
            csv_files: List of CSV file paths. If None, finds all CSVs in data_dir.
            
        Returns:
            Merged DataFrame with all data, sorted by Timestamp
        """
        if csv_files is None:
            csv_files = self.find_all_csv_files()
        
        if not csv_files:
            logger.error("No CSV files found to merge")
            return pd.DataFrame()
        
        all_dfs = []
        total_records = 0
        
        for csv_path in csv_files:
            try:
                logger.info(f"Loading {csv_path.name}...")
                df = pd.read_csv(csv_path)
                
                # Parse timestamps
                df['Timestamp'] = pd.to_datetime(
                    df['Timestamp'], 
                    format='%Y/%m/%d %H:%M:%S', 
                    errors='coerce'
                )
                
                # Drop rows with invalid timestamps
                initial_count = len(df)
                df = df[df['Timestamp'].notna()].copy()
                dropped = initial_count - len(df)
                if dropped > 0:
                    logger.warning(f"Dropped {dropped} invalid timestamp records from {csv_path.name}")
                
                # Clean sentinel values (-999999)
                numeric_cols = df.select_dtypes(include=[np.number]).columns
                for col in numeric_cols:
                    df[col] = df[col].replace(-999999, np.nan)
                
                all_dfs.append(df)
                total_records += len(df)
                logger.info(f"Loaded {len(df)} records from {csv_path.name}")
                
            except Exception as e:
                logger.error(f"Error loading {csv_path.name}: {e}")
                continue
        
        if not all_dfs:
            logger.error("No data loaded from any CSV files")
            return pd.DataFrame()
        
        # Merge all DataFrames
        merged_df = pd.concat(all_dfs, ignore_index=True)
        
        # Sort by timestamp
        merged_df = merged_df.sort_values('Timestamp').reset_index(drop=True)
        
        # Remove duplicate timestamps (keep first occurrence)
        initial_count = len(merged_df)
        merged_df = merged_df.drop_duplicates(subset=['Timestamp'], keep='first')
        duplicates_removed = initial_count - len(merged_df)
        if duplicates_removed > 0:
            logger.warning(f"Removed {duplicates_removed} duplicate timestamp records")
        
        logger.info(f"Merged {len(csv_files)} CSV files into {len(merged_df)} total records")
        logger.info(f"Date range: {merged_df['Timestamp'].min()} to {merged_df['Timestamp'].max()}")
        
        return merged_df
    
    def align_to_continuous_10s_index(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Align timestamps to a continuous 10-second index.
        
        This creates a complete time series with 10-second intervals covering
        the entire date range. Missing timestamps are added as NaN rows, which
        will be interpolated later.
        
        Args:
            df: DataFrame with Timestamp column (may have gaps)
            
        Returns:
            DataFrame with continuous 10-second intervals
        """
        if df.empty:
            return df
        
        # Ensure Timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(df['Timestamp']):
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        # Round timestamps to nearest 10-second boundary to align with continuous index
        # This ensures timestamps like "00:00:01" become "00:00:00"
        df_rounded = df.copy()
        df_rounded['Timestamp'] = df_rounded['Timestamp'].dt.floor('10S')
        
        # Set Timestamp as index for easier reindexing
        df_indexed = df_rounded.set_index('Timestamp').sort_index()
        
        # Handle duplicates after rounding (keep first occurrence)
        initial_duplicates = df_indexed.index.duplicated().sum()
        if initial_duplicates > 0:
            logger.info(f"Handling {initial_duplicates} duplicate timestamps after rounding (keeping mean values)")
            # Group by rounded timestamp and take mean for duplicates
            df_indexed = df_indexed.groupby(df_indexed.index).mean()
        
        # Create continuous 10-second range
        start_time = df_indexed.index.min()
        end_time = df_indexed.index.max()
        
        # Round start to nearest 10-second boundary (should already be rounded)
        start_time = start_time.floor('10S')
        end_time = end_time.ceil('10S')  # Round up to include the last interval
        
        # Create continuous index with 10-second intervals
        continuous_index = pd.date_range(
            start=start_time,
            end=end_time,
            freq='10S'
        )
        
        logger.info(f"Creating continuous 10-second index from {start_time} to {end_time}")
        logger.info(f"Continuous index will have {len(continuous_index)} intervals")
        
        # Reindex to continuous index (missing values become NaN)
        df_aligned = df_indexed.reindex(continuous_index)
        
        # Count how many timestamps were missing
        # Count rows where ALL numeric columns are NaN (truly missing intervals)
        numeric_cols = df_aligned.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            missing_count = df_aligned[numeric_cols].isna().all(axis=1).sum()
        else:
            missing_count = df_aligned.isna().all(axis=1).sum()
        
        if missing_count > 0:
            logger.info(f"Found {missing_count} missing 10-second intervals that need interpolation")
        
        # Reset index to make Timestamp a column again
        df_aligned = df_aligned.reset_index()
        df_aligned.rename(columns={'index': 'Timestamp'}, inplace=True)
        
        logger.info(f"Aligned data to continuous 10-second index: {len(df_aligned)} total records")
        
        return df_aligned
    
    def filter_outliers(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
        """
        Filter extreme outliers based on physical bounds.
        
        Values outside physical bounds are replaced with NaN, which will
        be handled by interpolation. This ensures we only keep physically
        plausible values.
        
        Args:
            df: DataFrame with sensor data
            
        Returns:
            Tuple of (filtered DataFrame, dictionary of outlier counts per column)
        """
        if df.empty:
            return df, {}
        
        df_filtered = df.copy()
        outlier_counts = {}
        
        # Filter each column that has defined bounds
        for col, (min_val, max_val) in self.PHYSICAL_BOUNDS.items():
            if col not in df_filtered.columns:
                continue
            
            # Count outliers before filtering
            initial_nan = df_filtered[col].isna().sum()
            
            # Replace values outside bounds with NaN
            mask_outside_bounds = (
                (df_filtered[col] < min_val) | 
                (df_filtered[col] > max_val)
            ) & df_filtered[col].notna()
            
            outlier_count = mask_outside_bounds.sum()
            df_filtered.loc[mask_outside_bounds, col] = np.nan
            
            final_nan = df_filtered[col].isna().sum()
            new_nans = final_nan - initial_nan
            
            if outlier_count > 0:
                outlier_counts[col] = outlier_count
                logger.info(
                    f"Filtered {outlier_count} outliers from {col} "
                    f"(bounds: [{min_val}, {max_val}])"
                )
        
        total_outliers = sum(outlier_counts.values())
        if total_outliers > 0:
            logger.info(f"Total outliers filtered: {total_outliers} across {len(outlier_counts)} columns")
        else:
            logger.info("No outliers found outside physical bounds")
        
        return df_filtered, outlier_counts
    
    def interpolate_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Interpolate missing values in the DataFrame.
        
        Uses linear interpolation along the time axis (which is sorted),
        which is appropriate for time-series sensor data. This fills in
        gaps created by missing timestamps or filtered outliers.
        
        Args:
            df: DataFrame with missing values (NaN)
            
        Returns:
            DataFrame with interpolated values
        """
        if df.empty:
            return df
        
        df_interpolated = df.copy()
        
        # Get numeric columns (excluding Timestamp)
        numeric_cols = df_interpolated.select_dtypes(include=[np.number]).columns.tolist()
        
        if not numeric_cols:
            logger.warning("No numeric columns found for interpolation")
            return df_interpolated
        
        # Count missing values before interpolation
        missing_before = df_interpolated[numeric_cols].isna().sum().sum()
        
        # Set Timestamp as index for time-based interpolation
        df_interpolated = df_interpolated.set_index('Timestamp')
        
        # Interpolate using time as the index (linear interpolation)
        # This fills gaps by interpolating between known values
        df_interpolated[numeric_cols] = df_interpolated[numeric_cols].interpolate(
            method='time',
            limit_direction='both',
            limit=None  # No limit on consecutive NaNs to interpolate
        )
        
        # Fill any remaining edge NaNs with forward/backward fill
        # This handles cases where interpolation couldn't fill edges
        df_interpolated[numeric_cols] = df_interpolated[numeric_cols].bfill().ffill()
        
        # Reset index
        df_interpolated = df_interpolated.reset_index()
        
        # Count missing values after interpolation
        missing_after = df_interpolated[numeric_cols].isna().sum().sum()
        interpolated_count = missing_before - missing_after
        
        if interpolated_count > 0:
            logger.info(f"Interpolated {interpolated_count} missing values")
        else:
            logger.info("No missing values to interpolate")
        
        if missing_after > 0:
            logger.warning(f"{missing_after} values remain missing after interpolation (likely at edges)")
        
        return df_interpolated
    
    def create_hourly_resolution(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create hourly resolution data from 10-second data.
        
        Aggregates 10-second records to hourly intervals using mean values
        for power/voltage/frequency metrics. This reduces data size while
        preserving overall patterns.
        
        Args:
            df: DataFrame with 10-second resolution data
            
        Returns:
            DataFrame with hourly resolution data
        """
        if df.empty:
            return pd.DataFrame()
        
        # Ensure Timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(df['Timestamp']):
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        # Set Timestamp as index
        df_indexed = df.set_index('Timestamp')
        
        # Group by hourly intervals and aggregate
        hourly_groups = df_indexed.groupby(pd.Grouper(freq='1H'))
        
        # Define aggregation strategy for each column
        agg_dict = {}
        numeric_cols = df_indexed.select_dtypes(include=[np.number]).columns
        
        # Use mean for all numeric columns (power, voltage, frequency, temperature)
        for col in numeric_cols:
            agg_dict[col] = 'mean'
        
        # Aggregate to hourly
        # Use 'mean' which will return NaN if all values in a group are NaN
        # But if at least one value exists, it will calculate mean
        hourly_df = hourly_groups.agg(agg_dict)
        
        # Fill any remaining NaNs in aggregated data with forward/backward fill
        # This handles cases where an entire hour had no data
        hourly_df[numeric_cols] = hourly_df[numeric_cols].bfill().ffill()
        
        # Remove any hourly buckets that are completely empty (after fill attempt)
        hourly_df = hourly_df.dropna(how='all')
        
        # Reset index to make Timestamp a column
        hourly_df = hourly_df.reset_index()
        
        # Add time features
        hourly_df['hour'] = hourly_df['Timestamp'].dt.hour
        hourly_df['day_of_week'] = hourly_df['Timestamp'].dt.dayofweek
        hourly_df['is_weekend'] = hourly_df['day_of_week'] >= 5
        hourly_df['date'] = hourly_df['Timestamp'].dt.date
        
        logger.info(
            f"Aggregated from {len(df)} 10-second records to {len(hourly_df)} hourly intervals"
        )
        logger.info(
            f"Hourly data range: {hourly_df['Timestamp'].min()} to {hourly_df['Timestamp'].max()}"
        )
        
        return hourly_df
    
    def generate_normalized_hourly_pattern(
        self,
        hourly_df: pd.DataFrame,
        output_filename: str = "communityA_hourly_pattern.csv",
        output_dir: Optional[Path] = None
    ) -> pd.DataFrame:
        """
        Generate a single normalized 15-month hourly pattern file.
        
        This creates a canonical pattern source with:
        - Complete temporal continuity (one row per hour from start to end)
        - All numeric columns normalized globally using min-max scaling
        - Preserved temporal correlation between features
        
        Args:
            hourly_df: DataFrame with hourly resolution data (from preprocess)
            output_filename: Name of output CSV file
            output_dir: Directory to save output. If None, uses artifacts directory.
            
        Returns:
            Normalized DataFrame with complete temporal continuity
        """
        if hourly_df.empty:
            logger.error("Cannot generate pattern from empty hourly DataFrame")
            return pd.DataFrame()
        
        logger.info("=" * 80)
        logger.info("GENERATING NORMALIZED HOURLY PATTERN FILE")
        logger.info("=" * 80)
        
        # Ensure Timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(hourly_df['Timestamp']):
            hourly_df['Timestamp'] = pd.to_datetime(hourly_df['Timestamp'])
        
        # Define expected date range
        start_date = pd.Timestamp('2022-05-01 00:00:00')
        end_date = pd.Timestamp('2023-07-31 23:00:00')
        
        logger.info(f"Ensuring complete temporal continuity from {start_date} to {end_date}")
        
        # Create complete hourly index
        complete_index = pd.date_range(start=start_date, end=end_date, freq='1H')
        logger.info(f"Complete hourly index contains {len(complete_index)} hours")
        
        # Set Timestamp as index for reindexing
        hourly_indexed = hourly_df.set_index('Timestamp').sort_index()
        
        # Identify numeric columns (exclude time feature columns added by create_hourly_resolution)
        # These are the 18 measured features from the original dataset
        time_feature_cols = ['hour', 'day_of_week', 'is_weekend', 'date']
        numeric_cols = [
            col for col in hourly_indexed.select_dtypes(include=[np.number]).columns
            if col not in time_feature_cols
        ]
        
        logger.info(f"Found {len(numeric_cols)} numeric feature columns to normalize:")
        for i, col in enumerate(numeric_cols, 1):
            logger.info(f"  {i:2d}. {col}")
        
        # Reindex to complete hourly index (missing hours become NaN)
        pattern_df = hourly_indexed.reindex(complete_index)
        
        # Count missing hours before interpolation
        missing_hours = pattern_df[numeric_cols].isna().all(axis=1).sum()
        if missing_hours > 0:
            logger.info(f"Found {missing_hours} missing hours, will interpolate")
        
        # Interpolate any missing hours (temporal interpolation)
        pattern_df[numeric_cols] = pattern_df[numeric_cols].interpolate(
            method='time',
            limit_direction='both'
        )
        
        # Fill any remaining edge NaNs with forward/backward fill
        pattern_df[numeric_cols] = pattern_df[numeric_cols].bfill().ffill()
        
        # Verify we have complete data
        remaining_nans = pattern_df[numeric_cols].isna().sum().sum()
        if remaining_nans > 0:
            logger.warning(f"Warning: {remaining_nans} NaN values remain after interpolation")
        else:
            logger.info("All hours have complete data")
        
        # Normalize each numeric column using min-max scaling globally
        # Formula: (x - min) / (max - min)
        logger.info("\nNormalizing features using global min-max scaling...")
        normalization_params = {}
        
        for col in numeric_cols:
            col_min = pattern_df[col].min()
            col_max = pattern_df[col].max()
            
            # Handle case where all values are the same (min == max)
            if col_max == col_min:
                logger.warning(f"Column {col} has constant values, setting to 0.5")
                pattern_df[col] = 0.5
            else:
                # Min-max normalization: values between 0 and 1
                pattern_df[col] = (pattern_df[col] - col_min) / (col_max - col_min)
            
            normalization_params[col] = {'min': col_min, 'max': col_max}
            logger.info(
                f"  {col}: normalized (original range: [{col_min:.3f}, {col_max:.3f}])"
            )
        
        # Reset index to make Timestamp a column
        pattern_df = pattern_df.reset_index()
        pattern_df.rename(columns={'index': 'Timestamp'}, inplace=True)
        
        # Select only Timestamp and the 18 measured features for output
        # (exclude derived time feature columns)
        output_cols = ['Timestamp'] + numeric_cols
        pattern_df_output = pattern_df[output_cols].copy()
        
        # Verify normalization range
        normalized_min = pattern_df_output[numeric_cols].min().min()
        normalized_max = pattern_df_output[numeric_cols].max().max()
        logger.info(f"\nNormalization verification: all values in range [{normalized_min:.6f}, {normalized_max:.6f}]")
        
        # Determine output directory
        if output_dir is None:
            script_path = Path(__file__).parent  # be/data_pipeline
            be_path = script_path.parent  # be/
            output_dir = be_path / "artifacts"
        else:
            output_dir = Path(output_dir)
        
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save to CSV
        output_path = output_dir / output_filename
        pattern_df_output.to_csv(output_path, index=False)
        
        logger.info(f"\nSaved normalized hourly pattern: {output_path}")
        logger.info(f"  Total rows: {len(pattern_df_output):,}")
        logger.info(f"  Total columns: {len(pattern_df_output.columns)} (1 Timestamp + {len(numeric_cols)} features)")
        logger.info(f"  Date range: {pattern_df_output['Timestamp'].min()} to {pattern_df_output['Timestamp'].max()}")
        logger.info("=" * 80)
        
        return pattern_df_output
    
    def preprocess(
        self,
        csv_files: Optional[List[Path]] = None,
        filter_outliers: bool = True,
        interpolate: bool = True,
        create_hourly: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        Complete preprocessing pipeline.
        
        This orchestrates all preprocessing steps:
        1. Merge all CSV files
        2. Align to continuous 10-second index
        3. Filter outliers (optional)
        4. Interpolate missing values (optional)
        5. Create hourly resolution (optional)
        
        Args:
            csv_files: List of CSV file paths. If None, finds all CSVs.
            filter_outliers: Whether to filter extreme outliers
            interpolate: Whether to interpolate missing values
            create_hourly: Whether to create hourly resolution data
            
        Returns:
            Dictionary with keys:
                - '10s_resolution': Continuous 10-second resolution data
                - 'hourly_resolution': Hourly aggregated data (if create_hourly=True)
                - 'outlier_counts': Dictionary of outlier counts per column
        """
        logger.info("=" * 80)
        logger.info("STARTING DATA PREPROCESSING PIPELINE")
        logger.info("=" * 80)
        
        # Step 1: Merge all CSVs
        logger.info("\n[Step 1/5] Merging all CSV files...")
        merged_df = self.load_and_merge_csvs(csv_files)
        
        if merged_df.empty:
            logger.error("No data to preprocess")
            return {
                '10s_resolution': pd.DataFrame(),
                'hourly_resolution': pd.DataFrame(),
                'outlier_counts': {}
            }
        
        # Step 2: Align to continuous 10-second index
        logger.info("\n[Step 2/5] Aligning timestamps to continuous 10-second index...")
        aligned_df = self.align_to_continuous_10s_index(merged_df)
        
        # Step 3: Filter outliers
        outlier_counts = {}
        if filter_outliers:
            logger.info("\n[Step 3/5] Filtering extreme outliers...")
            aligned_df, outlier_counts = self.filter_outliers(aligned_df)
        else:
            logger.info("\n[Step 3/5] Skipping outlier filtering")
        
        # Step 4: Interpolate missing values
        if interpolate:
            logger.info("\n[Step 4/5] Interpolating missing values...")
            aligned_df = self.interpolate_missing_values(aligned_df)
        else:
            logger.info("\n[Step 4/5] Skipping interpolation")
        
        # Step 5: Create hourly resolution
        hourly_df = pd.DataFrame()
        if create_hourly:
            logger.info("\n[Step 5/5] Creating hourly resolution data...")
            hourly_df = self.create_hourly_resolution(aligned_df)
        else:
            logger.info("\n[Step 5/5] Skipping hourly aggregation")
        
        logger.info("\n" + "=" * 80)
        logger.info("PREPROCESSING PIPELINE COMPLETED")
        logger.info("=" * 80)
        logger.info(f"10-second resolution records: {len(aligned_df)}")
        if not hourly_df.empty:
            logger.info(f"Hourly resolution records: {len(hourly_df)}")
        logger.info(f"Columns processed: {len(aligned_df.columns)}")
        
        return {
            '10s_resolution': aligned_df,
            'hourly_resolution': hourly_df,
            'outlier_counts': outlier_counts
        }


def main():
    """
    Main entry point for running the data preprocessor.
    
    This function:
    1. Merges all CSV files
    2. Aligns to continuous 10-second index
    3. Filters outliers and interpolates missing values
    4. Creates hourly resolution data
    5. Generates normalized hourly pattern file (communityA_hourly_pattern.csv)
    """
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("=" * 80)
    logger.info("DATA PREPROCESSOR - MAIN EXECUTION")
    logger.info("=" * 80)
    
    # Initialize preprocessor
    preprocessor = DataPreprocessor()
    
    # Run preprocessing pipeline
    results = preprocessor.preprocess(
        csv_files=None,  # Auto-discover all CSVs in data_dir
        filter_outliers=True,
        interpolate=True,
        create_hourly=True
    )
    
    # Check if preprocessing was successful
    if results['hourly_resolution'].empty:
        logger.error("Preprocessing failed - no hourly data generated")
        return
    
    # Generate normalized hourly pattern
    logger.info("\n" + "=" * 80)
    logger.info("GENERATING NORMALIZED HOURLY PATTERN")
    logger.info("=" * 80)
    
    normalized_pattern = preprocessor.generate_normalized_hourly_pattern(
        hourly_df=results['hourly_resolution'],
        output_filename="communityA_hourly_pattern.csv"
    )
    
    if not normalized_pattern.empty:
        logger.info("\n" + "=" * 80)
        logger.info("SUCCESS - PREPROCESSING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Normalized pattern file created: be/artifacts/communityA_hourly_pattern.csv")
        logger.info(f"  Total hourly records: {len(normalized_pattern):,}")
        logger.info(f"  Total features: {len(normalized_pattern.columns) - 1} (plus Timestamp)")
        logger.info(f"  Date range: {normalized_pattern['Timestamp'].min()} to {normalized_pattern['Timestamp'].max()}")
    else:
        logger.error("Failed to generate normalized pattern file")


if __name__ == "__main__":
    main()

