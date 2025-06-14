import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
from datetime import datetime, timedelta
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap
from .models import DetectedNoiseAudioFile, OriginalAudioFile


def load_and_merge_data(existing_excel_path, new_excel_path):
    """
    Load and merge data from existing and new Excel files.
    
    Parameters:
    - existing_excel_path: Path to the existing Excel file
    - new_excel_path: Path to the new Excel file
    
    Returns:
    - merged_df: DataFrame containing merged data
    - existing_df: DataFrame containing only existing data
    - new_df: DataFrame containing only new data
    """
    try:
        # Load existing data
        existing_df = pd.read_excel(existing_excel_path)
        existing_df['Source'] = 'Existing'
        
        # Load new data
        new_df = pd.read_excel(new_excel_path)
        new_df['Source'] = 'New'
        
        # Ensure consistent column names
        existing_columns = set(existing_df.columns)
        new_columns = set(new_df.columns)
        
        # Check for missing columns
        missing_in_existing = new_columns - existing_columns
        missing_in_new = existing_columns - new_columns
        
        # Add missing columns with NaN values
        for col in missing_in_existing:
            existing_df[col] = np.nan
        
        for col in missing_in_new:
            new_df[col] = np.nan
        
        # Standardize timestamp format if needed
        for df in [existing_df, new_df]:
            if 'Start' in df.columns and not pd.api.types.is_datetime64_dtype(df['Start']):
                try:
                    df['Start'] = pd.to_datetime(df['Start'], format='%H:%M:%S.%f').dt.time
                except:
                    pass
            
            if 'End' in df.columns and not pd.api.types.is_datetime64_dtype(df['End']):
                try:
                    df['End'] = pd.to_datetime(df['End'], format='%H:%M:%S.%f').dt.time
                except:
                    pass
        
        # Merge the dataframes
        merged_df = pd.concat([existing_df, new_df], ignore_index=True)
        
        # Check for duplicates based on Start, End, and Frequency
        duplicates = merged_df.duplicated(subset=['File', 'Start', 'End', 'Frequency (Hz)'], keep=False)
        if duplicates.any():
            print(f"Found {duplicates.sum()} potential duplicate entries")
            # Mark duplicates but keep them for now
            merged_df['Duplicate'] = duplicates
        
        return merged_df, existing_df, new_df
    
    except Exception as e:
        print(f"Error merging data: {str(e)}")
        return None, None, None


def create_timeline_visualization(merged_df, output_path=None, show_plot=True):
    """
    Create a comprehensive timeline visualization showing call timestamps with frequency and magnitude.
    
    Parameters:
    - merged_df: DataFrame containing the merged data
    - output_path: Path to save the visualization (optional)
    - show_plot: Whether to display the plot (default: True)
    
    Returns:
    - fig: The matplotlib figure object
    """
    # Convert time columns to datetime for plotting if they're not already
    df = merged_df.copy()
    
    # Create a reference date to plot times
    reference_date = pd.to_datetime('2023-01-01')
    
    # Process Start and End columns
    if 'Start' in df.columns and not pd.api.types.is_datetime64_dtype(df['Start']):
        # Convert time objects to strings then to timedelta
        df['Start_Time'] = pd.to_datetime(df['Start'].astype(str))
        df['Start_DateTime'] = reference_date + pd.to_timedelta(df['Start_Time'].dt.hour, unit='h') + \
                             pd.to_timedelta(df['Start_Time'].dt.minute, unit='m') + \
                             pd.to_timedelta(df['Start_Time'].dt.second, unit='s')
    
    if 'End' in df.columns and not pd.api.types.is_datetime64_dtype(df['End']):
        df['End_Time'] = pd.to_datetime(df['End'].astype(str))
        df['End_DateTime'] = reference_date + pd.to_timedelta(df['End_Time'].dt.hour, unit='h') + \
                           pd.to_timedelta(df['End_Time'].dt.minute, unit='m') + \
                           pd.to_timedelta(df['End_Time'].dt.second, unit='s')
    
    # Create the figure and axes
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
    
    # Color mapping for source
    colors = {'Existing': 'blue', 'New': 'red'}
    
    # Scatter plot for calls with frequency on y-axis
    for source, group in df.groupby('Source'):
        scatter = ax1.scatter(group['Start_DateTime'], 
                            group['Frequency (Hz)'], 
                            s=group['Magnitude'] * 20,  # Size based on magnitude
                            alpha=0.7,
                            c=colors[source],
                            label=source)
    
    # Add horizontal lines for each call from start to end time
    for idx, row in df.iterrows():
        ax1.hlines(y=row['Frequency (Hz)'], 
                 xmin=row['Start_DateTime'], 
                 xmax=row['End_DateTime'],
                 colors=colors[row['Source']], 
                 alpha=0.3)
    
    # Highlight notable calls (high frequency or magnitude)
    notable_calls = df[(df['Frequency (Hz)'] > df['Frequency (Hz)'].quantile(0.9)) | 
                      (df['Magnitude'] > df['Magnitude'].quantile(0.9))]
    
    if not notable_calls.empty:
        ax1.scatter(notable_calls['Start_DateTime'], 
                  notable_calls['Frequency (Hz)'],
                  s=notable_calls['Magnitude'] * 30,
                  facecolors='none', 
                  edgecolors='green',
                  linewidth=2,
                  label='Notable Calls')
    
    # Customize the frequency plot
    ax1.set_ylabel('Frequency (Hz)', fontsize=12)
    ax1.set_title('Big Cat Vocalization Analysis - Saw Calls', fontsize=16)
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # Format x-axis to show only time
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    
    # Create histogram of calls by time
    time_bins = pd.date_range(start=df['Start_DateTime'].min(), 
                             end=df['Start_DateTime'].max(), 
                             periods=20)
    
    # Plot histograms for each source
    for source, group in df.groupby('Source'):
        ax2.hist(group['Start_DateTime'], 
                bins=time_bins, 
                alpha=0.6, 
                label=source,
                color=colors[source])
    
    ax2.set_xlabel('Time', fontsize=12)
    ax2.set_ylabel('Number of Calls', fontsize=12)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save the figure if output path is provided
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
    
    # Show the plot if requested
    if show_plot:
        plt.show()
    
    return fig


