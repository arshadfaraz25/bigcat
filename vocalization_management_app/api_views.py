from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .tasks import start_background_processor, stop_background_processor, get_processor_status
from .models import OriginalAudioFile, DetectedNoiseAudioFile
from datetime import datetime, timedelta

@login_required
@require_POST
def start_processor(request):
    """
    API endpoint to start the background audio processor
    """
    # Only admin and staff can start the processor
    if request.user.user_type not in ['1', '2']:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    success = start_background_processor()
    
    return JsonResponse({
        'success': success,
        'message': 'Background processor started' if success else 'Background processor is already running',
        'status': get_processor_status()
    })

@login_required
@require_POST
def stop_processor(request):
    """
    API endpoint to stop the background audio processor
    """
    # Only admin and staff can stop the processor
    if request.user.user_type not in ['1', '2']:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    success = stop_background_processor()
    
    return JsonResponse({
        'success': success,
        'message': 'Background processor stopped' if success else 'Background processor is not running',
        'status': get_processor_status()
    })

@login_required
def get_status(request):
    """
    API endpoint to get the current status of the background processor
    """
    # Only admin and staff can view the processor status
    if request.user.user_type not in ['1', '2']:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    from .audio_processing import get_processing_status
    
    status_data = get_processing_status()
    
    return JsonResponse({
        'success': True,
        'data': status_data
    })

@login_required
def get_file_logs(request, file_id):
    """
    API endpoint to get the processing logs for a specific file
    """
    from .models import OriginalAudioFile, ProcessingLog
    
    try:
        # Get the audio file
        audio_file = OriginalAudioFile.objects.get(id=file_id)
        
        # Get the processing logs for this file
        logs = ProcessingLog.objects.filter(audio_file=audio_file).order_by('-timestamp')[:20]
        
        # Format the logs for JSON response
        from django.utils import timezone
        
        logs_data = [{
            'id': log.id,
            'timestamp': timezone.localtime(log.timestamp).strftime('%Y-%m-%d %H:%M:%S'),  # Convert to local timezone
            'level': log.level,
            'message': log.message,
            # Include additional metadata for new changes
            'contains_timestamp': any(keyword in log.message.lower() for keyword in ['start=', 'end=', 'duration']),
            'contains_frequency': 'freq=' in log.message.lower(),
            'contains_magnitude': 'mag=' in log.message.lower(),
            'contains_impulses': 'impulses=' in log.message.lower()
        } for log in logs]
        
        return JsonResponse({
            'success': True,
            'data': logs_data
        })
    except OriginalAudioFile.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Audio file not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

@login_required
def get_recent_logs(request):
    """
    API endpoint to get recent processing logs for the admin dashboard
    """
    from .models import ProcessingLog
    from django.db import connection
    
    # Only admin and staff can view the logs
    if request.user.user_type not in ['1', '2']:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    # Force a database connection reset to ensure fresh data
    connection.close()
    
    # Get recent logs with a fresh query
    logs = ProcessingLog.objects.select_related('audio_file').order_by('-timestamp')[:30]
    
    # Format the logs for JSON response
    from django.utils import timezone
    from datetime import datetime
    
    logs_data = [{
        'id': log.id,
        'timestamp': timezone.localtime(log.timestamp).strftime('%Y-%m-%d %H:%M:%S'),  # Convert to local timezone
        'level': log.level,
        'message': log.message,
        'file_name': log.audio_file.audio_file_name if log.audio_file else 'System',
        'file_id': log.audio_file.file_id if log.audio_file else None,
        # Include additional metadata for new changes
        'contains_timestamp': any(keyword in log.message.lower() for keyword in ['start=', 'end=', 'duration']),
        'contains_frequency': 'freq=' in log.message.lower(),
        'contains_magnitude': 'mag=' in log.message.lower(),
        'contains_impulses': 'impulses=' in log.message.lower()
    } for log in logs]
    
    return JsonResponse({
        'success': True,
        'data': logs_data
    })

@login_required
def get_processed_files(request):
    """
    API endpoint to get processed audio files for dynamic updates
    """
    from .models import OriginalAudioFile, Database
    from django.db import connection
    
    # Only admin and staff can view the processed files
    if request.user.user_type not in ['1', '2']:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    # Force a database connection reset to ensure fresh data
    connection.close()
    
    # Get all processed audio files
    processed_files = OriginalAudioFile.objects.select_related('uploaded_by').prefetch_related(
        'database_entry'
    ).filter(database_entry__status='Processed').order_by('-upload_date')
    
    # Format the files for JSON response
    from django.utils import timezone
    
    files_data = [{
        'id': file.file_id,
        'file_name': file.audio_file_name,
        'animal_type': file.animal_type,
        'upload_date': timezone.localtime(file.upload_date).strftime('%Y-%m-%d %H:%M:%S'),
        'processing_end_time': timezone.localtime(file.database_entry.first().processing_end_time).strftime('%Y-%m-%d %H:%M:%S') if file.database_entry.first().processing_end_time else None,
    } for file in processed_files]
    
    return JsonResponse({
        'success': True,
        'data': files_data
    })

