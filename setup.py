import os

from setuptools import setup, find_packages

PACKAGE_VERSION = os.environ.get("PACKAGE_VERSION", '1.0.1.rc7')

setup(name='flask_resource_chassis',
      version=PACKAGE_VERSION,
      description='Extends flask restful functionality',
      packages=['flask_resource_chassis', 'oauth_client', "utils"],
      zip_safe=False)
