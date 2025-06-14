from django.urls import path
from . import views, adminViews, staffViews, api_views

urlpatterns = [
    # Authentication URLs
    path('', views.loginPage, name="login"),
    path('doLogin/', views.doLogin, name="doLogin"),
    path('logout_user/', views.logout_user, name="logout_user"),
    path('register/', views.registerPage, name="register"),
    path('doRegister/', views.doRegister, name="doRegister"),
    
    # Admin URLs
    path('admin_home/', adminViews.admin_home, name="admin_home"),
    path('upload_audio/', adminViews.upload_audio, name="upload_audio"),
    path('process_audio_files/', adminViews.process_audio_files, name="process_audio_files"),
    path('generate_excel_reports/', adminViews.generate_excel_report, name="generate_excel_reports"),
    path('generate_excel_report/<int:file_id>/', adminViews.generate_excel_report, name="generate_excel_report"),
    path('manage_staff/', adminViews.manage_staff, name="manage_staff"),
    path('add_staff/', adminViews.add_staff, name="add_staff"),
    path('delete_staff/<int:staff_id>/', adminViews.delete_staff, name="delete_staff"),
    path('view_spectrograms/', views.view_spectrograms_list, name="view_spectrograms_list"),
    path('view_spectrograms/<int:file_id>/', views.view_spectrograms, name="view_spectrograms"),
    # Removed interactive_spectrogram route - merged into view_spectrograms
    path('advanced_search/', views.advanced_search, name="advanced_search"),
    path('graphs/', views.graphs, name="graphs"),
    path('api/graph-data/', views.get_graph_data, name="get_graph_data"),
    path('view_timelines/', views.view_timelines, name='view_timelines'),
    path('view_analysis/<int:file_id>/', views.view_analysis, name="view_analysis"),
    path('download_excel/<int:file_id>/', views.download_excel, name="download_excel"),
    
    # Staff URLs
    path('staff_home/', staffViews.staff_home, name="staff_home"),
    path('staff/process_audio_files/', staffViews.process_audio_files, name="staff_process_audio_files"),
    path('staff/generate_excel_reports/', staffViews.generate_excel_report, name="staff_generate_excel_reports"),
    path('staff/generate_excel_report/<int:file_id>/', staffViews.generate_excel_report, name="staff_generate_excel_report"),
    path('staff/view_audio_analysis/', staffViews.view_audio_analysis, name="view_audio_analysis"),
    path('staff/view_spectrograms/', staffViews.view_spectrograms_list, name="staff_view_spectrograms_list"),
    path('staff/view_spectrograms/<int:file_id>/', staffViews.view_spectrograms, name="staff_view_spectrograms"),
    # Removed interactive_spectrogram route - merged into view_spectrograms
    path('staff/view_analysis/<int:file_id>/', views.view_analysis, name="staff_view_analysis"),
    path('staff/download_excel/<int:file_id>/', staffViews.download_excel, name="staff_download_excel"),
    
    # API URLs for background processing
    path('api/start_processor/', api_views.start_processor, name="api_start_processor"),
    path('api/stop_processor/', api_views.stop_processor, name="api_stop_processor"),
    path('api/get_status/', api_views.get_status, name="api_get_status"),
    path('check_drive_credentials/', views.check_drive_credentials, name="check_drive_credentials"),
    path('oauth2callback/', views.oauth2callback, name="oauth2callback"),
    path('api/get_file_logs/<int:file_id>/', api_views.get_file_logs, name="api_get_file_logs"),
    path('api/get_recent_logs/', api_views.get_recent_logs, name="api_get_recent_logs"),
    path('api/get_processed_files/', api_views.get_processed_files, name="api_get_processed_files"),
    path('api/get_timeplot_data/', api_views.get_timeplot_data, name="api_get_timeplot_data"),
    
    # Animal Detection Parameters URLs
    path('animal_detection_parameters/', views.animal_detection_parameters_list, name="animal_detection_parameters_list"),
    path('animal_detection_parameters/add/', views.add_animal_detection_parameters, name="add_animal_detection_parameters"),
    path('animal_detection_parameters/edit/<int:parameter_id>/', views.edit_animal_detection_parameters, name="edit_animal_detection_parameters"),
    path('animal_detection_parameters/delete/<int:parameter_id>/', views.delete_animal_detection_parameters, name="delete_animal_detection_parameters"),
    
    # Zoo Management URLs
    path('zoos/', views.zoo_list, name="zoo_list"),
    path('zoos/add/', views.add_zoo, name="add_zoo"),
    path('zoos/edit/<int:zoo_id>/', views.edit_zoo, name="edit_zoo"),
    path('zoos/delete/<int:zoo_id>/', views.delete_zoo, name="delete_zoo"),
    
    # Animal Management URLs
    path('animals/', views.animal_list, name="animal_list"),
    path('animals/add/', views.add_animal, name="add_animal"),
    path('animals/edit/<int:animal_id>/', views.edit_animal, name="edit_animal"),
    path('animals/delete/<int:animal_id>/', views.delete_animal, name="delete_animal"),
]
