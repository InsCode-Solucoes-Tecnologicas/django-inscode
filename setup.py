from setuptools import setup, find_packages
import sys

CURRENT_PYTHON = sys.version_info[:2]
REQUIRED_PYTHON = (3, 12)

if CURRENT_PYTHON < REQUIRED_PYTHON:
    sys.stderr.write(
        """
==============================
Versão do Python não suportada
==============================

Esta versão do Django Inscode requer o python Python {}.{}, mas você está tentando
instalar na versão {}.{}.

""".format(
            *(REQUIRED_PYTHON + CURRENT_PYTHON)
        )
    )
    sys.exit(1)

setup(
    name="django-inscode",
    version="0.1.6",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "Django>=5.1",
        "django-soft-delete>=1.0.16",
        "pytz>=2024.2",
    ],
    python_requires=">=3.12",
    classifiers=[
        "Framework :: Django",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
