from django.contrib import admin
from .models import AdminProfile, StaffProfile, CustomUser

# Register your models here.
admin.site.register(AdminProfile)
admin.site.register(StaffProfile)
admin.site.register(CustomUser)