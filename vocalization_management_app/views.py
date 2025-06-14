from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.forms import PasswordChangeForm
import logging
import os
from .audio_processing import update_audio_metadata, advanced_search_audio, handle_duplicate_file
from .tasks import process_pending_audio_files
import json
from .models import CustomUser, OriginalAudioFile, DetectedNoiseAudioFile, Spectrogram, Database, ProcessingLog, Zoo, AnimalTable, AnimalDetectionParameters
from .forms import AudioUploadForm, AnimalDetectionParametersForm, ZooForm, AnimalForm
from .google_drive_utils import extract_folder_id_from_url, is_valid_drive_url, process_drive_folder, CREDENTIALS_PATH, CLIENT_CONFIG

# Create a logger
logger = logging.getLogger(__name__)

@login_required
def check_drive_credentials(request):
    """
    Check if Google Drive API credentials exist and return the result as JSON.
    This endpoint is used by the frontend to determine whether to show setup instructions.
    """
    # We're now using client-side OAuth, so we always return true
    return JsonResponse({
        'credentials_exist': True,
        'client_id': CLIENT_CONFIG['web']['client_id']
    })

@login_required
def oauth2callback(request):
    """
    Handle the OAuth2 callback from Google.
    This view is called after the user authenticates with Google.
    """
    from .google_drive_utils import CLIENT_CONFIG, SCOPES, Flow
    
    # Get the authorization code from the request
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')
    
    if error:
        return JsonResponse({'success': False, 'error': error})
    
    if not code:
        return JsonResponse({'success': False, 'error': 'No authorization code received'})
    
    try:
        # Create a flow instance using client config
        flow = Flow.from_client_config(
            CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=CLIENT_CONFIG['web']['redirect_uris'][0]
        )
        
        # Exchange the authorization code for credentials
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Store the token in the session
        request.session['google_token'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # Return success page that will close the popup and notify the parent window
        return render(request, 'admin_template/oauth2_callback.html', {
            'success': True,
            'message': 'Successfully authenticated with Google Drive!'
        })
        
    except Exception as e:
        logger.error(f"Error in OAuth2 callback: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

def home(request):
    return redirect('login')

def loginPage(request):
    if request.user.is_authenticated:
        if request.user.user_type == '1':
            return redirect('admin_home')
        else:
            return redirect('staff_home')
    return render(request, "login.html")

def doLogin(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        
        if not username or not password:
            messages.error(request, "Please provide both username and password")
            return redirect('login')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            if user.user_type == '1':  # Admin
                return redirect('admin_home')
            else:  # Staff
                return redirect('staff_home')
        else:
            messages.error(request, "Invalid username or password")
            return redirect('login')
    
    return redirect('login')

def registerPage(request):
    return render(request, 'register.html')  

def doRegister(request):
    if request.method == "POST":
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        user_type = request.POST.get('user_type')

        # Check if passwords match
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect('register')

        # Check if email is already registered
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "Email is already registered.")
            return redirect('register')

        # **Set `username` as email to avoid UNIQUE constraint error**
        user = CustomUser.objects.create(
            username=email,
            email=email,
            full_name=full_name,
            password=make_password(password),
            user_type=user_type
        )
        user.save()

        messages.success(request, "Registration successful! You can now log in.")
        return redirect('login')
    else:
        return redirect('register')

def get_user_details(request):
    if request.user.is_authenticated:
        return HttpResponse(f"User: {request.user.email}, User Type: {request.user.user_type}")
    else:
        return HttpResponse("Please Login First")

def logout_user(request):
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect('login')

@login_required
def graphs(request):
    """
    View for displaying the graphs page with spectrograph and Fourier transform options.
    Only accessible to authenticated users.
    """
    return render(request, 'graphs.html')

@login_required
def get_graph_data(request):
    """
    API endpoint to get graph data based on the selected date and options.
    Returns spectrograph and/or Fourier transform data as requested.
    """
    date_str = request.GET.get('date')
    show_spectrograph = request.GET.get('spectrograph') == 'true'
    show_fourier = request.GET.get('fourier') == 'true'
    
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        audio_files = OriginalAudioFile.objects.filter(
            upload_date__date=selected_date
        )
        
        if not audio_files:
            return JsonResponse({'error': 'No audio files found for the selected date'})
            
        # For demonstration, we'll use the first audio file
        audio_file = audio_files[0]
        
        response_data = {}
        
        if show_spectrograph:
            # Get spectrogram data (you'll need to implement the actual audio processing)
            # This is a placeholder that should be replaced with actual spectrogram calculation
            response_data['spectrograph'] = {
                'frequencies': [],
                'times': [],
                'intensities': []
            }
            
        if show_fourier:
            # Get Fourier transform data (you'll need to implement the actual audio processing)
            # This is a placeholder that should be replaced with actual FFT calculation
            response_data['fourier'] = {
                'frequencies': [],
                'magnitudes': []
            }
            
        return JsonResponse(response_data)
        
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'})
    except Exception as e:
        return JsonResponse({'error': str(e)})

def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep user logged in after password change
            messages.success(request, "Your password has been changed successfully!")
            return redirect('staff_home')  # Redirect to staff home
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, "staff_template/change_password.html", {'form': form})

@login_required
def view_extracted_clips(request, file_id=None):
    """
    View to display extracted clips and their spectrograms
    """
    context = {}
    
    if file_id:
        # Get specific file and its clips
        original_file = get_object_or_404(OriginalAudioFile, file_id=file_id)
        context['original_file'] = original_file
        
        # Get full audio spectrogram
        full_spectrogram = original_file.spectrograms.filter(is_full_audio=True).first()
        context['full_spectrogram'] = full_spectrogram
        
        # Get all clip spectrograms for this file
        clip_spectrograms = original_file.spectrograms.filter(
            is_full_audio=False
        ).order_by('clip_start_time')
        
        context['clip_spectrograms'] = clip_spectrograms
        
        # Get processing status
        processing_status = original_file.database_entry.first()
        context['processing_status'] = processing_status
        
    else:
        # Get all processed files
        processed_files = OriginalAudioFile.objects.filter(
            database_entry__status="Processed"
        ).order_by('-upload_date')
        
        context['processed_files'] = processed_files
    
    return render(request, 'staff_template/view_clips.html', context)

@login_required
def view_interactive_spectrogram(request, file_id):
    """
    View for displaying the interactive spectrogram visualization with saw call timestamps
    """
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Get the audio file
    audio_file = get_object_or_404(OriginalAudioFile, pk=file_id)
    
    # Get all spectrograms for this file
    spectrograms = Spectrogram.objects.filter(audio_file=audio_file)
    
    # Get all detected noise clips
    detected_noises = DetectedNoiseAudioFile.objects.filter(original_file=audio_file)
    
    # Get processing logs
    processing_logs = ProcessingLog.objects.filter(audio_file=audio_file).order_by('-timestamp')
    
    # Get processing status
    processing_status = Database.objects.filter(audio_file=audio_file).first()
    
    # Calculate total impulses
    total_impulses = sum(noise.saw_count for noise in detected_noises)
    
    # Get the full audio spectrogram if it exists
    full_spectrogram = spectrograms.filter(is_full_audio=True).first()
    
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
    
    context = {
        'original_file': audio_file,
        'clips_data': clips_data,
        'full_spectrogram': full_spectrogram,
        'processing_logs': processing_logs,
        'processing_status': processing_status,
        'detected_noises': detected_noises,
        'total_impulses': total_impulses,
    }
    
    return render(request, 'common/interactive_spectrogram.html', context)

@login_required
def view_spectrograms(request, file_id):
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Get the audio file
    audio_file = get_object_or_404(OriginalAudioFile, pk=file_id)
    
    # Get all spectrograms for this file
    spectrograms = Spectrogram.objects.filter(audio_file=audio_file)
    
    # Get all detected noise clips
    detected_noises = DetectedNoiseAudioFile.objects.filter(original_file=audio_file)
    
    # Get processing logs
    processing_logs = ProcessingLog.objects.filter(audio_file=audio_file).order_by('-timestamp')
    
    # Get processing status
    processing_status = Database.objects.filter(audio_file=audio_file).first()
    
    # Calculate total impulses
    total_impulses = sum(noise.saw_count for noise in detected_noises)
    
    # Check if Excel file exists
    has_excel = bool(audio_file.analysis_excel)
    
    # Prepare chart data for visualization
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
    
    # If Excel file exists, read it to display in the page
    excel_data = None
    if audio_file.analysis_excel:
        try:
            import pandas as pd
            excel_path = audio_file.analysis_excel.path
            excel_data = pd.read_excel(excel_path).to_html(classes='table table-striped', index=False)
        except Exception as e:
            logger.error(f"Error reading Excel file: {str(e)}")
    
    # Prepare JSON-serializable data for the interactive spectrogram
    json_clips_data = []
    for clip in clips_data:
        # Convert times to seconds for JavaScript
        if hasattr(clip['start_time'], 'hour'):
            start_time_seconds = clip['start_time'].hour * 3600 + clip['start_time'].minute * 60 + clip['start_time'].second
            end_time_seconds = clip['end_time'].hour * 3600 + clip['end_time'].minute * 60 + clip['end_time'].second
        else:
            start_time_seconds = float(clip['start_time'])
            end_time_seconds = float(clip['end_time'])
        
        json_clips_data.append({
            'start_time': start_time_seconds,
            'end_time': end_time_seconds,
            'display_start': clip['display_start'],
            'display_end': clip['display_end'],
            'audio_clip': {
                'saw_count': clip['audio_clip'].saw_count,
                'detected_noise_file_path': clip['audio_clip'].detected_noise_file_path.url if hasattr(clip['audio_clip'], 'detected_noise_file_path') and clip['audio_clip'].detected_noise_file_path else None
            },
            'spectrogram': {
                'image': {
                    'url': clip['spectrogram'].image.url if clip['spectrogram'] and hasattr(clip['spectrogram'], 'image') and clip['spectrogram'].image else None
                }
            } if clip['spectrogram'] else None
        })
    
    context = {
        'original_file': audio_file,
        'clips_data': clips_data,
        'json_clips_data': json_clips_data,  # Add JSON-serializable data for the interactive spectrogram
        'full_spectrogram': full_spectrogram,
        'processing_logs': processing_logs,
        'processing_status': processing_status,
        'detected_noises': detected_noises,
        'total_impulses': total_impulses,
        'has_excel': has_excel,
        'excel_data': excel_data,
        'spectrograms': spectrograms,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data)
    }
    
    return render(request, 'common/view_spectrograms.html', context)

