from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import OriginalAudioFile, Database, ProcessingLog, Spectrogram, DetectedNoiseAudioFile
from .audio_processing import process_pending_audio_files, get_processing_status

@login_required
def staff_home(request):
    """
    Staff home view showing recent processing activity and audio files
    """
    if request.user.user_type != '2':  # Restrict access to staff only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    
    # Get processing status data
    status_data = get_processing_status()
    
    # Get recent processing logs
    recent_logs = ProcessingLog.objects.select_related('audio_file').order_by('-timestamp')[:10]
    
    # Get files currently being processed
    processing_files_details = Database.objects.filter(
        status='Processing'
    ).select_related('audio_file')
    
    # Get pending files
    pending_files_details = Database.objects.filter(
        status='Pending'
    ).select_related('audio_file').order_by('-audio_file__upload_date')
    
    # Get all audio files with their processing status
    audio_files = OriginalAudioFile.objects.prefetch_related(
        'database_entry'
    ).order_by('-upload_date')
    
    context = {
        'page_title': 'Staff Dashboard',
        'total_files': status_data['total'],
        'pending_files': status_data['pending'],
        'processing_files': status_data['processing'],
        'processed_files': status_data['processed'],
        'failed_files': status_data['failed'],
        'processor_status': status_data['processor_status'],
        'recent_logs': recent_logs,
        'pending_files_details': pending_files_details,
        'processing_files_details': processing_files_details,
        'audio_files': audio_files,
    }
    
    return render(request, "staff_template/staff_home.html", context)

@login_required
def process_audio_files(request):
    """
    View for processing pending audio files
    """
    if request.user.user_type != '2':  # Restrict access to staff only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    
    # Get pending files count before processing
    pending_count = Database.objects.filter(status='Pending').count()
    
    if pending_count == 0:
        messages.info(request, "No pending audio files to process.")
        return redirect('staff_home')
    
    try:
        # Process all pending audio files
        processed_count, failed_count = process_pending_audio_files()
        
        if processed_count > 0:
            messages.success(request, f"Successfully processed {processed_count} audio files.")
        
        if failed_count > 0:
            messages.warning(request, f"Failed to process {failed_count} audio files. Check logs for details.")
            
    except Exception as e:
        messages.error(request, f"Error during batch processing: {str(e)}")
    
    return redirect('staff_home')

@login_required
def view_audio_analysis(request):
    if request.user.user_type != '2':  # Restrict access to staff only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    return render(request, "staff_template/view_audio_analysis.html")

@login_required
def view_spectrograms(request, file_id):
    """
    View for displaying spectrograms and classified clips for a specific audio file
    """
    if request.user.user_type != '2':  # Restrict access to staff only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    
    try:
        # Get the audio file
        original_file = get_object_or_404(OriginalAudioFile, file_id=file_id)
        
        # Get all spectrograms for this file
        spectrograms = Spectrogram.objects.filter(audio_file=original_file)
        
        # Get all detected noise clips
        detected_noises = DetectedNoiseAudioFile.objects.filter(original_file=original_file)
        
        # Calculate total impulses
        total_impulses = sum(noise.saw_count for noise in detected_noises)
        
        # Get processing logs
        processing_logs = ProcessingLog.objects.filter(audio_file=original_file).order_by('-timestamp')
        
        # Get processing status
        processing_status = Database.objects.filter(audio_file=original_file).first()
        
        # Prepare data for the template
        clips_data = []
        for noise in detected_noises:
            # Find the corresponding spectrogram if it exists
            spec = spectrograms.filter(start_time=noise.start_time, end_time=noise.end_time).first()
            clips_data.append({
                'audio_clip': noise,
                'spectrogram': spec,
                'start_time': noise.start_time,
                'end_time': noise.end_time
            })
        
        # Get the full audio spectrogram if it exists
        full_spectrogram = spectrograms.filter(is_full_audio=True).first()
        
        context = {
            'original_file': original_file,
            'clips_data': clips_data,
            'full_spectrogram': full_spectrogram,
            'processing_logs': processing_logs,
            'processing_status': processing_status,
            'detected_noises': detected_noises,
            'total_impulses': total_impulses
        }
        
        return render(request, 'common/view_spectrograms.html', context)
    
    except Exception as e:
        messages.error(request, f"Error viewing spectrograms: {str(e)}")
        return redirect('staff_home')

