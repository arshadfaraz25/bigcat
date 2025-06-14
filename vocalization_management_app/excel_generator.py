import os
import pandas as pd
from django.conf import settings
from django.utils.timezone import now
from .models import OriginalAudioFile, ProcessingLog, DetectedNoiseAudioFile

def generate_excel_report_for_processed_file(audio_file_id):
    """
    Generate an Excel report for a processed audio file based on its ID.
    This function is meant to be called after audio processing is complete.
    
    Parameters:
    - audio_file_id: The ID of the OriginalAudioFile to generate a report for
    
    Returns:
    - str: Path to the generated Excel file, or None if generation failed
    """
    try:
        # Get the audio file
        audio_file = OriginalAudioFile.objects.get(file_id=audio_file_id)
        
        # Check if the file has been processed
        db_entry = audio_file.database_entry.first()
        if not db_entry or db_entry.status != 'Processed':
            ProcessingLog.objects.create(
                audio_file=audio_file,
                message="Cannot generate Excel report: File not fully processed",
                level="WARNING"
            )
            return None
        
        # Get the detected noise entries for this file
        detected_noises = DetectedNoiseAudioFile.objects.filter(original_file=audio_file).order_by('start_time')
        
        if not detected_noises.exists():
            ProcessingLog.objects.create(
                audio_file=audio_file,
                message="No saw calls detected, generating empty Excel report",
                level="INFO"
            )
        
        # Create a DataFrame to store the data
        data = []
        
        # Extract date from filename if available
        file_date = None
        try:
            from .audio_processing import parse_audio_filename
            device_info, recording_datetime = parse_audio_filename(audio_file.audio_file_name)
            file_date = recording_datetime.date()
        except Exception as e:
            ProcessingLog.objects.create(
                audio_file=audio_file,
                message=f"Warning: Could not extract date from filename for Excel report: {str(e)}",
                level="WARNING"
            )
        
        # Add each detected noise to the data list
        for noise in detected_noises:
            # Calculate duration in seconds
            start_seconds = noise.start_time.hour * 3600 + noise.start_time.minute * 60 + noise.start_time.second + noise.start_time.microsecond / 1000000
            end_seconds = noise.end_time.hour * 3600 + noise.end_time.minute * 60 + noise.end_time.second + noise.end_time.microsecond / 1000000
            duration = end_seconds - start_seconds
            
            # Format timestamps
            start_time = f"{noise.start_time.hour:02d}:{noise.start_time.minute:02d}:{noise.start_time.second:02d}.{noise.start_time.microsecond // 10000:02d}"
            end_time = f"{noise.end_time.hour:02d}:{noise.end_time.minute:02d}:{noise.end_time.second:02d}.{noise.end_time.microsecond // 10000:02d}"
            
            # Add to data list
            data.append({
                'File Name': audio_file.audio_file_name,
                'Date': file_date.strftime('%Y-%m-%d') if file_date else 'Unknown',
                'Start Time': start_time,
                'End Time': end_time,
                'Duration (s)': f"{duration:.2f}",
                'Impulses': noise.saw_count,
                'Frequency (Hz)': f"{noise.frequency:.2f}" if noise.frequency else 'N/A',
                'Magnitude': f"{noise.magnitude:.2f}" if noise.magnitude else 'N/A',
                'Animal Type': audio_file.get_animal_type_display()
            })
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Ensure the analysis_excel directory exists
        excel_dir = os.path.join(settings.MEDIA_ROOT, 'analysis_excel')
        os.makedirs(excel_dir, exist_ok=True)
        
        # Generate Excel file path
        timestamp = now().strftime('%Y%m%d_%H%M%S')
        excel_filename = f"analysis_{audio_file.audio_file_name.split('.')[0]}_{timestamp}.xlsx"
        excel_path = os.path.join(excel_dir, excel_filename)
        
        # Write to Excel
        if not data:  # If no data, create an empty Excel file with headers
            df = pd.DataFrame(columns=[
                'File Name', 'Date', 'Start Time', 'End Time', 'Duration (s)', 
                'Impulses', 'Frequency (Hz)', 'Magnitude', 'Animal Type'
            ])
        
        # Write to Excel with proper column formatting
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Saw Calls')
            worksheet = writer.sheets['Saw Calls']
            
            # Auto-adjust column widths
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.column_dimensions[chr(65 + idx)].width = max_len
        
        # Update the audio file's analysis_excel field
        relative_path = os.path.join('analysis_excel', excel_filename)
        audio_file.analysis_excel = relative_path
        audio_file.save(update_fields=['analysis_excel'])
        
        # Log successful Excel generation
        ProcessingLog.objects.create(
            audio_file=audio_file,
            message=f"Excel report generated and saved: {excel_filename}",
            level="SUCCESS"
        )
        
        return excel_path
        
    except Exception as e:
        # Log error
        try:
            ProcessingLog.objects.create(
                audio_file=OriginalAudioFile.objects.get(file_id=audio_file_id),
                message=f"Error generating Excel report: {str(e)}",
                level="ERROR"
            )
        except:
            # If we can't even get the audio file, log to console
            print(f"Error generating Excel report for file ID {audio_file_id}: {str(e)}")
        
        return None

def generate_excel_reports_for_processed_files():
    """
    Generate Excel reports for all processed files that don't have an Excel report yet.
    This can be called periodically or after batch processing.
    
    Returns:
    - tuple: (success_count, failed_count)
    """
    # Get all processed files without Excel reports
    processed_files = OriginalAudioFile.objects.filter(
        database_entry__status='Processed',
        analysis_excel=''
    )
    
    success_count = 0
    failed_count = 0
    
    for audio_file in processed_files:
        try:
            excel_path = generate_excel_report_for_processed_file(audio_file.file_id)
            if excel_path:
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            print(f"Error generating Excel for {audio_file.audio_file_name}: {str(e)}")
            failed_count += 1
    
    return success_count, failed_count