@login_required
def view_spectrograms_list(request):
    """
    View to display a list of all audio files with their spectrograms
    """
    if not request.user.is_authenticated:
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
            logger.error(f"Error parsing date filter: {str(e)}")
    
    context = {
        'audio_files': audio_files,
        'recent_logs': recent_logs,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_filter': date_filter
    }
    
    return render(request, 'common/view_spectrograms_list.html', context)


@login_required
def advanced_search(request):
    """
    Advanced search view that allows filtering by multiple criteria
    """
    # Get all zoos for the dropdown
    zoos = Zoo.objects.all()
    
    # Get animal types from the model choices
    animal_types = OriginalAudioFile.ANIMAL_CHOICES
    
    # Initialize with all audio files
    audio_files = OriginalAudioFile.objects.all().order_by('-upload_date')
    
    # Initialize search parameters dictionary
    search_params = {}
    
    # Check if this is a search request
    if request.method == 'GET' and 'search' in request.GET:
        # Extract search parameters from request
        search_query = request.GET.get('search_query', '')
        animal_type = request.GET.get('animal_type', '')
        zoo_id = request.GET.get('zoo', '')
        device_id = request.GET.get('device_id', '')
        upload_date_start = request.GET.get('upload_date_start', '')
        upload_date_end = request.GET.get('upload_date_end', '')
        recording_date_start = request.GET.get('recording_date_start', '')
        recording_date_end = request.GET.get('recording_date_end', '')
        
        # Add valid parameters to the search_params dictionary
        if search_query:
            search_params['search_query'] = search_query
        
        if animal_type:
            search_params['animal_type'] = animal_type
        
        if zoo_id:
            search_params['zoo'] = zoo_id
        
        if device_id:
            search_params['device_id'] = device_id
        
        # Parse and add date parameters
        try:
            if upload_date_start:
                search_params['upload_date_start'] = datetime.strptime(upload_date_start, '%Y-%m-%d')
            
            if upload_date_end:
                # Add one day to include the end date fully
                end_date = datetime.strptime(upload_date_end, '%Y-%m-%d') + timedelta(days=1)
                search_params['upload_date_end'] = end_date
            
            if recording_date_start:
                search_params['recording_date_start'] = datetime.strptime(recording_date_start, '%Y-%m-%d')
            
            if recording_date_end:
                # Add one day to include the end date fully
                end_date = datetime.strptime(recording_date_end, '%Y-%m-%d') + timedelta(days=1)
                search_params['recording_date_end'] = end_date
        except Exception as e:
            logger.error(f"Error parsing date parameters: {str(e)}")
            messages.error(request, f"Error with date format: {str(e)}")
        
        # Perform the search if we have any parameters
        if search_params:
            audio_files = advanced_search_audio(search_params)
            
            # Add a message about the search results
            result_count = audio_files.count()
            messages.info(request, f"Found {result_count} audio file(s) matching your search criteria.")
    
    # Prepare context for the template
    context = {
        'audio_files': audio_files,
        'zoos': zoos,
        'animal_types': animal_types,
        # Pass back the search parameters for form persistence
        'search_query': request.GET.get('search_query', ''),
        'animal_type': request.GET.get('animal_type', ''),
        'zoo_id': request.GET.get('zoo', ''),
        'device_id': request.GET.get('device_id', ''),
        'upload_date_start': request.GET.get('upload_date_start', ''),
        'upload_date_end': request.GET.get('upload_date_end', ''),
        'recording_date_start': request.GET.get('recording_date_start', ''),
        'recording_date_end': request.GET.get('recording_date_end', '')
    }
    
    return render(request, 'common/advanced_search.html', context)

