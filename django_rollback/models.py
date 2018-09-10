from django.db import models


class AppsState(models.Model):
    commit = models.CharField(max_length=40, help_text='Hex sha of commit.')
    migrations = models.TextField(help_text='JSON text for current top migrations [(id, app, name), ...]'
                                            ' for app state')
    timestamp = models.DateTimeField(auto_now_add=True)
