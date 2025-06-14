from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class VocalizationManagementAppConfig(AppConfig):
    name = 'vocalization_management_app'
    
    def ready(self):
        """
        Start the background audio processor when Django starts
        This method is called once when Django starts
        """
        # Initialize storage directories
        self.initialize_storage_directories()
        
        # Only start the processor in the main process, not in management commands
        import sys
        if 'runserver' in sys.argv:
            logger.info("Starting background audio processor...")
            try:
                # Import here to avoid circular imports
                from .tasks import start_background_processor
                start_background_processor()
                logger.info("Background audio processor started successfully")
            except Exception as e:
                logger.error(f"Failed to start background audio processor: {str(e)}")
    
    def initialize_storage_directories(self):
        """
        Create the necessary directory structure for audio file storage
        """
        import os
        from django.conf import settings
        
        # Create the base storage directory
        storage_base = os.path.join(settings.MEDIA_ROOT, 'storage')
        if not os.path.exists(storage_base):
            os.makedirs(storage_base)
            logger.info(f"Created storage base directory at {storage_base}")
            
        # Create the temp directory for initial uploads
        temp_dir = os.path.join(storage_base, 'temp')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            logger.info(f"Created temporary upload directory at {temp_dir}")
