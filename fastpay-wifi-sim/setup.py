"""Setup configuration for FastPay WiFi Simulation."""

from setuptools import find_packages, setup

setup(
    name="fastpay_wifi_sim",
    version="0.1.0",
    description="FastPay WiFi Simulation for Mininet-WiFi",
    author="FastPay Team",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "pytest>=7.0.0",
        "pytest-mock>=3.10.0",
    ],
    extras_require={
        "dev": [
            "pytest-cov>=4.0.0",
            "ruff>=0.1.0",
        ]
    }
) 