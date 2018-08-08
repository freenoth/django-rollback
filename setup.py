import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='django_rollback',
    version='0.1.1',
    author='Aleksey Yakovlev',
    author_email='nothscr@gmail.com',
    description='Package to automate django rollback',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/freenoth/django-rollback',
    packages=setuptools.find_packages(),
    classifiers=(
        'Programming Language :: Python :: 3',
        'License :: WTFPL License',
        'Operating System :: OS Independent',
        'Framework :: Django :: 1.11',
        'Database :: PostgreSQL',
    ),
    install_requires=[
        'GitPython>=2.1.8',
        'django==1.11'
    ],
)
