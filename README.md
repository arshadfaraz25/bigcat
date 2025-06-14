# Felidetect - Vocalization Management System

A Django-based web application for managing and analyzing felid vocalizations. This system helps researchers and staff members process audio recordings to detect and analyze specific vocalization patterns.

## Features

- Audio file upload and management
- Automatic processing of audio files
- Spectrogram generation and visualization
- Detection of specific vocalization patterns
- User management with role-based access control
- Real-time processing status updates
- Detailed logging system

## Prerequisites

- Python 3.11 or higher
- pip (Python package installer)
- Virtual environment (recommended)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/your-username/Felidetect.git
cd Felidetect/vocalization_management_system
```

2. Create and activate a virtual environment:
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create necessary directories:
```bash
# The following directories will be created automatically when needed:
# media/audio_files/
# media/spectrograms/
# media/waveforms/
# media/processed_audio/
```

5. Set up the database:
```bash
python manage.py makemigrations
python manage.py migrate
```

6. Create a superuser:
```bash
python manage.py createsuperuser
```

7. Run the development server:
```bash
python manage.py runserver
```

The application will be available at `http://127.0.0.1:8000/`

## Usage

1. Log in with your admin credentials
2. Upload audio files through the upload interface
3. View processing status and results in real-time
4. Access spectrograms and detected vocalizations
5. Manage staff accounts and permissions

## Project Structure

- `vocalization_management_app/` - Main application directory
  - `templates/` - HTML templates
  - `static/` - Static files (CSS, JS, etc.)
  - `models.py` - Database models
  - `views.py` - View functions
  - `audio_processing.py` - Audio processing logic

## Contributing

1. Fork the repository
2. Create a new branch for your feature
3. Commit your changes
4. Push to your branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
