from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
import logging
from .models import CustomUser, OriginalAudioFile, Database, ProcessingLog, DetectedNoiseAudioFile, Spectrogram, AdminProfile
from .forms import UserRegistrationForm, AudioUploadForm
from .audio_processing import update_audio_metadata, process_pending_audio_files, get_processing_status, handle_duplicate_file
from .tasks import process_pending_audio_files
from django.shortcuts import get_object_or_404
import json

# Configure logging
logger = logging.getLogger(__name__)

@login_required
def create_user(request):
    if request.user.user_type != '1':  # Only Admin can create users
        messages.error(request, "Access Denied! Only Admins can create new users.")
        return redirect('admin_home')

    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "New user created successfully!")
            return redirect('manage_staff')  
        else:
            messages.error(request, "Error creating user. Please check the form.")
    else:
        form = UserRegistrationForm()

    return render(request, "admin_template/create_user.html", {"form": form})

@login_required
def admin_home(request):
    """
    Admin home view showing dashboard statistics and audio files
    """
    if request.user.user_type != '1':  # Restrict access to admin only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')

    # Get processing status data
    status_data = get_processing_status()
    
    # Get pending files details
    pending_files_details = Database.objects.filter(
        status='Pending'
    ).select_related('audio_file').order_by('-audio_file__upload_date')
    
    # Get processing files details
    processing_files_details = Database.objects.filter(
        status='Processing'
    ).select_related('audio_file').order_by('-audio_file__upload_date')
    
    # Get recent processing logs
    recent_logs = ProcessingLog.objects.select_related('audio_file').order_by('-timestamp')[:10]
    
    # Get all audio files with processed status
    audio_files = OriginalAudioFile.objects.select_related('uploaded_by').prefetch_related(
        'database_entry'
    ).filter(database_entry__status='Processed').order_by('-upload_date')
    
    context = {
        'total_files': status_data['total'],
        'pending_files': status_data['pending'],
        'processing_files': status_data['processing'],
        'processed_files': status_data['processed'],
        'failed_files': status_data['failed'],
        'processor_status': status_data['processor_status'],
        'pending_files_details': pending_files_details,
        'processing_files_details': processing_files_details,
        'recent_logs': recent_logs,
        'audio_files': audio_files,
        'page_title': 'Admin Dashboard'
    }
    
    return render(request, 'admin_template/admin_home.html', context)


