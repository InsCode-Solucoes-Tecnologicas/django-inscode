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


def read(f):
    with open(f, "r", encoding="utf-8") as file:
        return file.read()


setup(
    name="django-inscode",
    version="1.5.1",
    description="Django framework da Inscode.",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "Django>=5.1",
        "django-soft-delete>=1.0.16",
        "pytz>=2024.2",
        "marshmallow>=3.26.0",
        "django-filter>=24.3",
        "mozilla-django-oidc>=4.0.1",
    ],
    python_requires=">=3.12",
    classifiers=[
        "Framework :: Django",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