@login_required
def view_analysis(request, file_id):
    """
    View to display detailed analysis and Excel data for a specific audio file
    """
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Get the audio file
    audio_file = get_object_or_404(OriginalAudioFile, file_id=file_id)
    
    # Get processing status
    processing_status = Database.objects.filter(audio_file=audio_file).first()
    
    # Get all detected noise clips
    detected_noises = DetectedNoiseAudioFile.objects.filter(original_file=audio_file).order_by('start_time')
    
    # Get processing logs
    processing_logs = ProcessingLog.objects.filter(audio_file=audio_file).order_by('-timestamp')
    
    # Calculate total impulses
    total_impulses = sum(noise.saw_count for noise in detected_noises)
    
    # Check if Excel file exists
    has_excel = bool(audio_file.analysis_excel)
    
    # Prepare chart data for visualization
    chart_labels = []
    chart_data = []
    for noise in detected_noises:
        # Format the start time for display
        if hasattr(noise.start_time, 'strftime'):
            # If it's a datetime.time object
            formatted_time = noise.start_time.strftime("%H:%M:%S")
        else:
            # If it's a float (seconds)
            hours, remainder = divmod(int(noise.start_time), 3600)
            minutes, seconds = divmod(remainder, 60)
            formatted_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        chart_labels.append(formatted_time)
        chart_data.append(noise.saw_count)
    
    # If Excel file exists, read it to display in the page
    excel_data = None
    if has_excel:
        try:
            import pandas as pd
            import io
            
            # Read the Excel file into a pandas DataFrame
            excel_file = audio_file.analysis_excel.read()
            df = pd.read_excel(io.BytesIO(excel_file))
            # Convert DataFrame to HTML table
            excel_data = df.to_html(classes='table table-striped', index=False)
        except Exception as e:
            messages.error(request, f"Error reading Excel file: {str(e)}")
    
    context = {
        'original_file': audio_file,
        'processing_status': processing_status,
        'detected_noises': detected_noises,
        'processing_logs': processing_logs,
        'total_impulses': total_impulses,
        'has_excel': has_excel,
        'excel_data': excel_data,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data)
    }
    
    return render(request, 'common/view_analysis.html', context)
    
