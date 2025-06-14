from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.text import slugify
from .models import CustomUser, OriginalAudioFile, AnimalDetectionParameters, Zoo, AnimalTable

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    user_type = forms.ChoiceField(choices=CustomUser.USER_TYPE_CHOICES, required=True, label="User Role")

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password1', 'password2', 'user_type']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = self.cleaned_data['user_type']
        if commit:
            user.save()
        return user

class AudioUploadForm(forms.Form):
    # Use a regular FileField without the multiple attribute
    # The multiple file handling will be done in the view
    audio_files = forms.FileField(
        widget=forms.FileInput(attrs={'accept': '.wav'}),
        required=False,
        label="Select Audio Files",
        help_text="Select audio files to upload (.wav format only)"
    )
    folder_upload = forms.BooleanField(
        required=False,
        label="Upload Folder",
        help_text="Check this to upload an entire folder of audio files"
    )
    google_drive_url = forms.URLField(
        required=False,
        label="Google Drive Folder URL",
        help_text="Enter a Google Drive folder URL to import audio files"
    )
    # Dynamically fetch animal choices from AnimalTable
    def __init__(self, *args, **kwargs):
        super(AudioUploadForm, self).__init__(*args, **kwargs)
        # Get all animals from AnimalTable and format as choices
        animal_choices = [(animal.species_name.lower().replace(' ', '_'), animal.species_name) 
                         for animal in AnimalTable.objects.all()]
        # Add default choices if no animals exist in database
        if not animal_choices:
            animal_choices = OriginalAudioFile.ANIMAL_CHOICES
        self.fields['animal_type'].choices = animal_choices
    
    animal_type = forms.ChoiceField(
        choices=[],  # Will be populated in __init__
        required=True,
        label="Animal Type"
    )
    zoo = forms.ModelChoiceField(
        queryset=Zoo.objects.all(),
        required=True,
        label="Zoo",
        empty_label="Select Zoo"
    )

class AnimalDetectionParametersForm(forms.ModelForm):
    """Form for creating and editing animal detection parameters"""
    
    class Meta:
        model = AnimalDetectionParameters
        fields = [
            'name', 'min_magnitude', 'max_magnitude', 'min_frequency', 
            'max_frequency', 'segment_duration', 'time_threshold', 
            'min_impulse_count', 'is_default'
        ]
        widgets = {
            'min_magnitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '100'}),
            'max_magnitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '100'}),
            'min_frequency': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
            'max_frequency': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
            'segment_duration': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'time_threshold': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'min_impulse_count': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
        }
        labels = {
            'min_magnitude': 'Minimum Magnitude',
            'max_magnitude': 'Maximum Magnitude',
            'min_frequency': 'Minimum Frequency (Hz)',
            'max_frequency': 'Maximum Frequency (Hz)',
            'segment_duration': 'Segment Duration (seconds)',
            'time_threshold': 'Time Threshold (seconds)',
            'min_impulse_count': 'Minimum Impulse Count',
            'is_default': 'Use as Default Parameters',
        }
        help_texts = {
            'min_magnitude': 'Minimum magnitude threshold for detection (default: 3500)',
            'max_magnitude': 'Maximum magnitude threshold for detection (default: 10000)',
            'min_frequency': 'Minimum frequency in Hz (default: 15)',
            'max_frequency': 'Maximum frequency in Hz (default: 300)',
            'segment_duration': 'Duration of each segment in seconds (default: 0.1)',
            'time_threshold': 'Time threshold for merging events in seconds (default: 5)',
            'min_impulse_count': 'Minimum number of impulses to consider a valid saw call (default: 3)',
            'is_default': 'If checked, these parameters will be used as the default for processing',
        }
    
    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        # Generate slug from name if not provided
        if not instance.slug:
            instance.slug = slugify(instance.name)
        # Set created_by if provided
        if user:
            instance.created_by = user
        if commit:
            instance.save()
        return instance


class ZooForm(forms.ModelForm):
    """Form for creating and editing zoos"""
    
    class Meta:
        model = Zoo
        fields = ['zoo_name', 'location', 'contact_email']
        widgets = {
            'zoo_name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'zoo_name': 'Zoo Name',
            'location': 'Location',
            'contact_email': 'Contact Email',
        }
        help_texts = {
            'zoo_name': 'Name of the zoo or research facility',
            'location': 'Physical location of the zoo',
            'contact_email': 'Primary contact email for the zoo',
        }


class AnimalForm(forms.ModelForm):
    """Form for creating and editing animals"""
    
    class Meta:
        model = AnimalTable
        fields = ['species_name', 'zoo']
        widgets = {
            'species_name': forms.TextInput(attrs={'class': 'form-control'}),
            'zoo': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'species_name': 'Species Name',
            'zoo': 'Zoo',
        }
        help_texts = {
            'species_name': 'Name of the animal species (e.g., Amur Leopard, Amur Tiger)',
            'zoo': 'Zoo where this animal is located',
        }