from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.core.validators import FileExtensionValidator


# Custom User Model with Role-Based Access Control
class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ('1', 'Admin'),
        ('2', 'Staff'),
    )
    user_type = models.CharField(max_length=1, choices=USER_TYPE_CHOICES, default='2')
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, default="User")

    def __str__(self):
        return self.email


# Admin Profile Model
class AdminProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.email


# Staff Profile Model
class StaffProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    department = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.email


# Zoo Information Table
class Zoo(models.Model):
    zoo_id = models.AutoField(primary_key=True)
    zoo_name = models.CharField(max_length=100, unique=True, db_index=True)  # Add index for zoo name searches
    location = models.CharField(max_length=255, blank=True, null=True)
    contact_email = models.EmailField(unique=True)

    # Enable the index for zoo_name to improve query performance
    class Meta:
        indexes = [
            models.Index(fields=['zoo_name'])
        ]
    def __str__(self):
        return self.zoo_name


# Animal Table
class AnimalTable(models.Model):
    animal_id = models.AutoField(primary_key=True)
    species_name = models.CharField(max_length=50, unique=True)
    zoo = models.ForeignKey(Zoo, on_delete=models.CASCADE, related_name="animals")

    def __str__(self):
        return self.species_name


def audio_file_path(instance, filename):
    """
    Function to generate the upload path for audio files.
    Initially stores files in a temporary location.
    The files will be moved to their proper location after metadata extraction.
    """
    # Create a clean filename with animal type prefix
    clean_filename = f"{instance.animal_type}_{filename}"
    
    # Store initially in a temporary location
    # Files will be moved to a date-based structure after metadata extraction
    return f'storage/temp/{clean_filename}'


class OriginalAudioFile(models.Model):
    ANIMAL_CHOICES = [
        ('amur_leopard', 'Amur Leopard'),
        ('amur_tiger', 'Amur Tiger'),
    ]
    ZOO_CHOICES = [
        ('Breadsly_zoo', 'Breadsly Zoo'),
    ]

    file_id = models.AutoField(primary_key=True)
    audio_file = models.FileField(
        upload_to=audio_file_path,
        validators=[FileExtensionValidator(allowed_extensions=['wav'])],
        max_length=255
    )
    audio_file_name = models.CharField(max_length=255, db_index=True)  # Add index for faster filename searches
    recording_date = models.DateTimeField(blank=True, null=True, db_index=True)  # Add index for date range queries
    animal_type = models.CharField(max_length=20, choices=ANIMAL_CHOICES, db_index=True)  # Add index for filtering by animal type
    animal = models.ForeignKey(AnimalTable, on_delete=models.CASCADE, related_name="original_audio", blank=True, null=True)
    zoo = models.ForeignKey(Zoo, on_delete=models.CASCADE, related_name="original_audio", choices=ZOO_CHOICES, blank=True, null=True)
    file_size_mb = models.FloatField(blank=True, null=True)
    upload_date = models.DateTimeField(default=now, db_index=True)  # Add index for date range queries and sorting
    uploaded_by = models.ForeignKey(AdminProfile, on_delete=models.CASCADE, related_name="uploaded_audio", blank=True, null=True)
    analysis_excel = models.FileField(upload_to='analysis_excel/', null=True, blank=True)
    duration_seconds = models.FloatField(blank=True, null=True, default=0.0)
    duration = models.CharField(max_length=20, blank=True, null=True)
    sample_rate = models.IntegerField(blank=True, null=True)
    
    class Meta:
        # Add composite indexes for common search patterns
        indexes = [
            models.Index(fields=['animal_type', 'upload_date']),
            models.Index(fields=['recording_date', 'animal_type']),
        ]
    
    def __str__(self):
        return f"{self.animal_type} - {self.audio_file_name}"

    def save(self, *args, **kwargs):
        if not self.file_size_mb and self.audio_file:
            # Set file size in MB
            self.file_size_mb = self.audio_file.size / (1024 * 1024)
        super().save(*args, **kwargs)


# Processed & Reduced Audio File Table
# class ProcessedAudioFile(models.Model):
#     file_id = models.AutoField(primary_key=True)
#     audio_file_name = models.CharField(max_length=100)
#     recording_date = models.DateTimeField()
#     original_file = models.ForeignKey(OriginalAudioFile, on_delete=models.CASCADE, related_name="processed_audio")
#     file_size_mb = models.FloatField()
#     processed_by = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, null=True, blank=True)
#     upload_date = models.DateTimeField(default=now)

#     def __str__(self):
#         return f"Processed: {self.audio_file_name}"