def view_timelines(request):
    """
    View for displaying timeplots of saw calls over time.
    Allows users to filter by animal type, date range, and zoo.
    """
    # Get available animal types from model choices
    animal_types = OriginalAudioFile.ANIMAL_CHOICES
    
    # Get available zoos
    zoos = Zoo.objects.all()
    
    context = {
        'animal_types': animal_types,
        'zoos': zoos,
    }
    
    return render(request, 'common/view_timelines.html', context)


def download_excel(request, file_id):
    """
    View to download the Excel analysis file for a specific audio file
    """
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Get the audio file
    audio_file = get_object_or_404(OriginalAudioFile, file_id=file_id)
    
    # Check if Excel file exists
    if not audio_file.analysis_excel:
        messages.error(request, "Excel analysis file not found for this audio.")
        return redirect('view_spectrograms', file_id=file_id)
    
    # Prepare the response with the Excel file
    response = HttpResponse(
        audio_file.analysis_excel.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(audio_file.analysis_excel.name)}"'
    
    return response

@login_required
def upload_audio(request):
    """View for uploading audio files"""
    if request.method == 'POST':
        form = AudioUploadForm(request.POST, request.FILES)
        if form.is_valid():
            animal_type = form.cleaned_data['animal_type']
            zoo = form.cleaned_data['zoo']  # Zoo is now required in the form
            google_drive_url = form.cleaned_data.get('google_drive_url')
            uploaded_files = request.FILES.getlist('audio_files')
            
            # Track upload statistics
            upload_stats = {
                'total': len(uploaded_files),
                'processed': 0,
                'failed': 0,
                'duplicates': 0,
                'drive_processed': 0,
                'drive_failed': 0,
                'drive_duplicates': 0
            }
            
            # Process local file uploads
            for uploaded_file in uploaded_files:
                # Validate file format (.wav only)
                if not uploaded_file.name.lower().endswith('.wav'):
                    upload_stats['invalid_format'] = upload_stats.get('invalid_format', 0) + 1
                    continue
                
                try:
                    # Handle duplicate file detection and replacement
                    audio_file, is_duplicate, replaced_file_id = handle_duplicate_file(
                        new_file=uploaded_file,
                        animal_type=animal_type,
                        zoo=zoo
                    )
                    
                    # Add a message about the duplicate replacement if needed
                    if is_duplicate:
                        # Update the statistics to reflect the replacement
                        upload_stats['duplicates'] += 1
                        # Log the duplicate detection
                        logger.info(f"Duplicate file detected and replaced: {uploaded_file.name} (ID: {replaced_file_id})")
                    
                    # Update metadata for the file
                    file_path = audio_file.audio_file.path
                    update_audio_metadata(file_path, audio_file)
                    
                    # Track successful upload
                    upload_stats['processed'] += 1
                except Exception as e:
                    logger.error(f"Error uploading file {uploaded_file.name}: {str(e)}")
                    upload_stats['failed'] += 1
            
            # Process Google Drive folder if URL is provided
            if google_drive_url and is_valid_drive_url(google_drive_url):
                try:
                    # Extract folder ID from the URL
                    folder_id = extract_folder_id_from_url(google_drive_url)
                    
                    if folder_id:
                        # Get token from session if available
                        token_info = request.session.get('google_token')
                        
                        # Process the Google Drive folder
                        drive_stats = process_drive_folder(
                            folder_id=folder_id,
                            animal_type=animal_type,
                            zoo=zoo,
                            uploaded_by=request.user,
                            token_info=token_info
                        )
                        
                        # Check if authentication is required
                        if drive_stats.get('requires_auth', False):
                            # Store the form data in session for after authentication
                            request.session['pending_drive_upload'] = {
                                'folder_id': folder_id,
                                'animal_type': animal_type.pk if hasattr(animal_type, 'pk') else None,
                                'zoo': zoo.pk if hasattr(zoo, 'pk') else None,
                                'google_drive_url': google_drive_url
                            }
                            
                            # Return a response that will redirect to authentication
                            messages.info(request, "You need to authenticate with Google Drive first.")
                            return JsonResponse({
                                'success': False,
                                'requires_auth': True,
                                'auth_url': drive_stats['auth_url']
                            })
                        
                        # Update overall statistics with Google Drive results
                        upload_stats['drive_processed'] = drive_stats['processed']
                        upload_stats['drive_failed'] = drive_stats['failed']
                        upload_stats['drive_duplicates'] = drive_stats['duplicates']
                        upload_stats['total'] += drive_stats['total']
                        
                        # Log any errors from Google Drive processing
                        for error in drive_stats.get('errors', []):
                            logger.error(error)
                    else:
                        messages.error(request, "Could not extract folder ID from the provided Google Drive URL. Please check the URL and try again.")
                except Exception as e:
                    logger.error(f"Error processing Google Drive folder: {str(e)}")
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
                
                # Automatically process the uploaded files
                process_pending_audio_files()
                
                return redirect('upload_audio')
            else:
                if google_drive_url and not is_valid_drive_url(google_drive_url):
                    messages.error(request, "The provided Google Drive URL is invalid. Please check the URL and try again.")
                elif upload_stats.get('invalid_format', 0) > 0:
                    messages.error(request, f"No files were uploaded. {upload_stats['invalid_format']} file(s) were skipped because they were not in .wav format.")
                else:
                    messages.error(request, "No files were uploaded. Please try again.")
    else:
        form = AudioUploadForm()
    
    # Get all uploaded audio files for the current user
    audio_files = OriginalAudioFile.objects.all().order_by('-upload_date')
    
    context = {
        'form': form,
        'audio_files': audio_files,
    }
    return render(request, 'admin_template/upload_audio.html', context)