@login_required
def view_spectrograms_list(request):
    """
    View to display a list of all audio files with their spectrograms for staff
    """
    if request.user.user_type != '2':  # Restrict access to staff only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    
    # Get all audio files
    audio_files = OriginalAudioFile.objects.all().order_by('-upload_date')
    
    # Get recent processing logs
    recent_logs = ProcessingLog.objects.all().order_by('-timestamp')[:20]
    
    # Handle search and filtering
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')
    
    if search_query:
        audio_files = audio_files.filter(audio_file_name__icontains=search_query)
    
    if status_filter:
        audio_files = audio_files.filter(database_entry__status=status_filter)
    
    if date_filter:
        # Parse date filter and apply
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_filter, '%Y-%m-%d')
            audio_files = audio_files.filter(upload_date__date=date_obj.date())
        except Exception as e:
            print(f"Error parsing date filter: {str(e)}")
    
    context = {
        'audio_files': audio_files,
        'recent_logs': recent_logs,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_filter': date_filter
    }
    
    return render(request, 'common/view_spectrograms.html', context)

@login_required
def download_excel(request, file_id):
    """
    View to download the Excel analysis file for a specific audio file
    """
    if request.user.user_type != '2':  # Restrict access to staff only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    
    # Get the audio file
    audio_file = get_object_or_404(OriginalAudioFile, file_id=file_id)
    
    # Check if Excel file exists
    if not audio_file.analysis_excel:
        messages.error(request, "Excel analysis file not found for this audio.")
        return redirect('staff_view_spectrograms', file_id=file_id)
    
    # Prepare the response with the Excel file
    response = HttpResponse(
        audio_file.analysis_excel.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(audio_file.analysis_excel.name)}"'
    
    return response

@login_required
def generate_excel_report(request, file_id=None):
    """
    View for manually generating Excel reports for processed audio files
    """
    if request.user.user_type != '2':  # Restrict access to staff only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    
    try:
        if file_id:
            # Generate Excel for a specific file
            from .excel_generator import generate_excel_report_for_processed_file
            audio_file = OriginalAudioFile.objects.get(file_id=file_id)
            
            # Check if the file has been processed
            db_entry = audio_file.database_entry.first()
            if not db_entry or db_entry.status != 'Processed':
                messages.warning(request, f"Cannot generate Excel report: File '{audio_file.audio_file_name}' is not fully processed.")
                return redirect('staff_home')
            
            excel_path = generate_excel_report_for_processed_file(file_id)
            if excel_path:
                messages.success(request, f"Excel report for '{audio_file.audio_file_name}' generated successfully.")
            else:
                messages.error(request, f"Failed to generate Excel report for '{audio_file.audio_file_name}'.")
        else:
            # Generate Excel for all processed files without Excel reports
            from .excel_generator import generate_excel_reports_for_processed_files
            success_count, failed_count = generate_excel_reports_for_processed_files()
            
            if success_count > 0:
                messages.success(request, f"Successfully generated {success_count} Excel reports.")
            
            if failed_count > 0:
                messages.warning(request, f"Failed to generate {failed_count} Excel reports. Check logs for details.")
            
            if success_count == 0 and failed_count == 0:
                messages.info(request, "No files need Excel reports generated.")
    
    except Exception as e:
        messages.error(request, f"Error generating Excel reports: {str(e)}")
    
    # Redirect back to the referring page or staff home
    return redirect(request.META.get('HTTP_REFERER', 'staff_home'))