def create_frequency_magnitude_plot(merged_df, output_path=None, show_plot=True):
    """
    Create a scatter plot showing the relationship between frequency and magnitude.
    
    Parameters:
    - merged_df: DataFrame containing the merged data
    - output_path: Path to save the visualization (optional)
    - show_plot: Whether to display the plot (default: True)
    
    Returns:
    - fig: The matplotlib figure object
    """
    # Create the figure
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Color mapping for source
    colors = {'Existing': 'blue', 'New': 'red'}
    
    # Scatter plot for each source
    for source, group in merged_df.groupby('Source'):
        scatter = ax.scatter(group['Frequency (Hz)'], 
                           group['Magnitude'], 
                           s=group['Number of Calls'] * 10,  # Size based on call count
                           alpha=0.7,
                           c=colors[source],
                           label=f"{source} Data")
    
    # Add a best fit line for each source
    for source, group in merged_df.groupby('Source'):
        if len(group) > 1:  # Need at least 2 points for regression
            x = group['Frequency (Hz)']
            y = group['Magnitude']
            z = np.polyfit(x, y, 1)
            p = np.poly1d(z)
            ax.plot(x, p(x), '--', color=colors[source], alpha=0.8)
    
    # Customize the plot
    ax.set_xlabel('Frequency (Hz)', fontsize=12)
    ax.set_ylabel('Magnitude', fontsize=12)
    ax.set_title('Relationship Between Frequency and Magnitude in Saw Calls', fontsize=16)
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    # Add annotations for extreme values
    extreme_values = merged_df[(merged_df['Frequency (Hz)'] > merged_df['Frequency (Hz)'].quantile(0.95)) | 
                             (merged_df['Magnitude'] > merged_df['Magnitude'].quantile(0.95))]
    
    for idx, row in extreme_values.iterrows():
        ax.annotate(f"File: {row['File'][-10:]}, Calls: {row['Number of Calls']}",
                   xy=(row['Frequency (Hz)'], row['Magnitude']),
                   xytext=(10, 10),
                   textcoords='offset points',
                   arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=.2'))
    
    plt.tight_layout()
    
    # Save the figure if output path is provided
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
    
    # Show the plot if requested
    if show_plot:
        plt.show()
    
    return fig


def create_heatmap(merged_df, output_path=None, show_plot=True):
    """
    Create a heatmap showing the density of calls over time and frequency.
    
    Parameters:
    - merged_df: DataFrame containing the merged data
    - output_path: Path to save the visualization (optional)
    - show_plot: Whether to display the plot (default: True)
    
    Returns:
    - fig: The matplotlib figure object
    """
    # Create a copy of the dataframe
    df = merged_df.copy()
    
    # Create time bins (hours)
    if 'Start_DateTime' in df.columns:
        df['Hour'] = df['Start_DateTime'].dt.hour + df['Start_DateTime'].dt.minute/60
    else:
        # Extract hour from Start if Start_DateTime is not available
        df['Hour'] = df['Start'].apply(lambda x: x.hour + x.minute/60 if hasattr(x, 'hour') else 0)
    
    # Create frequency bins
    freq_min = df['Frequency (Hz)'].min()
    freq_max = df['Frequency (Hz)'].max()
    freq_bins = np.linspace(freq_min, freq_max, 20)
    df['Freq_Bin'] = pd.cut(df['Frequency (Hz)'], bins=freq_bins, labels=freq_bins[:-1])
    
    # Convert to numeric for plotting
    df['Freq_Bin'] = df['Freq_Bin'].astype(float)
    
    # Create pivot table for heatmap
    pivot = df.pivot_table(
        values='Magnitude',
        index='Freq_Bin',
        columns='Hour',
        aggfunc='mean'  # Can also use 'count', 'sum', etc.
    )
    
    # Create the figure
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Create a custom colormap that transitions from light to dark
    colors = [(0.9, 0.9, 0.9), (0.1, 0.3, 0.6)]  # Light gray to dark blue
    cmap = LinearSegmentedColormap.from_list('custom_cmap', colors, N=100)
    
    # Create the heatmap
    sns.heatmap(pivot, 
               cmap=cmap, 
               ax=ax, 
               cbar_kws={'label': 'Mean Magnitude'},
               linewidths=0.5)
    
    # Customize the plot
    ax.set_ylabel('Frequency (Hz)', fontsize=12)
    ax.set_xlabel('Hour of Day', fontsize=12)
    ax.set_title('Density of Saw Calls by Time and Frequency', fontsize=16)
    
    # Format x-axis to show hours
    ax.set_xticks(np.arange(0, 24, 2))
    ax.set_xticklabels([f"{int(h)}:00" for h in np.arange(0, 24, 2)])
    
    plt.tight_layout()
    
    # Save the figure if output path is provided
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
    
    # Show the plot if requested
    if show_plot:
        plt.show()
    
    return fig


def create_summary_statistics(merged_df):
    """
    Generate summary statistics for the merged dataset.
    
    Parameters:
    - merged_df: DataFrame containing the merged data
    
    Returns:
    - stats_df: DataFrame containing summary statistics
    """
    # Group by source
    stats = []
    
    # Overall statistics
    overall_stats = {
        'Dataset': 'Combined',
        'Total Calls': len(merged_df),
        'Mean Frequency (Hz)': merged_df['Frequency (Hz)'].mean(),
        'Median Frequency (Hz)': merged_df['Frequency (Hz)'].median(),
        'Mean Magnitude': merged_df['Magnitude'].mean(),
        'Mean Duration (s)': merged_df['Duration (s)'].mean() if 'Duration (s)' in merged_df.columns else None,
        'Total Files': merged_df['File'].nunique()
    }
    stats.append(overall_stats)
    
    # Statistics by source
    for source, group in merged_df.groupby('Source'):
        source_stats = {
            'Dataset': source,
            'Total Calls': len(group),
            'Mean Frequency (Hz)': group['Frequency (Hz)'].mean(),
            'Median Frequency (Hz)': group['Frequency (Hz)'].median(),
            'Mean Magnitude': group['Magnitude'].mean(),
            'Mean Duration (s)': group['Duration (s)'].mean() if 'Duration (s)' in group.columns else None,
            'Total Files': group['File'].nunique()
        }
        stats.append(source_stats)
    
    # Create DataFrame
    stats_df = pd.DataFrame(stats)
    
    # Round numeric columns
    numeric_cols = stats_df.select_dtypes(include=['float64']).columns
    stats_df[numeric_cols] = stats_df[numeric_cols].round(2)
    
    return stats_df


def export_visualizations(existing_excel_path, new_excel_path, output_dir):
    """
    Load data, create visualizations, and export them to the specified directory.
    
    Parameters:
    - existing_excel_path: Path to the existing Excel file
    - new_excel_path: Path to the new Excel file
    - output_dir: Directory to save the visualizations
    
    Returns:
    - True if successful, False otherwise
    """
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Load and merge data
        merged_df, existing_df, new_df = load_and_merge_data(existing_excel_path, new_excel_path)
        
        if merged_df is None:
            return False
        
        # Create timestamp for filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create and save visualizations
        timeline_fig = create_timeline_visualization(
            merged_df, 
            output_path=os.path.join(output_dir, f"timeline_visualization_{timestamp}.png"),
            show_plot=False
        )
        
        scatter_fig = create_frequency_magnitude_plot(
            merged_df, 
            output_path=os.path.join(output_dir, f"frequency_magnitude_plot_{timestamp}.png"),
            show_plot=False
        )
        
        heatmap_fig = create_heatmap(
            merged_df, 
            output_path=os.path.join(output_dir, f"heatmap_{timestamp}.png"),
            show_plot=False
        )
        
        # Generate summary statistics
        stats_df = create_summary_statistics(merged_df)
        
        # Save merged data and statistics to Excel
        with pd.ExcelWriter(os.path.join(output_dir, f"merged_data_{timestamp}.xlsx")) as writer:
            merged_df.to_excel(writer, sheet_name='Merged Data', index=False)
            stats_df.to_excel(writer, sheet_name='Summary Statistics', index=False)
        
        return True
    
    except Exception as e:
        print(f"Error exporting visualizations: {str(e)}")
        return False


def load_data_from_database(days_limit=30):
    """
    Load data directly from the database for the specified time period.
    
    Parameters:
    - days_limit: Number of days to look back (default: 30)
    
    Returns:
    - DataFrame containing the data
    """
    try:
        # Calculate the cutoff date
        cutoff_date = datetime.now() - timedelta(days=days_limit)
        
        # Query the database
        noise_files = DetectedNoiseAudioFile.objects.filter(
            upload_date__gte=cutoff_date
        ).select_related('original_file')
        
        # Convert to DataFrame
        data = []
        for noise in noise_files:
            row = {
                'File': noise.original_file.audio_file_name,
                'Start': noise.start_time.strftime('%H:%M:%S.%f')[:-4],
                'End': noise.end_time.strftime('%H:%M:%S.%f')[:-4],
                'Frequency (Hz)': noise.frequency,
                'Magnitude': noise.magnitude,
                'Number of Calls': noise.saw_call_count,
                'Upload Date': noise.upload_date,
                'Animal Type': noise.original_file.animal_type
            }
            
            # Add recording date if available
            if noise.original_file.recording_date:
                row['Recording Date'] = noise.original_file.recording_date.date()
            
            # Calculate duration
            start_seconds = noise.start_time.hour * 3600 + noise.start_time.minute * 60 + noise.start_time.second
            end_seconds = noise.end_time.hour * 3600 + noise.end_time.minute * 60 + noise.end_time.second
            row['Duration (s)'] = end_seconds - start_seconds
            
            data.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Add source column (all are from database)
        df['Source'] = 'Database'
        
        return df
    
    except Exception as e:
        print(f"Error loading data from database: {str(e)}")
        return None


def visualize_database_data(output_dir=None, days_limit=30, show_plots=True):
    """
    Load data from the database and create visualizations.
    
    Parameters:
    - output_dir: Directory to save the visualizations (optional)
    - days_limit: Number of days to look back (default: 30)
    - show_plots: Whether to display the plots (default: True)
    
    Returns:
    - True if successful, False otherwise
    """
    try:
        # Load data from database
        df = load_data_from_database(days_limit)
        
        if df is None or df.empty:
            print("No data found in the database for the specified time period.")
            return False
        
        # Create timestamp for filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create output directory if it doesn't exist and output_dir is provided
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # Create visualizations
        create_timeline_visualization(
            df, 
            output_path=os.path.join(output_dir, f"timeline_visualization_{timestamp}.png") if output_dir else None,
            show_plot=show_plots
        )
        
        create_frequency_magnitude_plot(
            df, 
            output_path=os.path.join(output_dir, f"frequency_magnitude_plot_{timestamp}.png") if output_dir else None,
            show_plot=show_plots
        )
        
        create_heatmap(
            df, 
            output_path=os.path.join(output_dir, f"heatmap_{timestamp}.png") if output_dir else None,
            show_plot=show_plots
        )
        
        # Generate and display summary statistics
        stats_df = create_summary_statistics(df)
        print("Summary Statistics:")
        print(stats_df)
        
        # Save data and statistics to Excel if output_dir is provided
        if output_dir:
            with pd.ExcelWriter(os.path.join(output_dir, f"database_data_{timestamp}.xlsx")) as writer:
                df.to_excel(writer, sheet_name='Data', index=False)
                stats_df.to_excel(writer, sheet_name='Summary Statistics', index=False)
        
        return True
    
    except Exception as e:
        print(f"Error visualizing database data: {str(e)}")
        return False