@login_required
def animal_detection_parameters_list(request):
    """View to list all animal detection parameters"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
        
    parameters = AnimalDetectionParameters.objects.all().order_by('-is_default', 'name')
    
    context = {
        'parameters': parameters,
        'page_title': 'Animal Detection Parameters'
    }
    
    return render(request, 'admin_template/animal_detection_parameters_list.html', context)


@login_required
def add_animal_detection_parameters(request):
    """View to add new animal detection parameters"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
    
    if request.method == 'POST':
        form = AnimalDetectionParametersForm(request.POST)
        if form.is_valid():
            # Save with the current user as creator
            parameters = form.save(commit=True, user=request.user)
            messages.success(request, f"Parameters for {parameters.name} created successfully.")
            return redirect('animal_detection_parameters_list')
    else:
        # Create form with default Amur Leopard values
        form = AnimalDetectionParametersForm(initial={
            'min_magnitude': 3500,
            'max_magnitude': 10000,
            'min_frequency': 15,
            'max_frequency': 300,
            'segment_duration': 0.1,
            'time_threshold': 5,
            'min_impulse_count': 3
        })
    
    context = {
        'form': form,
        'page_title': 'Add Animal Detection Parameters'
    }
    
    return render(request, 'admin_template/animal_detection_parameters_form.html', context)