@login_required
def upload_audio(request):
    if not request.user.is_authenticated or request.user.user_type != '1':
        return redirect('login')
    
    # Get recent audio files for display
    audio_files = OriginalAudioFile.objects.all().order_by('-upload_date')[:10]
    
    if request.method == 'POST':
        form = AudioUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            # Get form data
            animal_type = form.cleaned_data['animal_type']
            zoo = form.cleaned_data['zoo']  # Zoo is now required in the form
            folder_upload = form.cleaned_data.get('folder_upload', False)
            google_drive_url = form.cleaned_data.get('google_drive_url')
            
            # Track upload statistics
            upload_stats = {
                'total': 0,
                'processed': 0,
                'failed': 0,
                'duplicates': 0,
                'invalid_format': 0,
                'drive_processed': 0,
                'drive_failed': 0,
                'drive_duplicates': 0
            }
            
            # Get files from request.FILES
            files = request.FILES.getlist('audio_files')
            upload_stats['total'] = len(files)
            
            # Process local file uploads if any files were selected
            if files:
                # Get or create admin profile
                try:
                    admin_profile = AdminProfile.objects.get(user=request.user)
                except AdminProfile.DoesNotExist:
                    # Create admin profile if it doesn't exist
                    admin_profile = AdminProfile.objects.create(user=request.user)
                
                # Process each file
                for audio_file in files:
                    # Validate file format (.wav only)
                    if not audio_file.name.lower().endswith('.wav'):
                        upload_stats['invalid_format'] += 1
                        continue
                    
                    try:
                        # Handle duplicate file detection and replacement
                        original_audio, is_duplicate, replaced_file_id = handle_duplicate_file(
                            new_file=audio_file,
                            animal_type=animal_type,
                            zoo=zoo,
                            uploaded_by=admin_profile
                        )
                        
                        # Create initial processing log if this is a new file (not a duplicate)
                        if not is_duplicate:
                            ProcessingLog.objects.create(
                                audio_file=original_audio,
                                timestamp=now(),
                                level='INFO',
                                message=f'Audio file "{ audio_file.name}" uploaded successfully.'
                            )
                        else:
                            # Track duplicate count
                            upload_stats['duplicates'] += 1
                            # Add a message about the duplicate replacement
                            logging.info(f"Duplicate file detected and replaced: {audio_file.name} (ID: {replaced_file_id})")
                        
                        # Update metadata
                        file_path = original_audio.audio_file.path
                        update_audio_metadata(file_path, original_audio)
                        
                        upload_stats['processed'] += 1
                        
                    except Exception as e:
                        logging.error(f"Error uploading file {audio_file.name}: {str(e)}")
                        messages.error(request, f"Error uploading {audio_file.name}: {str(e)}")
                        upload_stats['failed'] += 1
            
            # Process Google Drive folder if URL is provided
            from .google_drive_utils import is_valid_drive_url, extract_folder_id_from_url, process_drive_folder
            
            if google_drive_url and is_valid_drive_url(google_drive_url):
                try:
                    # Extract folder ID from the URL
                    folder_id = extract_folder_id_from_url(google_drive_url)
                    
                    if folder_id:
                        # Process the Google Drive folder
                        drive_stats = process_drive_folder(
                            folder_id=folder_id,
                            animal_type=animal_type,
                            zoo=zoo,
                            uploaded_by=request.user
                        )
                        
                        # Update overall statistics with Google Drive results
                        upload_stats['drive_processed'] = drive_stats['processed']
                        upload_stats['drive_failed'] = drive_stats['failed']
                        upload_stats['drive_duplicates'] = drive_stats['duplicates']
                        upload_stats['total'] += drive_stats['total']
                        
                        # Log any errors from Google Drive processing
                        for error in drive_stats.get('errors', []):
                            logging.error(error)
                    else:
                        messages.error(request, "Could not extract folder ID from the provided Google Drive URL. Please check the URL and try again.")
                except Exception as e:
                    logging.error(f"Error processing Google Drive folder: {str(e)}")
                    messages.error(request, f"Error processing Google Drive folder: {str(e)}")
            elif google_drive_url:
                messages.error(request, "The provided URL does not appear to be a valid Google Drive folder URL.")
            
            # Create success message with upload statistics
            total_processed = upload_stats['processed'] + upload_stats['drive_processed']
            
            if total_processed > 0:
                success_message = f"Successfully uploaded {total_processed} audio file(s). "
                
                # Add details about local file uploads
                if upload_stats['processed'] > 0:
                    success_message += f"{upload_stats['processed']} file(s) from local upload. "
                
                # Add details about Google Drive uploads
                if upload_stats['drive_processed'] > 0:
                    success_message += f"{upload_stats['drive_processed']} file(s) from Google Drive. "
                
                # Add details about duplicates
                total_duplicates = upload_stats['duplicates'] + upload_stats['drive_duplicates']
                if total_duplicates > 0:
                    success_message += f"{total_duplicates} duplicate file(s) were detected and replaced. "
                
                # Add details about invalid formats
                if upload_stats.get('invalid_format', 0) > 0:
                    success_message += f"{upload_stats['invalid_format']} file(s) were skipped (not .wav format). "
                
                # Add details about failures
                total_failed = upload_stats['failed'] + upload_stats['drive_failed']
                if total_failed > 0:
                    success_message += f"{total_failed} file(s) failed to upload due to errors."
                
                messages.success(request, success_message)
                
                # Trigger processing if there are valid files
                process_pending_audio_files()
            else:
                if google_drive_url and not is_valid_drive_url(google_drive_url):
                    messages.error(request, "The provided Google Drive URL is invalid. Please check the URL and try again.")
                elif upload_stats.get('invalid_format', 0) > 0:
                    messages.error(request, f"No files were uploaded. {upload_stats['invalid_format']} file(s) were skipped because they were not in .wav format.")
                elif not files and not google_drive_url:
                    messages.error(request, "No files were selected for upload and no Google Drive URL was provided.")
                else:
                    messages.warning(request, "No files were successfully uploaded. Please try again.")
            
            return redirect('upload_audio')
        else:
            messages.error(request, "Form validation failed. Please check your inputs.")
    else:
        form = AudioUploadForm()
    
    context = {
        'form': form,
        'audio_files': audio_files
    }
    
    return render(request, 'admin_template/upload_audio.html', context)


