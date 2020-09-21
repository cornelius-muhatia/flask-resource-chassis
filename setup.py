from setuptools import setup, find_packages

setup(name='flask_resource_chassis',
      version='1.0.0.dev2',
      description='Extends flask restful functionality',
      packages=find_packages(include=('flask_resource_chassis', 'flask_resource_chassis*')),
      zip_safe=True)