@login_required
def edit_animal_detection_parameters(request, parameter_id):
    """View to edit existing animal detection parameters"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
    
    parameters = get_object_or_404(AnimalDetectionParameters, id=parameter_id)
    
    if request.method == 'POST':
        form = AnimalDetectionParametersForm(request.POST, instance=parameters)
        if form.is_valid():
            # Save with the current user as updater
            updated_parameters = form.save(commit=True, user=request.user)
            messages.success(request, f"Parameters for {updated_parameters.name} updated successfully.")
            return redirect('animal_detection_parameters_list')
    else:
        form = AnimalDetectionParametersForm(instance=parameters)
    
    context = {
        'form': form,
        'parameters': parameters,
        'page_title': f'Edit {parameters.name} Parameters'
    }
    
    return render(request, 'admin_template/animal_detection_parameters_form.html', context)


@login_required
def delete_animal_detection_parameters(request, parameter_id):
    """View to delete animal detection parameters"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
    
    parameters = get_object_or_404(AnimalDetectionParameters, id=parameter_id)
    
    # Don't allow deletion of the default parameters
    if parameters.is_default:
        messages.error(request, "Cannot delete the default parameters. Set another parameter set as default first.")
        return redirect('animal_detection_parameters_list')
    
    if request.method == 'POST':
        # Store name for the success message
        name = parameters.name
        parameters.delete()
        messages.success(request, f"Parameters for {name} deleted successfully.")
        return redirect('animal_detection_parameters_list')
    
    context = {
        'parameters': parameters,
        'page_title': f'Delete {parameters.name} Parameters'
    }
    
    return render(request, 'admin_template/animal_detection_parameters_delete.html', context)


# Zoo Management Views
@login_required
def zoo_list(request):
    """View to list all zoos"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
        
    zoos = Zoo.objects.all().order_by('zoo_name')
    
    context = {
        'zoos': zoos,
        'page_title': 'Zoo Management'
    }
    
    return render(request, 'admin_template/zoo_list.html', context)


@login_required
def add_zoo(request):
    """View to add a new zoo"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
    
    if request.method == 'POST':
        form = ZooForm(request.POST)
        if form.is_valid():
            zoo = form.save()
            messages.success(request, f"Zoo '{zoo.zoo_name}' created successfully.")
            return redirect('zoo_list')
    else:
        form = ZooForm()
    
    context = {
        'form': form,
        'page_title': 'Add Zoo'
    }
    
    return render(request, 'admin_template/zoo_form.html', context)