@login_required
def process_audio_files(request):
    """
    View for processing pending audio files
    """
    if request.user.user_type != '1':  # Restrict access to admin only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    
    # Get pending files count before processing
    pending_count = Database.objects.filter(status='Pending').count()
    
    if pending_count == 0:
        messages.info(request, "No pending audio files to process.")
        return redirect('admin_home')
    
    try:
        # Process all pending audio files
        processed_count, failed_count = process_pending_audio_files()
        
        if processed_count > 0:
            messages.success(request, f"Successfully processed {processed_count} audio files.")
        
        if failed_count > 0:
            messages.warning(request, f"Failed to process {failed_count} audio files. Check logs for details.")
            
    except Exception as e:
        messages.error(request, f"Error during batch processing: {str(e)}")
    
    return redirect('admin_home')


@login_required
def manage_staff(request):
    if request.user.user_type != '1':  # Restrict access to admin only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')

    staff_users = CustomUser.objects.filter(user_type='2')  # Fetch all staff users
    return render(request, "admin_template/manage_staff.html", {"staff_users": staff_users})


@login_required
def add_staff(request):
    """
    Add a new staff member
    """
    if request.user.user_type != '1':  # Restrict access to admin only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        # Validate inputs
        if not (full_name and email and password):
            messages.error(request, "All fields are required")
            return redirect('manage_staff')
        
        # Check if email already exists
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, f"User with email {email} already exists")
            return redirect('manage_staff')
        
        try:
            # Create a new user with staff privileges
            username = email.split('@')[0]  # Use part of email as username
            
            # Ensure username is unique
            base_username = username
            count = 1
            while CustomUser.objects.filter(username=username).exists():
                username = f"{base_username}{count}"
                count += 1
            
            # Create the user
            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                password=password,
                full_name=full_name,
                user_type='2'  # Staff user type
            )
            
            messages.success(request, f"Staff member {full_name} added successfully")
        except Exception as e:
            messages.error(request, f"Error adding staff member: {str(e)}")
    
    return redirect('manage_staff')


@login_required
def delete_staff(request, staff_id):
    """
    Delete a staff member
    """
    if request.user.user_type != '1':  # Restrict access to admin only
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    
    if request.method == 'POST':
        try:
            staff = CustomUser.objects.get(id=staff_id, user_type='2')
            
            # Prevent deleting yourself
            if staff.id == request.user.id:
                messages.error(request, "You cannot delete your own account")
                return redirect('manage_staff')
            
            staff_name = staff.full_name
            staff.delete()
            messages.success(request, f"Staff member {staff_name} removed successfully")
        except CustomUser.DoesNotExist:
            messages.error(request, "Staff member not found")
        except Exception as e:
            messages.error(request, f"Error removing staff member: {str(e)}")
    
    return redirect('manage_staff')