@login_required
def get_timeplot_data(request):
    """
    API endpoint to get saw call data for timeplot visualization.
    Accepts filters for animal type, date range, and zoo.
    Returns daily counts of saw calls for the specified period.
    """
    # Only admin and staff can access this data
    if request.user.user_type not in ['1', '2']:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    try:
        # Get filter parameters
        animal_type = request.GET.get('animal_type', '')
        zoo_id = request.GET.get('zoo_id', '')
        date_type = request.GET.get('date_type', 'recording')  # Default to recording date
        
        # Get date parameters based on date type
        if date_type == 'recording':
            # Recording date parameters
            start_date_str = request.GET.get('start_date', '')
            end_date_str = request.GET.get('end_date', '')
            # Set upload date parameters to empty
            upload_start_date_str = ''
            upload_end_date_str = ''
        else:
            # Upload date parameters
            upload_start_date_str = request.GET.get('upload_start_date', '')
            upload_end_date_str = request.GET.get('upload_end_date', '')
            # Set recording date parameters to empty
            start_date_str = ''
            end_date_str = ''
        
        # No time parameters needed anymore
        start_time_str = ''
        end_time_str = ''
        upload_start_time_str = ''
        upload_end_time_str = ''
        
        # Validate date parameters based on date type
        if date_type == 'recording':
            if not start_date_str or not end_date_str:
                return JsonResponse({
                    'success': False,
                    'message': 'Start date and end date are required for recording date filtering'
                }, status=400)
        else:  # upload date type
            if not upload_start_date_str or not upload_end_date_str:
                return JsonResponse({
                    'success': False,
                    'message': 'Start date and end date are required for upload date filtering'
                }, status=400)
        
        # Parse dates based on date type
        try:
            # Initialize all date variables
            start_date = None
            end_date = None
            upload_start_date = None
            upload_end_date = None
            
            # Parse based on date type
            if date_type == 'recording':
                # Parse recording dates
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                # Add one day to end_date to make it inclusive
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() + timedelta(days=1)
            else:  # upload date type
                # Parse upload dates
                upload_start_date = datetime.strptime(upload_start_date_str, '%Y-%m-%d').date()
                # Add one day to end_date to make it inclusive
                upload_end_date = datetime.strptime(upload_end_date_str, '%Y-%m-%d').date() + timedelta(days=1)
            
            # No time parsing needed anymore
            start_time = None
            end_time = None
            upload_start_time = None
            upload_end_time = None
        except ValueError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid date or time format. Use YYYY-MM-DD for dates and HH:MM for times.'
            }, status=400)
        
        # Build the query for original audio files
        query = OriginalAudioFile.objects.filter(
            database_entry__status='Processed'  # Only include processed files
        )
        
        # Apply date filters based on date type
        if date_type == 'recording':
            # Apply recording date filters
            query = query.filter(
                recording_date__date__gte=start_date,
                recording_date__date__lt=end_date
            )
        else:  # upload date type
            # Apply upload date filters
            query = query.filter(
                upload_date__date__gte=upload_start_date,
                upload_date__date__lt=upload_end_date
            )
        
        # Apply additional filters if provided
        if animal_type:
            query = query.filter(animal_type=animal_type)
        
        if zoo_id:
            query = query.filter(zoo_id=zoo_id)
        
        # Get all matching audio files - don't use prefetch_related since we're querying directly
        audio_files = query.all()
        
        # Prepare data for timeplot
        daily_data = {}
        
        # Process each audio file and count saw calls by date
        for audio_file in audio_files:
            # Get the relevant date based on date type
            relevant_date = None
            if date_type == 'recording' and audio_file.recording_date:
                relevant_date = audio_file.recording_date.date()
            elif date_type == 'upload' and audio_file.upload_date:
                relevant_date = audio_file.upload_date.date()
                
            # Skip if no valid date
            if not relevant_date:
                continue
                
            # Ensure the date is within our selected range
            if date_type == 'recording':
                if not (start_date <= relevant_date < end_date):
                    continue
            else:  # upload date
                if not (upload_start_date <= relevant_date < upload_end_date):
                    continue
                    
            # Convert to ISO format for the dictionary key
            date_str = relevant_date.isoformat()
                
            # Initialize the date entry if it doesn't exist
            if date_str not in daily_data:
                daily_data[date_str] = {
                    'date': date_str,
                    'saw_count': 0,
                    'file_count': 0
                }
                
                # Count the detected noises (saw calls)
                # Get the count of saw calls from the related DetectedNoiseAudioFile objects
                noise_files = DetectedNoiseAudioFile.objects.filter(original_file=audio_file)
                saw_count = sum(noise.saw_count for noise in noise_files) if noise_files else 0
                
                # Update the counts
                daily_data[date_str]['saw_count'] += saw_count
                daily_data[date_str]['file_count'] += 1
        
        # Convert the dictionary to a list for the response
        timeplot_data = list(daily_data.values())
        
        # Sort by date
        timeplot_data.sort(key=lambda x: x['date'])
        
        return JsonResponse({
            'success': True,
            'data': timeplot_data,
            'filters': {
                'animal_type': animal_type,
                'zoo_id': zoo_id,
                'date_type': date_type,
                'start_date': start_date_str if date_type == 'recording' else upload_start_date_str,
                'end_date': end_date_str if date_type == 'recording' else upload_end_date_str
            }
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': f'Error generating timeplot data: {str(e)}'
        }, status=500)
