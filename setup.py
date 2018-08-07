import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='django_auto_rollback',
    version='0.0.1',
    author='Aleksey Yakovlev',
    author_email='a_yakovlev@gcore.lu',
    description='Test package to automate django rollback',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://bitbucket.gcore.lu/scm/~aleksey.yakovlev_gcore.lu/django-auto-rollback',
    packages=setuptools.find_packages(),
    classifiers=(
        'Programming Language :: Python :: 3',
        'License :: WTFPL License',
        'Operating System :: OS Independent',
        'Framework :: Django :: 1.11',
    ),
    install_requires=[
        'GitPython>=2.1.8',
        'django==1.11'
    ],
)