@login_required
def view_spectrograms(request, file_id):
    if not request.user.is_authenticated or request.user.user_type != '1':
        return redirect('login')
    
    # Get the audio file
    audio_file = get_object_or_404(OriginalAudioFile, pk=file_id)
    
    # Get all spectrograms for this file
    spectrograms = Spectrogram.objects.filter(audio_file=audio_file)
    
    # Get all detected noise clips
    detected_noises = DetectedNoiseAudioFile.objects.filter(original_audio=audio_file)
    
    # Get processing logs
    processing_logs = ProcessingLog.objects.filter(audio_file=audio_file).order_by('-timestamp')
    
    # Get processing status
    processing_status = Database.objects.filter(original_audio=audio_file).first()
    
    # Calculate total impulses
    total_impulses = sum(noise.saw_count for noise in detected_noises)
    
    # Prepare chart data
    chart_labels = []
    chart_data = []
    for noise in detected_noises:
        if hasattr(noise.start_time, 'strftime'):
            # If it's a datetime.time object
            chart_labels.append(noise.start_time.strftime("%H:%M:%S"))
        else:
            # If it's a float (seconds)
            hours, remainder = divmod(int(noise.start_time), 3600)
            minutes, seconds = divmod(remainder, 60)
            chart_labels.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        chart_data.append(noise.saw_count)
    
    # Prepare data for the template
    clips_data = []
    for noise in detected_noises:
        # Find the corresponding spectrogram if it exists
        # Handle both datetime.time and float formats for start/end times
        matching_specs = []
        for spec in spectrograms:
            # Convert times to seconds for comparison if needed
            noise_start = noise.start_time
            noise_end = noise.end_time
            spec_start = spec.clip_start_time
            spec_end = spec.clip_end_time
            
            # Convert datetime.time to seconds if needed
            if hasattr(noise_start, 'hour'):
                noise_start = noise_start.hour * 3600 + noise_start.minute * 60 + noise_start.second + noise_start.microsecond/1000000
            if hasattr(noise_end, 'hour'):
                noise_end = noise_end.hour * 3600 + noise_end.minute * 60 + noise_end.second + noise_end.microsecond/1000000
            if hasattr(spec_start, 'hour'):
                spec_start = spec_start.hour * 3600 + spec_start.minute * 60 + spec_start.second + spec_start.microsecond/1000000
            if hasattr(spec_end, 'hour'):
                spec_end = spec_end.hour * 3600 + spec_end.minute * 60 + spec_end.second + spec_end.microsecond/1000000
            
            # Compare as floats
            if abs(float(noise_start) - float(spec_start)) < 0.1 and abs(float(noise_end) - float(spec_end)) < 0.1:
                matching_specs.append(spec)
        
        spec = matching_specs[0] if matching_specs else None
        
        # Format display times
        if hasattr(noise.start_time, 'strftime'):
            display_start = noise.start_time.strftime("%H:%M:%S")
            display_end = noise.end_time.strftime("%H:%M:%S")
        else:
            # Convert seconds to formatted time string
            start_hours, start_remainder = divmod(int(noise.start_time), 3600)
            start_minutes, start_seconds = divmod(start_remainder, 60)
            display_start = f"{start_hours:02d}:{start_minutes:02d}:{start_seconds:02d}"
            
            end_hours, end_remainder = divmod(int(noise.end_time), 3600)
            end_minutes, end_seconds = divmod(end_remainder, 60)
            display_end = f"{end_hours:02d}:{end_minutes:02d}:{end_seconds:02d}"
        
        clips_data.append({
            'audio_clip': noise,
            'spectrogram': spec,
            'start_time': noise.start_time,
            'end_time': noise.end_time,
            'display_start': display_start,
            'display_end': display_end
        })
    
    # Get the full audio spectrogram if it exists
    full_spectrogram = spectrograms.filter(is_full_audio=True).first()
    
    context = {
        'audio_file': audio_file,
        'clips_data': clips_data,
        'full_spectrogram': full_spectrogram,
        'processing_logs': processing_logs,
        'processing_status': processing_status,
        'detected_noises': detected_noises,
        'total_impulses': total_impulses,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data)
    }
    
    return render(request, 'admin_template/view_spectrograms.html', context)

@login_required
def generate_excel_report(request, file_id=None):
    """
    View for manually generating Excel reports for processed audio files
    """
    if request.user.user_type not in ['1', '2']:  # Restrict access to admin and staff
        messages.error(request, "You do not have permission to access this page.")
        return redirect('login')
    
    try:
        if file_id:
            # Generate Excel for a specific file
            from .excel_generator import generate_excel_report_for_processed_file
            audio_file = OriginalAudioFile.objects.get(pk=file_id)
            
            # Check if the file has been processed
            db_entry = audio_file.database_entry.first()
            if not db_entry or db_entry.status != 'Processed':
                messages.warning(request, f"Cannot generate Excel report: File '{audio_file.audio_file_name}' is not fully processed.")
                return redirect('admin_home')
            
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
    
    # Redirect back to the referring page or admin home
    return redirect(request.META.get('HTTP_REFERER', 'admin_home'))