# Detected Noise in Audio Files
class DetectedNoiseAudioFile(models.Model):
    detected_noise_file_id = models.AutoField(primary_key=True)
    original_file = models.ForeignKey(OriginalAudioFile, on_delete=models.CASCADE, related_name="detected_noises_manual")
    detected_noise_file_path = models.CharField(max_length=255, blank=True, null=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    saw_count = models.IntegerField()
    saw_call_count = models.IntegerField()
    file_size_mb = models.FloatField(blank=True, null=True)
    upload_date = models.DateTimeField(default=now)
    frequency = models.FloatField(blank=True, null=True)  # Frequency in Hz
    magnitude = models.FloatField(blank=True, null=True)  # Magnitude of the detected call
    noise_verified = models.BooleanField(default=True)  # Whether this noise is verified

    # Automatically determine if the noise should be verified
    def save(self, *args, **kwargs):
        self.noise_verified = self.saw_count > 0 or self.saw_call_count > 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Detected Noise: {self.detected_noise_file_path}"
    
# Auto Detected Noise in Audio Files
class AutoDetectedNoiseAudioFile(models.Model):
    detected_noise_file_id = models.AutoField(primary_key=True)
    original_file = models.ForeignKey(OriginalAudioFile, on_delete=models.CASCADE, related_name="detected_noises_auto")
    detected_noise_file_path = models.CharField(max_length=255)
    start_time = models.TimeField()
    end_time = models.TimeField()
    saw_count = models.IntegerField()
    saw_call_count = models.IntegerField()
    file_size_mb = models.FloatField()
    upload_date = models.DateTimeField(default=now)
    noise_verified = True

    def __str__(self):
        return f"Auto Detected Noise: {self.detected_noise_file_path}"


# Spectrogram Table
class Spectrogram(models.Model):
    audio_file = models.ForeignKey(OriginalAudioFile, on_delete=models.CASCADE, related_name='spectrograms')
    image_path = models.ImageField(upload_to='spectrograms/')
    generated_by = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_full_audio = models.BooleanField(default=False)
    clip_start_time = models.FloatField(null=True, blank=True)
    clip_end_time = models.FloatField(null=True, blank=True)

    def __str__(self):
        if self.is_full_audio:
            return f"Full Spectrogram - {self.audio_file.audio_file_name}"
        return f"Clip Spectrogram - {self.audio_file.audio_file_name} ({self.clip_start_time:.2f}s - {self.clip_end_time:.2f}s)"


# Waveform Table
class Waveform(models.Model):
    audio_file = models.ForeignKey(OriginalAudioFile, on_delete=models.CASCADE, related_name='waveforms')
    image_path = models.ImageField(upload_to='waveforms/')
    generated_by = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Waveform for {self.audio_file.audio_file_name}"
    
# Fourier Transform Table
class STFT(models.Model):
    audio_file = models.ForeignKey(OriginalAudioFile, on_delete=models.CASCADE, related_name='stfts')
    image_path = models.ImageField(upload_to='stfts/')
    generated_by = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Fourier Transform for {self.audio_file.audio_file_name}"


# Audio Processing Table (Processes Audio Files)
class AudioProcessor(models.Model):
    audio_file = models.ForeignKey(OriginalAudioFile, on_delete=models.CASCADE, related_name='processing_results')
    processed_by = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, null=True, blank=True)
    saw_count = models.IntegerField(default=0)
    saw_call_count = models.IntegerField(default=0)
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Processed {self.audio_file.audio_file_name}"


# Processing Log Model
class ProcessingLog(models.Model):
    LOG_LEVELS = (
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('SUCCESS', 'Success'),
    )
    
    audio_file = models.ForeignKey(OriginalAudioFile, on_delete=models.CASCADE, related_name='processing_logs')
    message = models.TextField()
    level = models.CharField(max_length=10, choices=LOG_LEVELS, default='INFO')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.get_level_display()} - {self.timestamp}: {self.message[:50]}"


# Database Model (Metadata & Processing Status)
class Database(models.Model):
    audio_file = models.ForeignKey(OriginalAudioFile, on_delete=models.CASCADE, related_name='database_entry')
    status = models.CharField(max_length=20, choices=[
        ('Pending', 'Pending'), 
        ('Processing', 'Processing'), 
        ('Processed', 'Processed'),
        ('Failed', 'Failed')
    ], default='Pending', db_index=True)  # Add index for status filtering
    processed_by = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)  # Add index for date filtering
    processing_start_time = models.DateTimeField(null=True, blank=True)
    processing_end_time = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status', 'uploaded_at']),  # Composite index for common query pattern
        ]

    def __str__(self):
        return f"Database entry for {self.audio_file.audio_file_name}"


# Animal Detection Parameters Model
class AnimalDetectionParameters(models.Model):
    """Stores the parameters used for detecting saw calls for different animal types"""
    name = models.CharField(max_length=100, unique=True, help_text="Name of the animal type (e.g., 'Amur Leopard')")
    slug = models.SlugField(max_length=100, unique=True, help_text="URL-friendly identifier (e.g., 'amur_leopard')")
    min_magnitude = models.FloatField(default=3500, help_text="Minimum magnitude threshold for detection")
    max_magnitude = models.FloatField(default=10000, help_text="Maximum magnitude threshold for detection")
    min_frequency = models.FloatField(default=15, help_text="Minimum frequency in Hz")
    max_frequency = models.FloatField(default=300, help_text="Maximum frequency in Hz")
    segment_duration = models.FloatField(default=0.1, help_text="Duration of each segment in seconds")
    time_threshold = models.FloatField(default=5, help_text="Time threshold for merging events in seconds")
    min_impulse_count = models.IntegerField(default=3, help_text="Minimum number of impulses to consider a valid saw call")
    is_default = models.BooleanField(default=False, help_text="Whether this is the default parameter set")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_parameters')
    
    class Meta:
        verbose_name = "Animal Detection Parameters"
        verbose_name_plural = "Animal Detection Parameters"
    
    def __str__(self):
        return f"{self.name} Parameters"
    
    def save(self, *args, **kwargs):
        # Ensure only one default parameter set exists
        if self.is_default:
            AnimalDetectionParameters.objects.filter(is_default=True).update(is_default=False)
        # If no default exists, make this the default
        elif not AnimalDetectionParameters.objects.filter(is_default=True).exists():
            self.is_default = True
        super().save(*args, **kwargs)