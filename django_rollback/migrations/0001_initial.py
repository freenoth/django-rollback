# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2018-09-05 10:51
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AppsState',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('commit', models.CharField(help_text='Hex sha of commit.', max_length=40)),
                ('migrations', models.TextField(help_text='JSON text for current top migrations [(id, app, name), ...] for app state')),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
