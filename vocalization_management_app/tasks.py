import time
import threading
import logging
import os
from django.utils import timezone
from django.db import transaction
from .models import Database, ProcessingLog, OriginalAudioFile, DetectedNoiseAudioFile
from .audio_processing import process_audio
from .excel_generator import generate_excel_report_for_processed_file

# Configure logging
logger = logging.getLogger(__name__)

# Global variables to control the background processor
processor_running = False
processor_thread = None
processing_interval = 10  # seconds between checking for new files


def get_pending_audio_files():
    """
    Get all audio files that have been uploaded but not yet processed
    Returns a QuerySet of OriginalAudioFile objects with status 'Pending'
    """
    # Get IDs of audio files that have pending status in the Database model
    pending_audio_file_ids = Database.objects.filter(status='Pending').values_list('audio_file_id', flat=True)
    
    # Return a QuerySet of OriginalAudioFile objects with those IDs
    # Use file_id instead of id since OriginalAudioFile uses file_id as primary key
    return OriginalAudioFile.objects.filter(file_id__in=pending_audio_file_ids)


def get_failed_audio_files(max_retry_age=None):
    """
    Get all audio files that failed processing and could be retried
    
    Args:
        max_retry_age: Optional datetime to limit how old failed files can be for retry
                      If None, all failed files are returned regardless of age
    
    Returns a QuerySet of OriginalAudioFile objects with status 'Failed'
    """
    # Start with all failed files
    failed_query = Database.objects.filter(status='Failed')
    
    # If max_retry_age is provided, only get files that failed after that time
    if max_retry_age:
        failed_query = failed_query.filter(processing_end_time__gte=max_retry_age)
    
    # Get the IDs of failed audio files
    failed_audio_file_ids = failed_query.values_list('audio_file_id', flat=True)
    
    # Return a QuerySet of OriginalAudioFile objects with those IDs
    return OriginalAudioFile.objects.filter(file_id__in=failed_audio_file_ids)


def mark_file_as_processing(audio_file):
    """
    Mark a file as currently being processed
    """
    with transaction.atomic():
        db_entry = Database.objects.select_for_update().get(audio_file=audio_file)
        if db_entry.status != 'Pending':
            return False  # File is no longer pending, skip it
        
        db_entry.status = 'Processing'
        db_entry.processing_start_time = timezone.now()
        db_entry.save()
        
        # Log the start of processing
        ProcessingLog.objects.create(
            audio_file=audio_file,
            message=f"Started processing file: {audio_file.audio_file_name}",
            level="INFO"
        )
        return True


def mark_file_for_retry(audio_file):
    """
    Mark a failed file as pending for reprocessing
    Returns True if the file was successfully marked for retry, False otherwise
    """
    with transaction.atomic():
        try:
            db_entry = Database.objects.select_for_update().get(audio_file=audio_file)
            
            # Only retry files that are currently in 'Failed' status
            if db_entry.status != 'Failed':
                return False
            
            # Update the status to 'Pending' for retry
            db_entry.status = 'Pending'
            db_entry.processing_start_time = None  # Clear the previous processing start time
            db_entry.processing_end_time = None   # Clear the previous processing end time
            db_entry.save()
            
            # Log the retry attempt
            ProcessingLog.objects.create(
                audio_file=audio_file,
                message=f"Marked for retry after previous processing failure: {audio_file.audio_file_name}",
                level="INFO"
            )
            return True
            
        except Database.DoesNotExist:
            # Log error if the database entry doesn't exist
            logger.error(f"Cannot retry file {audio_file.audio_file_name}: No database entry found")
            return False
        except Exception as e:
            # Log any other errors
            logger.error(f"Error marking file {audio_file.audio_file_name} for retry: {str(e)}")
            return False