@login_required
def edit_zoo(request, zoo_id):
    """View to edit an existing zoo"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
    
    zoo = get_object_or_404(Zoo, zoo_id=zoo_id)
    
    if request.method == 'POST':
        form = ZooForm(request.POST, instance=zoo)
        if form.is_valid():
            updated_zoo = form.save()
            messages.success(request, f"Zoo '{updated_zoo.zoo_name}' updated successfully.")
            return redirect('zoo_list')
    else:
        form = ZooForm(instance=zoo)
    
    context = {
        'form': form,
        'zoo': zoo,
        'page_title': f'Edit {zoo.zoo_name}'
    }
    
    return render(request, 'admin_template/zoo_form.html', context)


@login_required
def delete_zoo(request, zoo_id):
    """View to delete a zoo"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
    
    zoo = get_object_or_404(Zoo, zoo_id=zoo_id)
    
    # Check if zoo has any animals
    if zoo.animals.exists():
        messages.error(request, f"Cannot delete zoo '{zoo.zoo_name}' because it has animals associated with it. Please remove the animals first.")
        return redirect('zoo_list')
    
    # Check if zoo has any audio files
    if zoo.original_audio.exists():
        messages.error(request, f"Cannot delete zoo '{zoo.zoo_name}' because it has audio files associated with it.")
        return redirect('zoo_list')
    
    if request.method == 'POST':
        zoo_name = zoo.zoo_name
        zoo.delete()
        messages.success(request, f"Zoo '{zoo_name}' deleted successfully.")
        return redirect('zoo_list')
    
    context = {
        'zoo': zoo,
        'page_title': f'Delete {zoo.zoo_name}'
    }
    
    return render(request, 'admin_template/zoo_delete.html', context)


# Animal Management Views
@login_required
def animal_list(request):
    """View to list all animals"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
        
    animals = AnimalTable.objects.all().order_by('species_name')
    
    context = {
        'animals': animals,
        'page_title': 'Animal Management'
    }
    
    return render(request, 'admin_template/animal_list.html', context)


@login_required
def add_animal(request):
    """View to add a new animal"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
    
    if request.method == 'POST':
        form = AnimalForm(request.POST)
        if form.is_valid():
            animal = form.save()
            messages.success(request, f"Animal '{animal.species_name}' created successfully.")
            return redirect('animal_list')
    else:
        form = AnimalForm()
    
    context = {
        'form': form,
        'page_title': 'Add Animal'
    }
    
    return render(request, 'admin_template/animal_form.html', context)


@login_required
def edit_animal(request, animal_id):
    """View to edit an existing animal"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
    
    animal = get_object_or_404(AnimalTable, animal_id=animal_id)
    
    if request.method == 'POST':
        form = AnimalForm(request.POST, instance=animal)
        if form.is_valid():
            updated_animal = form.save()
            messages.success(request, f"Animal '{updated_animal.species_name}' updated successfully.")
            return redirect('animal_list')
    else:
        form = AnimalForm(instance=animal)
    
    context = {
        'form': form,
        'animal': animal,
        'page_title': f'Edit {animal.species_name}'
    }
    
    return render(request, 'admin_template/animal_form.html', context)


@login_required
def delete_animal(request, animal_id):
    """View to delete an animal"""
    # Only admin users can access this page
    if request.user.user_type != '1':
        messages.error(request, "You do not have permission to access this page.")
        return redirect('staff_home')
    
    animal = get_object_or_404(AnimalTable, animal_id=animal_id)
    
    # Check if animal has any audio files
    if animal.original_audio.exists():
        messages.error(request, f"Cannot delete animal '{animal.species_name}' because it has audio files associated with it.")
        return redirect('animal_list')
    
    if request.method == 'POST':
        animal_name = animal.species_name
        animal.delete()
        messages.success(request, f"Animal '{animal_name}' deleted successfully.")
        return redirect('animal_list')
    
    context = {
        'animal': animal,
        'page_title': f'Delete {animal.species_name}'
    }
    
    return render(request, 'admin_template/animal_delete.html', context)