def process_single_file(audio_file):
    """
    Process a single audio file and update its status
    Returns True if processing was successful, False otherwise
    """
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            # Mark the file as processing
            if not mark_file_as_processing(audio_file):
                return False  # File was already being processed or is not pending
            
            # Process the audio file
            file_path = audio_file.audio_file.path
            success = process_audio(file_path, audio_file)
            
            if success:
                # Generate Excel report after successful processing
                # Use transaction to prevent database locking issues
                with transaction.atomic():
                    excel_path = generate_excel_report_for_processed_file(audio_file.file_id)
                    
                    if excel_path:
                        ProcessingLog.objects.create(
                            audio_file=audio_file,
                            message=f"Excel report generated after processing: {os.path.basename(excel_path)}",
                            level="SUCCESS"
                        )
                    else:
                        ProcessingLog.objects.create(
                            audio_file=audio_file,
                            message="Failed to generate Excel report after processing",
                            level="WARNING"
                        )
            
            return success
            
        except Exception as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                # If database is locked and we have retries left, wait and try again
                logger.warning(f"Database locked during processing of {audio_file.audio_file_name}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                continue
            
            # Log the error
            try:
                with transaction.atomic():
                    ProcessingLog.objects.create(
                        audio_file=audio_file,
                        message=f"Unexpected error during processing: {str(e)}",
                        level="ERROR"
                    )
                    
                    # Update database entry to Failed status
                    db_entry = Database.objects.select_for_update().get(audio_file=audio_file)
                    db_entry.status = 'Failed'
                    db_entry.processing_end_time = timezone.now()
                    db_entry.save()
            except Exception as inner_e:
                logger.error(f"Error updating status for {audio_file.audio_file_name}: {str(inner_e)}")
            
            return False


def process_pending_files_continuously():
    """
    Continuously process pending audio files one by one
    This function runs in a separate thread
    """
    global processor_running
    
    logger.info("Background audio processor started")
    
    # Track when we last retried failed files to avoid too frequent retries
    last_failed_retry_time = None
    retry_interval = 3600  # Default: retry failed files once per hour (in seconds)
    max_retries_per_cycle = 5  # Maximum number of failed files to retry in one cycle
    
    # Track consecutive idle cycles to determine when to retry failed files
    idle_cycles = 0
    idle_cycles_before_retry = 3  # Number of idle cycles before retrying failed files
    
    while processor_running:
        try:
            # Get the next pending file
            pending_files = get_pending_audio_files()
            
            if pending_files.exists():
                # Process one file at a time
                audio_file = pending_files.first()
                logger.info(f"Processing file: {audio_file.audio_file_name}")
                
                # Process the file
                success = process_single_file(audio_file)
                
                if success:
                    logger.info(f"Successfully processed file: {audio_file.audio_file_name}")
                else:
                    logger.warning(f"Failed to process file: {audio_file.audio_file_name}")
                
                # Reset idle cycles counter since we processed a file
                idle_cycles = 0
            else:
                # No pending files, increment idle cycles counter
                idle_cycles += 1
                logger.info(f"No pending files to process. Idle cycle {idle_cycles}. Waiting for new uploads.")
                
                # Check if we should retry failed files
                current_time = time.time()
                should_retry_failed = (
                    idle_cycles >= idle_cycles_before_retry and
                    (last_failed_retry_time is None or
                     current_time - last_failed_retry_time >= retry_interval)
                )
                
                if should_retry_failed:
                    # Get failed files from the last 7 days (604800 seconds)
                    retry_age = timezone.now() - timezone.timedelta(seconds=604800)
                    failed_files = get_failed_audio_files(max_retry_age=retry_age)
                    
                    if failed_files.exists():
                        retry_count = 0
                        logger.info(f"Found {failed_files.count()} failed files to retry")
                        
                        # Retry up to max_retries_per_cycle failed files
                        for failed_file in failed_files[:max_retries_per_cycle]:
                            logger.info(f"Attempting to retry failed file: {failed_file.audio_file_name}")
                            
                            if mark_file_for_retry(failed_file):
                                retry_count += 1
                                logger.info(f"Marked failed file for retry: {failed_file.audio_file_name}")
                            
                            # Small delay between marking files for retry
                            time.sleep(0.5)
                        
                        logger.info(f"Marked {retry_count} failed files for retry")
                        last_failed_retry_time = current_time
                        
                        # Reset idle cycles after retrying failed files
                        idle_cycles = 0
                    else:
                        logger.info("No failed files to retry")
                        last_failed_retry_time = current_time
            
            # Sleep for a while before checking again
            time.sleep(processing_interval)
            
        except Exception as e:
            logger.error(f"Error in background processor: {str(e)}")
            time.sleep(processing_interval)  # Sleep and try again
    
    logger.info("Background audio processor stopped")


def start_background_processor():
    """
    Start the background processing thread if it's not already running
    """
    global processor_running, processor_thread
    
    if processor_running and processor_thread and processor_thread.is_alive():
        logger.info("Background processor is already running")
        return False
    
    processor_running = True
    processor_thread = threading.Thread(target=process_pending_files_continuously)
    processor_thread.daemon = True  # Thread will exit when main program exits
    processor_thread.start()
    
    logger.info("Started background audio processor")
    return True


def stop_background_processor():
    """
    Stop the background processing thread
    """
    global processor_running, processor_thread
    
    if not processor_running or not processor_thread:
        logger.info("Background processor is not running")
        return False
    
    processor_running = False
    processor_thread.join(timeout=5.0)  # Wait for thread to finish
    processor_thread = None
    
    logger.info("Stopped background audio processor")
    return True


def get_processor_status():
    """
    Get the current status of the background processor
    """
    global processor_running, processor_thread
    
    if processor_running and processor_thread and processor_thread.is_alive():
        return "Running"
    else:
        return "Stopped"


def process_pending_audio_files_batch():
    """
    Process all pending audio files in a batch (one by one)
    This is for manual triggering of processing
    Returns a tuple of (processed_count, failed_count)
    """
    # Get pending files with a transaction to ensure consistency
    with transaction.atomic():
        # Use select_for_update with nowait to avoid blocking if another process is already working
        try:
            # Get IDs of audio files that have pending status in the Database model
            pending_audio_file_ids = Database.objects.filter(status='Pending').select_for_update(nowait=True).values_list('audio_file_id', flat=True)
            # Get the actual audio files
            pending_files = list(OriginalAudioFile.objects.filter(file_id__in=pending_audio_file_ids))
        except Exception as e:
            if "database is locked" in str(e).lower() or "could not obtain lock" in str(e).lower():
                logger.warning("Another process is already handling pending files. Skipping this batch.")
                return 0, 0
            raise
    
    processed_count = 0
    failed_count = 0
    
    for audio_file in pending_files:
        try:
            # Process the file with a small delay between files to reduce database contention
            success = process_single_file(audio_file)
            
            if success:
                processed_count += 1
            else:
                failed_count += 1
                
            # Small delay to prevent database contention
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error processing file {audio_file.audio_file_name}: {str(e)}")
            failed_count += 1
    
    return processed_count, failed_count


def process_pending_audio_files():
    """
    Process all pending audio files in a batch (one by one)
    This is a wrapper function for process_pending_audio_files_batch that can be called from views
    """
    # Start processing in a separate thread to avoid blocking the request
    threading.Thread(target=process_pending_audio_files_batch).start()
    return {'status': 'Processing started in background'}
